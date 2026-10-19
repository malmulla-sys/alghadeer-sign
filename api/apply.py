"""
صفحة «تقديم طلب» العامة (/apply) — 2026-10-19.

المتقدّم: init (البيانات + قائمة الملفات) ⟵ chunk لكل جزء ⟵ done.
كمبيوتر المكتب (بمفتاح البوت): list ⟵ get لكل جزء ⟵ del بعد الحفظ محلياً.
لا يبقى شيء في السحابة بعد السحب؛ وما لم يكتمل رفعه يسقط وحده بعد 7 أيام.
"""
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')

TTL = 7 * 86400
MAX_FILES = 20
MAX_TOTAL = 16 * 1024 * 1024          # بعد ضغط الصور في المتصفح
MAX_CHUNK_B64 = 1_000_000
MAX_CHUNKS = 40
PER_IP_HOUR = 6
PER_DAY = 300
_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _kv(*cmd):
    import urllib.request
    req = urllib.request.Request(KV_REST_API_URL, data=json.dumps([str(c) for c in cmd]).encode(), method='POST')
    req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode()).get('result')


def _riyadh():
    return datetime.now(timezone.utc) + timedelta(hours=3)


def _meta(rid):
    if not re.fullmatch(r'[0-9a-f]{16}', rid or ''):
        return None
    raw = _kv('GET', f'apply:m:{rid}')
    return json.loads(raw) if raw else None


def _clean(s, n):
    return re.sub(r'\s+', ' ', str(s or '')).strip()[:n]


