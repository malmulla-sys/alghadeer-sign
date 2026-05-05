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
    إرسال بيانات التوقيع للبوت عبر Telegram كملف JSON
    البوت سيستقبل الملف ويولّد PDF بالتوقيع
    """
    import io

    try:
        # بيانات كاملة مع صورة التوقيع
        message_data = {
            'type': 'SIGNATURE_RECEIVED',
            'receipt_no': data.get('receipt_no', ''),
            'beneficiary_name': data.get('beneficiary_name', ''),
            'national_id': data.get('national_id', ''),
            'amount': data.get('amount', ''),
            'subject': data.get('subject', ''),
            'date': data.get('date', ''),
            'signature': data.get('signature', ''),
            'signed_at': data.get('signed_at', '')
        }

        # إرسال إشعار نصي أولاً
        message = f"""✅ تم استلام توقيع إلكتروني

📄 رقم السند: {data.get('receipt_no', 'غير محدد')}
👤 المستفيد: {data.get('beneficiary_name', 'غير محدد')}
🪪 الهوية: {data.get('national_id', 'غير محدد')}
💰 المبلغ: {data.get('amount', '0')} ريال
📝 الموضوع: {data.get('subject', 'غير محدد')}
🕐 وقت التوقيع: {data.get('signed_at', '')[:19].replace('T', ' ')}

⏳ جاري توليد السند الموقّع..."""

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        msg_data = urllib.parse.urlencode({
            'chat_id': ADMIN_CHAT_ID,
            'text': message,
        }).encode()

        req = urllib.request.Request(url, data=msg_data)
        urllib.request.urlopen(req, timeout=10)

        # إرسال بيانات التوقيع كملف JSON
        json_content = json.dumps(message_data, ensure_ascii=False).encode('utf-8')

        # استخدام multipart/form-data لإرسال الملف
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'

        body = []
        body.append(f'--{boundary}'.encode())
        body.append(b'Content-Disposition: form-data; name="chat_id"')
        body.append(b'')
        body.append(ADMIN_CHAT_ID.encode())

        body.append(f'--{boundary}'.encode())
        body.append(b'Content-Disposition: form-data; name="document"; filename="esign_data.json"')
        body.append(b'Content-Type: application/json')
        body.append(b'')
        body.append(json_content)

        body.append(f'--{boundary}'.encode())
        body.append(b'Content-Disposition: form-data; name="caption"')
        body.append(b'')
        body.append('ESIGN_FILE'.encode())

        body.append(f'--{boundary}--'.encode())

        body_bytes = b'\r\n'.join(body)

        url2 = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        req2 = urllib.request.Request(url2, data=body_bytes)
        req2.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
        urllib.request.urlopen(req2, timeout=30)

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
