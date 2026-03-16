import sys
import os

# إضافة المسار الرئيسي للمشروع حتى يتمكن Python من العثور على مجلد server
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, root_dir)

# استيراد تطبيق Flask الأساسي ليعمل مع Vercel
from server.app import app
