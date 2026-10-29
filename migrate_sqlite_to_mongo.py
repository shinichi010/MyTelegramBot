"""
نقل بيانات البوت من SQLite (bot_data.db) إلى MongoDB — مرة وحدة.

الاستخدام:
    pip install pymongo
    # Windows (CMD):         set MONGO_URI=mongodb+srv://user:pass@cluster/...
    # Windows (PowerShell):  $env:MONGO_URI="mongodb+srv://user:pass@cluster/..."
    # Linux/Mac:             export MONGO_URI="mongodb+srv://user:pass@cluster/..."
    python migrate_sqlite_to_mongo.py [مسار/bot_data.db]

ملاحظة: سجل الرسائل القديم (messages/...) ما ينتقل، لأن البوت صار يحفظ الرسائل مؤقتاً بشكل مستقل.
"""
import os, sys, sqlite3
from pymongo import MongoClient

uri = os.environ.get('MONGO_URI', '').strip()
if not uri:
    sys.exit("❌ المتغير MONGO_URI غير مضبوط.")
db_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('DB_PATH', 'bot_data.db')
if not os.path.exists(db_path):
    sys.exit(f"❌ الملف غير موجود: {db_path}")

client = MongoClient(uri, serverSelectionTimeoutMS=8000)
client.admin.command('ping')
col = client[os.environ.get('MONGO_DB', 'sikbot')]['kv']

moved = skipped = 0
with sqlite3.connect(db_path) as c:
    for path, value in c.execute('SELECT path, value FROM kv'):
        if path.startswith('messages/'):
            skipped += 1
            continue
        col.replace_one({'_id': path}, {'_id': path, 'value': value}, upsert=True)
        moved += 1
print(f"✅ انتقل {moved} سجل إلى MongoDB (تخطيت {skipped} من سجل الرسائل القديم).")
