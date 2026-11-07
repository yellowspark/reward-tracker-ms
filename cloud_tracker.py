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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("RewardsCloudTracker")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


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
                }
                return mapping.get(env_key, default)
        except Exception:
            pass
    return default


def send_telegram(token: str, chat_id: str, message: str, direct_url: str = "") -> bool:
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
    payload = {
        "chat_id": chat_id.strip(),
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    if direct_url and direct_url.startswith("http"):
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "⚡ REDEEM GIFT CARD NOW ⚡", "url": direct_url}]
            ]
        }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Telegram notification sent successfully!")
            return True
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


def get_headers(cookie: str) -> dict:
    clean_cookie = cookie.strip()
    if clean_cookie.lower().startswith("cookie:"):
        clean_cookie = clean_cookie[7:].strip()
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
        "Cookie": clean_cookie
    }


def fetch_url(url: str, cookie: str) -> str:
    headers = get_headers(cookie)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        final_url = resp.geturl()
        body = resp.read().decode("utf-8", errors="ignore")
        if "login.live.com" in final_url or "Sign in to your Microsoft account" in body:
            raise ValueError("Microsoft session cookie expired or invalid. Please update cookie.")
        return body


def check_flipkart_stock(cookie: str) -> tuple[str, str]:
    """Specifically checks the Flipkart SKU page to see if restocking banner has disappeared."""
    sku_url = "https://rewards.bing.com/redeem/sku/000885000034"
    try:
        content = fetch_url(sku_url, cookie)
        lower_content = content.lower()
        
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
            return "RESTOCKING", sku_url
        elif has_redeem and not is_restocking:
            return "IN_STOCK", sku_url
        return "RESTOCKING", sku_url
    except Exception as e:
        logger.error(f"Error checking Flipkart SKU page: {e}")
        return "ERROR", sku_url


def check_specific_sku(name: str, sku_url: str, cookie: str) -> tuple[str, str]:
    """Checks an exact SKU page (Amazon, Croma, etc.) for active in-stock state."""
    try:
        content = fetch_url(sku_url, cookie)
        lower_content = content.lower()

        # If page redirected or fallback triggered to "recommended items"
        if "recommended items" in lower_content[:600] or "notfound" in lower_content:
            return "OUT_OF_STOCK", sku_url

        if any(p in lower_content for p in ["so popular", "restocking", "out of stock"]):
            return "RESTOCKING", sku_url

        if "redeem now" in lower_content or ("redeem" in lower_content and '"isdisabled":false' in lower_content):
            return "IN_STOCK", sku_url

        return "OUT_OF_STOCK", sku_url
    except Exception as e:
        logger.error(f"Error checking {name} SKU ({sku_url}): {e}")
        return "ERROR", sku_url


def scan_all_retail_cards(catalog_html: str, cookie: str) -> list[tuple[str, str]]:
    """
    Scans the entire Indian catalog for Flipkart, Amazon Pay, Croma,
    AND any other retail/shopping chains (Myntra, Swiggy, Zomato, Reliance, Tata, etc.)
    """
    in_stock_found = []

    # 1. First, check Flipkart with direct SKU check
    fk_status, fk_url = check_flipkart_stock(cookie)
    logger.info(f"Target: Flipkart Gift Card -> Status: {fk_status}")
    if fk_status == "IN_STOCK":
        in_stock_found.append(("Flipkart Gift Card", fk_url))

    # 2. Check known VIP SKUs: Amazon Pay & Croma
    vip_skus = [
        ("Amazon Pay Gift Card (SKU 25)", "https://rewards.bing.com/redeem/sku/000885000025"),
        ("Amazon Pay Gift Card (SKU 00)", "https://rewards.bing.com/redeem/sku/000885000000"),
        ("Croma Gift Card (₹500)", "https://rewards.bing.com/redeem/sku/000885000017"),
    ]

    for name, sku_url in vip_skus:
        # Check if fallback parameter is removed from catalog HTML for this SKU
        sku_id = sku_url.split("/")[-1]
        pattern = rf'href="(/redeem/sku/{sku_id}[^"]*)"'
        m = re.search(pattern, catalog_html)
        if m:
            raw_href = m.group(1)
            # If "notfound" fallback is gone, check SKU live!
            if "notfound" not in raw_href.lower():
                status, full_url = check_specific_sku(name, sku_url, cookie)
                logger.info(f"Target: {name} (Live check) -> Status: {status}")
                if status == "IN_STOCK":
                    in_stock_found.append((name, full_url))
            else:
                logger.info(f"Target: {name} -> Status: OUT_OF_STOCK (Fallback active)")
        else:
            logger.info(f"Target: {name} -> Status: NOT_IN_CATALOG")

    # 3. Dynamic Discovery: Scan for ALL other retail/shopping gift cards
    # Keywords covering popular retail chains in India
    retail_keywords = [
        "amazon", "croma", "myntra", "swiggy", "zomato", "bookmyshow",
        "lifestyle", "shoppers stop", "reliance", "uber", "ola",
        "bigbasket", "blinkit", "zepto", "dominos", "pizza hut",
        "pantaloons", "westside", "tatacliq", "tata cliq", "bata",
        "apollo", "nykaa", "ajio", "decathlon", "kfc", "starbucks"
    ]

    # Non-shopping items to ignore (sweepstakes, games, charity)
    ignored_keywords = ["sweepstake", "overwatch", "spotify", "roblox", "league of legends", "donate", "charity", "entry", "entries"]

    # Extract all cards currently listed in catalog
    all_cards = re.findall(r'href="(/redeem/sku/[^"]+)"[^>]*>.*?alt="([^"]+)"', catalog_html, re.DOTALL)
    for href, title in all_cards:
        title_lower = title.lower()

        # Skip ignored non-shopping items or flipkart (already handled)
        if any(ik in title_lower for ik in ignored_keywords) or "flipkart" in title_lower:
            continue

        # Check if it matches any shopping / retail chain
        is_retail = any(rk in title_lower for rk in retail_keywords)
        if is_retail:
            if "notfound" not in href.lower():
                full_sku_url = "https://rewards.bing.com" + href.split("?")[0]
                status, direct_url = check_specific_sku(title, full_sku_url, cookie)
                logger.info(f"Target: {title} (Retail match) -> Status: {status}")
                if status == "IN_STOCK" and (title, direct_url) not in in_stock_found:
                    in_stock_found.append((title, direct_url))

    return in_stock_found


