"""
API endpoint to check environment variables status (without revealing values)
"""
import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Check environment variables (show if set, not the values)
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        admin_chat_id = os.environ.get('ADMIN_CHAT_ID', '')
        kv_url = os.environ.get('KV_REST_API_URL', '')
        kv_token = os.environ.get('KV_REST_API_TOKEN', '')
        bot_api_key = os.environ.get('SIGNATURE_BOT_API_KEY', '')
        sig_users = os.environ.get('SIGNATURE_USERS', '')

        # Parse users to show count and names (not passwords)
        users_info = '⚠️ يستخدم الافتراضي'
        if sig_users:
            try:
                user_list = []
                for u in sig_users.split(','):
                    parts = u.strip().split(':')
                    if len(parts) >= 1:
                        user_list.append(parts[0])
                users_info = f'✅ {len(user_list)} مستخدم: {", ".join(user_list)}'
            except:
                users_info = '❌ خطأ في الصيغة'

        status = {
            'TELEGRAM_BOT_TOKEN': '✅ مضبوط' if bot_token else '❌ غير مضبوط',
            'ADMIN_CHAT_ID': '✅ مضبوط' if admin_chat_id else '❌ غير مضبوط',
            'KV_REST_API_URL': '✅ مضبوط' if kv_url else '❌ غير مضبوط',
            'KV_REST_API_TOKEN': '✅ مضبوط' if kv_token else '❌ غير مضبوط',
            'SIGNATURE_BOT_API_KEY': '✅ مضبوط' if bot_api_key else '⚠️ يستخدم الافتراضي',
            'SIGNATURE_USERS': users_info,
        }

        # Check if critical vars are set
        all_critical_set = bool(bot_token and admin_chat_id)

        response = {
            'success': True,
            'env_status': status,
            'ready_for_signatures': all_critical_set,
            'message': 'جميع الإعدادات الأساسية مضبوطة ✅' if all_critical_set else '⚠️ يجب ضبط TELEGRAM_BOT_TOKEN و ADMIN_CHAT_ID'
        }

        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
