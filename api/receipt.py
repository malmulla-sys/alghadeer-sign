"""
API endpoint to get receipt data
Vercel Serverless Function
"""
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler

# For demo - in production, connect to real database
DEMO_RECEIPTS = {
    'TEST001': {
        'id': 'TEST001',
        'receipt_no': '2026-0001',
        'beneficiary_name': 'محمد أحمد العلي',
        'national_id': '1234567890',
        'amount': '2,500',
        'subject': 'مساعدة شهر رمضان',
        'date': '2026-05-05',
        'status': 'pending'
    }
}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Get receipt data by ID"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Parse query parameters
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        receipt_id = params.get('id', [''])[0]

        if not receipt_id:
            response = {'error': 'معرف السند مطلوب'}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return

        # Check demo receipts first
        if receipt_id in DEMO_RECEIPTS:
            receipt = DEMO_RECEIPTS[receipt_id]
            self.wfile.write(json.dumps(receipt, ensure_ascii=False).encode('utf-8'))
            return

        # In production: query database
        # For now, try to parse receipt_id as database lookup
        try:
            # This would be replaced with actual DB query
            # from your bot's database
            response = {'error': 'السند غير موجود'}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            response = {'error': str(e)}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

    def do_POST(self):
        """Create a new receipt for signing"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            # Validate required fields
            required = ['receipt_no', 'beneficiary_name', 'national_id', 'amount', 'subject']
            for field in required:
                if field not in data:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': f'Missing field: {field}'}).encode())
                    return

            # Generate unique ID
            import hashlib
            import time
            unique_id = hashlib.md5(f"{data['receipt_no']}{time.time()}".encode()).hexdigest()[:8].upper()

            # Store receipt (in production, save to database)
            receipt = {
                'id': unique_id,
                **data,
                'status': 'pending',
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }

            # Add to demo storage
            DEMO_RECEIPTS[unique_id] = receipt

            self.send_response(201)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            response = {
                'success': True,
                'receipt_id': unique_id,
                'sign_url': f"/sign/{unique_id}",
                'message': 'تم إنشاء السند بنجاح'
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
