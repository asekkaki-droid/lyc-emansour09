import sys
import os

# Add the project root to the sys.path so server can be imported
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, root_dir)

from server.app import app

# Vercel serverless functions require the handler to be named 'app'.