def auto_disable_github_workflow():
    """Optionally disables this GitHub workflow once restock alert has fired to avoid duplicate alerts."""
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
            logger.info("Successfully paused GitHub Actions workflow following restock alert!")
    except Exception as e:
        logger.debug(f"Workflow auto-pause notice: {e}")


def main():
    logger.info("Starting 24/7 Cloud Restock Check for Microsoft Rewards (India)...")

    cookie = get_val("MS_COOKIE")
    if not cookie:
        logger.error("MS_COOKIE is not provided. Set MS_COOKIE secret or environment variable.")
        sys.exit(1)

    tg_token = get_val("TELEGRAM_BOT_TOKEN")
    tg_chat = get_val("TELEGRAM_CHAT_ID")
    green_id = get_val("GREEN_API_INSTANCE_ID")
    green_token = get_val("GREEN_API_TOKEN_INSTANCE")
    green_host = get_val("GREEN_API_HOST")
    phone = get_val("WHATSAPP_PHONE")
    callme_key = get_val("CALLMEBOT_API_KEY")

    try:
        catalog_html = fetch_url("https://rewards.bing.com/redeem/in", cookie)
        logger.info("Catalog HTML retrieved successfully. Scanning target vouchers...")
    except Exception as e:
        logger.error(f"Error fetching Microsoft Rewards page: {e}")
        if "session cookie expired" in str(e).lower() and tg_token and tg_chat:
            send_telegram(tg_token, tg_chat, "⚠️ *Microsoft Rewards Cloud Tracker*\n\nYour session cookie has expired. Please update it in GitHub Secrets.")
        sys.exit(1)

    in_stock_vouchers = scan_all_retail_cards(catalog_html, cookie)

    if in_stock_vouchers:
        names_str = ", ".join([v[0] for v in in_stock_vouchers])
        first_url = in_stock_vouchers[0][1]
        logger.info(f"🎉 RESTOCK DETECTED! Vouchers in stock: {names_str}")

        msg = (
            f"🚨 *MICROSOFT REWARDS RESTOCK ALERT!* 🚨\n\n"
            f"🎁 *Available Now:* {names_str}\n"
            f"⚡ *Status:* **IN STOCK / READY TO REDEEM!**\n\n"
            f"👉 *CLAIM NOW BEFORE IT SELLS OUT:*\n"
            f"{first_url}\n\n"
            f"⏰ _Stock is extremely limited. Claim immediately!_"
        )

        # 1. Telegram
        if tg_token and tg_chat:
            send_telegram(tg_token, tg_chat, msg, direct_url=first_url)

        # 2. Green-API WhatsApp
        sent_wa = False
        if green_id and green_token and phone:
            sent_wa = send_green_api(green_id, green_token, phone, msg, green_host)

        # 3. CallMeBot WhatsApp (Fallback)
        if not sent_wa and phone and callme_key:
            send_callmebot(phone, callme_key, msg)

        # Auto-pause GitHub workflow to prevent spamming
        if os.environ.get("AUTO_PAUSE_ON_ALERT", "false").lower() == "true":
            auto_disable_github_workflow()

    else:
        logger.info("Checked all retail vouchers. None are currently in stock. Check complete.")


if __name__ == "__main__":
    main()
