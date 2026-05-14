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
WELCOME_MESSAGE = "مرحباً بك في مجموعة الغدير 👋\n\nاختر الخدمة:"

# خيارات الاستطلاع
POLL_OPTIONS = [
    {"optionName": "📍 العنوان وأوقات العمل"},
    {"optionName": "📞 تواصل مع موظف"},
]

# الردود على الخيارات
OPTION_RESPONSES = {
    "📍 العنوان وأوقات العمل": """مجموعة الغدير
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

    "📞 تواصل مع موظف": """للتواصل مع موظف:

📱 جوال: 0530364878
📧 إيميل: info@alghadeer.com

سيتم الرد عليك في أقرب وقت ممكن.""",
}

# كلمات تُظهر القائمة من جديد
MENU_KEYWORDS = ["قائمة", "ابدأ", "ابدا", "القائمة", "start", "menu", "hi", "hello", "مرحبا", "السلام"]

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
            "poll_options": [o["optionName"] for o in POLL_OPTIONS],
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
                    # التحقق من اختيار في الاستطلاع
                    if msg_type == "pollUpdateMessage":
                        poll_data = message_data.get("pollUpdateMessage", {})
                        votes = poll_data.get("votes", [])
                        for vote in votes:
                            option_name = vote.get("optionName", "")
                            if option_name in OPTION_RESPONSES:
                                send_message(phone, OPTION_RESPONSES[option_name])
                                break

                    # رسالة نصية
                    elif msg_type == "textMessage":
                        text = message_data.get("textMessageData", {}).get("textMessage", "").strip().lower()

                        # كلمة مفتاحية لإظهار القائمة
                        if any(kw in text for kw in MENU_KEYWORDS):
                            send_poll(phone, WELCOME_MESSAGE, POLL_OPTIONS)
                            replied.add(phone)

                        # رسالة جديدة من شخص لم نرد عليه
                        elif phone not in replied:
                            if send_poll(phone, WELCOME_MESSAGE, POLL_OPTIONS):
                                replied.add(phone)
                                if len(replied) > 100:
                                    replied = set(list(replied)[-50:])

                    # أنواع أخرى - رد للأشخاص الجدد فقط
                    elif phone not in replied:
                        if send_poll(phone, WELCOME_MESSAGE, POLL_OPTIONS):
                            replied.add(phone)
                            if len(replied) > 100:
                                replied = set(list(replied)[-50:])

        except Exception as e:
            print(f"Webhook error: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
