"""
مراجعة كشف إهداءات التمور برابط (2026-11-22).

المكتب (بمفتاح البوت): push نسخة مجموعات المراجع ⟵ رابط /dg/<token> يُرسل له.
المراجع (بالرابط وحده): load ⟵ save (مسودة تلقائية) ⟵ submit «اعتماد وإرسال».
المكتب: list المُرسَلة ⟵ يراجعها المستخدم في اللوحة ⟵ close يمحوها من السحابة (أو reopen ليعدّل المراجع ثانية).
لا يُكتب شيء في الكشف من هنا — اللوحة وحدها تطبّق ما يوافق عليه المستخدم.
"""
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KV_REST_API_URL = os.environ.get('KV_REST_API_URL', '')
KV_REST_API_TOKEN = os.environ.get('KV_REST_API_TOKEN', '')
BOT_API_KEY = os.environ.get('SIGNATURE_BOT_API_KEY', 'bot-secret-key-2026')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '')
TTL = 45 * 86400
MAX_BODY = 600_000


def _kv(*cmd):
    import urllib.request
    req = urllib.request.Request(KV_REST_API_URL, data=json.dumps([str(c) for c in cmd]).encode(), method='POST')
    req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode()).get('result')


def _now():
    return (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')


def _get(t):
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,64}', t or ''):
        return None
    raw = _kv('GET', f'dgr:{t}')
    return json.loads(raw) if raw else None


def _put(d):
    _kv('SET', f"dgr:{d['token']}", json.dumps(d, ensure_ascii=False), 'EX', TTL)


def _c(s, n):
    return re.sub(r'\s+', ' ', str(s or '')).strip()[:n]


def _changes(ch, d):
    """تنظيف ما يرسله المتصفح: حذف/تعديل لأسطر موجودة فقط، وإضافات بحقول محدودة."""
    ids = {it['id'] for s in d['sections'] for e in s['ents'] for it in e['items']}
    keys = {s['key'] for s in d['sections']}
    ch = ch if isinstance(ch, dict) else {}
    dels = sorted({int(x) for x in (ch.get('del') or []) if str(x).isdigit() and int(x) in ids})
    edit = {}
    for k, v in (ch.get('edit') or {}).items():
        if str(k).isdigit() and int(k) in ids and isinstance(v, dict):
            edit[str(int(k))] = {f: _c(v.get(f), 120) for f in ('name', 'phone', 'via', 'title') if f in v}
    add = []
    for a in (ch.get('add') or [])[:200]:
        if isinstance(a, dict) and _c(a.get('name'), 120) and a.get('section') in keys:
            add.append({'k': _c(a.get('k'), 20), 'section': a['section'], 'name': _c(a.get('name'), 120),
                        'phone': _c(a.get('phone'), 30), 'via': _c(a.get('via'), 120), 'title': _c(a.get('title'), 120)})
    return {'del': dels, 'edit': edit, 'add': add, 'note': _c(ch.get('note'), 600)}


def _notify(text):
    if not (BOT_TOKEN and ADMIN_CHAT_ID):
        return
    import urllib.request
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                     data=json.dumps({'chat_id': ADMIN_CHAT_ID, 'text': text}).encode('utf-8'))
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


