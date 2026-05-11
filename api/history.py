"""
API endpoint to get signature history
Vercel Serverless Function
"""
import json
import os
import hashlib
import time
from http.server import BaseHTTPRequestHandler

# Vercel KV credentials
KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

# Bot API key
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')


def _verify_token(token: str) -> tuple[bool, str]:
    """التحقق من صحة الـ token"""
    if not token:
        return False, ''

    if token == BOT_API_KEY:
        return True, 'bot'

    try:
        parts = token.split(':')
        if len(parts) != 3:
            return False, ''

        username, timestamp, token_hash = parts
        secret = os.environ.get('SIGNATURE_SECRET', 'default-secret-key')

        raw = f"{username}:{timestamp}:{secret}"
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]

        if token_hash != expected_hash:
            return False, ''

        token_time = int(timestamp)
        if time.time() - token_time > 7 * 24 * 60 * 60:
            return False, ''

        return True, username
    except Exception:
        return False, ''


def _kv_get_history() -> list:
    """Get signature history from KV"""
    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return []

    import urllib.request
    try:
        url = f"{KV_REST_API_URL}/get/signature_history"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            result = data.get("result")
            if result:
                return json.loads(result)
            return []
    except Exception as e:
        print(f"KV get history error: {e}")
        return []


def _kv_save_history(history: list) -> bool:
    """Save history to KV"""
    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return False

    import urllib.request
    try:
        url = f"{KV_REST_API_URL}/set/signature_history"
        data = json.dumps(history).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"KV save history error: {e}")
        return False


def _get_user_role(username: str) -> str:
    """Get user role from SIGNATURE_USERS"""
    users_raw = os.environ.get('SIGNATURE_USERS', '')
    for user_str in users_raw.split(','):
        parts = user_str.strip().split(':')
        if len(parts) >= 1 and parts[0].strip().lower() == username.lower():
            return parts[3].strip().lower() if len(parts) > 3 else 'user'
    return 'user'


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        """Get signature history"""
        auth_header = self.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''

        valid, username = _verify_token(token)
        if not valid:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': 'unauthorized'
            }).encode('utf-8'))
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        history = _kv_get_history()

        response = {
            'success': True,
            'count': len(history),
            'history': history
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

    def do_DELETE(self):
        """Delete a history entry (admin only)"""
        import urllib.parse

        auth_header = self.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''

        valid, username = _verify_token(token)
        if not valid:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': 'unauthorized'
            }).encode('utf-8'))
            return

        # Check if admin
        role = _get_user_role(username)
        if role != 'admin':
            self.send_response(403)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': 'admin_only'
            }).encode('utf-8'))
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Get entry id from query string
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        entry_id = params.get('id', [''])[0]

        if not entry_id:
            self.wfile.write(json.dumps({
                'success': False,
                'error': 'Missing entry id'
            }).encode('utf-8'))
            return

        # Remove from history
        history = _kv_get_history()
        history = [h for h in history if h.get('id') != entry_id]
        success = _kv_save_history(history)

        self.wfile.write(json.dumps({
            'success': success,
            'message': 'تم حذف السجل' if success else 'فشل في الحذف'
        }, ensure_ascii=False).encode('utf-8'))
