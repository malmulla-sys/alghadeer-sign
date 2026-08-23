"""
API endpoint for the signing page to check an OTP code the beneficiary typed in.
Public (called from the browser) — protected by the code itself plus a small
attempt cap to blunt brute-forcing within the code's lifetime. Does NOT delete
the code on success: api/sign.py performs the authoritative check-and-consume
at actual signature submission, so this endpoint is a UX gate only.
"""
import json
import os
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')
MAX_ATTEMPTS = 5


def _kv_get(key: str):
    url = f"{KV_REST_API_URL}/get/{key}"
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        result = data.get('result')
        return json.loads(result) if result else None


def _kv_set_keep_ttl(key: str, value: dict):
    """يحدّث القيمة بدون تحديد EX جديد — Upstash يحافظ على TTL الحالي عند تحديث نفس المفتاح
    بدون تمرير KEEPTTL صراحة فقط لو ما مررنا EX؛ للتبسيط هنا نمرر XX (يحدّث فقط لو موجود)."""
    url = f"{KV_REST_API_URL}/set/{key}?XX=true&KEEPTTL=true"
    payload = json.dumps(value).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='POST')
    req.add_header('Authorization', f'Bearer {KV_REST_API_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError:
        pass


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

            otp_id = str(data.get('id', '')).strip()
            submitted_code = str(data.get('code', '')).strip()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            if not otp_id or not submitted_code:
                self.wfile.write(json.dumps({'success': False, 'error': 'missing_fields'}).encode('utf-8'))
                return

            if not KV_REST_API_URL or not KV_REST_API_TOKEN:
                self.wfile.write(json.dumps({'success': False, 'error': 'kv_not_configured'}).encode('utf-8'))
                return

            record = _kv_get(f'otp:{otp_id}')
            if not record:
                self.wfile.write(json.dumps({'success': False, 'error': 'expired'}).encode('utf-8'))
                return

            attempts = int(record.get('attempts', 0))
            if attempts >= MAX_ATTEMPTS:
                self.wfile.write(json.dumps({'success': False, 'error': 'too_many_attempts'}).encode('utf-8'))
                return

            if submitted_code == record.get('code'):
                self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
                return

            record['attempts'] = attempts + 1
            _kv_set_keep_ttl(f'otp:{otp_id}', record)
            self.wfile.write(json.dumps({'success': False, 'error': 'wrong_code'}).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
