"""
API endpoint to receive and save signatures
Vercel Serverless Function
"""
import json
import os
import base64
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

# Telegram Bot Token (set in Vercel environment variables)
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '')
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')
KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

# توقيت الرياض (UTC+3)
RIYADH_TZ = timezone(timedelta(hours=3))
OTP_MAX_ATTEMPTS = 5


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        """Save signature and notify bot"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            # طلبات OTP (تخزين/تحقق) مُدمَجة بنفس هذا الملف لتفادي تجاوز حد عدد
            # الـ Serverless Functions المسموح به على خطة Vercel — بدل ملفات منفصلة
            mode = data.get('mode', 'sign')
            if mode == 'set_otp':
                auth_header = self.headers.get('Authorization', '')
                token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
                self.wfile.write(json.dumps(handle_set_otp(data, token)).encode('utf-8'))
                return
            if mode == 'verify_otp':
                self.wfile.write(json.dumps(handle_verify_otp(data)).encode('utf-8'))
                return

            # استخراج البيانات
            receipt_no = data.get('receipt_no', '')
            beneficiary_name = data.get('beneficiary_name', '')
            national_id = data.get('national_id', '')
            amount = data.get('amount', '')
            subject = data.get('subject', '')
            signature = data.get('signature', '')  # Base64 PNG
            signed_at = data.get('signed_at', datetime.now().isoformat())

            if not signature:
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'التوقيع مطلوب'
                }, ensure_ascii=False).encode('utf-8'))
                return

            # حفظ التوقيع في KV + السجل + حذف من الانتظار (بغض النظر عن نجاح الإشعار)
            request_id = data.get('receipt_id') or data.get('id', '')

            # التحقق النهائي من رمز OTP (لو هذا السند يتطلبه) — تحقق سيادي بغض النظر
            # عن أي تحقق سبق في الواجهة، ويستهلك الرمز (حذف بعد أول نجاح) لمنع إعادة الاستخدام
            otp_code = data.get('otp_code', '')
            otp_ok, otp_error = check_and_consume_otp(request_id, otp_code)
            if not otp_ok:
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': otp_error
                }, ensure_ascii=False).encode('utf-8'))
                return

            # 1. حفظ في KV
            try:
                send_signature_to_bot(data)  # هذا يحفظ في KV
            except:
                pass

            # 2. حفظ في سجل التوقيعات (للفحص الدوري)
            try:
                save_to_history(data)
            except:
                pass

            # 3. حذف من قائمة الانتظار
            if request_id:
                try:
                    remove_pending_request(request_id)
                except:
                    pass

            # 4. إرسال إشعار بسيط للمشرف (اختياري)
            if BOT_TOKEN and ADMIN_CHAT_ID:
                try:
                    notify_msg = f"✅ توقيع جديد: {data.get('beneficiary_name', '')} - {data.get('amount', '')} ريال"
                    notify_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    notify_data = json.dumps({'chat_id': ADMIN_CHAT_ID, 'text': notify_msg}).encode('utf-8')
                    notify_req = urllib.request.Request(notify_url, data=notify_data)
                    notify_req.add_header('Content-Type', 'application/json')
                    urllib.request.urlopen(notify_req, timeout=5)
                except:
                    pass  # الإشعار اختياري

            self.wfile.write(json.dumps({
                'success': True,
                'message': 'تم حفظ التوقيع بنجاح ✅'
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def check_and_consume_otp(request_id: str, otp_code: str) -> tuple[bool, str]:
    """يتحقق من رمز OTP لسند مُرسَل عن بُعد (واتساب) ويستهلكه (يحذفه) عند النجاح.
    لو ما فيه رمز OTP مخزّن لهذا السند أصلاً (المسار العادي: تابلت/قائمة الطلبات المشتركة)
    يمر التوقيع بدون أي تحقق — توافقية كاملة مع التدفق الحالي."""
    KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
    KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

    if not KV_REST_API_URL or not KV_REST_API_TOKEN or not request_id:
        return True, ''

    try:
        url = f"{KV_REST_API_URL}/get/otp:{request_id}"
        req = urllib.request.Request(url)
        req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            result_data = json.loads(resp.read().decode())
            result = result_data.get('result')
            record = json.loads(result) if result else None
    except Exception:
        record = None

    if not record:
        # لا يوجد رمز مخزّن لهذا السند — مسار عادي (تابلت)، لا حاجة لتحقق
        return True, ''

    if str(otp_code) != str(record.get('code', '')):
        return False, 'رمز التحقق غير صحيح'

    # استهلاك الرمز فوراً بعد نجاح التحقق لمنع إعادة استخدامه
    try:
        del_url = f"{KV_REST_API_URL}/del/otp:{request_id}"
        del_req = urllib.request.Request(del_url, method='POST')
        del_req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
        urllib.request.urlopen(del_req, timeout=10)
    except Exception:
        pass

    return True, ''


def handle_set_otp(data: dict, token: str) -> dict:
    """يخزّن رمز OTP لسند مُرسَل عن بُعد — بوت فقط (Bearer SIGNATURE_BOT_API_KEY)."""
    if token != BOT_API_KEY:
        return {'success': False, 'error': 'unauthorized'}

    otp_id = str(data.get('id', '')).strip()
    code = str(data.get('code', '')).strip()
    ttl_seconds = int(data.get('ttl_seconds', 600))

    if not otp_id or not code:
        return {'success': False, 'error': 'missing id or code'}

    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return {'success': False, 'error': 'KV not configured'}

    try:
        payload = json.dumps({'code': code, 'attempts': 0}).encode('utf-8')
        kv_url = f"{KV_REST_API_URL}/set/otp:{otp_id}?EX={ttl_seconds}"
        kv_req = urllib.request.Request(kv_url, data=payload, method='POST')
        kv_req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
        kv_req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(kv_req, timeout=10)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def handle_verify_otp(data: dict) -> dict:
    """يتحقق (بدون استهلاك) من رمز OTP لعرض لوحة التوقيع — بوابة تجربة استخدام فقط؛
    التحقق السيادي المُستهلِك للرمز يحصل عند التوقيع الفعلي (check_and_consume_otp)."""
    otp_id = str(data.get('id', '')).strip()
    submitted_code = str(data.get('code', '')).strip()

    if not otp_id or not submitted_code:
        return {'success': False, 'error': 'missing_fields'}

    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return {'success': False, 'error': 'kv_not_configured'}

    try:
        url = f"{KV_REST_API_URL}/get/otp:{otp_id}"
        req = urllib.request.Request(url)
        req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            result_data = json.loads(resp.read().decode())
            result = result_data.get('result')
            record = json.loads(result) if result else None
    except Exception:
        record = None

    if not record:
        return {'success': False, 'error': 'expired'}

    attempts = int(record.get('attempts', 0))
    if attempts >= OTP_MAX_ATTEMPTS:
        return {'success': False, 'error': 'too_many_attempts'}

    if submitted_code == record.get('code'):
        return {'success': True}

    record['attempts'] = attempts + 1
    try:
        upd_url = f"{KV_REST_API_URL}/set/otp:{otp_id}?XX=true&KEEPTTL=true"
        upd_req = urllib.request.Request(upd_url, data=json.dumps(record).encode('utf-8'), method='POST')
        upd_req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
        upd_req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(upd_req, timeout=10)
    except Exception:
        pass

    return {'success': False, 'error': 'wrong_code'}


def send_signature_to_bot(data: dict) -> bool:
    """
    حفظ بيانات التوقيع في KV وإرسال رسالة منسقة مع زر للبوت
    """
    try:
        # استخراج receipt_id من البيانات
        receipt_id = data.get('receipt_id') or data.get('id', '')

        # بيانات كاملة مع صورة التوقيع
        message_data = {
            'receipt_no': data.get('receipt_no', ''),
            'beneficiary_name': data.get('beneficiary_name', ''),
            'national_id': data.get('national_id', ''),
            'amount': data.get('amount', ''),
            'subject': data.get('subject', ''),
            'date': data.get('date', ''),
            'signature': data.get('signature', ''),
            'signed_at': data.get('signed_at', ''),
            'proxy_name': data.get('proxy_name', ''),
            'proxy_national_id': data.get('proxy_national_id', ''),
        }

        # حفظ في KV باستخدام receipt_id (statement_id) كمفتاح
        KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
        KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

        if KV_REST_API_URL and KV_REST_API_TOKEN and receipt_id:
            kv_url = f"{KV_REST_API_URL}/set/sig:{receipt_id}"
            kv_data = json.dumps(message_data).encode('utf-8')
            kv_req = urllib.request.Request(kv_url, data=kv_data, method='POST')
            kv_req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
            kv_req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(kv_req, timeout=10)

        # تنسيق وقت التوقيع
        signed_at = data.get('signed_at', '')
        formatted_time = signed_at.replace('T', ' ')[:19] if signed_at else ''

        # إرسال رسالة منسقة مع زر
        message = f"""✅ تم استلام توقيع إلكتروني

