"""
wa_webhook.py - WhatsApp Auto-Reply Webhook with Interactive List Menu
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

# الرسالة الترحيبية
WELCOME_MESSAGE = "مرحباً بك في مجموعة الغدير 👋"

# قائمة الخدمات التفاعلية
LIST_SECTIONS = [
    {
        "title": "خدماتنا",
        "rows": [
            {"rowId": "address", "title": "📍 العنوان وأوقات العمل"},
            {"rowId": "contact", "title": "📞 تواصل مع موظف"},
        ]
    }
]

# الردود
RESPONSE_ADDRESS = """مجموعة الغدير
Alghadeer Group

https://maps.app.goo.gl/JfggoLXjf5AmpgwF9

أوقات العمل :
السبت    :  08:30 ص - 04:30 م
الأحد     :  08:30 ص - 04:30 م
الاثنين   :  08:30 ص - 04:30 م
الثلاثاء  :  08:30 ص - 04:30 م
الأربعاء  :  08:30 ص - 04:30 م
الخميس  :  08:30 ص - 04:30 م
الجمعة   :  مغلق"""

RESPONSE_CONTACT = """للتواصل مع موظف:

📱 جوال: 0530364878
📧 إيميل: info@alghadeer.com

سيتم الرد عليك في أقرب وقت ممكن."""

# كلمات مفتاحية
MENU_KEYWORDS = ["قائمة", "ابدأ", "ابدا", "القائمة", "start", "menu", "hi", "hello", "مرحبا", "السلام"]
ADDRESS_KEYWORDS = ["1", "١", "عنوان", "العنوان", "موقع", "الموقع", "اوقات", "أوقات"]
CONTACT_KEYWORDS = ["2", "٢", "موظف", "تواصل", "اتصال", "رقم"]

# أرقام مستثناة
EXCLUDED = ["966530364878", "966560454000"]
replied = set()


def normalize(phone):
    p = str(phone).replace("@c.us", "").replace("+", "").replace(" ", "").replace("-", "")
    return "966" + p[1:] if p.startswith("0") else p


def send_list(phone, message, sections, button_text="اختر خدمة"):
    """إرسال قائمة تفاعلية."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN or not urlopen:
        print("Missing credentials or urlopen", flush=True)
        return False

    url = f"{BASE_URL}/sendList/{GREEN_API_TOKEN}"
    payload = {
        "chatId": f"{normalize(phone)}@c.us",
        "message": message,
        "title": "مجموعة الغدير",
        "buttonText": button_text,
        "sections": sections,
    }
    print(f"Sending list to {phone}: {json.dumps(payload, ensure_ascii=False)}", flush=True)
    data = json.dumps(payload).encode()

    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r:
            response_body = r.read().decode()
            print(f"sendList response: {r.status} - {response_body}", flush=True)
            return r.status == 200
    except Exception as e:
        print(f"Error sending list: {e}", flush=True)
        # Fallback: إرسال رسالة نصية عادية
        fallback_msg = f"{message}\n\n1️⃣ العنوان وأوقات العمل\n2️⃣ تواصل مع موظف\n\nأرسل رقم الخيار"
        return send_message(phone, fallback_msg)


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
        }).encode())

    def do_POST(self):
        global replied
        response_sent = False

        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body.decode())

            type_webhook = data.get("typeWebhook", "")

            # Log ALL incoming webhooks for debugging
            print(f"=== WEBHOOK RECEIVED ===", flush=True)
            print(f"Type: {type_webhook}", flush=True)
            print(f"Full data: {json.dumps(data, ensure_ascii=False)[:1000]}", flush=True)

            if type_webhook == "incomingMessageReceived":
                sender_data = data.get("senderData", {})
                message_data = data.get("messageData", {})

                phone = normalize(sender_data.get("sender", ""))
                msg_type = message_data.get("typeMessage", "")

                print(f"From: {phone}, Type: {msg_type}", flush=True)

                if phone and phone not in EXCLUDED:

                    # رسالة نصية
                    if msg_type == "textMessage":
                        text = message_data.get("textMessageData", {}).get("textMessage", "").strip()
                        text_lower = text.lower()

                        print(f"Text: {text}", flush=True)

                        # طلب العنوان
                        if any(kw in text_lower or kw in text for kw in ADDRESS_KEYWORDS):
                            send_message(phone, RESPONSE_ADDRESS)
                            response_sent = True

                        # طلب التواصل
                        elif any(kw in text_lower or kw in text for kw in CONTACT_KEYWORDS):
                            send_message(phone, RESPONSE_CONTACT)
                            response_sent = True

                        # كلمة مفتاحية لإظهار القائمة
                        elif any(kw in text_lower for kw in MENU_KEYWORDS):
                            menu_msg = "مرحباً بك في مجموعة الغدير 👋\n\nاختر الخدمة:\n\n1️⃣ العنوان وأوقات العمل\n2️⃣ تواصل مع موظف\n\nأرسل رقم الخيار"
                            send_message(phone, menu_msg)
                            replied.add(phone)
                            response_sent = True

                        # أي رسالة أخرى - أرسل القائمة
                        else:
                            menu_msg = "مرحباً بك في مجموعة الغدير 👋\n\nاختر الخدمة:\n\n1️⃣ العنوان وأوقات العمل\n2️⃣ تواصل مع موظف\n\nأرسل رقم الخيار"
                            send_message(phone, menu_msg)
                            response_sent = True

                    # التعامل مع رد القائمة التفاعلية
                    elif msg_type == "listResponseMessage":
                        print(f"List response: {json.dumps(message_data, ensure_ascii=False)}", flush=True)
                        list_data = message_data.get("listResponseMessageData", {})
                        selected_id = list_data.get("selectedRowId", "")

                        if selected_id == "address":
                            send_message(phone, RESPONSE_ADDRESS)
                            response_sent = True
                        elif selected_id == "contact":
                            send_message(phone, RESPONSE_CONTACT)
                            response_sent = True

                    # أنواع أخرى (صور، صوت، فيديو...) - أرسل القائمة
                    elif not response_sent:
                        menu_msg = "مرحباً بك في مجموعة الغدير 👋\n\nاختر الخدمة:\n\n1️⃣ العنوان وأوقات العمل\n2️⃣ تواصل مع موظف\n\nأرسل رقم الخيار"
                        send_message(phone, menu_msg)

        except Exception as e:
            print(f"Webhook error: {e}", flush=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
