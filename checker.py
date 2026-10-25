import datetime
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request

import notifier

logger = logging.getLogger("RewardsChecker")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
MAX_LOG_ENTRIES = 120

# In-memory storage for real-time logs and last check details
activity_logs = []
last_check_summary = {
    "timestamp": None,
    "status": "Idle",
    "points_found": None,
    "items_checked": 0,
    "in_stock_items": [],
    "restocking_items": [],
    "out_of_stock_items": []
}

# Cooldown tracker to prevent repeated alert spam for the same in-stock item
alert_history = {}


def log_event(message: str, level: str = "info"):
    """Appends an event to the in-memory rotating activity log."""
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    entry = {
        "time": now_str,
        "message": message,
        "level": level
    }
    activity_logs.insert(0, entry)
    if len(activity_logs) > MAX_LOG_ENTRIES:
        activity_logs.pop()

    if level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)


def get_logs():
    return activity_logs


def get_last_summary():
    return last_check_summary


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def extract_user_points(html_content: str) -> int:
    """Attempt to parse current user points balance from the rewards page HTML."""
    try:
        # Regex patterns commonly used on Microsoft Rewards HTML/JSON
        patterns = [
            r'"availablePoints"\s*:\s*(\d+)',
            r'"userPoints"\s*:\s*(\d+)',
            r'id="userPointsBalance"[^>]*>([\d,]+)<',
            r'class="[^"]*c-point-balance[^"]*"[^>]*>([\d,]+)<',
            r'data-bi-name="user-points"[^>]*>([\d,]+)<',
            r'>([\d,]+)\s*(?:points|available)\b',
        ]
        for p in patterns:
            match = re.search(p, html_content, re.IGNORECASE)
            if match:
                raw_val = match.group(1).replace(",", "")
                val = int(raw_val)
                if 100 <= val <= 200000:
                    return val
    except Exception as e:
        logger.debug(f"Point extraction notice: {e}")
    return 0


def analyze_card_stock(card_text: str, card_html: str) -> str:
    """
    Determines if a gift card tile/modal indicates restocking, out of stock, or available.
    """
    lower_text = card_text.lower()
    lower_html = card_html.lower()

    # Known Microsoft Rewards out-of-stock / restocking phrases
    restocking_keywords = [
        "so popular we're restocking",
        "so popular we are restocking",
        "restocking back soon",
        "restocking soon",
        "restocking",
        "temporarily out of stock",
        "out of stock",
        "currently unavailable",
        "not available",
        "sold out",
        "check back later"
    ]

    for kw in restocking_keywords:
        if kw in lower_text or kw in lower_html:
            return "RESTOCKING"

    # Check for disabled button attributes
    if "is-disabled" in lower_html or "disabled=" in lower_html or 'aria-disabled="true"' in lower_html:
        if "redeem" in lower_html:
            return "RESTOCKING"

    # If neither is found and redeem option exists, it's in stock!
    if "redeem" in lower_text or "points" in lower_text or "gift card" in lower_text:
        return "IN_STOCK"

    return "UNKNOWN"


