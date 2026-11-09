"""
24/7 Cloud Runner for Microsoft Rewards Gift Card Restock Tracker.
Can be executed via GitHub Actions cron, AWS Lambda, or any 24/7 cloud server.
Runs even when your local laptop is completely turned off or asleep.
"""

import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("RewardsCloudTracker")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_USER_POINTS = 31000  # Fallback point budget if cookie expires


def get_val(env_key: str, default: str = "") -> str:
    """Read configuration from environment variable first, then fallback to config.json."""
    val = os.environ.get(env_key)
    if val:
        return val.strip()

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                mapping = {
                    "MS_COOKIE": cfg.get("session", {}).get("cookie", ""),
                    "TELEGRAM_BOT_TOKEN": cfg.get("telegram", {}).get("bot_token", ""),
                    "TELEGRAM_CHAT_ID": cfg.get("telegram", {}).get("chat_id", ""),
                    "GREEN_API_INSTANCE_ID": cfg.get("green_api", {}).get("id_instance", ""),
                    "GREEN_API_TOKEN_INSTANCE": cfg.get("green_api", {}).get("api_token_instance", ""),
                    "GREEN_API_HOST": cfg.get("green_api", {}).get("host_url", ""),
                    "WHATSAPP_PHONE": cfg.get("green_api", {}).get("phone", "") or cfg.get("whatsapp", {}).get("phone", ""),
                    "CALLMEBOT_API_KEY": cfg.get("whatsapp", {}).get("callmebot_api_key", ""),
                    "USER_POINTS": str(cfg.get("user_points", DEFAULT_USER_POINTS)),
                }
                return mapping.get(env_key, default)
        except Exception:
            pass
    return default


