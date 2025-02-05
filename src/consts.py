import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODE_DEBUG = os.getenv('DEBUG', '0') == '1'
