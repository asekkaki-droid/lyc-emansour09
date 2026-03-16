import sys
import os

# 1. Fix Pathing: Add project root and server directory
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
server_dir = os.path.join(root_dir, 'server')
sys.path.insert(0, root_dir)
sys.path.insert(0, server_dir)

try:
    # 2. Resilient Import
    try:
        from server.app import app
    except ImportError:
        from app import app
        
    import serverless_wsgi
except Exception as e:
    from flask import Flask, jsonify
    app = Flask(__name__)
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def catch_all(path):
        return jsonify({"status": "error", "message": "Import Error", "details": str(e), "sys_path": sys.path}), 500

# 3. Handle Request
def handler(event, context):
    # Strip Netlify prefix so Flask router sees exactly '/api/...'
    if 'path' in event:
        if event['path'].startswith('/.netlify/functions/app'):
            event['path'] = event['path'].replace('/.netlify/functions/app', '', 1)
            if not event['path']:
                event['path'] = '/'
                
    return serverless_wsgi.handle_request(app, event, context)
