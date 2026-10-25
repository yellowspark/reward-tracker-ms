import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger("RewardsNotifier")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def send_telegram_message(bot_token: str, chat_id: str, message: str, direct_url: str = "") -> dict:
    """Send a Telegram notification with direct 1-click redeem button."""
    if not bot_token or not chat_id:
        return {"success": False, "error": "Telegram Bot Token or Chat ID missing."}

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
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
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "MSRewardsTracker/1.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            logger.info(f"Telegram response: {resp.status} - {body[:100]}")
            return {"success": True, "response": json.loads(body) if body.startswith("{") else body}
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return {"success": False, "error": str(e)}


def send_green_api_message(id_instance: str, api_token_instance: str, phone: str, message: str, host_url: str = "") -> dict:
    """Send a WhatsApp message via Green-API."""
    if not id_instance or not api_token_instance or not phone:
        return {"success": False, "error": "Green-API ID Instance, API Token, or phone number missing."}

    digits = "".join(filter(str.isdigit, phone.strip()))
    if not digits:
        return {"success": False, "error": "Invalid phone number format."}
    chat_id = f"{digits}@c.us"

    if not host_url:
        prefix = id_instance[:4] if len(id_instance) >= 4 else ""
        host_url = f"https://{prefix}.api.greenapi.com" if prefix else "https://api.green-api.com"
    host_url = host_url.rstrip("/")

    url = f"{host_url}/waInstance{id_instance.strip()}/sendMessage/{api_token_instance.strip()}"
    payload = json.dumps({"chatId": chat_id, "message": message}).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "MSRewardsTracker/1.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            logger.info(f"Green-API WhatsApp response: {resp.status} - {body[:100]}")
            return {"success": True, "response": json.loads(body) if body.startswith("{") else body}
    except Exception as e:
        logger.error(f"Error sending Green-API message: {e}")
        return {"success": False, "error": str(e)}


def send_callmebot_message(phone: str, api_key: str, message: str) -> dict:
    """Send a WhatsApp message via CallMeBot API."""
    if not phone or not api_key:
        return {"success": False, "error": "Phone number or CallMeBot API Key missing."}

    clean_phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not clean_phone.startswith("+"):
        clean_phone = "+" + clean_phone

    encoded_text = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded_text}&apikey={api_key.strip()}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MSRewardsTracker/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            logger.info(f"CallMeBot response: {resp.status} - {body[:100]}")
            return {"success": True, "response": body}
    except Exception as e:
        logger.error(f"Error sending CallMeBot message: {e}")
        return {"success": False, "error": str(e)}


def trigger_phone_call_alert(phone: str, api_key: str, message: str) -> dict:
    """Trigger voice call via CallMeBot."""
    clean_phone = phone.strip().replace(" ", "").replace("-", "")
    if not clean_phone.startswith("+"):
        clean_phone = "+" + clean_phone

    encoded_text = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/start.php?user={clean_phone}&text={encoded_text}&lang=en-IN-Standard-A"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MSRewardsTracker/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            logger.info(f"Voice Call response: {resp.status} - {body[:100]}")
            return {"success": True, "response": body}
    except Exception as e:
        logger.debug(f"Voice call attempt notice: {e}")
        return {"success": False, "error": str(e)}


