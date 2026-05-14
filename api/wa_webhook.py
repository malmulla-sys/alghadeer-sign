"""
wa_webhook.py - WhatsApp Auto-Reply Webhook with Interactive Buttons
"""
import os
import json
from http.server import BaseHTTPRequestHandler

try:
    from urllib.request import urlopen, Request
except ImportError:
    urlopen = None
    Request = None

GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID", "")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "")
BASE_URL = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}"

# الرسالة الترحيبية مع الأزرار
WELCOME_MESSAGE = "مرحباً بك في مجموعة الغدير 👋"

# الأزرار (buttonText يجب أن يكون string)
BUTTONS = [
    {"buttonId": "btn_address", "buttonText": "📍 العنوان"},
]

# الردود على الأزرار
BUTTON_RESPONSES = {
    "btn_address": """مجموعة الغدير
Alghadeer Group

https://maps.app.goo.gl/JfggoLXjf5AmpgwF9

أوقات العمل :
السبت    :  08:30 ص - 04:30 م
الأحد     :  08:30 ص - 04:30 م
الاثنين   :  08:30 ص - 04:30 م
الثلاثاء  :  08:30 ص - 04:30 م
الأربعاء  :  08:30 ص - 04:30 م
الخميس  :  08:30 ص - 04:30 م
الجمعة   :  مغلق""",
}

# كلمات تُظهر القائمة من جديد
MENU_KEYWORDS = ["قائمة", "ابدأ", "ابدا", "القائمة", "start", "menu", "hi", "hello", "مرحبا", "السلام"]

# أرقام مستثناة
EXCLUDED = ["966530364878", "966560454000"]
replied = set()


def normalize(phone):
    p = str(phone).replace("@c.us", "").replace("+", "").replace(" ", "").replace("-", "")
    return "966" + p[1:] if p.startswith("0") else p


def send_buttons(phone, message, buttons):
    """إرسال رسالة مع أزرار تفاعلية."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN or not urlopen:
        return False

    url = f"{BASE_URL}/sendButtons/{GREEN_API_TOKEN}"
    data = json.dumps({
        "chatId": f"{normalize(phone)}@c.us",
        "message": message,
        "buttons": buttons,
    }).encode()

    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"Error sending buttons: {e}")
        return False


def send_message(phone, message):
    """إرسال رسالة نصية عادية."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN or not urlopen:
        return False

    url = f"{BASE_URL}/sendMessage/{GREEN_API_TOKEN}"
    data = json.dumps({
        "chatId": f"{normalize(phone)}@c.us",
        "message": message,
    }).encode()

    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "configured": bool(GREEN_API_INSTANCE_ID and GREEN_API_TOKEN),
            "buttons": len(BUTTONS),
            "menu_keywords": MENU_KEYWORDS
        }).encode())

    def do_POST(self):
        global replied
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body.decode())

            type_webhook = data.get("typeWebhook", "")

            if type_webhook == "incomingMessageReceived":
                sender_data = data.get("senderData", {})
                message_data = data.get("messageData", {})

                phone = normalize(sender_data.get("sender", ""))
                msg_type = message_data.get("typeMessage", "")

                if phone and phone not in EXCLUDED:
                    # التحقق من ضغط زر
                    if msg_type == "buttonsResponseMessage":
                        button_id = message_data.get("buttonsResponseMessage", {}).get("selectedButtonId", "")
                        if button_id in BUTTON_RESPONSES:
                            send_message(phone, BUTTON_RESPONSES[button_id])

                    # رسالة نصية
                    elif msg_type == "textMessage":
                        text = message_data.get("textMessageData", {}).get("textMessage", "").strip().lower()

                        # كلمة مفتاحية لإظهار القائمة
                        if any(kw in text for kw in MENU_KEYWORDS):
                            send_buttons(phone, WELCOME_MESSAGE, BUTTONS)
                            replied.add(phone)

                        # رسالة جديدة من شخص لم نرد عليه
                        elif phone not in replied:
                            if send_buttons(phone, WELCOME_MESSAGE, BUTTONS):
                                replied.add(phone)
                                if len(replied) > 100:
                                    replied = set(list(replied)[-50:])

                    # أنواع أخرى (صور، صوت، إلخ) - رد للأشخاص الجدد فقط
                    elif phone not in replied:
                        if send_buttons(phone, WELCOME_MESSAGE, BUTTONS):
                            replied.add(phone)
                            if len(replied) > 100:
                                replied = set(list(replied)[-50:])

        except Exception as e:
            print(f"Webhook error: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
