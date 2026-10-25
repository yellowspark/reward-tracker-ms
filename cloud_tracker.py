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


def fetch_catalog(cookie: str) -> str:
    url = "https://rewards.bing.com/redeem/"
    clean_cookie = cookie.strip()
    if clean_cookie.lower().startswith("cookie:"):
        clean_cookie = clean_cookie[7:].strip()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
        "Cookie": clean_cookie
    }

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        final_url = resp.geturl()
        body = resp.read().decode("utf-8", errors="ignore")
        if "login.live.com" in final_url or "Sign in to your Microsoft account" in body:
            raise ValueError("Microsoft session cookie expired or invalid. Please update cookie.")
        return body


def check_stock_status(html: str, target_name: str, keywords: list) -> str:
    lower_html = html.lower()

    # Check if brand is present
    found = any(kw.lower() in lower_html for kw in keywords)
    if not found:
        return "NOT_IN_CATALOG"

    # Restocking indicators
    restocking_phrases = [
        "so popular we're restocking",
        "so popular we are restocking",
        "restocking back soon",
        "restocking soon",
        "restocking",
        "out of stock",
        "temporarily out of stock",
        "currently unavailable",
        "not available"
    ]

    # Find context blocks
    for kw in keywords:
        for m in re.finditer(re.escape(kw.lower()), lower_html):
            chunk = lower_html[max(0, m.start() - 250):min(len(lower_html), m.end() + 500)]
            if any(phrase in chunk for phrase in restocking_phrases):
                return "RESTOCKING"

    return "IN_STOCK"


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
    logger.info("Starting 24/7 Cloud Restock Check for Microsoft Rewards...")

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
        html = fetch_catalog(cookie)
        logger.info("Catalog HTML retrieved successfully. Scanning target vouchers...")
    except Exception as e:
        logger.error(f"Error fetching Microsoft Rewards page: {e}")
        # Notify user on telegram if session cookie expired
        if "session cookie expired" in str(e).lower() and tg_token and tg_chat:
            send_telegram(tg_token, tg_chat, "⚠️ *Microsoft Rewards Cloud Tracker*\n\nYour session cookie has expired. Please update it in GitHub Secrets.")
        sys.exit(1)

    targets = [
        {"name": "Flipkart Gift Card", "keywords": ["flipkart"]},
        {"name": "Amazon Pay Gift Card", "keywords": ["amazon", "amazon pay"]},
        {"name": "Croma Gift Card", "keywords": ["croma"]},
        {"name": "Shopping Vouchers", "keywords": ["myntra", "swiggy", "zomato", "bookmyshow", "lifestyle"]}
    ]

    in_stock_vouchers = []

    for t in targets:
        name = t["name"]
        keywords = t["keywords"]
        status = check_stock_status(html, name, keywords)
        logger.info(f"Target: {name} -> Status: {status}")

        if status == "IN_STOCK":
            in_stock_vouchers.append(name)

    if in_stock_vouchers:
        vouchers_str = ", ".join(in_stock_vouchers)
        logger.info(f"🎉 RESTOCK DETECTED! Vouchers in stock: {vouchers_str}")

        msg = (
            f"🚨 *MICROSOFT REWARDS RESTOCK ALERT!* 🚨\n\n"
            f"🎁 *Available Now:* {vouchers_str}\n"
            f"💰 *Your Points:* ~29,000 pts ready to redeem!\n"
            f"⚡ *Status:* **IN STOCK / READY TO REDEEM!**\n\n"
            f"👉 *CLAIM NOW BEFORE IT SELLS OUT:*\n"
            f"https://rewards.bing.com/redeem/\n\n"
            f"⏰ _Stock for popular vouchers is extremely limited. Claim immediately!_"
        )

        # 1. Telegram
        if tg_token and tg_chat:
            send_telegram(tg_token, tg_chat, msg, direct_url="https://rewards.bing.com/redeem/")

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
        logger.info("Checked all target vouchers. None are currently in stock. Check complete.")


if __name__ == "__main__":
    main()
