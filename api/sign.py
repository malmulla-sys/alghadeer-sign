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

            # إرسال البيانات للبوت عبر Telegram
            if BOT_TOKEN and ADMIN_CHAT_ID:
                success = send_signature_to_bot(data)
                if success:
                    # محاولة حذف الطلب من قائمة الانتظار (لا يؤثر على النجاح)
                    request_id = data.get('receipt_id') or data.get('id', '')
                    if request_id:
                        try:
                            remove_pending_request(request_id)
                        except:
                            pass  # تجاهل أي خطأ في الحذف

                self.wfile.write(json.dumps({
                    'success': True,
                    'message': 'تم حفظ التوقيع بنجاح ✅'
                }, ensure_ascii=False).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'إعدادات البوت غير مكتملة'
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
        # بيانات كاملة مع صورة التوقيع
        message_data = {
            'receipt_no': data.get('receipt_no', ''),
            'beneficiary_name': data.get('beneficiary_name', ''),
            'national_id': data.get('national_id', ''),
            'amount': data.get('amount', ''),
            'subject': data.get('subject', ''),
            'date': data.get('date', ''),
            'proxy_name': data.get('proxy_name', ''),
            'proxy_national_id': data.get('proxy_national_id', ''),
            'signature': data.get('signature', ''),
            'signed_at': data.get('signed_at', '')
        }

        # إرسال البيانات مباشرة للبوت (يولّد PDF تلقائياً)
        message = f"SIGNATURE_DATA:{json.dumps(message_data, ensure_ascii=False)}"

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': ADMIN_CHAT_ID,
            'text': message
        }
        msg_data = urllib.parse.urlencode(payload).encode()

        req = urllib.request.Request(url, data=msg_data)
        urllib.request.urlopen(req, timeout=10)

        return True

    except Exception as e:
        print(f"Failed to send to bot: {e}")
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
