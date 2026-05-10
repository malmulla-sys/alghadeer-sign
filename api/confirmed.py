"""
API endpoint to get and clear confirmed signatures
"""
import json
import os
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def _verify_auth(self) -> bool:
        auth_header = self.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
        return token == BOT_API_KEY

    def do_GET(self):
        """Get all confirmed signatures"""
        if not self._verify_auth():
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': 'unauthorized'}).encode())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        signatures = self._get_confirmed()
        self.wfile.write(json.dumps({
            'success': True,
            'count': len(signatures),
            'signatures': signatures
        }, ensure_ascii=False).encode('utf-8'))

    def do_DELETE(self):
        """Clear all confirmed signatures (after bot processes them)"""
        if not self._verify_auth():
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': 'unauthorized'}).encode())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Get IDs to delete from query string
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        ids_to_delete = params.get('ids', [''])[0].split(',') if params.get('ids') else []

        if ids_to_delete and ids_to_delete[0]:
            # Delete specific IDs
            signatures = self._get_confirmed()
            signatures = [s for s in signatures if s.get('id') not in ids_to_delete and s.get('national_id') not in ids_to_delete]
            self._save_confirmed(signatures)
            self.wfile.write(json.dumps({
                'success': True,
                'message': f'تم حذف {len(ids_to_delete)} توقيع'
            }, ensure_ascii=False).encode('utf-8'))
        else:
            # Clear all
            self._save_confirmed([])
            self.wfile.write(json.dumps({
                'success': True,
                'message': 'تم مسح جميع التوقيعات المؤكدة'
            }, ensure_ascii=False).encode('utf-8'))

    def _get_confirmed(self) -> list:
        if not KV_REST_API_URL or not KV_REST_API_TOKEN:
            return []
        try:
            url = f"{KV_REST_API_URL}/get/confirmed_signatures"
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                result = data.get("result")
                return json.loads(result) if result else []
        except:
            return []

    def _save_confirmed(self, signatures: list) -> bool:
        if not KV_REST_API_URL or not KV_REST_API_TOKEN:
            return False
        try:
            url = f"{KV_REST_API_URL}/set/confirmed_signatures"
            data = json.dumps(signatures).encode()
            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req, timeout=5)
            return True
        except:
            return False
