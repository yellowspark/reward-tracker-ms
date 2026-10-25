import json
import logging
import os
import threading
import time
from flask import Flask, jsonify, render_template, request

import checker
import notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("RewardsServer")

app = Flask(__name__)
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# Background thread control
monitoring_thread = None
stop_event = threading.Event()
is_checking = False


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def background_monitor_worker():
    """Background worker daemon that checks Microsoft Rewards restock on schedule."""
    global is_checking
    logger.info("Background monitoring worker started.")
    checker.log_event("Microsoft Rewards monitoring daemon started.")

    while not stop_event.is_set():
        cfg = load_config()
        if cfg.get("enabled", True):
            try:
                is_checking = True
                checker.log_event("Starting scheduled Microsoft Rewards check cycle...")
                checker.run_single_check()
            except Exception as e:
                checker.log_event(f"Unexpected error in monitor loop: {e}", level="error")
            finally:
                is_checking = False
        else:
            checker.log_event("Tracker is PAUSED (disabled). Waiting for activation...")

        # Sleep in small 1-second chunks so we can respond instantly to stop/check requests
        interval = cfg.get("check_interval_seconds", 90)
        for _ in range(int(interval)):
            if stop_event.is_set():
                break
            time.sleep(1)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    cfg = load_config()
    summary = checker.get_last_summary()
    logs = checker.get_logs()

    session_cfg = cfg.get("session", {})
    has_cookie = bool(session_cfg.get("cookie", "").strip())

    return jsonify({
        "enabled": cfg.get("enabled", True),
        "is_checking": is_checking,
        "check_interval_seconds": cfg.get("check_interval_seconds", 90),
        "user_points": cfg.get("user_points", 29000),
        "has_session_cookie": has_cookie,
        "targets": cfg.get("targets", []),
        "alerts_config": cfg.get("alerts", {}),
        "telegram_config": {
            "enabled": cfg.get("telegram", {}).get("enabled", False),
            "configured": bool(cfg.get("telegram", {}).get("bot_token") and cfg.get("telegram", {}).get("chat_id"))
        },
        "green_api_config": {
            "enabled": cfg.get("green_api", {}).get("enabled", False),
            "configured": bool(cfg.get("green_api", {}).get("id_instance") and cfg.get("green_api", {}).get("api_token_instance"))
        },
        "whatsapp_config": {
            "enabled": cfg.get("whatsapp", {}).get("enabled", False),
            "configured": bool(cfg.get("whatsapp", {}).get("phone") and cfg.get("whatsapp", {}).get("callmebot_api_key"))
        },
        "last_summary": summary,
        "logs": logs[:40]
    })


@app.route("/api/toggle", methods=["POST"])
def toggle_monitoring():
    cfg = load_config()
    current = cfg.get("enabled", True)
    cfg["enabled"] = not current
    save_config(cfg)
    msg = f"Monitoring {'RESUMED' if cfg['enabled'] else 'PAUSED'}."
    checker.log_event(msg)
    return jsonify({"success": True, "enabled": cfg["enabled"], "message": msg})


@app.route("/api/check_now", methods=["POST"])
def check_now():
    global is_checking
    if is_checking:
        return jsonify({"success": False, "message": "A check cycle is already in progress."})

    def _run():
        global is_checking
        try:
            is_checking = True
            checker.run_single_check()
        finally:
            is_checking = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"success": True, "message": "Manual check triggered."})


@app.route("/api/settings", methods=["POST"])
def update_settings():
    try:
        new_settings = request.json
        cfg = load_config()

        # Update root attributes
        if "check_interval_seconds" in new_settings:
            val = int(new_settings["check_interval_seconds"])
            cfg["check_interval_seconds"] = max(15, min(3600, val))

        if "user_points" in new_settings:
            cfg["user_points"] = int(new_settings["user_points"])

        # Update session
        if "session" in new_settings:
            cfg["session"] = cfg.get("session", {})
            if "cookie" in new_settings["session"]:
                raw_cookie = new_settings["session"]["cookie"].strip()
                if raw_cookie.lower().startswith("cookie:"):
                    raw_cookie = raw_cookie[7:].strip()
                cfg["session"]["cookie"] = raw_cookie
            if "user_agent" in new_settings["session"]:
                cfg["session"]["user_agent"] = new_settings["session"]["user_agent"].strip()

        # Update targets
        if "targets" in new_settings:
            cfg["targets"] = new_settings["targets"]

        # Update telegram
        if "telegram" in new_settings:
            cfg["telegram"] = new_settings["telegram"]

        # Update Green-API
        if "green_api" in new_settings:
            cfg["green_api"] = new_settings["green_api"]

        # Update CallMeBot WhatsApp
        if "whatsapp" in new_settings:
            cfg["whatsapp"] = new_settings["whatsapp"]

        # Update alert preferences
        if "alerts" in new_settings:
            cfg["alerts"] = new_settings["alerts"]

        save_config(cfg)
        checker.log_event("Settings updated successfully.")
        return jsonify({"success": True, "message": "Settings saved!"})
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/sync_session", methods=["POST"])
def sync_session_quick():
    """Allows one-click session cookie import from a browser bookmarklet."""
    data = request.json or {}
    cookie = data.get("cookie", "").strip()
    if not cookie:
        return jsonify({"success": False, "error": "No cookie provided."}), 400

    cfg = load_config()
    cfg["session"] = cfg.get("session", {})
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[7:].strip()
    cfg["session"]["cookie"] = cookie
    save_config(cfg)
    checker.log_event("✅ Microsoft Session Cookie successfully synced via 1-click import!")
    return jsonify({"success": True, "message": "Session cookie synced successfully!"})


@app.route("/api/test_alert", methods=["POST"])
def test_alert():
    data = request.json or {}
    channel = data.get("channel", "all")
    result = notifier.send_test_alert(channel)
    checker.log_event(f"Test alert triggered for channel: {channel}")
    return jsonify({"success": True, "results": result})


@app.route("/api/simulate_stock", methods=["POST"])
def simulate_stock():
    data = request.json or {}
    target_id = data.get("target_id", "flipkart")
    res = checker.simulate_stock_alert(target_id)
    return jsonify({"success": True, "message": "Simulated in-stock alert triggered!", "results": res})


def start_server():
    global monitoring_thread
    # Start background daemon
    monitoring_thread = threading.Thread(target=background_monitor_worker, daemon=True)
    monitoring_thread.start()

    port = 5001
    logger.info(f"Starting Microsoft Rewards Stock Tracker Dashboard on http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    start_server()
