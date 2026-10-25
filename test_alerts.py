"""
Standalone Test Script for Microsoft Rewards Tracker Notifications (WhatsApp & Telegram).
Run:
    python test_alerts.py --channel telegram
    python test_alerts.py --channel whatsapp
    python test_alerts.py --channel all
    python test_alerts.py --simulate
"""

import argparse
import sys
import checker
import notifier


def main():
    parser = argparse.ArgumentParser(description="Test Microsoft Rewards Tracker Alerts (WhatsApp & Telegram)")
    parser.add_argument("--channel", choices=["telegram", "whatsapp", "all"], default="all")
    parser.add_argument("--simulate", action="store_true", help="Simulate a real restock event for Flipkart")
    args = parser.parse_args()

    print("==================================================")
    print("  Microsoft Rewards Tracker — Alert Diagnostics  ")
    print("==================================================")

    if args.simulate:
        print("\n[+] Triggering simulated IN-STOCK event for Flipkart (WhatsApp & Telegram)...")
        res = checker.simulate_stock_alert("flipkart")
        print(f"[+] Result: {res}")
        return

    print(f"\n[+] Testing alert channel: {args.channel}...")
    res = notifier.send_test_alert(args.channel)
    print(f"[+] Result: {res}")


if __name__ == "__main__":
    main()