def fetch_rewards_page(cookie: str, user_agent: str = "") -> dict:
    """
    Fetches https://rewards.bing.com/redeem/ using authenticated headers.
    """
    url = "https://rewards.bing.com/redeem/"
    headers = {
        "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Microsoft Edge";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    if cookie:
        # Clean cookie format if user pasted full header
        clean_cookie = cookie.strip()
        if clean_cookie.lower().startswith("cookie:"):
            clean_cookie = clean_cookie[7:].strip()
        headers["Cookie"] = clean_cookie

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            final_url = resp.geturl()
            status_code = resp.status
            body_bytes = resp.read()
            body_text = body_bytes.decode("utf-8", errors="ignore")

            # Detect login redirect
            if "login.live.com" in final_url or "Sign in to your Microsoft account" in body_text:
                return {
                    "success": False,
                    "session_valid": False,
                    "error": "Redirected to Microsoft Login. Cookie expired or invalid."
                }

            return {
                "success": True,
                "session_valid": True,
                "url": final_url,
                "status_code": status_code,
                "html": body_text
            }
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"success": False, "session_valid": False, "error": f"HTTP {e.code} Unauthorized - Invalid session cookie"}
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_target_brand(target: dict, full_html: str) -> dict:
    """
    Searches the rewards page HTML for a specific target brand's card and determines its status.
    """
    brand_name = target.get("name", "Unknown")
    keywords = target.get("keywords", [])
    target_id = target.get("id")

    # Look for cards or sections containing keywords
    found_in_catalog = False
    card_snippets = []

    # Regex to extract card blocks
    # Microsoft Rewards uses elements with classes like card, c-card, promo-card, or data-bi-name
    blocks = re.findall(r'(<(?:div|li|a)[^>]*(?:card|item|reward|tile)[^>]*>[\s\S]*?<\/(?:div|li|a)>)', full_html, re.IGNORECASE)
    
    # Fallback to general keyword chunks if specific card tags aren't cleanly regexed
    if not blocks:
        for kw in keywords:
            for m in re.finditer(re.escape(kw), full_html, re.IGNORECASE):
                start = max(0, m.start() - 300)
                end = min(len(full_html), m.end() + 600)
                blocks.append(full_html[start:end])

    matched_status = "NOT_IN_CATALOG"
    detail_url = "https://rewards.bing.com/redeem/"
    points_text = ""

    for block in blocks:
        block_lower = block.lower()
        if any(kw.lower() in block_lower for kw in keywords):
            found_in_catalog = True
            card_snippets.append(block)

            # Check for direct redemption SKU link
            url_match = re.search(r'href="([^"]*redeem/[^"]*)"', block, re.IGNORECASE)
            if url_match:
                extracted = url_match.group(1)
                if extracted.startswith("/"):
                    detail_url = "https://rewards.bing.com" + extracted
                elif extracted.startswith("http"):
                    detail_url = extracted

            # Extract points required if mentioned
            pts_match = re.search(r'([\d,]+)\s*(?:points|pts)', block, re.IGNORECASE)
            if pts_match:
                points_text = pts_match.group(0)

            # Check stock condition
            status = analyze_card_stock(block, block)
            if status == "IN_STOCK":
                matched_status = "IN_STOCK"
                break
            elif status == "RESTOCKING":
                matched_status = "RESTOCKING"

    if not found_in_catalog:
        # Check if keyword exists anywhere in page text
        for kw in keywords:
            if kw.lower() in full_html.lower():
                found_in_catalog = True
                matched_status = "RESTOCKING" if ("restocking" in full_html.lower() or "popular" in full_html.lower()) else "IN_STOCK"
                break

    return {
        "id": target_id,
        "name": brand_name,
        "found_in_catalog": found_in_catalog,
        "status": matched_status,
        "url": detail_url,
        "points": points_text
    }


