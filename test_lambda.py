import sys
import os

os.environ['NETLIFY'] = 'true'

try:
    from functions.app import handler
    
    event = {
        'path': '/api/admin/login',
        'httpMethod': 'POST',
        'headers': {'Content-Type': 'application/json'},
        'body': '{"email": "a.sekkaki@edu.umi.ac.ma", "password": "admin"}'
    }
    context = {}
    
    res = handler(event, context)
    print("RESPONSE:", res)
    
except Exception as e:
    import traceback
    traceback.print_exc()