📄 رقم السند: {data.get('receipt_no', receipt_id)}
👤 المستفيد: {data.get('beneficiary_name', '')}
🪪 الهوية: {data.get('national_id', '')}
💰 المبلغ: {data.get('amount', '')} ريال
📝 الموضوع: {data.get('subject', '')}
🕐 وقت التوقيع: {formatted_time}"""

        # زر لتوليد PDF
        inline_keyboard = {
            "inline_keyboard": [[
                {"text": "📄 توليد سند PDF", "callback_data": f"esign_pdf:sig:{receipt_id}"}
            ]]
        }

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            'chat_id': ADMIN_CHAT_ID,
            'text': message,
            'reply_markup': inline_keyboard
        })

        req = urllib.request.Request(url, data=payload.encode('utf-8'))
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, timeout=10)

        return True

    except Exception as e:
        print(f"Failed to send to bot: {e}")
        return False


def save_to_history(data: dict) -> bool:
    """حفظ التوقيع المكتمل في السجل"""
    KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
    KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return False

    try:
        # Get current history
        url = f"{KV_REST_API_URL}/get/signature_history"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            result_data = json.loads(resp.read().decode())
            result = result_data.get("result")
            history = json.loads(result) if result else []

        # Create history entry (without signature image to save space)
        history_entry = {
            'id': data.get('receipt_id') or data.get('id', ''),
            'receipt_no': data.get('receipt_no', ''),
            'beneficiary_name': data.get('beneficiary_name', ''),
            'national_id': data.get('national_id', ''),
            'amount': data.get('amount', ''),
            'subject': data.get('subject', ''),
            'signed_at': datetime.now(RIYADH_TZ).isoformat()
        }

        # Add to beginning of list
        history.insert(0, history_entry)

        # Keep only last 100 entries
        history = history[:100]

        # Save back
        save_url = f"{KV_REST_API_URL}/set/signature_history"
        save_data = json.dumps(history).encode()
        save_req = urllib.request.Request(save_url, data=save_data, method='POST')
        save_req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        save_req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(save_req, timeout=5)

        return True
    except Exception as e:
        print(f"Failed to save history: {e}")
        return False


def remove_pending_request(request_id: str) -> bool:
    """حذف الطلب من قائمة الانتظار بعد التوقيع"""
    KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
    KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return True  # No KV configured, skip

    try:
        # Get current requests
        url = f"{KV_REST_API_URL}/get/signature_requests"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            result = data.get("result")
            requests = json.loads(result) if result else []

        # Remove the signed request
        requests = [r for r in requests if r.get('id') != request_id]

        # Save back
        save_url = f"{KV_REST_API_URL}/set/signature_requests"
        save_data = json.dumps(requests).encode()
        save_req = urllib.request.Request(save_url, data=save_data, method='POST')
        save_req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        save_req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(save_req, timeout=5)

        return True
    except Exception as e:
        print(f"Failed to remove request: {e}")
        return False
