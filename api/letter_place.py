"""
API endpoint receiving where the user dropped the signature on the letter
preview (place_signature.html). Stores the placement in KV and notifies the
bot via a normal Telegram message with an inline button (same pattern as
api/sign.py) so the local bot's existing callback handler picks it up —
no polling needed.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '')


def _kv_set(key: str, value: dict) -> bool:
    if not KV_REST_API_URL or not KV_REST_API_TOKEN:
        return False
    import urllib.request
    try:
        url = f"{KV_REST_API_URL}/set/{key}"
        data = json.dumps(value).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"KV set error: {e}")
        return False


def _notify_bot(request_id: str) -> None:
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    import urllib.request
    try:
        message = "📍 تم تحديد موضع التوقيع على الخطاب"
        inline_keyboard = {
            "inline_keyboard": [[
                {"text": "✅ تطبيق الموضع", "callback_data": f"letter_place_done:{request_id}"}
            ]]
        }
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            'chat_id': ADMIN_CHAT_ID,
            'text': message,
            'reply_markup': inline_keyboard,
        })
        req = urllib.request.Request(url, data=payload.encode('utf-8'))
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Failed to notify bot: {e}")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            request_id = data.get('id', '')
            placements = data.get('placements')  # قائمة، فهرسها = رقم الصفحة (0-based)، عنصر null = بلا توقيع

            if not request_id or placements is None:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Missing fields'}).encode())
                return

            ok = _kv_set(f"letter_place:{request_id}", {
                'placements': placements,
                'placed_at': int(time.time()),
            })

            if ok:
                _notify_bot(request_id)

            self.send_response(200 if ok else 500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': ok}).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
