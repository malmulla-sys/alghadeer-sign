"""
wa_webhook.py
=============
Webhook للرد التلقائي على رسائل واتساب.
"""

import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import URLError


# إعدادات Green API من متغيرات البيئة
GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID", "")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "")

# الرد التلقائي الثابت
AUTO_REPLY_MESSAGE = """مرحباً بك 👋

شكراً لتواصلك معنا.
سيتم الرد عليك في أقرب وقت ممكن.

— شركة الغدير"""

# أرقام لا نرد عليها تلقائياً
EXCLUDED_NUMBERS = [
    "966530364878",
    "966560454000",
]

# لتجنب الرد المتكرر
_replied_cache = set()


def normalize_phone(phone: str) -> str:
    """تنسيق رقم الهاتف."""
    phone = str(phone).replace("@c.us", "").replace("+", "").replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "966" + phone[1:]
    return phone


def send_reply(phone: str, message: str) -> bool:
    """إرسال رد عبر Green API."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN:
        print("⚠️ Green API credentials not configured")
        return False

    url = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    chat_id = f"{normalize_phone(phone)}@c.us"

    data = json.dumps({
        "chatId": chat_id,
        "message": message,
    }).encode("utf-8")

    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"⚠️ Error sending reply: {e}")
        return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """للتحقق من أن الـ webhook يعمل."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        status = {
            "status": "ok",
            "message": "WhatsApp Webhook is active",
            "green_api_configured": bool(GREEN_API_INSTANCE_ID and GREEN_API_TOKEN),
        }
        self.wfile.write(json.dumps(status).encode())

    def do_POST(self):
        """استقبال إشعارات Green API."""
        global _replied_cache

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            type_webhook = data.get("typeWebhook", "")

            if type_webhook == "incomingMessageReceived":
                sender_data = data.get("senderData", {})
                sender = sender_data.get("sender", "")
                sender_phone = normalize_phone(sender)

                print(f"📩 رسالة من {sender_phone}")

                if sender_phone in EXCLUDED_NUMBERS:
                    print(f"⏭️ رقم مستثنى")
                elif sender_phone not in _replied_cache:
                    success = send_reply(sender_phone, AUTO_REPLY_MESSAGE)
                    if success:
                        print(f"✅ تم الرد على {sender_phone}")
                        _replied_cache.add(sender_phone)
                        if len(_replied_cache) > 100:
                            _replied_cache = set(list(_replied_cache)[-50:])
                    else:
                        print(f"❌ فشل الرد")
                else:
                    print(f"⏭️ سبق الرد")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())

        except Exception as e:
            print(f"❌ Webhook error: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
