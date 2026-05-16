"""
wa_webhook.py - WhatsApp Webhook
- رد تلقائي بالعنوان للعملاء
- تخزين صور الهوية من الزملاء في KV ليعالجها البوت
"""
import os
import json
import time
from http.server import BaseHTTPRequestHandler

try:
    from urllib.request import urlopen, Request
except ImportError:
    urlopen = None
    Request = None

# Green API
GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID", "")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "")
GREEN_BASE_URL = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}"

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

# Upstash KV
KV_REST_API_URL = os.environ.get("KV_REST_API_URL", "")
KV_REST_API_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")

# أرقام الزملاء (يتم تحويل صورهم للبوت)
COLLEAGUE_NUMBERS = ["966530364878", "966560454000"]

# الرد التلقائي بالعنوان
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

# كلمات مفتاحية للتحية
GREETING_KEYWORDS = ["قائمة", "ابدأ", "ابدا", "القائمة", "start", "menu", "hi", "hello", "مرحبا", "السلام", "هلا", "اهلا", "أهلا", "السلام عليكم", "هاي"]

# تتبع من رددنا عليهم
replied = set()


def normalize(phone):
    p = str(phone).replace("@c.us", "").replace("+", "").replace(" ", "").replace("-", "")
    return "966" + p[1:] if p.startswith("0") else p


def send_whatsapp_message(phone, message):
    """إرسال رسالة واتساب."""
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN or not urlopen:
        return False
    url = f"{GREEN_BASE_URL}/sendMessage/{GREEN_API_TOKEN}"
    data = json.dumps({
        "chatId": f"{normalize(phone)}@c.us",
        "message": message,
    }).encode()
    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"[WA] Error sending message: {e}", flush=True)
        return False


def download_whatsapp_file(download_url):
    """تحميل ملف من Green API."""
    if not urlopen or not download_url:
        return None
    try:
        req = Request(download_url)
        with urlopen(req, timeout=30) as r:
            return r.read()
    except Exception as e:
        print(f"[WA] Error downloading file: {e}", flush=True)
        return None


def send_telegram_message(text):
    """إرسال رسالة نصية لـ Telegram."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID or not urlopen:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
    }).encode()
    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"[TG] Error sending message: {e}", flush=True)
        return False


def store_pending_image(download_url, caption, sender_phone):
    """تخزين صورة معلّقة في KV ليعالجها البوت."""
    if not KV_REST_API_URL or not KV_REST_API_TOKEN or not urlopen:
        print("[KV] Missing credentials", flush=True)
        return False

    # إنشاء معرف فريد
    image_id = f"wa_img_{int(time.time() * 1000)}"

    # البيانات للتخزين
    image_info = {
        "id": image_id,
        "download_url": download_url,
        "caption": caption or "",
        "sender": sender_phone,
        "timestamp": int(time.time()),
        "status": "pending",
    }

    # تخزين في KV
    url = f"{KV_REST_API_URL}/set/{image_id}"
    data = json.dumps(image_info).encode()

    try:
        req = Request(url, data=data, headers={
            "Authorization": f"Bearer {KV_REST_API_TOKEN}",
            "Content-Type": "application/json",
        })
        with urlopen(req, timeout=10) as r:
            result = r.status == 200
            print(f"[KV] Stored pending image: {image_id} = {result}", flush=True)

            # إضافة للقائمة
            if result:
                add_to_pending_list(image_id)

            return result
    except Exception as e:
        print(f"[KV] Error storing image: {e}", flush=True)
        return False


def add_to_pending_list(image_id):
    """إضافة معرف الصورة لقائمة المعلّقات."""
    if not KV_REST_API_URL or not KV_REST_API_TOKEN or not urlopen:
        return False

    # جلب القائمة الحالية
    url = f"{KV_REST_API_URL}/get/wa_pending_images"
    try:
        req = Request(url, headers={"Authorization": f"Bearer {KV_REST_API_TOKEN}"})
        with urlopen(req, timeout=10) as r:
            resp = json.loads(r.read().decode())
            current_list = resp.get("result") or "[]"
            if isinstance(current_list, str):
                current_list = json.loads(current_list)
    except:
        current_list = []

    # إضافة المعرف الجديد
    if image_id not in current_list:
        current_list.append(image_id)

    # حفظ القائمة المحدّثة
    url = f"{KV_REST_API_URL}/set/wa_pending_images"
    data = json.dumps(current_list).encode()
    try:
        req = Request(url, data=data, headers={
            "Authorization": f"Bearer {KV_REST_API_TOKEN}",
            "Content-Type": "application/json",
        })
        with urlopen(req, timeout=10) as r:
            return r.status == 200
    except:
        return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "green_api": bool(GREEN_API_INSTANCE_ID and GREEN_API_TOKEN),
            "telegram": bool(TELEGRAM_BOT_TOKEN and ADMIN_CHAT_ID),
        }).encode())

    def do_POST(self):
        global replied

        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body.decode())

            type_webhook = data.get("typeWebhook", "")
            print(f"[WH] Type: {type_webhook}", flush=True)

            if type_webhook == "incomingMessageReceived":
                sender_data = data.get("senderData", {})
                message_data = data.get("messageData", {})

                phone = normalize(sender_data.get("sender", ""))
                msg_type = message_data.get("typeMessage", "")

                print(f"[WH] From: {phone}, Type: {msg_type}", flush=True)

                # ═══════════════════════════════════════════
                # صور من الزملاء → تخزين في KV + إشعار Telegram
                # ═══════════════════════════════════════════
                if phone in COLLEAGUE_NUMBERS and msg_type == "imageMessage":
                    print(f"[WH] Image from colleague {phone}", flush=True)

                    image_data = message_data.get("fileMessageData", {})
                    download_url = image_data.get("downloadUrl", "")
                    caption = image_data.get("caption", "")

                    if download_url:
                        # تخزين في KV ليعالجها البوت
                        if store_pending_image(download_url, caption, phone):
                            send_telegram_message(f"📱 صورة هوية جديدة من واتساب\n📞 {phone}\n📝 {caption or '-'}\n\n⏳ جاري المعالجة...")
                            print("[WH] Image stored in KV for processing", flush=True)
                        else:
                            send_telegram_message(f"⚠️ فشل تخزين صورة من {phone}\nالرابط: {download_url[:50]}...")

                # ═══════════════════════════════════════════
                # رسائل من غير الزملاء → رد تلقائي
                # ═══════════════════════════════════════════
                elif phone not in COLLEAGUE_NUMBERS:

                    if msg_type == "textMessage":
                        text = message_data.get("textMessageData", {}).get("textMessage", "").strip()
                        text_lower = text.lower()

                        # تحية → رد بالعنوان
                        if any(kw in text_lower for kw in GREETING_KEYWORDS):
                            send_whatsapp_message(phone, RESPONSE_ADDRESS)
                            replied.add(phone)

                        # شخص جديد → رد بالعنوان
                        elif phone not in replied:
                            send_whatsapp_message(phone, RESPONSE_ADDRESS)
                            replied.add(phone)
                            if len(replied) > 500:
                                replied = set(list(replied)[-250:])

                    # صور/صوت/فيديو من شخص جديد → رد بالعنوان
                    elif phone not in replied:
                        send_whatsapp_message(phone, RESPONSE_ADDRESS)
                        replied.add(phone)
                        if len(replied) > 500:
                            replied = set(list(replied)[-250:])

        except Exception as e:
            print(f"[WH] Error: {e}", flush=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
