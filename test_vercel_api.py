import sys
import os

os.environ['VERCEL'] = '1'

from api.index import app

if __name__ == '__main__':
    with app.test_client() as client:
        print("Testing /api/admin/login")
        response = client.post('/api/admin/login', json={
            'email': 'a.sekkaki@edu.umi.ac.ma',
            'password': 'admin'
        })
        print("Status:", response.status_code)
        
        try:
            print("Response:", response.get_json())
        except:
            print("Response Data:", response.data.decode('utf-8'))
