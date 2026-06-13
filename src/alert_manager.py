"""
alert_manager.py
----------------
Module 4: the completion ping. After the digest email is dispatched, fire a
short WhatsApp message via CallMeBot (FREE, no business account, no Twilio).

Setup (one time, ~2 min):
  1) Add +34 644 51 95 23 to your contacts as "CallMeBot".
  2) WhatsApp it:  "I allow callmebot to send me messages"
  3) It replies with your personal API key.
  4) Put WHATSAPP_PHONE and CALLMEBOT_APIKEY in your .env / GitHub Secrets.

If either secret is missing, this no-ops silently (the email still went out).
"""

import os
import urllib.parse
import requests


def send_whatsapp(message):
    phone = os.getenv("WHATSAPP_PHONE", "").strip()
    apikey = os.getenv("CALLMEBOT_APIKEY", "").strip()

    if not phone or not apikey:
        print("  [whatsapp] No WHATSAPP_PHONE / CALLMEBOT_APIKEY — skipping ping.")
        return False

    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={urllib.parse.quote(phone)}"
        f"&text={urllib.parse.quote(message)}"
        f"&apikey={urllib.parse.quote(apikey)}"
    )
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200:
            print("  [whatsapp] Completion ping sent.")
            return True
        print(f"  [whatsapp] CallMeBot returned {resp.status_code}: {resp.text[:120]}")
        return False
    except requests.RequestException as e:
        print(f"  [whatsapp] Failed: {e}")
        return False
