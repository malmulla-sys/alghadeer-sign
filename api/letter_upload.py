"""
API endpoint for the bot to upload a letter preview image (base64) for the
drag-to-place signature page. Bot-authenticated only (same key as api/requests.py).
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')


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


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_POST(self):
        try:
            auth_header = self.headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
            if token != BOT_API_KEY:
                self.send_response(401)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'unauthorized'}).encode())
                return

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            request_id = data.get('id', '')
            image_base64 = data.get('image_base64', '')
            page_index = data.get('page_index', 0)
            page_count = data.get('page_count', 1)
            if not request_id or not image_base64:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Missing id or image_base64'}).encode())
                return

            # كل صفحة تُخزَّن في مفتاح منفصل لتفادي تجاوز حد حجم القيمة الواحدة في KV
            ok = _kv_set(f"letter_img:{request_id}:{page_index}", {
                'image_base64': image_base64,
                'page_count': page_count,
                'created_at': int(time.time()),
            })

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