def run_single_check() -> dict:
    """
    Executes a complete monitoring check across all enabled target gift cards.
    """
    global last_check_summary, alert_history
    cfg = load_config()

    if not cfg.get("enabled", True):
        log_event("Monitoring is PAUSED in settings. Skipping cycle.", level="warning")
        return {"status": "paused"}

    targets = cfg.get("targets", [])
    session_cfg = cfg.get("session", {})
    cookie = session_cfg.get("cookie", "").strip()
    user_points = cfg.get("user_points", 29000)

    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # If cookie is not configured, inform the user
    if not cookie:
        log_event("⚠️ Session Cookie is NOT configured! Tracking in standby mode. Please paste your cookie in Settings.", level="warning")
        last_check_summary = {
            "timestamp": now_time,
            "status": "Awaiting Session Cookie",
            "points_found": user_points,
            "items_checked": 0,
            "in_stock_items": [],
            "restocking_items": [],
            "out_of_stock_items": []
        }
        return {"status": "no_cookie"}

    log_event("Fetching Microsoft Rewards redeem catalog...")
    res = fetch_rewards_page(cookie, session_cfg.get("user_agent", ""))

    if not res.get("success"):
        error_msg = res.get("error", "Unknown network error")
        log_event(f"❌ Failed to reach rewards page: {error_msg}", level="error")
        last_check_summary["status"] = f"Error: {error_msg}"
        last_check_summary["timestamp"] = now_time
        return {"status": "fetch_failed", "error": error_msg}

    html = res.get("html", "")
    log_event("Successfully retrieved rewards page (HTTP 200). Analyzing catalog...")

    # Update points if found in page
    extracted_pts = extract_user_points(html)
    if extracted_pts > 0:
        if extracted_pts != user_points:
            log_event(f"🎯 Updated point balance: {extracted_pts:,} points (previous: {user_points:,})")
            cfg["user_points"] = extracted_pts
            user_points = extracted_pts
            save_config(cfg)
    
    in_stock_list = []
    restocking_list = []
    out_of_stock_list = []

    for target in targets:
        if not target.get("enabled", True):
            continue

        result = check_target_brand(target, html)
        status = result["status"]
        brand_name = result["name"]
        item_id = result["id"]

        target["last_status"] = status
        target["last_checked"] = now_time
        if result["url"]:
            target["url"] = result["url"]

        if status == "IN_STOCK":
            in_stock_list.append(result)
            log_event(f"🎉 [IN STOCK] {brand_name} is available for redemption!", level="info")

            # Check alert cooldown (cooldown: 20 minutes)
            last_alerted = alert_history.get(item_id, 0)
            now_ts = time.time()
            if (now_ts - last_alerted) > 1200:
                log_event(f"🚀 DISPATCHING RESTOCK ALERTS for {brand_name}...")
                notifier.alert_restock_found(
                    item_name=brand_name,
                    points_info=result.get("points", ""),
                    redeem_url=result.get("url", "https://rewards.bing.com/redeem/"),
                    user_points=user_points
                )
                alert_history[item_id] = now_ts
            else:
                log_event(f"ℹ️ Alert for {brand_name} recently sent. Skipping cooldown.")

        elif status == "RESTOCKING":
            restocking_list.append(result)
            log_event(f"⏳ [RESTOCKING] {brand_name} shows 'So popular we are restocking back soon'.")
        else:
            out_of_stock_list.append(result)
            log_event(f"⚪ [NOT IN CATALOG] {brand_name} is currently not listed.")

    save_config(cfg)

    last_check_summary = {
        "timestamp": now_time,
        "status": "Check Complete",
        "points_found": user_points,
        "items_checked": len(in_stock_list) + len(restocking_list) + len(out_of_stock_list),
        "in_stock_items": in_stock_list,
        "restocking_items": restocking_list,
        "out_of_stock_items": out_of_stock_list
    }

    log_event(f"Cycle completed. In Stock: {len(in_stock_list)} | Restocking: {len(restocking_list)} | Absent: {len(out_of_stock_list)}")
    return last_check_summary


def simulate_stock_alert(target_id: str = "flipkart") -> dict:
    """
    Triggers a mock in-stock alert to test sound, toast, Telegram, and WhatsApp end-to-end.
    """
    cfg = load_config()
    targets = {t.get("id"): t for t in cfg.get("targets", [])}
    target = targets.get(target_id) or {
        "name": "Flipkart Gift Card (₹1,000)",
        "url": "https://rewards.bing.com/redeem/"
    }

    log_event(f"🧪 [SIMULATION] Simulating IN-STOCK event for {target.get('name')}...")
    res = notifier.alert_restock_found(
        item_name=target.get("name"),
        points_info="~19,320 pts",
        redeem_url=target.get("url", "https://rewards.bing.com/redeem/"),
        user_points=cfg.get("user_points", 29000)
    )
    log_event(f"🧪 [SIMULATION] Alert dispatch completed: {res}")
    return res