def send_telegram(token: str, chat_id: str, message: str, direct_url: str = "") -> bool:
    """Robust Telegram sender that tries Markdown first, then auto-retries plain text if HTTP 400."""
    if not token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
    clean_chat_id = chat_id.strip()

    base_payload = {
        "chat_id": clean_chat_id,
        "text": message,
        "disable_web_page_preview": False
    }

    if direct_url and direct_url.startswith("http"):
        base_payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "⚡ REDEEM GIFT CARD NOW ⚡", "url": direct_url}]
            ]
        }

    # Attempt 1: With Markdown formatting
    try:
        md_payload = dict(base_payload)
        md_payload["parse_mode"] = "Markdown"
        data = json.dumps(md_payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Telegram notification sent successfully (Markdown mode)!")
            return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        logger.warning(f"Telegram Markdown error: {e.code} - {err_body}. Retrying in plain text...")

        # Attempt 2: Fallback without Markdown (prevents HTTP 400 parse errors)
        try:
            plain_payload = dict(base_payload)
            # Remove markdown syntax characters for plain text
            plain_text = message.replace("*", "").replace("_", "")
            plain_payload["text"] = plain_text
            data_plain = json.dumps(plain_payload).encode("utf-8")
            req_plain = urllib.request.Request(url, data=data_plain, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_plain, timeout=15) as resp2:
                logger.info("Telegram notification sent successfully (Plain text fallback)!")
                return True
        except urllib.error.HTTPError as e2:
            err_body2 = e2.read().decode("utf-8", errors="ignore")
            logger.error(f"Telegram Plain Text fallback failed: {e2.code} - {err_body2}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def send_green_api(instance_id: str, token: str, phone: str, message: str, host_url: str = "") -> bool:
    if not instance_id or not token or not phone:
        return False
    digits = "".join(filter(str.isdigit, phone.strip()))
    if not digits:
        return False

    chat_id = f"{digits}@c.us"
    if not host_url:
        prefix = instance_id[:4] if len(instance_id) >= 4 else ""
        host_url = f"https://{prefix}.api.greenapi.com" if prefix else "https://api.green-api.com"
    host_url = host_url.rstrip("/")

    url = f"{host_url}/waInstance{instance_id.strip()}/sendMessage/{token.strip()}"
    payload = json.dumps({"chatId": chat_id, "message": message}).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Green-API WhatsApp message sent successfully!")
            return True
    except Exception as e:
        logger.error(f"Failed to send Green-API message: {e}")
        return False


def send_callmebot(phone: str, api_key: str, message: str) -> bool:
    if not phone or not api_key:
        return False
    clean_phone = phone.strip().replace(" ", "").replace("-", "")
    if not clean_phone.startswith("+"):
        clean_phone = "+" + clean_phone
    encoded_text = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded_text}&apikey={api_key.strip()}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MSRewardsCloud/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("CallMeBot WhatsApp message sent successfully!")
            return True
    except Exception as e:
        logger.error(f"Failed to send CallMeBot message: {e}")
        return False


def fetch_url(url: str, cookie: str = "") -> tuple[str, bool]:
    """
    Smart fetch: tries with cookie first for live user balance.
    If the cookie is expired or redirects to login.live.com,
    it automatically falls back to public catalog mode (200 OK) without cookie.
    Never crashes or stops monitoring!
    Returns (html_content, is_authenticated)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"
    }

    clean_cookie = cookie.strip() if cookie else ""
    if clean_cookie.lower().startswith("cookie:"):
        clean_cookie = clean_cookie[7:].strip()

    # 1. Try with cookie if provided
    if clean_cookie:
        auth_headers = dict(headers)
        auth_headers["Cookie"] = clean_cookie
        req = urllib.request.Request(url, headers=auth_headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                final_url = resp.geturl()
                body = resp.read().decode("utf-8", errors="ignore")
                if "login.live.com" not in final_url and "Sign in to your Microsoft account" not in body:
                    return body, True
                else:
                    logger.warning("Session cookie redirected to login (expired). Auto-switching to public catalog check mode...")
        except Exception as e:
            logger.warning(f"Cookie fetch warning: {e}. Auto-switching to public catalog check mode...")

    # 2. Resilient Fallback: Fetch without cookie (public mode)
    req_pub = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req_pub, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return body, False


def extract_user_points(html: str, cookie: str) -> int:
    """Extracts live user points balance directly from Microsoft Rewards HTML or Cookie."""
    m = re.search(r'\"balance\":\s*(\d+)', html)
    if m:
        return int(m.group(1))

    m_cookie = re.search(r'\brb=(\d+)', cookie)
    if m_cookie:
        return int(m_cookie.group(1))

    try:
        cfg_pts = int(get_val("USER_POINTS", str(DEFAULT_USER_POINTS)))
        return cfg_pts
    except Exception:
        return DEFAULT_USER_POINTS


def extract_card_points_cost(card_html: str, sku_html: str = "") -> int:
    """Extracts the point cost required to redeem this specific card."""
    for src in [card_html, sku_html]:
        if not src:
            continue
        m = re.search(r'text-itemHeader\">([\d,]+)<', src)
        if m:
            return int(m.group(1).replace(",", ""))
        m_pts = re.search(r'\"price\":\s*(\d+)', src)
        if m_pts:
            return int(m_pts.group(1))
        m_general = re.search(r'([\d,]+)\s*(?:pts|points)', src, re.I)
        if m_general:
            val = int(m_general.group(1).replace(",", ""))
            if val >= 500:
                return val
    return 0


def check_flipkart_stock(cookie: str) -> tuple[str, str, int]:
    """Specifically checks the Flipkart SKU page to see if restocking banner has disappeared."""
    sku_url = "https://rewards.bing.com/redeem/sku/000885000034"
    cost = 19320  # Default ₹1,000 Flipkart cost
    try:
        content, _ = fetch_url(sku_url, cookie)
        lower_content = content.lower()
        extracted_cost = extract_card_points_cost("", content)
        if extracted_cost > 0:
            cost = extracted_cost

        restocking_phrases = [
            "so popular we're restocking",
            "so popular we are restocking",
            "so popular we&#x27;re restocking",
            "restocking back soon",
            "restocking soon",
            "temporarily out of stock"
        ]

        is_restocking = any(phrase in lower_content for phrase in restocking_phrases)
        is_disabled = '"isdisabled":true' in lower_content
        has_redeem = "redeem now" in lower_content or "redeem" in lower_content

        if is_restocking or is_disabled:
            return "RESTOCKING", sku_url, cost
        elif has_redeem and not is_restocking:
            return "IN_STOCK", sku_url, cost
        return "RESTOCKING", sku_url, cost
    except Exception as e:
        logger.error(f"Error checking Flipkart SKU page: {e}")
        return "ERROR", sku_url, cost


def check_specific_sku(name: str, sku_url: str, default_cost: int, cookie: str) -> tuple[str, str, int]:
    """Checks an exact SKU page (Amazon, Croma, etc.) for active in-stock state."""
    cost = default_cost
    try:
        content, _ = fetch_url(sku_url, cookie)
        lower_content = content.lower()
        extracted_cost = extract_card_points_cost("", content)
        if extracted_cost > 0:
            cost = extracted_cost

        if "recommended items" in lower_content[:600] or "notfound" in lower_content:
            return "OUT_OF_STOCK", sku_url, cost

        if any(p in lower_content for p in ["so popular", "restocking", "out of stock"]):
            return "RESTOCKING", sku_url, cost

        if "redeem now" in lower_content or ("redeem" in lower_content and '"isdisabled":false' in lower_content):
            return "IN_STOCK", sku_url, cost

        return "OUT_OF_STOCK", sku_url, cost
    except Exception as e:
        logger.error(f"Error checking {name} SKU ({sku_url}): {e}")
        return "ERROR", sku_url, cost


def scan_all_retail_cards(catalog_html: str, cookie: str) -> list[dict]:
    """
    Scans the entire Indian catalog for Flipkart, Amazon Pay, Croma,
    AND any other retail/shopping chains (Myntra, Swiggy, Zomato, Reliance, Tata, etc.)
    Returns list of dicts: {"name": ..., "url": ..., "cost": ...}
    """
    in_stock_found = []

    # 1. First, check Flipkart with direct SKU check
    fk_status, fk_url, fk_cost = check_flipkart_stock(cookie)
    logger.info(f"Target: Flipkart Gift Card -> Status: {fk_status} (Cost: {fk_cost:,} pts)")
    if fk_status == "IN_STOCK":
        in_stock_found.append({"name": "Flipkart Gift Card (₹1,000)", "url": fk_url, "cost": fk_cost})

    # 2. Check known VIP SKUs: Amazon Pay & Croma
    vip_skus = [
        ("Amazon Pay Gift Card (₹500)", "https://rewards.bing.com/redeem/sku/000885000025", 8150),
        ("Amazon Pay Gift Card (₹250)", "https://rewards.bing.com/redeem/sku/000885000000", 4000),
        ("Croma Gift Card (₹500)", "https://rewards.bing.com/redeem/sku/000885000017", 7475),
    ]

    for name, sku_url, default_cost in vip_skus:
        sku_id = sku_url.split("/")[-1]
        pattern = rf'href="(/redeem/sku/{sku_id}[^"]*)"'
        m = re.search(pattern, catalog_html)
        if m:
            raw_href = m.group(1)
            card_block_m = re.search(rf'<a[^>]*href="{re.escape(raw_href)}"[^>]*>.*?</a>', catalog_html, re.DOTALL)
            cost = default_cost
            if card_block_m:
                c_cost = extract_card_points_cost(card_block_m.group(0))
                if c_cost > 0:
                    cost = c_cost

            if "notfound" not in raw_href.lower():
                status, full_url, final_cost = check_specific_sku(name, sku_url, cost, cookie)
                logger.info(f"Target: {name} (Live check) -> Status: {status} (Cost: {final_cost:,} pts)")
                if status == "IN_STOCK":
                    in_stock_found.append({"name": name, "url": full_url, "cost": final_cost})
            else:
                logger.info(f"Target: {name} -> Status: OUT_OF_STOCK (Fallback active) (Cost: {cost:,} pts)")
        else:
            logger.info(f"Target: {name} -> Status: NOT_IN_CATALOG")

    # 3. Dynamic Discovery: Scan for ALL other retail/shopping gift cards
    retail_keywords = [
        "amazon", "croma", "myntra", "swiggy", "zomato", "bookmyshow",
        "lifestyle", "shoppers stop", "reliance", "uber", "ola",
        "bigbasket", "blinkit", "zepto", "dominos", "pizza hut",
        "pantaloons", "westside", "tatacliq", "tata cliq", "bata",
        "apollo", "nykaa", "ajio", "decathlon", "kfc", "starbucks"
    ]

    ignored_keywords = ["sweepstake", "overwatch", "spotify", "roblox", "league of legends", "donate", "charity", "entry", "entries"]

    card_blocks = re.findall(r'(<a[^>]*href=\"/redeem/sku/[^\"]+\"[^>]*>.*?</a>)', catalog_html, re.DOTALL)
    for block in card_blocks:
        name_m = re.search(r'alt=\"([^\"]+)\"', block)
        href_m = re.search(r'href=\"([^\"]+)\"', block)
        if not name_m or not href_m:
            continue

        title = name_m.group(1)
        href = href_m.group(1)
        title_lower = title.lower()

        if any(ik in title_lower for ik in ignored_keywords) or "flipkart" in title_lower:
            continue

        is_retail = any(rk in title_lower for rk in retail_keywords)
        if is_retail and "notfound" not in href.lower():
            full_sku_url = "https://rewards.bing.com" + href.split("?")[0]
            card_cost = extract_card_points_cost(block)
            status, direct_url, final_cost = check_specific_sku(title, full_sku_url, card_cost, cookie)
            logger.info(f"Target: {title} (Retail match) -> Status: {status} (Cost: {final_cost:,} pts)")
            if status == "IN_STOCK":
                if not any(item["url"] == direct_url for item in in_stock_found):
                    in_stock_found.append({"name": title, "url": direct_url, "cost": final_cost})

    return in_stock_found


def calculate_redemption_plans(available_items: list[dict], user_points: int) -> list[str]:
    """Generates intelligent combination suggestions based on available balance."""
    suggestions = []
    if not available_items or user_points <= 0:
        return suggestions

    for item in available_items:
        cost = item["cost"]
        if cost > 0:
            count = user_points // cost
            if count > 1:
                total = count * cost
                rem = user_points - total
                suggestions.append(f"• *{count}x {item['name']}* ({total:,} pts total, leaves {rem:,} pts)")

    if len(available_items) >= 2:
        for i in range(len(available_items)):
            for j in range(i + 1, len(available_items)):
                c1 = available_items[i]
                c2 = available_items[j]
                combo_cost = c1["cost"] + c2["cost"]
                if combo_cost <= user_points and combo_cost > 0:
                    rem = user_points - combo_cost
                    suggestions.append(f"• *1x {c1['name']}* + *1x {c2['name']}* ({combo_cost:,} pts total, leaves {rem:,} pts)")

    return suggestions[:4]


def auto_disable_github_workflow():
    """Disables this GitHub workflow once restock alert has fired to avoid duplicate alerts."""
    github_token = os.environ.get("GITHUB_TOKEN")
    github_repo = os.environ.get("GITHUB_REPOSITORY")
    workflow_name = "rewards_tracker.yml"

    if not github_token or not github_repo:
        return

    try:
        url = f"https://api.github.com/repos/{github_repo}/actions/workflows/{workflow_name}/disable"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "MSRewardsCloud/1.0"
            },
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("Successfully auto-paused GitHub Actions workflow following restock alert!")
    except Exception as e:
        logger.debug(f"Workflow auto-pause notice: {e}")


def main():
    logger.info("Starting 24/7 Cloud Restock Check for Microsoft Rewards (India)...")

    cookie = get_val("MS_COOKIE", "")
    tg_token = get_val("TELEGRAM_BOT_TOKEN")
    tg_chat = get_val("TELEGRAM_CHAT_ID")
    green_id = get_val("GREEN_API_INSTANCE_ID")
    green_token = get_val("GREEN_API_TOKEN_INSTANCE")
    green_host = get_val("GREEN_API_HOST")
    phone = get_val("WHATSAPP_PHONE")
    callme_key = get_val("CALLMEBOT_API_KEY")

    # Resilient Fetch: Tries authenticated mode, auto-falls back to public catalog
    try:
        catalog_html, is_authenticated = fetch_url("https://rewards.bing.com/redeem/in", cookie)
        mode_label = "Authenticated" if is_authenticated else "Public Fallback"
        logger.info(f"Catalog HTML retrieved successfully ({mode_label} mode). Scanning vouchers...")
    except Exception as e:
        logger.error(f"Failed to fetch Microsoft Rewards catalog: {e}")
        # Never crash GitHub Action with sys.exit(1) on transient connection hiccups
        return

    # 1. Read live points balance
    user_points = extract_user_points(catalog_html, cookie)
    logger.info(f"User Balance for Affordability: {user_points:,} reward points")

    # 2. Scan all target retail cards
    in_stock_items = scan_all_retail_cards(catalog_html, cookie)

    if not in_stock_items:
        logger.info(f"Checked all retail vouchers. None are currently in stock. User points: {user_points:,}. Check complete.")
        return

    # 3. Budget / Affordability Gate:
    affordable_items = []
    for item in in_stock_items:
        cost = item.get("cost", 0)
        if user_points >= cost or cost == 0:
            affordable_items.append(item)
        else:
            logger.info(f"Item in stock but UNAFFORDABLE: {item['name']} requires {cost:,} pts (User has: {user_points:,} pts). Skipping.")

    if not affordable_items:
        logger.info(f"Cards in stock, but none affordable with balance ({user_points:,} pts). Skipping notification.")
        return

    # 4. Generate notification message
    logger.info(f"🎉 AFFORDABLE RESTOCK DETECTED! Items: {[i['name'] for i in affordable_items]}")

    items_block = []
    for item in affordable_items:
        cost_str = f" ({item['cost']:,} pts)" if item.get("cost") else ""
        items_block.append(f"• *{item['name']}*{cost_str}\n  👉 {item['url']}")

    items_text = "\n".join(items_block)
    combo_suggestions = calculate_redemption_plans(affordable_items, user_points)
    combo_text = ""
    if combo_suggestions:
        combo_text = "\n\n💡 *What you can redeem with your balance:*\n" + "\n".join(combo_suggestions)

    repo = os.environ.get("GITHUB_REPOSITORY", "yellowspark/reward-tracker-ms")
    re_enable_url = f"https://github.com/{repo}/actions"

    msg = (
        f"🚨 *MICROSOFT REWARDS RESTOCK ALERT!* 🚨\n\n"
        f"💰 *Your Balance:* *{user_points:,} Points*\n"
        f"⚡ *In Stock & Redeemable by You:*\n\n"
        f"{items_text}"
        f"{combo_text}\n\n"
        f"⏰ _Stock is extremely limited. Claim immediately!_\n\n"
        f"🛑 _The tracker auto-paused so you aren't spammed with repeated alerts while redeeming. Re-enable anytime here:_\n"
        f"{re_enable_url}"
    )

    first_url = affordable_items[0]["url"]

    # Send Telegram
    if tg_token and tg_chat:
        send_telegram(tg_token, tg_chat, msg, direct_url=first_url)

    # Send WhatsApp (Green-API)
    sent_wa = False
    if green_id and green_token and phone:
        sent_wa = send_green_api(green_id, green_token, phone, msg, green_host)

    # Send WhatsApp (CallMeBot fallback)
    if not sent_wa and phone and callme_key:
        send_callmebot(phone, callme_key, msg)

    # Auto-pause GitHub workflow
    if os.environ.get("AUTO_PAUSE_ON_ALERT", "false").lower() == "true":
        auto_disable_github_workflow()


if __name__ == "__main__":
    main()
