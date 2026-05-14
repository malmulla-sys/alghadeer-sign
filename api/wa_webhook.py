"""
wa_webhook.py - WhatsApp Auto-Reply Webhook
"""
import os
import json
from http.server import BaseHTTPRequestHandler

try:
    from urllib.request import urlopen, Request
except ImportError:
    urlopen = None
    Request = None

GREEN_API_INSTANCE_ID = os.environ.get("GREEN_API_INSTANCE_ID", "")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "")

AUTO_REPLY = "مرحباً بك 👋\n\nشكراً لتواصلك معنا.\nسيتم الرد عليك في أقرب وقت ممكن.\n\n— شركة الغدير"

EXCLUDED = ["966530364878", "966560454000"]
replied = set()


def normalize(phone):
    p = str(phone).replace("@c.us", "").replace("+", "").replace(" ", "").replace("-", "")
    return "966" + p[1:] if p.startswith("0") else p


def reply(phone, msg):
    if not GREEN_API_INSTANCE_ID or not GREEN_API_TOKEN or not urlopen:
        return False
    url = f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE_ID}/sendMessage/{GREEN_API_TOKEN}"
    data = json.dumps({"chatId": f"{normalize(phone)}@c.us", "message": msg}).encode()
    try:
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r:
            return r.status == 200
    except:
        return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "configured": bool(GREEN_API_INSTANCE_ID and GREEN_API_TOKEN)
        }).encode())

    def do_POST(self):
        global replied
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.loads(body.decode())

            if data.get("typeWebhook") == "incomingMessageReceived":
                phone = normalize(data.get("senderData", {}).get("sender", ""))
                if phone and phone not in EXCLUDED and phone not in replied:
                    if reply(phone, AUTO_REPLY):
                        replied.add(phone)
                        if len(replied) > 100:
                            replied = set(list(replied)[-50:])
        except:
            pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