class handler(BaseHTTPRequestHandler):
    def _out(self, code, obj):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def _bot(self):
        h = self.headers.get('Authorization', '')
        return h.startswith('Bearer ') and secrets.compare_digest(h[7:], BOT_API_KEY)

    def _ip(self):
        return (self.headers.get('x-forwarded-for', '') or self.headers.get('x-real-ip', '') or '?').split(',')[0].strip()

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        if n > 1_500_000:
            return None
        try:
            return json.loads(self.rfile.read(n).decode('utf-8') or '{}')
        except Exception:
            return None

    # ───────── المكتب ─────────
    def do_GET(self):
        try:
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if not self._bot():
                return self._out(401, {'ok': False})
            a = q.get('a')
            if a == 'list':
                out = []
                for rid in (_kv('LRANGE', 'apply:q', 0, -1) or []):
                    m = _meta(rid)
                    if m and m.get('status') == 'ready':
                        m.pop('token', None)
                        out.append(m)
                    elif not m:
                        _kv('LREM', 'apply:q', 0, rid)
                return self._out(200, {'ok': True, 'items': out})
            if a == 'get':
                d = _kv('GET', f"apply:c:{q.get('id')}:{int(q.get('f', 0))}:{int(q.get('i', 0))}")
                return self._out(200 if d else 404, {'ok': bool(d), 'data': d or ''})
            return self._out(400, {'ok': False})
        except Exception as e:
            return self._out(500, {'ok': False, 'error': str(e)[:200]})

    def do_POST(self):
        try:
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            a = q.get('a')
            b = self._body()
            if b is None:
                return self._out(413, {'ok': False, 'error': 'big'})
            if a == 'init':
                return self._init(b)
            if a == 'chunk':
                return self._chunk(b)
            if a == 'done':
                return self._done(b)
            if a == 'del':
                if not self._bot():
                    return self._out(401, {'ok': False})
                rid = b.get('id', '')
                m = _meta(rid)
                if m:
                    keys = [f'apply:c:{rid}:{fi}:{i}' for fi, f in enumerate(m['files']) for i in range(f['chunks'])]
                    if keys:
                        _kv('DEL', *keys)
                    _kv('DEL', f'apply:m:{rid}')
                _kv('LREM', 'apply:q', 0, rid)
                return self._out(200, {'ok': True})
            return self._out(400, {'ok': False})
        except Exception as e:
            return self._out(500, {'ok': False, 'error': str(e)[:200]})

    # ───────── المتقدّم ─────────
    def _init(self, b):
        if b.get('website'):                       # حقل خفي — لا يملؤه إلا الروبوت
            return self._out(200, {'ok': True, 'id': '0' * 16, 'token': 'x'})
        name = _clean(b.get('name'), 80)
        phone = re.sub(r'\D', '', str(b.get('phone') or '').translate(_AR))
        if phone.startswith('9665') and len(phone) == 12:
            phone = '0' + phone[3:]
        city = _clean(b.get('city'), 40)
        subject = _clean(b.get('subject'), 80)
        files = b.get('files') or []
        if len(name.split(' ')) < 3:
            return self._out(400, {'ok': False, 'error': 'اكتب الاسم رباعياً'})
        if not re.fullmatch(r'05\d{8}', phone):
            return self._out(400, {'ok': False, 'error': 'رقم الجوال غير صحيح'})
        if len(city) < 2 or len(subject) < 3:
            return self._out(400, {'ok': False, 'error': 'أكمل الحقول المطلوبة'})
        if not files or len(files) > MAX_FILES:
            return self._out(400, {'ok': False, 'error': 'أرفق المستندات'})
        clean = []
        total = chunks = 0
        for f in files:
            size, n = int(f.get('size') or 0), int(f.get('chunks') or 0)
            typ = str(f.get('type') or '')
            if typ not in ('application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif') or n < 1:
                return self._out(400, {'ok': False, 'error': 'نوع ملف غير مقبول'})
            total += size
            chunks += n
            clean.append({'name': _clean(f.get('name'), 80) or 'file', 'type': typ, 'size': size, 'chunks': n})
        if total > MAX_TOTAL or chunks > MAX_CHUNKS:
            return self._out(400, {'ok': False, 'error': 'حجم المستندات كبير'})
        now = _riyadh()
        hour_key = f"apply:rl:{self._ip()}:{now:%Y%m%d%H}"
        if int(_kv('INCR', hour_key) or 0) > PER_IP_HOUR:
            return self._out(429, {'ok': False, 'error': 'محاولات كثيرة، حاول لاحقاً'})
        _kv('EXPIRE', hour_key, 3600)
        day_key = f"apply:day:{now:%Y%m%d}"
        if int(_kv('INCR', day_key) or 0) > PER_DAY:
            return self._out(429, {'ok': False, 'error': 'حاول لاحقاً'})
        _kv('EXPIRE', day_key, 90000)
        rid, token = secrets.token_hex(8), secrets.token_urlsafe(18)
        meta = {'id': rid, 'token': token, 'status': 'uploading', 'name': name, 'phone': phone, 'city': city,
                'subject': subject, 'files': clean, 'created': now.strftime('%Y-%m-%d %H:%M:%S'), 'ts': int(time.time())}
        _kv('SET', f'apply:m:{rid}', json.dumps(meta, ensure_ascii=False), 'EX', TTL)
        return self._out(200, {'ok': True, 'id': rid, 'token': token})

    def _auth_up(self, b):
        m = _meta(b.get('id', ''))
        if not m or m.get('status') != 'uploading' or not secrets.compare_digest(str(b.get('token', '')), m['token']):
            return None
        return m

    def _chunk(self, b):
        m = self._auth_up(b)
        if not m:
            return self._out(403, {'ok': False})
        fi, i, data = int(b.get('f', -1)), int(b.get('i', -1)), str(b.get('data') or '')
        if not (0 <= fi < len(m['files']) and 0 <= i < m['files'][fi]['chunks']) or not data or len(data) > MAX_CHUNK_B64:
            return self._out(400, {'ok': False})
        _kv('SET', f"apply:c:{m['id']}:{fi}:{i}", data, 'EX', TTL)
        return self._out(200, {'ok': True})

    def _done(self, b):
        m = self._auth_up(b)
        if not m:
            return self._out(403, {'ok': False})
        keys = [f"apply:c:{m['id']}:{fi}:{i}" for fi, f in enumerate(m['files']) for i in range(f['chunks'])]
        if int(_kv('EXISTS', *keys) or 0) != len(keys):
            return self._out(400, {'ok': False, 'error': 'لم يكتمل رفع المستندات'})
        m['status'] = 'ready'
        m['submitted'] = _riyadh().strftime('%Y-%m-%d %H:%M:%S')
        _kv('SET', f"apply:m:{m['id']}", json.dumps(m, ensure_ascii=False), 'EX', TTL)
        _kv('RPUSH', 'apply:q', m['id'])
        return self._out(200, {'ok': True, 'date': m['submitted'][:10]})