class handler(BaseHTTPRequestHandler):
    def _out(self, code, obj):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Robots-Tag', 'noindex')
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def _bot(self):
        h = self.headers.get('Authorization', '')
        return h.startswith('Bearer ') and secrets.compare_digest(h[7:], BOT_API_KEY)

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        if n > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n).decode('utf-8') or '{}')
        except Exception:
            return None

    def do_GET(self):
        try:
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            a = q.get('a')
            if a == 'load':
                d = _get(q.get('t'))
                if not d:
                    return self._out(404, {'ok': False, 'error': 'الرابط غير صالح أو انتهت مدته'})
                d.pop('token', None)
                for s in d.get('sections', []):          # الكمية لا تُعرض للمراجع (طلب المستخدم)
                    for e in s.get('ents', []):
                        for it in e.get('items', []):
                            it.pop('qty', None)
                return self._out(200, {'ok': True, 'data': d})
            if not self._bot():
                return self._out(401, {'ok': False})
            if a == 'list':
                out = []
                for t in (_kv('LRANGE', 'dgr:q', 0, -1) or []):
                    d = _get(t)
                    if d and d.get('status') == 'submitted':
                        out.append({'token': t, 'year': d['year'], 'reviewer': d['reviewer'],
                                    'submitted_at': d.get('submitted_at'), 'changes': d.get('changes') or {}})
                    elif not d:
                        _kv('LREM', 'dgr:q', 0, t)
                return self._out(200, {'ok': True, 'items': out})
            if a == 'status':
                d = _get(q.get('t'))
                return self._out(200, {'ok': True, 'status': d['status'] if d else 'gone',
                                       'saved_at': (d or {}).get('saved_at')})
            return self._out(400, {'ok': False})
        except Exception as e:
            return self._out(500, {'ok': False, 'error': str(e)[:200]})

    def do_POST(self):
        try:
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            a = q.get('a')
            b = self._body()
            if b is None:
                return self._out(413, {'ok': False, 'error': 'كبير'})
            if a in ('save', 'submit'):
                d = _get(b.get('t'))
                if not d:
                    return self._out(404, {'ok': False, 'error': 'الرابط غير صالح أو انتهت مدته'})
                if d.get('status') != 'open':
                    return self._out(409, {'ok': False, 'error': 'أُرسلت المراجعة — لا تعديل بعد الإرسال'})
                d['changes'] = _changes(b.get('changes'), d)
                d['saved_at'] = _now()
                if a == 'submit':
                    d['status'] = 'submitted'
                    d['submitted_at'] = d['saved_at']
                    _put(d)
                    _kv('LREM', 'dgr:q', 0, d['token'])
                    _kv('RPUSH', 'dgr:q', d['token'])
                    c = d['changes']
                    _notify(f"🌴 {d['reviewer']} أرسل مراجعة كشف التمور {d['year']}: "
                            f"حذف {len(c['del'])} · إضافة {len(c['add'])} · تعديل {len(c['edit'])} — راجعها في صفحة إهداءات التمور.")
                    return self._out(200, {'ok': True, 'submitted_at': d['submitted_at']})
                _put(d)
                return self._out(200, {'ok': True, 'saved_at': d['saved_at']})
            if not self._bot():
                return self._out(401, {'ok': False})
            if a == 'push':
                d = b.get('data') or {}
                if not d.get('sections'):
                    return self._out(400, {'ok': False})
                old = _get(b.get('token')) if b.get('token') else None
                d['token'] = old['token'] if old else secrets.token_urlsafe(18)
                d['status'] = 'open'
                d['changes'] = (old or {}).get('changes') if old and old.get('status') == 'open' else None
                d['created'] = (old or {}).get('created') or _now()
                if d['changes']:
                    d['changes'] = _changes(d['changes'], d)
                _put(d)
                return self._out(200, {'ok': True, 'token': d['token']})
            if a == 'reopen':
                d = _get(b.get('t'))
                if not d:
                    return self._out(404, {'ok': False})
                d['status'] = 'open'
                _put(d)
                _kv('LREM', 'dgr:q', 0, d['token'])
                return self._out(200, {'ok': True})
            if a == 'close':
                t = b.get('t', '')
                if re.fullmatch(r'[A-Za-z0-9_-]{20,64}', t):
                    _kv('DEL', f'dgr:{t}')
                    _kv('LREM', 'dgr:q', 0, t)
                return self._out(200, {'ok': True})
            return self._out(400, {'ok': False})
        except Exception as e:
            return self._out(500, {'ok': False, 'error': str(e)[:200]})