def alert_restock_found(item_name: str, points_info: str = "", redeem_url: str = "https://rewards.bing.com/redeem/", user_points: int = 29000):
    """
    Dispatches alerts strictly to WhatsApp and Telegram when a gift card is back in stock.
    """
    cfg = load_config()
    alerts_cfg = cfg.get("alerts", {})
    tg_cfg = cfg.get("telegram", {})
    green_cfg = cfg.get("green_api", {})
    whatsapp_cfg = cfg.get("whatsapp", {})

    pts_str = f"\n💰 *Points:* {points_info}" if points_info else ""
    balance_str = f" (Your Balance: ~{user_points:,} pts)" if user_points else ""

    msg = (
        f"🚨 *MICROSOFT REWARDS RESTOCK ALERT!* 🚨\n\n"
        f"🎁 *Item:* {item_name}{pts_str}{balance_str}\n"
        f"⚡ *Status:* **IN STOCK / READY TO REDEEM!**\n\n"
        f"👉 *CLAIM NOW BEFORE IT SELLS OUT:*\n"
        f"{redeem_url}\n\n"
        f"⏰ _Stock is extremely limited. Claim immediately!_"
    )

    results = {}

    # 1. Telegram Alert
    if alerts_cfg.get("telegram_message", True) and tg_cfg.get("enabled", True):
        tg_token = tg_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        tg_chat = tg_cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID", "")
        if tg_token and tg_chat:
            results["telegram"] = send_telegram_message(tg_token, tg_chat, msg, direct_url=redeem_url)

    # 2. Green-API WhatsApp Alert
    if alerts_cfg.get("whatsapp_message", True) and green_cfg.get("enabled", False):
        g_id = green_cfg.get("id_instance") or os.environ.get("GREEN_API_INSTANCE_ID", "")
        g_token = green_cfg.get("api_token_instance") or os.environ.get("GREEN_API_TOKEN_INSTANCE", "")
        g_phone = green_cfg.get("phone") or whatsapp_cfg.get("phone") or os.environ.get("WHATSAPP_PHONE", "")
        g_host = green_cfg.get("host_url") or os.environ.get("GREEN_API_HOST", "")
        if g_id and g_token and g_phone:
            results["green_api"] = send_green_api_message(g_id, g_token, g_phone, msg, g_host)

    # 3. CallMeBot WhatsApp Alert (Fallback)
    phone = whatsapp_cfg.get("phone", "")
    callme_key = whatsapp_cfg.get("callmebot_api_key", "")
    if alerts_cfg.get("whatsapp_message", True) and whatsapp_cfg.get("enabled", False) and phone and callme_key:
        if "green_api" not in results or not results["green_api"].get("success"):
            results["whatsapp"] = send_callmebot_message(phone, callme_key, msg)

    # 4. Voice Call / Ring Alert (if enabled)
    if alerts_cfg.get("whatsapp_call", False) and phone and callme_key:
        call_msg = f"Alert! Microsoft Rewards {item_name} is in stock now! Redeem fast!"
        results["call"] = trigger_phone_call_alert(phone, callme_key, call_msg)

    # Auto-disable if configured
    if alerts_cfg.get("auto_disable_after_alert", False):
        cfg["enabled"] = False
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        logger.info("Auto-disabled tracker following restock alert.")

    return results


def send_test_alert(channel: str = "all") -> dict:
    """Send test alerts to verify WhatsApp and Telegram notifications."""
    cfg = load_config()
    test_msg = (
        "✅ *Microsoft Rewards Tracker — Test Alert*\n\n"
        "Your notifications are successfully configured and active!\n"
        "You will receive an instant notification with a direct redeem link the moment Flipkart, Amazon, Croma, or other gift cards are back in stock."
    )

    results = {}

    if channel in ("all", "telegram"):
        tg_cfg = cfg.get("telegram", {})
        token = tg_cfg.get("bot_token")
        chat_id = tg_cfg.get("chat_id")
        if token and chat_id:
            results["telegram"] = send_telegram_message(token, chat_id, test_msg, "https://rewards.bing.com/redeem/")
        else:
            results["telegram"] = {"success": False, "error": "Telegram Bot Token or Chat ID not configured in Settings."}

    if channel in ("all", "whatsapp", "green_api"):
        green_cfg = cfg.get("green_api", {})
        wa_cfg = cfg.get("whatsapp", {})
        g_id = green_cfg.get("id_instance")
        g_token = green_cfg.get("api_token_instance")
        g_phone = green_cfg.get("phone") or wa_cfg.get("phone")
        g_host = green_cfg.get("host_url")

        if green_cfg.get("enabled", False) and g_id and g_token and g_phone:
            results["green_api"] = send_green_api_message(g_id, g_token, g_phone, test_msg, g_host)
        elif wa_cfg.get("enabled", False) and wa_cfg.get("phone") and wa_cfg.get("callmebot_api_key"):
            results["whatsapp"] = send_callmebot_message(wa_cfg.get("phone"), wa_cfg.get("callmebot_api_key"), test_msg)
        else:
            results["whatsapp"] = {"success": False, "error": "Neither Green-API nor CallMeBot is enabled/configured."}

    return results
