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





# ── السندات الخاصة 🔒: لا تظهر إلا للمدير (role=admin) — مفتاح KV مستقل يبقى بعد التوقيع ──
PRIVATE_KEY = 'private_sig_ids'


def _get_user_role(username: str) -> str:
    """المدير (حذف + الموقّعة + الخاص) = SIGNATURE_ADMIN_USERS فقط (الافتراضي m.almulla)، أياً كان
    الدور المكتوب في SIGNATURE_USERS — bilal كان «مدير» هناك فرأى الخاص والموقّعة (2026-10-13)."""
    if username == 'bot':
        return 'admin'
    admins = {u.strip().lower() for u in os.environ.get('SIGNATURE_ADMIN_USERS', 'm.almulla').split(',') if u.strip()}
    return 'admin' if (username or '').lower() in admins else 'user'


def _can_see_private(username: str) -> bool:
    return _get_user_role(username) == 'admin'


def _kv_cmd(path: str, body=None):
    import urllib.request
    url = f"{KV_REST_API_URL}/{path}"
    req = urllib.request.Request(url, data=body, method='POST' if body is not None else 'GET')
    req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode()).get("result")


def _private_ids() -> set:
    if not (KV_REST_API_URL and KV_REST_API_TOKEN):
        return set()
    try:
        raw = _kv_cmd(f"get/{PRIVATE_KEY}")
        return set(str(x) for x in (json.loads(raw) if raw else []))
    except Exception as e:
        print(f"KV private get error: {e}")
        return set()


def _save_private_ids(ids: set) -> bool:
    if not (KV_REST_API_URL and KV_REST_API_TOKEN):
        return False
    try:
        _kv_cmd(f"set/{PRIVATE_KEY}", json.dumps(sorted(ids)).encode())
        return True
    except Exception as e:
        print(f"KV private save error: {e}")
        return False


def _visible(items: list, username: str) -> list:
    """يعلّم الخاص بـ private=True، ويحذفه من القائمة لغير المدير."""
    priv = _private_ids()
    for it in items:
        if str(it.get('id')) in priv:
            it['private'] = True
    if _can_see_private(username):
        return items
    return [it for it in items if not it.get('private')]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_POST(self):
        """Add entry to history (bot only)"""
        auth_header = self.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''

        valid, username = _verify_token(token)
        if not valid or username != 'bot':
            self.send_response(401)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': 'unauthorized - bot only'
            }).encode('utf-8'))
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            entry = json.loads(body.decode('utf-8'))

            # Validate required fields
            if not entry.get('id') or not entry.get('beneficiary_name'):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Missing required fields'
                }).encode('utf-8'))
                return

            # Get current history
            history = _kv_get_history()

            # Check if already exists
            if str(entry.get('id')) in [str(h.get('id')) for h in history]:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': 'Already exists'
                }).encode('utf-8'))
                return

            # Add to beginning
            history.insert(0, entry)

            # Keep only last 100
            history = history[:100]

            # Save
            success = _kv_save_history(history)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': success,
                'message': 'تمت الإضافة' if success else 'فشل في الإضافة'
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())

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

        if _get_user_role(username) != 'admin':                 # تبويب «الموقّعة» للمدير وحده
            self.wfile.write(json.dumps({'success': False, 'error': 'admin_only', 'history': []}).encode('utf-8'))
            return
        history = _visible(_kv_get_history(), username)

        response = {
            'success': True,
            'count': len(history),
            'history': history,
            'can_private': _can_see_private(username)
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
        if not _can_see_private(username) and str(entry_id) in _private_ids():
            self.wfile.write(json.dumps({'success': False, 'error': 'not_found'}).encode('utf-8'))
            return

        # Remove from history
        history = _kv_get_history()
        history = [h for h in history if h.get('id') != entry_id]
        success = _kv_save_history(history)

        self.wfile.write(json.dumps({
            'success': success,
            'message': 'تم حذف السجل' if success else 'فشل في الحذف'
        }, ensure_ascii=False).encode('utf-8'))
