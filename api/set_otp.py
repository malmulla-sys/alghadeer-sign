"""
API endpoint to store a one-time verification code (OTP) for a remote WhatsApp
signing link. Bot-only (requires SIGNATURE_BOT_API_KEY). The code is stored in
KV with an expiry so it self-invalidates without any cleanup job.
"""
import json
import os
from http.server import BaseHTTPRequestHandler
import urllib.request

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')


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
                self.wfile.write(json.dumps({'success': False, 'error': 'unauthorized'}).encode('utf-8'))
                return

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            otp_id = str(data.get('id', '')).strip()
            code = str(data.get('code', '')).strip()
            ttl_seconds = int(data.get('ttl_seconds', 600))

            if not otp_id or not code:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'missing id or code'}).encode('utf-8'))
                return

            if not KV_REST_API_URL or not KV_REST_API_TOKEN:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'KV not configured'}).encode('utf-8'))
                return

            payload = json.dumps({'code': code, 'attempts': 0}).encode('utf-8')
            kv_url = f"{KV_REST_API_URL}/set/otp:{otp_id}?EX={ttl_seconds}"
            kv_req = urllib.request.Request(kv_url, data=payload, method='POST')
            kv_req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
            kv_req.add_header('Content-Type', 'application/json')
            urllib.request.urlopen(kv_req, timeout=10)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
