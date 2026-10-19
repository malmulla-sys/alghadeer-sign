"""
كل عنوان لا يطابق أي مسار (كان يعطي 404 من Vercel) — 2026-10-19.
يُسجَّل في KV (apply:miss، آخر 50) لمعرفة العنوان الذي تطلبه أجهزة أندرويد،
ثم يُحوَّل الزائر إلى صفحة التقديم.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')


def _kv(*cmd):
    import urllib.request
    req = urllib.request.Request(KV_REST_API_URL, data=json.dumps([str(c) for c in cmd]).encode(), method='POST')
    req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode()).get('result')


class handler(BaseHTTPRequestHandler):
    def _go(self):
        h = {k.lower(): v for k, v in self.headers.items()}
        orig = h.get('x-vercel-original-path') or h.get('x-matched-path') or ''
        rec = {'t': int(time.time()), 'path': self.path, 'orig': orig,
               'ua': h.get('user-agent', '')[:300], 'ref': h.get('referer', '')[:200],
               'hdrs': {k: v[:200] for k, v in h.items() if k.startswith('x-') and 'forwarded' not in k and 'ip' not in k}}
        try:
            _kv('LPUSH', 'apply:miss', json.dumps(rec, ensure_ascii=False))
            _kv('LTRIM', 'apply:miss', 0, 49)
        except Exception as e:
            print(f"miss log: {e}")
        if 'r=1' in self.path:
            body = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<p style="font-family:Tahoma;padding:24px;font-size:18px" dir="rtl">تعذّر فتح الصفحة. '
                    '<a href="/apply">اضغط هنا للمحاولة</a></p><p style="font:12px monospace;padding:0 24px;color:#666">'
                    + quote(self.path)[:300] + '</p>').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(302)
        self.send_header('Location', '/apply?r=1')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def do_GET(self):
        self._go()

    def do_HEAD(self):
        self._go()
