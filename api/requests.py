"""
API endpoint to manage pending signature requests
Vercel Serverless Function with KV storage
"""
import json
import os
import hashlib
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import urllib.parse

# Vercel KV (Upstash Redis) credentials
KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')

# Bot API key for adding requests
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')


def _verify_token(token: str) -> tuple[bool, str]:
    """التحقق من صحة الـ token"""
    if not token:
        return False, ''

    # إذا كان المفتاح هو مفتاح البوت، السماح
    if token == BOT_API_KEY:
        return True, 'bot'

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

# In-memory fallback for local testing (will reset on each deploy)
_local_requests = {}


def _kv_available() -> bool:
    return bool(KV_REST_API_URL and KV_REST_API_TOKEN)


def _kv_get_all() -> list:
    """Get all pending requests from Vercel KV"""
    if not _kv_available():
        return list(_local_requests.values())

    import urllib.request
    try:
        url = f"{KV_REST_API_URL}/get/signature_requests"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            result = data.get("result")
            if result:
                return json.loads(result)
            return []
    except Exception as e:
        print(f"KV get error: {e}")
        return []


def _kv_save_all(requests: list) -> bool:
    """Save all requests to Vercel KV"""
    if not _kv_available():
        _local_requests.clear()
        for r in requests:
            _local_requests[r['id']] = r
        return True

    import urllib.request
    try:
        url = f"{KV_REST_API_URL}/set/signature_requests"
        data = json.dumps(requests).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"KV save error: {e}")
        return False


def _add_request(request_data: dict) -> bool:
    """Add a new signature request"""
    requests = _kv_get_all()

    # Remove if already exists (same id)
    requests = [r for r in requests if r.get('id') != request_data.get('id')]

    # Add new request
    request_data['created_at'] = datetime.now().isoformat()
    requests.append(request_data)

    return _kv_save_all(requests)


def _remove_request(request_id: str) -> bool:
    """Remove a request after signing"""
    requests = _kv_get_all()
    requests = [r for r in requests if r.get('id') != request_id]
    return _kv_save_all(requests)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Get all pending signature requests"""
        # التحقق من التفويض
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

        requests = _kv_get_all()

        # Sort by created_at descending (newest first)
        requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        response = {
            'success': True,
            'count': len(requests),
            'requests': requests
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

    def do_POST(self):
        """Add a new signature request"""
        try:
            # التحقق من التفويض (البوت فقط يمكنه الإضافة)
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

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            # Validate required fields
            required = ['id', 'beneficiary_name', 'amount']
            for field in required:
                if field not in data:
                    self.wfile.write(json.dumps({
                        'success': False,
                        'error': f'Missing field: {field}'
                    }).encode())
                    return

            success = _add_request(data)

            self.wfile.write(json.dumps({
                'success': success,
                'message': 'تم إضافة الطلب' if success else 'فشل في الإضافة'
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())

    def do_DELETE(self):
        """Remove a request after signing"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            # Get request_id from query string
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            request_id = params.get('id', [''])[0]

            if not request_id:
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Missing request id'
                }).encode())
                return

            success = _remove_request(request_id)

            self.wfile.write(json.dumps({
                'success': success,
                'message': 'تم حذف الطلب' if success else 'فشل في الحذف'
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
