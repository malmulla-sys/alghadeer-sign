"""
API endpoint to receive and save signatures
Vercel Serverless Function
"""
import json
import os
import base64
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

# Telegram Bot Token (set in Vercel environment variables)
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '')


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

            # حفظ التوقيع المؤكد في KV ليجلبه البوت
            save_success = save_confirmed_signature(data)

            # حذف الطلب من قائمة الانتظار
            request_id = data.get('receipt_id') or data.get('id', '')
            if request_id:
                try:
                    remove_pending_request(request_id)
                except:
                    pass

            # إرسال إشعار للبوت (اختياري - قد لا يعمل)
            if BOT_TOKEN and ADMIN_CHAT_ID:
                try:
                    send_signature_to_bot(data)
                except:
                    pass  # تجاهل أي خطأ في الإرسال

            self.wfile.write(json.dumps({
                'success': True,
                'message': 'تم حفظ التوقيع بنجاح ✅',
                'saved_to_kv': save_success
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def send_signature_to_bot(data: dict) -> bool:
    """
    إرسال بيانات التوقيع مباشرة للبوت لتوليد PDF تلقائي
    """
    try:
        # بيانات بدون صورة التوقيع (لتجنب تجاوز حد الرسالة)
        # سنرسل تأكيد بسيط أولاً
        confirm_data = {
            'receipt_no': data.get('receipt_no', ''),
            'beneficiary_name': data.get('beneficiary_name', ''),
            'national_id': data.get('national_id', ''),
            'amount': data.get('amount', ''),
            'subject': data.get('subject', ''),
            'date': data.get('date', ''),
            'signed_at': data.get('signed_at', '')
        }

        # إرسال تأكيد بسيط (بدون صورة التوقيع لتجنب تجاوز الحد)
        message = f"ESIGN_CONFIRM:{json.dumps(confirm_data, ensure_ascii=False)}"

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        # استخدام JSON بدلاً من urlencode للتعامل الأفضل مع العربية
        headers = {'Content-Type': 'application/json'}
        payload = json.dumps({
            'chat_id': ADMIN_CHAT_ID,
            'text': message
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, headers=headers)
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode())

        if not result.get('ok'):
            print(f"Telegram API error: {result}")
            return False

        return True

    except Exception as e:
        print(f"Failed to send to bot: {e}")
        return False


def save_confirmed_signature(data: dict) -> bool:
    """حفظ التوقيع المؤكد في KV ليجلبه البوت"""
    KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
    KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return False

    try:
        # جلب التوقيعات المؤكدة الحالية
        url = f"{KV_REST_API_URL}/get/confirmed_signatures"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                result_data = json.loads(resp.read().decode())
                result = result_data.get("result")
                signatures = json.loads(result) if result else []
        except:
            signatures = []

        # إضافة التوقيع الجديد (مع صورة التوقيع لتوليد PDF)
        confirm_data = {
            'receipt_no': data.get('receipt_no', ''),
            'beneficiary_name': data.get('beneficiary_name', ''),
            'national_id': data.get('national_id', ''),
            'amount': data.get('amount', ''),
            'subject': data.get('subject', ''),
            'date': data.get('date', ''),
            'signed_at': data.get('signed_at', ''),
            'id': data.get('id') or data.get('receipt_id', ''),
            'signature': data.get('signature', ''),
            'proxy_name': data.get('proxy_name', ''),
            'proxy_national_id': data.get('proxy_national_id', '')
        }
        signatures.append(confirm_data)

        # حفظ
        save_url = f"{KV_REST_API_URL}/set/confirmed_signatures"
        save_data = json.dumps(signatures).encode()
        save_req = urllib.request.Request(save_url, data=save_data, method='POST')
        save_req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        save_req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(save_req, timeout=5)

        return True
    except Exception as e:
        print(f"Failed to save confirmed signature: {e}")
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
