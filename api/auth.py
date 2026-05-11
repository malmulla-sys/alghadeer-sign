"""
API endpoint for authentication
Vercel Serverless Function
"""
import json
import os
import hashlib
import time
from http.server import BaseHTTPRequestHandler

# المستخدمين المصرح لهم (من متغيرات البيئة)
# الصيغة: username:password:display_name:role
# role = admin (صلاحية حذف) أو user (بدون حذف)
USERS_RAW = os.environ.get('SIGNATURE_USERS', 'bilal:1234:بلال:admin,duraihim:5678:الدريهم:user')

def get_users() -> dict:
    """تحميل المستخدمين من متغير البيئة"""
    users = {}
    for user_str in USERS_RAW.split(','):
        parts = user_str.strip().split(':')
        if len(parts) >= 2:
            username = parts[0].strip().lower()
            password = parts[1].strip()
            display_name = parts[2].strip() if len(parts) > 2 else username
            role = parts[3].strip().lower() if len(parts) > 3 else 'user'
            users[username] = {
                'password': password,
                'name': display_name,
                'role': role
            }
    return users


def generate_token(username: str) -> str:
    """توليد token للمستخدم"""
    secret = os.environ.get('SIGNATURE_SECRET', 'default-secret-key')
    timestamp = str(int(time.time()))
    raw = f"{username}:{timestamp}:{secret}"
    token_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{username}:{timestamp}:{token_hash}"


def verify_token(token: str) -> tuple[bool, str]:
    """التحقق من صحة الـ token"""
    if not token:
        return False, ''

    try:
        parts = token.split(':')
        if len(parts) != 3:
            return False, ''

        username, timestamp, token_hash = parts
        secret = os.environ.get('SIGNATURE_SECRET', 'default-secret-key')

        # التحقق من الـ hash
        raw = f"{username}:{timestamp}:{secret}"
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]

        if token_hash != expected_hash:
            return False, ''

        # التحقق من صلاحية الـ token (7 أيام)
        token_time = int(timestamp)
        if time.time() - token_time > 7 * 24 * 60 * 60:
            return False, ''

        return True, username
    except Exception:
        return False, ''


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_POST(self):
        """تسجيل الدخول"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            username = data.get('username', '').strip().lower()
            password = data.get('password', '')

            users = get_users()

            if username not in users:
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'اسم المستخدم غير موجود'
                }, ensure_ascii=False).encode('utf-8'))
                return

            if users[username]['password'] != password:
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'كلمة المرور غير صحيحة'
                }, ensure_ascii=False).encode('utf-8'))
                return

            # توليد token
            token = generate_token(username)

            self.wfile.write(json.dumps({
                'success': True,
                'token': token,
                'name': users[username]['name'],
                'role': users[username]['role'],
                'message': 'تم تسجيل الدخول بنجاح'
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': str(e)
            }).encode())
