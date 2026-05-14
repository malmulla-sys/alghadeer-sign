"""
wa_webhook.py
=============
Webhook للرد التلقائي على رسائل واتساب.
"""

import os
import json
import httpx
from http.server import BaseHTTPRequestHandler


# إعدادات Green API من متغيرات البيئة
GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID", "")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "")

# الرد التلقائي الثابت
AUTO_REPLY_MESSAGE = """مرحباً بك 👋

شكراً لتواصلك معنا.
سيتم الرد عليك في أقرب وقت ممكن.

— شركة الغدير"""

# أرقام لا نرد عليها تلقائياً (مثل أرقامنا)
EXCLUDED_NUMBERS = [
    "966530364878",  # رقم الزميل
    "966560454000",  # رقم آخر
]

# لتجنب الرد المتكرر على نفس الشخص
_replied_cache = set()


def normalize_phone(phone: str) -> str:
    """تنسيق رقم الهاتف."""
    phone = phone.replace("@c.us", "").replace("+", "").replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "966" + phone[1:]
    return phone


async def send_reply(phone: str, message: str) -> bool:
    """إرسال رد عبر Green API."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN:
        print("⚠️ Green API credentials not configured")
        return False

    url = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"

    chat_id = f"{normalize_phone(phone)}@c.us"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={
                "chatId": chat_id,
                "message": message,
            })
            return resp.status_code == 200
    except Exception as e:
        print(f"⚠️ Error sending reply: {e}")
        return False


def send_reply_sync(phone: str, message: str) -> bool:
    """إرسال رد (متزامن) عبر Green API."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN:
        print("⚠️ Green API credentials not configured")
        return False

    url = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"

    chat_id = f"{normalize_phone(phone)}@c.us"

    try:
        resp = httpx.post(url, json={
            "chatId": chat_id,
            "message": message,
        }, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"⚠️ Error sending reply: {e}")
        return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """للتحقق من أن الـ webhook يعمل."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "message": "WhatsApp Webhook is active"
        }).encode())

    def do_POST(self):
        """استقبال إشعارات Green API."""
        global _replied_cache

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            # نوع الإشعار
            type_webhook = data.get("typeWebhook", "")

            # معالجة الرسائل الواردة فقط
            if type_webhook == "incomingMessageReceived":
                sender_data = data.get("senderData", {})
                message_data = data.get("messageData", {})

                sender = sender_data.get("sender", "")
                sender_phone = normalize_phone(sender)
                msg_type = message_data.get("typeMessage", "")

                print(f"📩 رسالة من {sender_phone} | النوع: {msg_type}")

                # تجاهل الأرقام المستثناة
                if sender_phone in EXCLUDED_NUMBERS:
                    print(f"⏭️ رقم مستثنى: {sender_phone}")
                else:
                    # تجنب الرد المتكرر (cache لآخر 100 رقم)
                    if sender_phone not in _replied_cache:
                        # إرسال الرد التلقائي
                        success = send_reply_sync(sender_phone, AUTO_REPLY_MESSAGE)
                        if success:
                            print(f"✅ تم الرد على {sender_phone}")
                            _replied_cache.add(sender_phone)
                            # حد الـ cache
                            if len(_replied_cache) > 100:
                                _replied_cache = set(list(_replied_cache)[-50:])
                        else:
                            print(f"❌ فشل الرد على {sender_phone}")
                    else:
                        print(f"⏭️ سبق الرد على {sender_phone}")

            # رد بنجاح
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())

        except Exception as e:
            print(f"❌ Webhook error: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
