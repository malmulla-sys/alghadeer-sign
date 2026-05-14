"""
wa_webhook.py - WhatsApp Auto-Reply Webhook with Interactive Poll
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
WELCOME_MESSAGE = "مرحباً بك في مجموعة الغدير 👋\n\nاختر الخدمة:\n\n1️⃣ العنوان وأوقات العمل\n2️⃣ تواصل مع موظف\n\nأرسل رقم الخيار أو اضغط على التصويت"

# خيارات الاستطلاع
POLL_OPTIONS = [
    {"optionName": "📍 العنوان وأوقات العمل"},
    {"optionName": "📞 تواصل مع موظف"},
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


def send_poll(phone, message, options):
    """إرسال استطلاع تفاعلي."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN or not urlopen:
        return False

    url = f"{BASE_URL}/sendPoll/{GREEN_API_TOKEN}"
    data = json.dumps({
        "chatId": f"{normalize(phone)}@c.us",
        "message": message,
        "options": options,
        "multipleAnswers": False,
    }).encode()

    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"Error sending poll: {e}")
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
                            send_poll(phone, WELCOME_MESSAGE, POLL_OPTIONS)
                            replied.add(phone)
                            response_sent = True

                        # رسالة جديدة من شخص لم نرد عليه
                        elif phone not in replied:
                            if send_poll(phone, WELCOME_MESSAGE, POLL_OPTIONS):
                                replied.add(phone)
                                if len(replied) > 100:
                                    replied = set(list(replied)[-50:])
                            response_sent = True

                    # التعامل مع جميع أنواع رسائل الاستطلاع
                    elif "poll" in msg_type.lower():
                        print(f"Poll message data: {json.dumps(message_data, ensure_ascii=False)}", flush=True)
                        # محاولة استخراج الخيار المحدد
                        poll_data = message_data.get("pollMessageData", message_data.get("pollUpdateMessage", {}))
                        selected = poll_data.get("selectedOptions", poll_data.get("votes", []))

                        for opt in selected:
                            opt_name = opt.get("optionName", opt.get("name", ""))
                            if "عنوان" in opt_name or "العنوان" in opt_name:
                                send_message(phone, RESPONSE_ADDRESS)
                                response_sent = True
                                break
                            elif "موظف" in opt_name or "تواصل" in opt_name:
                                send_message(phone, RESPONSE_CONTACT)
                                response_sent = True
                                break

                    # أنواع أخرى - رد للأشخاص الجدد فقط
                    elif phone not in replied and not response_sent:
                        if send_poll(phone, WELCOME_MESSAGE, POLL_OPTIONS):
                            replied.add(phone)
                            if len(replied) > 100:
                                replied = set(list(replied)[-50:])

        except Exception as e:
            print(f"Webhook error: {e}", flush=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
