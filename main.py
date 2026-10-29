import logging, os, asyncio, random, re, hashlib, requests, time
import tempfile, shutil, subprocess, sqlite3, json, threading, math
import datetime as _dt
from concurrent.futures import ThreadPoolExecutor
from html import escape as _esc
from urllib.parse import urlparse
from telegram import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.error import TimedOut
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from yt_dlp import YoutubeDL
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. القوائم والمحتوى
# ═══════════════════════════════════════════════════════════════════
WA3ED_LIST = [
    "عيونها السود والبيض 👀",
    " هلا بالحلو \\ ة 🌸",
    "مالي خلقك 😏",
    "اتسرسح منا وليدي 😤",
    "انا هسه مشغولة 😅",
]
KHAYROK_LIST = [
    "لو خيروك: تسافر للمستقبل لو للماضي؟ ⏳",
    "لو خيروك: تاكل بيتزا طول عمرك لو بركر؟ 🍕🍔",
    "لو خيروك: غني بلا أصدقاء، لو فقير وعندك أحباء؟ 💰",
    "لو خيروك: تقرأ أفكار الناس لو تطير؟ 🦅",
    "لو خيروك: ما تنام أبد لو ما تأكل أبد؟ 😴",
]
JOKES_LIST = [
    "شلون النملة تعدّ حياتها؟ — تحسب سنين! 🐜😂",
    "شو يقول الصفر للرقم 8؟ — حزامك ظاهر! 😄",
    "ليش الكمبيوتر بارد؟ — لأن عنده ويندوز! 🪟",
    "شو تقول السمكة لما اصطدمت بالحائط؟ — دام! 🐟",
]
# ── إعدادات المطور ──
DEVELOPER_USERNAME = "snh_1"  # يوزر المطور بدون @
_DISABLED_PLATFORMS = set()   # المنصات الموقوفة مؤقتاً

def is_dev(user) -> bool:
    """هل المستخدم هو المطور؟"""
    return (user.username or '').lower().strip('@') == DEVELOPER_USERNAME.lower()

def platform_enabled(name: str) -> bool:
    return name not in _DISABLED_PLATFORMS

async def platform_blocked(upd, name: str) -> bool:
    """True إذا المنصة موقوفة من لوحة المطور (ويرسل رسالة الصيانة)."""
    if platform_enabled(name):
        return False
    msg = upd.message
    dev = bool(msg and msg.from_user and is_dev(msg.from_user))
    await msg.reply_text(
        f"⚙️ [DEV] {name} موقوف — استخدم /admin لتفعيله." if dev
        else T('maintenance')
    )
    return True

async def send_safe(coro):
    """
    TimedOut أثناء رفع ملف غالباً يعني أن تيليقرام استلم الملف فعلاً وراح يوصله،
    فما نعتبره فشل (حتى ما تطلع رسالة خطأ والمقطع جاي).
    """
    try:
        return await coro
    except TimedOut:
        logger.warning("[send_safe] TimedOut — الملف غالباً وصل لتيليقرام")
        return None

async def send_error(ctx, chat_id, user, dev_msg: str, user_msg: str = None,
                      target_message=None, parse_mode="HTML"):
    """
    رسالة خطأ موحّدة بنوعين:
    - للمطور (@snh_1): يشوف dev_msg (تفصيلي بنوع الخطأ)
    - لبقية المستخدمين: يشوف user_msg (بسيط) وتنحذف تلقائياً بعد 30 ثانية

    target_message: إذا فيه رسالة "جاري التحميل..." موجودة، نعدّلها بدل إرسال رسالة جديدة.
    """
    is_developer = is_dev(user) if user else False
    final_text = dev_msg if is_developer else (user_msg or T('error_generic'))

    sent_msg = None
    try:
        if target_message is not None:
            try:
                await target_message.edit_text(final_text, parse_mode=parse_mode)
                sent_msg = target_message
            except Exception:
                sent_msg = await ctx.bot.send_message(chat_id, final_text, parse_mode=parse_mode)
        else:
            sent_msg = await ctx.bot.send_message(chat_id, final_text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"[send_error] failed to send: {e}")
        return

    # حذف تلقائي بعد 30 ثانية فقط لرسائل المستخدمين العاديين
    if not is_developer and sent_msg is not None:
        async def _auto_delete():
            await asyncio.sleep(30)
            try:
                await ctx.bot.delete_message(chat_id, sent_msg.message_id)
            except Exception:
                pass
        asyncio.create_task(_auto_delete())

# ── حد رفع تيليقرام للبوتات + أدوات الروابط ──
TG_MAX_BYTES = 50 * 1024 * 1024
URL_RE = re.compile(r'https?://\S+', re.I)

def find_url(text: str):
    """أول رابط حقيقي بالنص، أو None."""
    m = URL_RE.search(text or "")
    return m.group() if m else None

def host_in(url: str, *domains) -> bool:
    """هل دومين الرابط (أو أي دومين فرعي منه) من القائمة؟ — يمنع مطابقة netflix.com كـ x.com."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except Exception:
        return False
    return any(host == d or host.endswith('.' + d) for d in domains)

LANG_FLAG = {
    'ar':'🇸🇦','en':'🇬🇧','tr':'🇹🇷','fa':'🇮🇷','ru':'🇷🇺',
    'fr':'🇫🇷','de':'🇩🇪','es':'🇪🇸','hi':'🇮🇳','zh':'🇨🇳',
    'ja':'🇯🇵','ko':'🇰🇷','pt':'🇧🇷','it':'🇮🇹','uk':'🇺🇦',
}
TEXT_MAIN = "📋 <b>لوحة أوامر البوت</b>\n\nاختر القسم 👇"
TEXT_ADMIN = (
    "👑 <b>أوامر الإدارة:</b>\n"
    "• <code>رفع مالك | مدير | مميز</code> / <code>تنزيل رتبة</code>\n"
    "• <code>طرد | حظر | فك حظر | كتم | الغاء كتم</code>\n"
    "• <code>تثبيت | الغاء تثبيت</code>\n"
    "• <code>قفل الشات | فتح الشات</code>\n"
    "• <code>تحذير | الغاء تحذير | تحذيراتي</code>\n"
    "• <code>منع كلمة X | حذف كلمة X | الكلمات</code>\n"
    "• <code>منع ملصقات | منع قيف | منع مقاطع | منع صور</code>\n"
    "• <code>تفعيل ملصقات | تفعيل قيف | تفعيل مقاطع | تفعيل صور</code>\n"
    "• <code>اضافة رد X | Y</code> / <code>حذف رد X</code> / <code>قائمة الردود</code>\n"
    "• <code>الترحيب تشغيل/ايقاف</code> / <code>تعديل تشغيل/ايقاف</code>\n"
    "• <code>مسح X</code> — حذف X رسالة"
)
TEXT_FUN = (
    "🎮 <b>أوامر التسلية:</b>\n"
    "• <code>همسة</code> — همسة سرية (بالرد)\n"
    "• <code>ايدي</code> / <code>افتار</code>\n"
    "• <code>زواج | طلاق | شريكي | نسبة الحب</code>\n"
    "• <code>تحويل</code> — رد على فيديو لتحويله لصوت\n"
    "• <code>لو خيروك | ري | نكتة | نرد | عملة</code>\n"
    "• <code>اكس او</code> — لعبة إكس أو 🎮\n"
    "• <code>ترجمة [نص]</code> — ترجمة أي نص للعربي\n"
    "• <code>حساب [عملية]</code> — حاسبة رياضية"
)
TEXT_DL = (
    "📥 <b>التحميل — المواقع المدعومة:</b>\n\n"
    "🎬 يوتيوب — مقاطع وصوت\n"
    "🐦 تويتر/X — مقاطع وريلز\n"
    "🎵 تيك توك + 🇨🇳 دوين — فيديو وصور (بدون حد)\n"
    "📘 فيس بوك — مقاطع ريلز بافضل جودة\n"
    "📸 انستغرام — ريلز وبوستات* \n"
    "📌 بينترست — فيديو وصور\n"
    "🎵 ساوند كلاود — تحميل موسيقى MP3\n"
    "🎵 يوتيوب ميوزك — تحميل MP3 320kbps\n\n"
    "🎵 <b>معلومات تيك توك:</b>\n"
    "• <code>تيك @username</code>\n\n"
    "💡 أرسل الرابط مباشرة!"
)

def mk_main(): return InlineKeyboardMarkup([[
    InlineKeyboardButton("🛡️ الإدارة", callback_data="cmd_admin"),
    InlineKeyboardButton("🎮 التسلية", callback_data="cmd_fun")],
    [InlineKeyboardButton("📥 التحميل", callback_data="cmd_dl")]])
def mk_back(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data="cmd_main")]])

# ── إكس أو: الدوال المساعدة ──
_TTT_LINES = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))

def ttt_winner(board):
    """يرجع 'X' أو 'O' إذا فيه فائز، وإلا None."""
    for a, b, c in _TTT_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None

def ttt_kb(board, gid):
    """لوحة 3x3 — الخلية الفارغة ttt_{gid}_{i}، المشغولة ttt_noop، وزر إعادة."""
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            v = board[i]
            if v == 'X':
                row.append(InlineKeyboardButton("❌", callback_data="ttt_noop"))
            elif v == 'O':
                row.append(InlineKeyboardButton("⭕", callback_data="ttt_noop"))
            else:
                row.append(InlineKeyboardButton("▫️", callback_data=f"ttt_{gid}_{i}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔄 لعبة جديدة", callback_data=f"ttt_reset_{gid}")])
    return InlineKeyboardMarkup(rows)

def ttt_bot(board):
    """حركة البوت (O): يفوز إذا يكدر، يمنع فوزك، ثم الوسط، ثم عشوائي."""
    empty = [i for i, v in enumerate(board) if v == '']
    if not empty:
        return None
    for sym in ('O', 'X'):
        for i in empty:
            board[i] = sym
            won = ttt_winner(board) == sym
            board[i] = ''
            if won:
                return i
    if 4 in empty:
        return 4
    return random.choice(empty)

# ═══════════════════════════════════════════════════════════════════
# 2. قاعدة البيانات SQLite (بديل Firebase — يشتغل على Railway)
# ═══════════════════════════════════════════════════════════════════
DB_PATH = os.environ.get('DB_PATH', 'bot_data.db')
MONGO_URI = os.environ.get('MONGO_URI', '').strip()          # إذا موجود → MongoDB (دائمة)
MONGO_DB_NAME = os.environ.get('MONGO_DB', 'sikbot')
_db_lock = threading.Lock()
_io_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-writer")  # كتابة بالترتيب بدون تعطيل البوت
_mongo_kv = None      # collection: kv   (_id = path, value = نص JSON)
_mongo_msgs = None    # collection: msgs (فيها TTL — تنحذف تلقائياً)
DB_BACKEND = "sqlite"
DB_WARNING = ""

def _init_sqlite():
    with sqlite3.connect(DB_PATH) as c:
        c.execute('CREATE TABLE IF NOT EXISTS kv (path TEXT PRIMARY KEY, value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS msgs (k TEXT PRIMARY KEY, text TEXT, exp REAL)')
        # سجل الرسائل القديم كان يتراكم للأبد — صار له جدول بمدة انتهاء
        c.execute("DELETE FROM kv WHERE path LIKE 'messages/%'")
        c.commit()

def _init_mongo():
    global _mongo_kv, _mongo_msgs, DB_BACKEND
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
    client.admin.command('ping')
    db = client[MONGO_DB_NAME]
    _mongo_kv = db['kv']
    _mongo_msgs = db['msgs']
    _mongo_msgs.create_index('expireAt', expireAfterSeconds=0)   # حذف تلقائي عند وقت expireAt
    DB_BACKEND = "mongo"

if MONGO_URI:
    try:
        _init_mongo()
        logger.info("✅ MongoDB متصل — البيانات دائمة")
    except Exception as e:
        DB_WARNING = f"تعذر الاتصال بـ MongoDB ({type(e).__name__}) — يُستخدم SQLite المؤقت"
        logger.error(f"❌ {DB_WARNING}")
        _init_sqlite()
else:
    _init_sqlite()

# ── تحميل cookies من متغير البيئة (لـ Railway) ──
def _load_cookies():
    import base64
    data = os.environ.get('COOKIES_DATA', '').strip()
    if not data:
        logger.info("ℹ️ COOKIES_DATA not set")
        return

    success = False

    # محاولة 1: base64 مع إزالة الفراغات
    try:
        clean = ''.join(data.split())
        content = base64.b64decode(clean + '==').decode('utf-8')
        if '\t' in content:  # تحقق أنه ملف cookies حقيقي
            with open('cookies.txt', 'w', encoding='utf-8') as f:
                f.write(content)
            lines = [l for l in content.splitlines() if l and not l.startswith('#') and '\t' in l]
            domains = set(l.split('\t')[0].lstrip('.') for l in lines)
            logger.info(f"✅ cookies.txt loaded (base64) — {len(lines)} cookies — {domains}")
            success = True
    except Exception as e:
        logger.warning(f"[cookies] base64 failed: {e}")

    # محاولة 2: الـ data نفسها هي محتوى الملف
    if not success:
        try:
            if '\t' in data:
                with open('cookies.txt', 'w', encoding='utf-8') as f:
                    f.write(data)
                logger.info("✅ cookies.txt loaded (plain text)")
                success = True
        except Exception as e:
            logger.error(f"[cookies] plain text failed: {e}")

    if not success:
        logger.error("❌ Failed to load cookies from COOKIES_DATA")
_load_cookies()

_UNSET = object()
_cache: dict = {}    # path -> نص JSON أو None (غير موجود) — البوت هو الكاتب الوحيد فالكاش دقيق

def _cache_put(path, raw):
    if len(_cache) > 20000: _cache.clear()
    _cache[path] = raw

def _backend_get(path):
    """يرجع نص JSON أو None."""
    if DB_BACKEND == "mongo":
        doc = _mongo_kv.find_one({'_id': path})
        return doc['value'] if doc else None
    with sqlite3.connect(DB_PATH) as c:
        row = c.execute('SELECT value FROM kv WHERE path=?', (path,)).fetchone()
        return row[0] if row else None

def _backend_set(path, raw):
    try:
        if DB_BACKEND == "mongo":
            if raw is None: _mongo_kv.delete_one({'_id': path})
            else: _mongo_kv.replace_one({'_id': path}, {'_id': path, 'value': raw}, upsert=True)
        else:
            with sqlite3.connect(DB_PATH) as c:
                if raw is None: c.execute('DELETE FROM kv WHERE path=?', (path,))
                else: c.execute('INSERT OR REPLACE INTO kv (path,value) VALUES (?,?)', (path, raw))
                c.commit()
    except Exception as e:
        logger.error(f"[db_set] {path}: {e}")

def db_get(path: str, default=None):
    with _db_lock:
        raw = _cache.get(path, _UNSET)
        if raw is _UNSET:
            try:
                raw = _backend_get(path)
            except Exception as e:
                logger.error(f"[db_get] {path}: {e}")
                return default
            _cache_put(path, raw)
    if raw is None: return default
    try: return json.loads(raw)       # نسخة جديدة كل مرة (مثل السلوك القديم)
    except Exception: return default

def db_set(path: str, value):
    raw = None if value is None else json.dumps(value, ensure_ascii=False)
    with _db_lock: _cache_put(path, raw)
    if DB_BACKEND == "mongo": _io_pool.submit(_backend_set, path, raw)   # بالخلفية وبنفس الترتيب
    else: _backend_set(path, raw)


# ═══════════════════════════════════════════════════════════════════
# 2b. رسائل مؤقتة (تنحذف تلقائياً) + إعدادات دائمة + نصوص قابلة للتعديل
# ═══════════════════════════════════════════════════════════════════
def cfg_get(key, default=None): return db_get(f"config/{key}", default)
def cfg_set(key, value): db_set(f"config/{key}", value)

def _now_utc(): return _dt.datetime.now(_dt.timezone.utc)

def _retention_hours() -> int:
    try: return max(1, min(24 * 30, int(cfg_get('msg_retention_hours', 48))))
    except Exception: return 48

def _msg_save_sync(cid, mid, text):
    key = f"{cid}:{mid}"
    hours = _retention_hours()
    try:
        if DB_BACKEND == "mongo":
            _mongo_msgs.replace_one({'_id': key},
                {'_id': key, 'text': text, 'expireAt': _now_utc() + _dt.timedelta(hours=hours)}, upsert=True)
        else:
            now = time.time()
            with sqlite3.connect(DB_PATH) as c:
                c.execute('INSERT OR REPLACE INTO msgs (k,text,exp) VALUES (?,?,?)', (key, text, now + hours * 3600))
                if random.random() < 0.02:
                    c.execute('DELETE FROM msgs WHERE exp < ?', (now,))
                c.commit()
    except Exception as e:
        logger.error(f"[msg_save] {e}")

def _msg_get_sync(cid, mid):
    key = f"{cid}:{mid}"
    try:
        if DB_BACKEND == "mongo":
            doc = _mongo_msgs.find_one({'_id': key})
            if not doc: return None
            exp = doc.get('expireAt')
            if exp is not None:
                if exp.tzinfo is None: exp = exp.replace(tzinfo=_dt.timezone.utc)
                if exp < _now_utc(): return None     # TTL يتأخر حتى دقيقة
            return doc.get('text')
        with sqlite3.connect(DB_PATH) as c:
            row = c.execute('SELECT text, exp FROM msgs WHERE k=?', (key,)).fetchone()
        return row[0] if row and row[1] > time.time() else None
    except Exception as e:
        logger.error(f"[msg_get] {e}")
        return None

async def msg_save(cid, mid, text):
    await asyncio.get_running_loop().run_in_executor(None, _msg_save_sync, cid, mid, text)

async def msg_get(cid, mid):
    return await asyncio.get_running_loop().run_in_executor(None, _msg_get_sync, cid, mid)

# المنصات الموقوفة تنحفظ وتبقى بعد إعادة التشغيل
_DISABLED_PLATFORMS.update(cfg_get('disabled_platforms', []) or [])
def _save_disabled(): cfg_set('disabled_platforms', sorted(_DISABLED_PLATFORMS))

# ── النصوص القابلة للتعديل من /admin ──
# لإضافة رسالة جديدة: أضف سطر هنا، واستبدل النص بالكود بـ T('المفتاح')
TEXTS = {
    'start_private': {
        'label': '👋 رسالة /start (الترحيب)',
        'vars': {'name': 'اسم المستخدم'},
        'default': """أهلاً <b>{name}</b>! 👋

📥 <b>المواقع المدعومة:</b>
🎬 يوتيوب  🐦 X/تويتر  🎵 تيك توك
🇨🇳 دوين  📘 فيس بوك  📸 انستغرام
📌 بينترست  🎵 ساوند كلاود  🎵 يوتيوب ميوزك
🎧 سبوتيفاي  🧵 ثريدز

━━━━━━━━━━━━━━━━━━━━
🌐 <code>ترجمة [نص]</code> — ترجمة للعربي
🔢 <code>حساب [عملية]</code> — حاسبة
🎵 <code>تيك @username</code> — معلومات تيك توك
🔄 <code>تحويل</code> — رد على فيديو لتحويله لصوت

👥 للمجموعات: أضفني مشرفاً واكتب <code>الاوامر</code>

💡 أرسل أي رابط وأنا أتكفله! 🚀
❓ /help — مساعدة""",
    },
    'group_added': {
        'label': '👥 رسالة إضافة البوت لمجموعة',
        'vars': {},
        'default': "👋 <b>أهلاً! تم إضافتي للمجموعة!</b>\n\n⚠️ <b>لكي أعمل بشكل كامل:</b>\n1️⃣ اجعلني <b>مشرفاً</b> في المجموعة\n2️⃣ اكتب <code>الاوامر</code> لقائمة الأوامر الكاملة 📋\n",
    },
    'member_welcome': {
        'label': '🎉 ترحيب العضو الجديد (السطر الأخير)',
        'vars': {},
        'default': "🎉 أهلاً وسهلاً بيك بالمجموعة!",
    },
    'maintenance': {
        'label': '🔧 رسالة إيقاف منصة (صيانة)',
        'vars': {},
        'default': "🔧 التحميل من هذي المنصة موقوف مؤقتاً للصيانة.",
    },
    'error_generic': {
        'label': '❌ رسالة الخطأ العامة',
        'vars': {},
        'default': "❌ حدث خطأ، حاول مرة أخرى لاحقاً.",
    },
    'too_big': {
        'label': '📦 رسالة الفيديو أكبر من 50MB',
        'vars': {},
        'default': "❌ الفيديو أكبر من 50MB (حد تيليقرام للبوتات).",
    },
}

def T(key, **values):
    """نص الرسالة: المعدّل من لوحة الأدمن إن وُجد، وإلا الافتراضي."""
    txt = db_get(f"texts/{key}") or TEXTS[key]['default']
    for k, v in values.items():
        txt = txt.replace('{' + k + '}', str(v))
    return txt

def _text_preview(key, txt=None):
    meta = TEXTS[key]
    txt = txt if txt is not None else (db_get(f"texts/{key}") or meta['default'])
    for k, desc in meta['vars'].items():
        txt = txt.replace('{' + k + '}', f"[{desc}]")
    return txt

# ── تسجيل المستخدمين + إشعار المطور عند أول /start ──
_bg_tasks = set()

def _spawn(coro):
    t = asyncio.ensure_future(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)

async def _notify_new_user(ctx, u, total, dev_chat):
    try:
        full = ' '.join(x for x in [u.first_name, getattr(u, 'last_name', None)] if x) or '—'
        uname = f"@{_esc(u.username)}" if u.username else "لا يوجد"
        caption = (
            "🆕 <b>مستخدم جديد ضغط /start</b>\n\n"
            f"👤 <b>الاسم:</b> <a href=\"tg://user?id={u.id}\">{_esc(full)}</a>\n"
            f"🆔 <b>الآيدي:</b> <code>{u.id}</code>\n"
            f"📛 <b>اليوزر:</b> {uname}\n"
            f"🌐 <b>اللغة:</b> {_esc(u.language_code or '—')}\n"
            f"👥 <b>إجمالي المستخدمين:</b> {total}"
        )
        photo_id = None
        try:
            ph = await ctx.bot.get_user_profile_photos(u.id, limit=1)
            if ph.total_count > 0: photo_id = ph.photos[0][-1].file_id
        except Exception as e:
            logger.info(f"[new_user] no profile photo: {e}")
        if photo_id: await ctx.bot.send_photo(dev_chat, photo_id, caption=caption, parse_mode="HTML")
        else: await ctx.bot.send_message(dev_chat, caption, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"[notify_new_user] {e}")

async def register_user(upd, ctx):
    """يسجّل المستخدم أول مرة ويبلّغ المطور (صورة + اسم + ايدي + يوزر). المطور نفسه: يحفظ chat_id فقط."""
    try:
        msg = upd.message; u = msg.from_user
        if msg.chat.type != 'private' or u.is_bot: return
        if is_dev(u):
            if cfg_get('dev_chat_id') != msg.chat_id: cfg_set('dev_chat_id', msg.chat_id)
            return
        if db_get(f"users/{u.id}") is not None: return
        db_set(f"users/{u.id}", {'name': u.first_name, 'username': u.username, 'ts': int(time.time())})
        total = int(cfg_get('users_count', 0) or 0) + 1
        cfg_set('users_count', total)
        if not cfg_get('notify_new_users', True): return
        dev_chat = os.environ.get('DEV_CHAT_ID') or cfg_get('dev_chat_id')
        if not dev_chat:
            logger.warning("[new_user] ما أعرف chat_id المطور — اكتب /start مرة وحدة من حسابك")
            return
        _spawn(_notify_new_user(ctx, u, total, int(dev_chat)))
    except Exception as e:
        logger.warning(f"[register_user] {e}")

# ── لوحة المطور ──
ADMIN_PLATFORMS = ['youtube', 'instagram', 'tiktok', 'facebook', 'x', 'spotify', 'soundcloud', 'pinterest']

def _fmt_hours(h):
    if h % 24 == 0:
        d = h // 24
        return "يوم" if d == 1 else "يومين" if d == 2 else f"{d} أيام" if d <= 10 else f"{d} يوم"
    return f"{h} ساعة"

def _cookie_info():
    if not os.path.exists('cookies.txt'): return "❌ غير موجود"
    try:
        with open('cookies.txt', 'r') as f: c = f.read()
        lines = [l for l in c.splitlines() if l and not l.startswith('#') and '\t' in l]
        domains = set(l.split('\t')[0].lstrip('.') for l in lines)
        return f"✅ {len(lines)} cookie — {', '.join(sorted(domains))}"
    except Exception:
        return "⚠️ موجود لكن تعذر قراءته"

def admin_main(bot_username=None):
    status = [f"{'🟢' if platform_enabled(p) else '🔴'} {p}" for p in ADMIN_PLATFORMS]
    storage = "🟢 MongoDB (دائمة)" if DB_BACKEND == "mongo" else "🟠 SQLite محلي (يُمسح على Render المجاني)"
    warn = f"\n⚠️ {_esc(DB_WARNING)}" if DB_WARNING else ""
    text = (
        "⚙️ <b>لوحة تحكم المطور</b>\n\n"
        "<b>المنصات:</b>\n" + "\n".join(status) + "\n\n"
        f"<b>🍪 الكوكيز:</b> {_cookie_info()}\n"
        f"<b>💾 التخزين:</b> {storage}{warn}\n"
        f"<b>🗑 مدة حفظ الرسائل:</b> {_fmt_hours(_retention_hours())}\n"
        f"<b>👥 المستخدمين المسجلين:</b> {int(cfg_get('users_count', 0) or 0)}"
    )
    if bot_username: text += f"\n<b>🤖 البوت:</b> @{bot_username}"
    rows = []
    for p in ADMIN_PLATFORMS:
        on = platform_enabled(p)
        rows.append([InlineKeyboardButton(f"{'🔴 وقف' if on else '🟢 شغّل'} {p}", callback_data=f"adm_toggle_{p}")])
    rows.append([InlineKeyboardButton("🔄 تحديث", callback_data="adm_refresh"),
                 InlineKeyboardButton("🍪 فحص كوكيز", callback_data="adm_cookies")])
    rows.append([InlineKeyboardButton("✏️ تعديل الرسائل", callback_data="adm_texts")])
    rows.append([InlineKeyboardButton(f"🗑 مدة حفظ الرسائل: {_fmt_hours(_retention_hours())}", callback_data="adm_ret")])
    rows.append([InlineKeyboardButton(f"🔔 إشعار المستخدمين الجدد: {'✅ شغال' if cfg_get('notify_new_users', True) else '❌ موقوف'}",
                                      callback_data="adm_newuser")])
    return text, InlineKeyboardMarkup(rows)

async def admin_show_text(q, key):
    meta = TEXTS[key]
    custom = bool(db_get(f"texts/{key}"))
    vars_line = ("\n<b>الحقول المتاحة:</b> " + "، ".join(f"<code>{{{k}}}</code> = {d}" for k, d in meta['vars'].items())) if meta['vars'] else ""
    rows = [[InlineKeyboardButton("✏️ تعديل", callback_data=f"adm_te_{key}")]]
    if custom: rows[0].append(InlineKeyboardButton("↩️ الافتراضي", callback_data=f"adm_tr_{key}"))
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_texts")])
    try:
        await q.edit_message_text(
            f"{meta['label']}\n{'✏️ معدّلة' if custom else '📄 الافتراضية'}{vars_line}\n\n━━━━━━━━━━\n" + _text_preview(key),
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        logger.info(f"[admin_show_text] {e}")

async def admin_show_retention(q):
    cur = _retention_hours()
    btns = [InlineKeyboardButton(("✅ " if h == cur else "") + _fmt_hours(h), callback_data=f"adm_retset_{h}")
            for h in (6, 12, 24, 48, 72, 168)]
    rows = [btns[:3], btns[3:],
            [InlineKeyboardButton("✏️ مدة مخصصة", callback_data="adm_retcustom")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="adm_refresh")]]
    try:
        await q.edit_message_text(
            "🗑 <b>مدة حفظ الرسائل</b>\n\n"
            "البوت يحفظ نص رسائل الكروبات مؤقتاً عشان يعرف النص القديم لما أحد يعدّل رسالته، "
            "وبعد المدة تنحذف تلقائياً.\n\n"
            f"<b>المدة الحالية:</b> {_fmt_hours(cur)}\n"
            "<i>التغيير يطبق على الرسائل الجديدة.</i>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        logger.info(f"[admin_show_retention] {e}")

async def admin_wait_input(upd, ctx, wait):
    """يستقبل رد المطور بعد ضغط 'تعديل' أو 'مدة مخصصة'."""
    msg = upd.message
    raw = (msg.text or '').strip()
    if time.time() - wait.get('ts', 0) > 600:
        ctx.user_data.pop('adm_wait', None)
        return await msg.reply_text("⌛ انتهت مهلة التعديل (10 دقائق). افتح /admin من جديد.")
    if raw in ('الغاء', 'إلغاء', 'cancel'):
        ctx.user_data.pop('adm_wait', None)
        return await msg.reply_text("❎ تم الإلغاء. /admin للرجوع للقائمة.")
    if wait['kind'] == 'retention':
        digits = raw.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
        if not digits.isdigit() or not 1 <= int(digits) <= 720:
            return await msg.reply_text("❌ أرسل عدد ساعات من 1 إلى 720 (30 يوم)، أو اكتب «الغاء».")
        h = int(digits)
        cfg_set('msg_retention_hours', h)
        ctx.user_data.pop('adm_wait', None)
        return await msg.reply_text(f"✅ صارت مدة حفظ الرسائل <b>{_fmt_hours(h)}</b> (تطبق على الرسائل الجديدة).\n/admin للرجوع.",
                                    parse_mode="HTML")
    if wait['kind'] == 'text':
        key = wait.get('key')
        if key not in TEXTS:
            ctx.user_data.pop('adm_wait', None)
            return await msg.reply_text("❌ رسالة غير معروفة.")
        new = msg.text_html or raw          # يحافظ على تنسيق تيليجرام (غامق/مائل/كود)
        if len(new) > 3500:
            return await msg.reply_text("❌ النص طويل جداً (الحد 3500 حرف). اختصره وأرسله مرة ثانية.")
        try:
            await msg.reply_text("👁 <b>معاينة:</b>\n\n" + _text_preview(key, new), parse_mode="HTML")
        except Exception as e:
            logger.info(f"[admin text invalid] {e}")
            return await msg.reply_text("❌ تنسيق النص غير صالح — جرب مرة ثانية أو اكتب «الغاء».")
        db_set(f"texts/{key}", new)
        ctx.user_data.pop('adm_wait', None)
        await msg.reply_text("✅ تم الحفظ — من الآن البوت يستخدم هذا النص.\n/admin للرجوع.")

def get_settings(cid):
    return db_get(f"settings/{cid}", {
        "welcome":True,"banned_words":[],"locked":False,
        "edit_notify":True,"ai_mode":False,
        "ban_stickers":False,"ban_gifs":False,"ban_videos":False,"ban_photos":False
    })
def save_settings(cid, s): db_set(f"settings/{cid}", s)

def make_key(text): return "k"+hashlib.md5(text.strip().lower().encode()).hexdigest()[:16]

def store_reply(cid, trigger, reply):
    d = db_get(f"replies/{cid}", {})
    d[make_key(trigger)] = {"t": trigger.strip(), "r": reply.strip()}
    db_set(f"replies/{cid}", d)

def delete_reply(cid, trigger):
    d = db_get(f"replies/{cid}", {})
    d.pop(make_key(trigger), None)
    db_set(f"replies/{cid}", d)

def get_replies(cid):
    d = db_get(f"replies/{cid}", {})
    return [(v["t"], v["r"]) for v in d.values() if isinstance(v, dict) and v.get("t") and v.get("r")]

# ═══════════════════════════════════════════════════════════════════
# 3. الصلاحيات
# ═══════════════════════════════════════════════════════════════════
ROLE_OWNER, ROLE_MGR, ROLE_VIP = "owner","manager","vip"
ROLE_RANK = {ROLE_OWNER:3, ROLE_MGR:2, ROLE_VIP:1}
ROLE_LABEL = {ROLE_OWNER:"👑 مالك", ROLE_MGR:"🛡 مدير", ROLE_VIP:"⭐ مميز"}

def get_role(cid, uid): return db_get(f"roles/{cid}/{uid}")
def set_role(cid, uid, r): db_set(f"roles/{cid}/{uid}", r)
def rm_role(cid, uid): db_set(f"roles/{cid}/{uid}", None)

async def is_tg_owner(upd, ctx):
    try:
        admins = await ctx.bot.get_chat_administrators(upd.effective_chat.id)
        return any(a.user.id == upd.effective_user.id and a.status == "creator" for a in admins)
    except Exception as e:
        logger.warning(f"[is_tg_owner] {e}")
        return False

async def is_priv(upd, ctx, min_role=ROLE_OWNER):
    r = get_role(upd.effective_chat.id, upd.effective_user.id)
    return (bool(r and ROLE_RANK.get(r,0) >= ROLE_RANK.get(min_role,99))) or await is_tg_owner(upd, ctx)

async def get_target(upd, ctx):
    m = upd.message
    if m.reply_to_message: return m.reply_to_message.from_user
    if m.entities:
        for e in m.entities:
            if e.type == "text_mention" and e.user: return e.user
    return None

# ═══════════════════════════════════════════════════════════════════
# 4. الذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════════
async def ask_ai(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_KEY", "")  # أضف GEMINI_KEY كـ env variable
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "systemInstruction": {"parts": [{"text": "أنت مساعد ذكي اسمك سيك، تتحدث باللهجة العراقية أحياناً وتبقى لطيف وخفيف. كن مختصراً ومفيداً."}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.8}
    }
    def _call():
        try:
            r = requests.post(url, json=payload, timeout=30)
            logger.info(f"[AI-Gemini] status={r.status_code}")
            if not api_key: return "❌ GEMINI_KEY غير مضاف. أضفه كـ environment variable."
            if r.status_code in (401, 403): return "❌ مفتاح Gemini منتهي أو غلط. راجع GEMINI_KEY."
            if r.status_code == 429:
                # free tier: 15 req/min — انتظر وأعد المحاولة
                import time; time.sleep(12)
                r2 = requests.post(url, json=payload, timeout=30)
                if r2.status_code == 200:
                    return r2.json()["candidates"][0]["content"]["parts"][0]["text"]
                return "⚠️ Gemini مشغول الحين (free tier limit). انتظر دقيقة وأعد المحاولة."

            if r.status_code == 400:
                err = r.json().get("error", {}).get("message", "")
                return f"❌ خطأ في الطلب: {err[:80]}"
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except requests.Timeout: return "⏱ Gemini ما رد. حاول ثاني."
        except Exception as e: logger.error(f"[AI] {e}"); return f"❌ خطأ: {str(e)[:80]}"
    return await asyncio.get_running_loop().run_in_executor(None, _call)

# ═══════════════════════════════════════════════════════════════════
# 5. نظام التحميل
# ═══════════════════════════════════════════════════════════════════
active_dl = {}

def _progress(d, mid):
    if d['status'] == 'downloading':
        pct = re.sub(r'\x1b\[[0-9;]*m','', d.get('_percent_str','0%').strip())
        active_dl[mid] = pct

async def _progress_updater(ctx, cid, mid, smid, is_photo=False):
    last = ""
    while mid in active_dl:
        cur = active_dl.get(mid,"")
        if cur and cur != last:
            try:
                t = f"⏳ جاري التحميل: {cur}"
                if is_photo: await ctx.bot.edit_message_caption(chat_id=cid, message_id=smid, caption=t)
                else: await ctx.bot.edit_message_text(t, chat_id=cid, message_id=smid)
                last = cur
            except Exception: pass
        await asyncio.sleep(2.5)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def _base_opts(mid):
    opts = {
        'outtmpl': os.path.join(tempfile.mkdtemp(), '%(title)s.%(ext)s'),
        'quiet': True, 'noplaylist': True, 'nocheckcertificate': True,
        'geo_bypass': True, 'extractor_retries': 3, 'retries': 3,
        'ffmpeg_location': FFMPEG,
        'progress_hooks': [lambda d: _progress(d, mid)],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        },
    }
    if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
    return opts

def get_qualities(url: str):
    """إرجاع (format_map, info) — format_map = {height: format_id}"""
    is_yt = bool(re.search(r'(youtube\.com|youtu\.be)', url))
    try:
        opts = {**_base_opts(0), 'skip_download': True}
        opts.pop('progress_hooks')
        if is_yt:
            # ios يعطي أفضل جودة لـ YouTube
            opts['extractor_args'] = {'youtube': {'player_client': ['ios', 'android', 'web']}}
            opts['http_headers']['User-Agent'] = 'com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip'
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            format_map = {}  # {height: format_id}
            for f in info.get('formats', []):
                h = f.get('height')
                vcodec = f.get('vcodec','none')
                if not h or vcodec == 'none': continue
                tbr = f.get('tbr') or f.get('vbr') or 0
                if h not in format_map or tbr > format_map[h]['tbr']:
                    format_map[h] = {'id': f['format_id'], 'tbr': tbr, 'ext': f.get('ext','mp4')}
            return format_map, info
    except Exception as e:
        logger.error(f"[qualities] {e}")
        return {}, None

def build_quality_kb(format_map, uid, uhash, emoji="🎬"):
    """format_map = {height: {'id':..., 'tbr':...}} أو مجرد list of heights"""
    standard = [2160,1440,1080,720,480,360,240,144]
    if isinstance(format_map, dict):
        avail = sorted([h for h in format_map if h], reverse=True)
        avail = [q for q in standard if any(abs(a-q)<=q*0.15 for a in avail)]
    else:
        avail = [q for q in standard if any(h >= q*0.85 for h in (format_map or []))]
    avail = avail[:6] if avail else [720,480,360]
    rows, row = [], []
    for q in avail:
        row.append(InlineKeyboardButton(f"{emoji} {q}p", callback_data=f"dl_v{q}_{uid}_{uhash}"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🎵 صوت MP3", callback_data=f"dl_audio_{uid}_{uhash}")])
    return InlineKeyboardMarkup(rows)

async def do_download(url, media_type, quality, mid, cid, ctx, smid, is_photo=False):
    opts = _base_opts(mid)
    opts['outtmpl'] = opts['outtmpl'].replace('%(title)s', '%(id)s')
    tmp = os.path.dirname(opts['outtmpl'])

    is_yt = bool(re.search(r'(youtube\.com|youtu\.be)', url))
    if is_yt:
        opts['extractor_args'] = {'youtube': {'player_client': ['android', 'ios']}}
        opts['http_headers']['User-Agent'] = 'com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip'

    if media_type == "audio":
        opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
        opts['writethumbnail'] = True
        opts['postprocessors'] = [
            {'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'320'},
            {'key':'FFmpegMetadata','add_metadata':True},
            {'key':'EmbedThumbnail'},
        ]
    else:
        h = int(quality) if quality and str(quality).isdigit() else 720
        # استخدم format_id المخزن إذا متوفر (يضمن الجودة الصحيحة)
        fmt_info = None
        if ctx:
            raw_data = ctx.bot_data.get(url[:60] + '_fmt', {}) if url else {}
            if isinstance(raw_data, dict):
                # ابحث عن أقرب height
                for stored_h, fi in raw_data.items():
                    if abs(int(stored_h) - h) <= h * 0.15:
                        fmt_info = fi; break
        if fmt_info and fmt_info.get('id'):
            vid_id = fmt_info['id']
            opts['format'] = (f'{vid_id}+bestaudio[ext=m4a]/'
                              f'{vid_id}+bestaudio/'
                              f'bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/'
                              f'bestvideo[height<={h}]+bestaudio/best[height<={h}]')
        else:
            opts['format'] = (f'bestvideo[height<={h}]+bestaudio/'
                              f'best[height<={h}][ext=mp4]/best[height<={h}]/'
                              f'bestvideo+bestaudio/best')
            opts['format_sort'] = [f'res:{h}', 'ext:mp4', '+codec:h264']
        opts['merge_output_format'] = 'mp4'

    active_dl[mid] = "0%"
    task = asyncio.create_task(_progress_updater(ctx, cid, mid, smid, is_photo))

    def run():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp):
                if f.endswith(('.mp3','.mp4','.m4a','.webm','.mkv')):
                    return os.path.join(tmp, f), info.get('title','media')
        return None, None

    try:
        path, title = await asyncio.get_running_loop().run_in_executor(None, run)
        active_dl.pop(mid, None); task.cancel()
        return path, title, tmp
    except Exception as e:
        logger.error(f"[download] {e}")
        active_dl.pop(mid, None); task.cancel()
        shutil.rmtree(tmp, ignore_errors=True)
        return None, None, None

# تيك توك + دوين عبر API
def tiktok_api(url: str):
    """تيك توك + دوين عبر tikwm API"""
    encoded = requests.utils.quote(url, safe='')
    api_urls = [
        f'https://www.tikwm.com/api/?url={encoded}&hd=1',
        f'https://www.tikwm.com/api/?url={url}&hd=1',
        f'https://tikwm.com/api/?url={encoded}&hd=1',
        # API بديلة
        f'https://api.tikmate.app/api/lookup?url={encoded}',
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.tikwm.com/',
        'Origin': 'https://www.tikwm.com',
    }
    for api_url in api_urls[:3]:  # tikwm فقط
        try:
            r = requests.get(api_url, timeout=30, headers=headers)
            if r.status_code != 200: continue
            j = r.json()
            if j.get('code') == 0 and 'data' in j:
                d = j['data']
                author_obj = d.get('author', {})
                author = (author_obj.get('unique_id','') if isinstance(author_obj,dict) else str(author_obj)) or 'مجهول'
                music = d.get('music','')
                if isinstance(music, dict): music = music.get('play','')
                if d.get('images'):
                    return {'type':'images','data':d['images'],'author':author,'music':music}
                vid = d.get('hdplay') or d.get('play') or d.get('wmplay')
                if vid:
                    return {'type':'video','data':vid,'author':author,'music':music}
        except Exception as e:
            logger.warning(f"[tikwm] {api_url[:50]}: {e}")
    return None

# ═══════════════════════════════════════════════════════════════════
# 6. معالجات الروابط
# ═══════════════════════════════════════════════════════════════════
async def yt_handler(upd, ctx, url, uid):
    msg = upd.message
    dev = is_dev(msg.from_user)

    if not platform_enabled('youtube'):
        await msg.reply_text(
            T('maintenance') if not dev else
            "⚙️ [DEV] يوتيوب موقوف — استخدم /admin لتفعيله."
        )
        return

    wm = await msg.reply_text("🔍 جاري جلب معلومات الفيديو من يوتيوب...")

    def _get_info():
        clients = [
            ['tv_embedded'],
            ['ios'],
            ['android'],
            ['mweb'],
            ['web_embedded'],
        ]
        if os.path.exists('cookies.txt'):
            clients.insert(0, ['web'])
        last_err = ""
        for client in clients:
            try:
                opts = {
                    'quiet': True, 'noplaylist': True, 'nocheckcertificate': True,
                    'skip_download': True, 'geo_bypass': True,
                    'extractor_args': {'youtube': {'player_client': client}},
                    'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0'},
                }
                if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info: return info, None
            except Exception as e:
                last_err = str(e)
                logger.warning(f"[YT] client {client}: {e}")
                continue
        return None, last_err

    info, last_err = await asyncio.get_running_loop().run_in_executor(None, _get_info)
    if not info:
        await send_error(
            ctx, msg.chat_id, msg.from_user,
            dev_msg=f"⚙️ [DEV] فشل يوتيوب:\n<code>{(last_err or '')[:400]}</code>",
            user_msg="❌ تعذر جلب بيانات الفيديو.\n• تأكد أن الرابط صحيح وعام\n• حاول مرة ثانية بعد قليل",
            target_message=wm
        )
        return

    format_map = {}
    for f in info.get('formats', []):
        h = f.get('height')
        if not h or f.get('vcodec','none') == 'none': continue
        tbr = f.get('tbr') or f.get('vbr') or 0
        if h not in format_map or tbr > format_map[h].get('tbr', 0):
            format_map[h] = {'id': f['format_id'], 'tbr': tbr}

    uhash = str(random.randint(10000,99999))
    ctx.bot_data[uhash] = url
    ctx.bot_data[url[:60]+'_fmt'] = format_map

    dur   = info.get('duration', 0)
    views = info.get('view_count', 0)
    cap   = (
        f"🎬 <b>{info.get('title','')[:60]}</b>\n"
        f"⏱ {dur//60}:{dur%60:02d}"
        + (f" | 👁 {views:,}" if views else "")
    )
    kb = build_quality_kb(format_map, uid, uhash, "🎬")
    try:
        if info.get('thumbnail'):
            await ctx.bot.send_photo(msg.chat_id, info['thumbnail'], caption=cap, parse_mode="HTML", reply_markup=kb)
        else:
            await msg.reply_text(cap, parse_mode="HTML", reply_markup=kb)
        await wm.delete()
    except Exception:
        await wm.edit_text(cap, parse_mode="HTML", reply_markup=kb)

async def auto_download(upd, ctx, url, cid, platform="🎬", max_height=1440):
    """تحميل تلقائي بأعلى جودة متوفرة (حد أقصى max_height)"""
    msg = upd.message
    wm = await msg.reply_text(f"{platform} جاري التحميل بأعلى جودة...")
    tmp = tempfile.mkdtemp()
    opts = {**_base_opts(msg.message_id)}
    opts['outtmpl'] = os.path.join(tmp, '%(id)s.%(ext)s')
    opts['format'] = (
        f'bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/'
        f'bestvideo[height<={max_height}]+bestaudio/'
        f'best[height<={max_height}][ext=mp4]/'
        f'best[height<={max_height}]/best'
    )
    opts['format_sort'] = [f'res:{max_height}', '+codec:h264', 'ext:mp4']
    opts['merge_output_format'] = 'mp4'

    active_dl[msg.message_id] = "0%"
    prog_task = asyncio.create_task(
        _progress_updater(ctx, cid, msg.message_id, wm.message_id)
    )

    def _run():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = sorted(
                [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith('.mp4')],
                key=os.path.getsize, reverse=True
            )
            if not files:
                files = sorted(
                    [os.path.join(tmp, f) for f in os.listdir(tmp)
                     if f.endswith(('.webm', '.mkv'))],
                    key=os.path.getsize, reverse=True
                )
            return files[0] if files else None, info.get('title', '')

    def _reencode_for_compatibility(src_path):
        """
        إعادة ترميز صريحة (مو مجرد remux) لضمان توافق تام مع مشغل
        فيديو تيليقرام على iOS: H.264 (yuv420p) + AAC + moov atom بالمقدمة
        (faststart) — هذا يحل مشكلة الفيديو الرمادي / اللي ما ينحفظ بالجهاز.
        """
        out_path = src_path.rsplit('.', 1)[0] + '_fixed.mp4'
        cmd = [
            FFMPEG, '-y', '-i', src_path,
            '-c:v', 'libx264', '-profile:v', 'main', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            out_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                return out_path, None
            return None, result.stderr[-500:] if result.stderr else "فشل إعادة الترميز"
        except subprocess.TimeoutExpired:
            return None, "انتهى الوقت أثناء إعادة الترميز"
        except Exception as e:
            return None, str(e)

    try:
        fp, title = await asyncio.get_running_loop().run_in_executor(None, _run)
        active_dl.pop(msg.message_id, None); prog_task.cancel()

        if fp and os.path.exists(fp):
            # أعد الترميز دائماً لضمان توافق H.264/AAC/faststart (يحل مشكلة الفيديو الرمادي بالآيفون)
            fixed_fp, reencode_err = await asyncio.get_running_loop().run_in_executor(
                None, lambda: _reencode_for_compatibility(fp)
            )
            final_fp = fixed_fp if fixed_fp else fp
            if reencode_err:
                logger.warning(f"[auto_dl reencode] {reencode_err}")

            file_size = os.path.getsize(final_fp)
            if file_size > TG_MAX_BYTES:
                await send_error(
                    ctx, cid, msg.from_user,
                    dev_msg=f"⚙️ [DEV] الملف كبير ({file_size // 1048576}MB) وحد تيليقرام 50MB — {platform}",
                    user_msg=T('too_big'),
                    target_message=wm
                )
                return
            if file_size < 1000:
                await send_error(
                    ctx, cid, msg.from_user,
                    dev_msg=f"⚙️ [DEV] الملف الناتج فارغ تقريباً ({file_size} بايت) — {platform}",
                    user_msg="❌ حدث خطأ أثناء التحميل، حاول مرة أخرى.",
                    target_message=wm
                )
                return

            await wm.edit_text("📤 جاري الرفع...")
            safe_title = re.sub(r'[^\w\-]', '_', (title or platform))[:60] or 'video'
            fname = f"{safe_title}.mp4"
            with open(final_fp, 'rb') as f:
                await send_safe(ctx.bot.send_video(
                    cid, f,
                    filename=fname,
                    caption=f"{platform} {title[:60]}" if title else platform,
                    supports_streaming=True
                ))
            await wm.delete()
        else:
            await send_error(
                ctx, cid, msg.from_user,
                dev_msg=f"⚙️ [DEV] {platform} فشل التحميل — لم يُنتج أي ملف من الرابط:\n<code>{url[:200]}</code>",
                user_msg="❌ تعذر التحميل. تأكد أن الرابط عام وصحيح.",
                target_message=wm
            )
    except Exception as e:
        active_dl.pop(msg.message_id, None); prog_task.cancel()
        logger.error(f"[auto_dl] {e}")
        await send_error(
            ctx, cid, msg.from_user,
            dev_msg=f"⚙️ [DEV] خطأ {platform}:\n<code>{str(e)[:400]}</code>",
            user_msg="❌ حدث خطأ أثناء التحميل، حاول مرة أخرى لاحقاً.",
            target_message=wm
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

async def fb_handler(upd, ctx, url, uid):
    """فيس بوك — تحميل تلقائي بأعلى جودة"""
    if await platform_blocked(upd, 'facebook'): return
    await auto_download(upd, ctx, url, upd.message.chat_id, "📘")

async def x_handler(upd, ctx, url, uid):
    """X/Twitter — تحميل تلقائي بأعلى جودة"""
    if await platform_blocked(upd, 'x'): return
    msg = upd.message
    cid = msg.chat_id
    has_cookies = os.path.exists('cookies.txt')
    wm = await msg.reply_text("🐦 جاري التحميل من X...")
    fx_url = url.replace('x.com','fixupx.com').replace('twitter.com','fixupx.com')
    tmp = tempfile.mkdtemp()
    opts = {**_base_opts(msg.message_id)}
    opts['outtmpl'] = os.path.join(tmp,'%(id)s.%(ext)s')
    opts['format'] = 'bestvideo[height<=1440]+bestaudio/best[height<=1440]/best'
    opts['merge_output_format'] = 'mp4'
    if has_cookies: opts['cookiefile'] = 'cookies.txt'
    active_dl[msg.message_id] = "0%"
    prog = asyncio.create_task(_progress_updater(ctx, cid, msg.message_id, wm.message_id))

    def _dl():
        for try_url in [url, fx_url]:
            try:
                o = {**opts}
                with YoutubeDL(o) as ydl:
                    info = ydl.extract_info(try_url, download=True)
                    files = sorted(
                        [os.path.join(tmp,f) for f in os.listdir(tmp) if f.endswith(('.mp4','.webm','.mkv'))],
                        key=os.path.getsize, reverse=True
                    )
                    if files: return files[0], info.get('title','')
            except Exception as e:
                logger.warning(f"[X dl] {try_url[:80]}: {e}")
        return None, ''

    try:
        fp, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
        active_dl.pop(msg.message_id, None); prog.cancel()
        if fp and os.path.exists(fp) and os.path.getsize(fp) > TG_MAX_BYTES:
            await send_error(
                ctx, cid, msg.from_user,
                dev_msg=f"⚙️ [DEV] X: الملف كبير ({os.path.getsize(fp) // 1048576}MB) وحد تيليقرام 50MB",
                user_msg=T('too_big'),
                target_message=wm
            )
        elif fp and os.path.exists(fp):
            await wm.edit_text("📤 جاري الرفع...")
            with open(fp,'rb') as f:
                await send_safe(ctx.bot.send_video(cid, f, caption=f"🐦 {title[:60]}" if title else "🐦 X", supports_streaming=True))
            await wm.delete()
        else:
            await send_error(
                ctx, cid, msg.from_user,
                dev_msg=(f"⚙️ [DEV] X فشل — cookies={'موجودة' if has_cookies else 'غير موجودة'}\n"
                         f"الرابط: <code>{url[:200]}</code>"),
                user_msg="❌ تعذر التحميل من X. تأكد أن التغريدة عامة.",
                target_message=wm
            )
    except Exception as e:
        active_dl.pop(msg.message_id, None); prog.cancel()
        await send_error(
            ctx, cid, msg.from_user,
            dev_msg=f"⚙️ [DEV] خطأ X:\n<code>{str(e)[:400]}</code>",
            user_msg="❌ حدث خطأ، حاول مرة أخرى لاحقاً.",
            target_message=wm
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

async def tiktok_handler(upd, ctx, url, cid, reply_id):
    if await platform_blocked(upd, 'tiktok'): return
    msg = upd.message
    wm = await msg.reply_text("⏳ جاري التحميل...")
    # محاولة 1: tikwm API (يدعم تيك توك + دوين)
    data = await asyncio.get_running_loop().run_in_executor(None, lambda: tiktok_api(url))
    if data:
        author = data.get('author', 'tiktok')
        cap = f"👤 <b>@{author}</b>"
        try:
            if data['type'] == 'images':
                # تحميل الصور + الصوت (كملفات فعلية بايتات، مو روابط) — يضمن اسم ملف صحيح للصوت
                def _dl_imgs_and_audio():
                    imgs = []
                    audio_bytes = None
                    headers = {'User-Agent':'Mozilla/5.0','Referer':'https://www.tiktok.com/'}
                    for img_url in data['data']:
                        try:
                            r = requests.get(img_url, headers=headers, timeout=15)
                            if r.status_code == 200: imgs.append(r.content)
                        except Exception: pass
                    music_url = data.get('music')
                    if music_url:
                        try:
                            r = requests.get(music_url, headers=headers, timeout=20)
                            if r.status_code == 200 and len(r.content) > 2000:
                                audio_bytes = r.content
                        except Exception: pass
                    return imgs, audio_bytes

                img_bytes, audio_bytes = await asyncio.get_running_loop().run_in_executor(None, _dl_imgs_and_audio)
                if img_bytes:
                    total = len(img_bytes)
                    for i in range(0, total, 10):
                        batch = img_bytes[i:i+10]
                        media = [InputMediaPhoto(b) for b in batch]
                        await send_safe(ctx.bot.send_media_group(cid, media, reply_to_message_id=reply_id))
                        if i+10 < total: await asyncio.sleep(1)

                    if audio_bytes:
                        # اسم ملف صريح (safe_name.mp3) بدل الاعتماد على title/performer فقط
                        safe_name = re.sub(r'[^\w\-]', '_', author)[:50] or 'audio'
                        tmp_audio_dir = tempfile.mkdtemp()
                        raw_audio_path = os.path.join(tmp_audio_dir, f'{safe_name}_raw.mp3')
                        final_audio_path = os.path.join(tmp_audio_dir, f'{safe_name}.mp3')
                        try:
                            with open(raw_audio_path, 'wb') as f:
                                f.write(audio_bytes)
                            # أعد الترميز لـ mp3 حقيقي (الملف الأصلي أحياناً m4a بامتداد خاطئ)
                            conv = subprocess.run(
                                [FFMPEG, '-y', '-i', raw_audio_path, '-c:a', 'libmp3lame', '-q:a', '2', final_audio_path],
                                capture_output=True, text=True, timeout=60
                            )
                            audio_to_send = final_audio_path if (conv.returncode == 0 and os.path.exists(final_audio_path)) else raw_audio_path
                            with open(audio_to_send, 'rb') as f:
                                await send_safe(ctx.bot.send_audio(
                                    cid, f,
                                    filename=f'{safe_name}.mp3',
                                    title=author,
                                    performer=author,
                                    caption=f"{cap}\n🖼 {total} صورة", parse_mode="HTML"
                                ))
                        finally:
                            shutil.rmtree(tmp_audio_dir, ignore_errors=True)
                else:
                    await send_error(
                        ctx, cid, msg.from_user,
                        dev_msg="⚙️ [DEV] تيك توك — تعذّر تحميل صور الألبوم من tikwm.",
                        user_msg="❌ تعذر تحميل الصور من هذه الألبوم.",
                        target_message=wm
                    )
                    return
            else:
                await send_safe(ctx.bot.send_video(cid, data['data'], caption=cap, parse_mode="HTML",
                                                   reply_to_message_id=reply_id, supports_streaming=True))
            return await wm.delete()
        except Exception as e:
            logger.error(f"[TikTok send] {e}")

    # محاولة 2: yt-dlp مباشرة (يدعم تيك توك + دوين)
    await wm.edit_text("⏳ محاولة بديلة...")
    is_douyin = 'douyin.com' in url

    def _dl_tiktok():
        tmp2 = tempfile.mkdtemp()
        attempts = []
        if is_douyin:
            attempts = [
                {'format':'best[ext=mp4]/best',
                 'http_headers':{'User-Agent':'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36'}},
                {'format':'best',
                 'extractor_args':{'douyin':{'app_name':['trill']}},
                 'http_headers':{'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}},
            ]
        else:
            attempts = [
                {'format':'best[ext=mp4]/best',
                 'http_headers':{'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'}},
                {'format':'best',
                 'http_headers':{'User-Agent':'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36'}},
            ]
        base_opts = {
            'outtmpl': os.path.join(tmp2,'%(id)s.%(ext)s'),
            'quiet':True,'nocheckcertificate':True,'geo_bypass':True,
            'ffmpeg_location':FFMPEG,'merge_output_format':'mp4',
        }
        last_err = ""
        for attempt in attempts:
            try:
                opts = {**base_opts, **attempt}
                with YoutubeDL(opts) as ydl:
                    ydl.extract_info(url, download=True)
                    for f in os.listdir(tmp2):
                        if f.endswith(('.mp4','.webm','.mkv','.m4v')):
                            return os.path.join(tmp2,f), tmp2, None
            except Exception as e:
                last_err = str(e)
                logger.warning(f"[TikTok attempt] {e}")
                for f in os.listdir(tmp2):
                    try: os.remove(os.path.join(tmp2,f))
                    except Exception: pass
        return None, tmp2, last_err

    fp, tmp, last_err = await asyncio.get_running_loop().run_in_executor(None, _dl_tiktok)
    if fp and os.path.exists(fp) and os.path.getsize(fp) > TG_MAX_BYTES:
        await send_error(
            ctx, cid, msg.from_user,
            dev_msg=f"⚙️ [DEV] تيك توك/دوين: الملف كبير ({os.path.getsize(fp) // 1048576}MB) وحد تيليقرام 50MB",
            user_msg=T('too_big'),
            target_message=wm
        )
    elif fp and os.path.exists(fp):
        emoji = "🇨🇳 دوين" if is_douyin else "✅ تيك توك 🎵"
        with open(fp,'rb') as f: await send_safe(ctx.bot.send_video(cid, f, caption=emoji, supports_streaming=True))
        await wm.delete()
    else:
        await send_error(
            ctx, cid, msg.from_user,
            dev_msg=f"⚙️ [DEV] {'دوين' if is_douyin else 'تيك توك'} فشل نهائياً:\n<code>{(last_err or '')[:400]}</code>",
            user_msg="❌ فشل التحميل. قد يكون الرابط منتهياً أو الحساب خاص.",
            target_message=wm
        )
    if tmp: shutil.rmtree(tmp, ignore_errors=True)

async def _insta_download_and_send(ctx, cid, url, wm, username="", download_all=False, is_story=False, user=None):
    """تحميل انستغرام — فيديو + صور ثابتة + ستوريات + كاروسيل (بوستات /p/)"""
    has_cookies = os.path.exists('cookies.txt')
    tmp = tempfile.mkdtemp()
    ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
    base_opts = {
        'outtmpl': os.path.join(tmp, '%(id)s_%(autonumber)03d.%(ext)s'),
        'quiet': True, 'nocheckcertificate': True, 'geo_bypass': True,
        'ffmpeg_location': FFMPEG,
        'http_headers': {'User-Agent': ua},
    }
    if has_cookies: base_opts['cookiefile'] = 'cookies.txt'
    use_playlist = download_all or not is_story

    def _scrape_page_json(page_url):
        """
        استخراج بيانات المنشور مباشرة من صفحة HTML الانستغرام (بديل عن yt-dlp
        عندما يفشل بخطأ 'No video formats found' — شائع لبوستات /p/ الصور).
        نبحث عن __additional_data أو shared_data المضمّنة بالصفحة.
        """
        try:
            headers = {
                'User-Agent': ua,
                'Accept-Language': 'en-US,en;q=0.9',
            }
            cookies = {}
            if has_cookies:
                try:
                    with open('cookies.txt', 'r') as cf:
                        for line in cf:
                            if line.startswith('#') or '\t' not in line: continue
                            parts = line.strip().split('\t')
                            if len(parts) >= 7 and 'instagram.com' in parts[0]:
                                cookies[parts[5]] = parts[6]
                except Exception: pass
            r = requests.get(page_url, headers=headers, cookies=cookies, timeout=20)
            html = r.text

            image_urls = []
            audio_url = None
            acc_name = username

            # حاول ألقط اسم الحساب من og:title أو meta
            m = re.search(r'"owner":\s*{\s*"username":\s*"([^"]+)"', html)
            if m: acc_name = m.group(1)
            if not acc_name:
                m2 = re.search(r'"username"\s*:\s*"([^"]+)"', html)
                if m2: acc_name = m2.group(1)

            # جرب نمط display_url (صورة رئيسية) و edge_sidecar (كاروسيل)
            for match in re.finditer(r'"display_url":"([^"]+)"', html):
                u = match.group(1).encode().decode('unicode_escape')
                image_urls.append(u)

            # فيديو داخل بوست صور أحياناً يكون فيه clip صوتي فقط
            vid_match = re.search(r'"video_url":"([^"]+)"', html)
            if vid_match:
                audio_url = vid_match.group(1).encode().decode('unicode_escape')

            image_urls = list(dict.fromkeys(image_urls))
            return image_urls, audio_url, acc_name
        except Exception as e:
            logger.warning(f"[Insta scrape] {e}")
            return [], None, username

    def _extract_image_urls(info):
        """استخرج روابط الصور من info object (يدعم /p/ carousel) — يُستخدم لو yt-dlp نجح"""
        urls = []
        if not info: return urls
        entries = info.get('entries') or []
        if entries:
            for e in entries:
                got = False
                for f in e.get('formats', []):
                    fu = f.get('url', '')
                    if f.get('ext') in ('jpg', 'jpeg', 'png', 'webp') or \
                       (fu and any(x in fu for x in ('jpg', 'jpeg', 'png', 'webp', 'cdninstagram')) and '.mp4' not in fu):
                        urls.append(fu)
                        got = True
                        break
                if not got and e.get('thumbnail'):
                    urls.append(e['thumbnail'])
        else:
            got = False
            for f in info.get('formats', []):
                fu = f.get('url', '')
                if f.get('ext') in ('jpg', 'jpeg', 'png', 'webp') or \
                   (fu and 'cdninstagram' in fu and '.mp4' not in fu):
                    urls.append(fu)
                    got = True
                    break
            if not got and info.get('thumbnail'):
                urls.append(info['thumbnail'])
        return list(dict.fromkeys(urls))

    def _extract_audio_url(info):
        if not info: return None
        candidates = [info] + (info.get('entries') or [])
        for c in candidates:
            for f in c.get('formats', []):
                acodec = f.get('acodec', 'none')
                vcodec = f.get('vcodec', 'none')
                if acodec != 'none' and vcodec == 'none':
                    return f.get('url')
        return None

    def _dl():
        title = username or 'انستغرام'
        image_urls_from_info = []
        audio_url = None
        is_photo_post = False
        ytdlp_failed = False

        # الخطوة 1: جلب المعلومات عبر yt-dlp أولاً
        try:
            info_opts = {**base_opts, 'skip_download': True, 'noplaylist': not use_playlist}
            with YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    acc_name = (info.get('uploader') or info.get('channel') or
                                info.get('uploader_id') or title)
                    title = acc_name or title
                    image_urls_from_info = _extract_image_urls(info)
                    audio_url = _extract_audio_url(info)
                    entries = info.get('entries') or []
                    if entries:
                        has_real_video = any(
                            any(f.get('vcodec', 'none') != 'none' and f.get('ext') == 'mp4' for f in e.get('formats', []))
                            for e in entries
                        )
                        is_photo_post = not has_real_video
                    elif not any(f.get('vcodec', 'none') != 'none' for f in info.get('formats', [])):
                        is_photo_post = True
        except Exception as e:
            logger.warning(f"[Insta info yt-dlp] {e}")
            ytdlp_failed = True

        # الخطوة 1ب: إذا yt-dlp فشل تماماً (No video formats found وشبهه) — استخدم الـ scraper المباشر
        if ytdlp_failed or not image_urls_from_info:
            scraped_imgs, scraped_audio, scraped_name = _scrape_page_json(url)
            if scraped_imgs:
                image_urls_from_info = scraped_imgs
                is_photo_post = True
                title = scraped_name or title
                if not audio_url:
                    audio_url = scraped_audio

        # الخطوة 2: محاولة تحميل الفيديو (فقط لو مو بوست صور خالص ولم يفشل yt-dlp)
        if not is_photo_post and not ytdlp_failed:
            for fmt_opts in [
                {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                 'merge_output_format': 'mp4', 'noplaylist': not use_playlist},
                {'format': 'best[ext=mp4]/best', 'noplaylist': not use_playlist},
            ]:
                try:
                    opts = {**base_opts, **fmt_opts}
                    with YoutubeDL(opts) as ydl:
                        ydl.extract_info(url, download=True)
                    if any(f.endswith(('.mp4', '.webm', '.mkv')) for f in os.listdir(tmp)):
                        break
                except Exception as e:
                    logger.warning(f"[Insta video dl] {e}")

        # الخطوة 3: تحميل الصور من الروابط مباشرة
        if image_urls_from_info:
            hdrs = {'User-Agent': ua, 'Referer': 'https://www.instagram.com/'}
            for idx, img_url in enumerate(image_urls_from_info[:20]):
                try:
                    r = requests.get(img_url, headers=hdrs, timeout=20)
                    if r.status_code == 200 and len(r.content) > 5000:
                        ext = 'jpg'
                        ct = r.headers.get('content-type', '')
                        if 'png' in ct: ext = 'png'
                        elif 'webp' in ct: ext = 'webp'
                        fpath = os.path.join(tmp, f'img_{idx:03d}.{ext}')
                        with open(fpath, 'wb') as f:
                            f.write(r.content)
                except Exception as e:
                    logger.warning(f"[Insta img dl] {e}")

        # الخطوة 4: تحميل الصوت المستقل — اسم الملف = اسم الحساب
        audio_path = None
        if is_photo_post and audio_url:
            try:
                r = requests.get(audio_url, headers={'User-Agent': ua}, timeout=25)
                if r.status_code == 200 and len(r.content) > 2000:
                    safe_name = re.sub(r'[^\w\-]', '_', title or username or 'audio')[:50]
                    ext = 'mp4' if '.mp4' in audio_url else 'm4a'
                    audio_path = os.path.join(tmp, f'{safe_name}.{ext}')
                    with open(audio_path, 'wb') as f:
                        f.write(r.content)
            except Exception as e:
                logger.warning(f"[Insta audio dl] {e}")

        all_files = [os.path.join(tmp, f) for f in os.listdir(tmp) if os.path.isfile(os.path.join(tmp, f))]
        videos = sorted(
            [f for f in all_files if f.endswith(('.mp4', '.webm', '.mkv')) and f != audio_path],
            key=os.path.getsize, reverse=True
        )
        video_stems = {os.path.splitext(v)[0] for v in videos}
        images = sorted(
            [f for f in all_files
             if f.endswith(('.jpg', '.jpeg', '.png', '.webp'))
             and os.path.getsize(f) > 3000
             and os.path.splitext(f)[0] not in video_stems],
            key=os.path.getsize, reverse=True
        )
        return videos, images, title, audio_path

    async def _send(videos, images, title, audio_path):
        await wm.edit_text("📤 جاري الرفع...")
        for v in videos[:5]:
            if os.path.getsize(v) < 50 * 1024 * 1024:
                with open(v, 'rb') as f:
                    await send_safe(ctx.bot.send_video(cid, f, caption=f"📸 {title[:60]}", supports_streaming=True))
        if images:
            for i in range(0, min(len(images), 20), 10):
                batch = images[i:i + 10]
                if len(batch) == 1:
                    with open(batch[0], 'rb') as f:
                        await ctx.bot.send_photo(cid, f, caption=f"📸 {title[:60]}")
                else:
                    handles = []; grp = []
                    for img in batch:
                        fh = open(img, 'rb'); handles.append(fh)
                        grp.append(InputMediaPhoto(fh))
                    try: await ctx.bot.send_media_group(cid, grp)
                    finally:
                        for fh in handles: fh.close()
                if i + 10 < len(images): await asyncio.sleep(1)
        if audio_path and os.path.exists(audio_path):
            perf_name = username or title or 'Instagram'
            with open(audio_path, 'rb') as f:
                await ctx.bot.send_audio(cid, f, title=perf_name, performer=perf_name)
        await wm.delete()

    try:
        videos, images, title, audio_path = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if not videos and not images and not audio_path:
            await send_error(
                ctx, cid, user,
                dev_msg=(f"⚙️ [DEV] انستغرام — ما لقيت محتوى.\n"
                         f"cookies={'موجودة' if has_cookies else 'غير موجودة'}\n"
                         f"الرابط: <code>{url[:200]}</code>"),
                user_msg="❌ ما لقيت محتوى. تأكد أن الحساب عام.",
                target_message=wm
            )
            return
        await _send(videos, images, title, audio_path)
    except Exception as e:
        err = str(e)
        logger.error(f"[Insta] {err}")
        if 'login' in err.lower() or 'checkpoint' in err.lower():
            await send_error(
                ctx, cid, user,
                dev_msg=f"⚙️ [DEV] انستغرام يطلب تسجيل دخول (كوكيز منتهية):\n<code>{err[:300]}</code>",
                user_msg="🔒 تعذر التحميل. حاول مرة أخرى لاحقاً.",
                target_message=wm
            )
        elif 'private' in err.lower():
            await send_error(
                ctx, cid, user,
                dev_msg=f"⚙️ [DEV] انستغرام — الحساب خاص:\n<code>{err[:300]}</code>",
                user_msg="❌ الحساب خاص.",
                target_message=wm
            )
        else:
            await send_error(
                ctx, cid, user,
                dev_msg=f"⚙️ [DEV] خطأ انستغرام:\n<code>{err[:300]}</code>",
                user_msg="❌ حدث خطأ، حاول مرة أخرى لاحقاً.",
                target_message=wm
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

async def insta_handler(upd, ctx, url, cid):
    """انستغرام — ريلز + صور + ستوريات"""
    if await platform_blocked(upd, 'instagram'): return
    msg = upd.message
    has_cookies = os.path.exists('cookies.txt')
    is_story = '/stories/' in url

    if is_story:
        if not has_cookies:
            return await msg.reply_text(
                "🔒 <b>تحميل الستوريات يحتاج كوكيز انستغرام</b>\n\n"
                "الكوكيز غير موجودة على السيرفر.\n"
                "أضف <code>COOKIES_DATA</code> بـ Railway.",
                parse_mode="HTML"
            )
        # استخرج اليوزرنيم من الرابط
        m = re.search(r'/stories/([^/?]+)', url)
        username = m.group(1) if m else 'مجهول'
        # رابط كل الستوريات
        all_url = f"https://www.instagram.com/stories/{username}/"

        # خزّن بيانات الستوري
        shash = str(random.randint(10000,99999))
        ctx.bot_data[f'ist_{shash}'] = {'url': url, 'all_url': all_url, 'uname': username}

        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("📥 هذا الستوري", callback_data=f"ist_one_{shash}"),
            InlineKeyboardButton("📥 جميع الستوريات", callback_data=f"ist_all_{shash}")
        ]])
        return await msg.reply_text(
            f"📸 <b>ستوريات @{username}</b>\nاختر:",
            parse_mode="HTML", reply_markup=markup
        )

    # منشورات عادية (ريلز / صور)
    wm = await msg.reply_text("📸 جاري التحميل من انستغرام...")
    await _insta_download_and_send(ctx, cid, url, wm, user=msg.from_user)


async def insta_stories_handler(upd, ctx, username, cid):
    """ستوري @username — يعرض زرين"""
    if await platform_blocked(upd, 'instagram'): return
    msg = upd.message
    username = username.lstrip('@').strip()
    has_cookies = os.path.exists('cookies.txt')

    if not has_cookies:
        return await msg.reply_text(
            "🔒 <b>تحميل الستوريات يحتاج كوكيز انستغرام</b>\n\n"
            "أضف <code>COOKIES_DATA</code> من انستغرام.",
            parse_mode="HTML"
        )

    all_url = f"https://www.instagram.com/stories/{username}/"
    shash = str(random.randint(10000,99999))
    ctx.bot_data[f'ist_{shash}'] = {'url': all_url, 'all_url': all_url, 'uname': username}

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("📥 آخر ستوري", callback_data=f"ist_one_{shash}"),
        InlineKeyboardButton("📥 جميع الستوريات", callback_data=f"ist_all_{shash}")
    ]])
    await msg.reply_text(
        f"📸 <b>ستوريات @{username}</b>\nاختر:",
        parse_mode="HTML", reply_markup=markup
    )


async def pinterest_handler(upd, ctx, url, cid):
    """بينترست — فيديو وصور"""
    if await platform_blocked(upd, 'pinterest'): return
    msg = upd.message
    wm = await msg.reply_text("📌 جاري التحميل من بينترست...")
    tmp = tempfile.mkdtemp()

    def _get_info():
        opts = {'quiet':True,'nocheckcertificate':True,'skip_download':True,'geo_bypass':True}
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    def _dl():
        opts = {
            'quiet':True,'nocheckcertificate':True,'geo_bypass':True,
            'ffmpeg_location':FFMPEG,
            'outtmpl':os.path.join(tmp,'%(id)s.%(ext)s'),
            'format':'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
            'merge_output_format':'mp4',
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            all_files = [os.path.join(tmp,f) for f in os.listdir(tmp) if os.path.isfile(os.path.join(tmp,f))]
            if all_files:
                best = max(all_files, key=os.path.getsize)
                return best, info.get('title','بينترست')
        return None, 'بينترست'

    try:
        info = await asyncio.get_running_loop().run_in_executor(None, _get_info)
        thumb = info.get('thumbnail','') if info else ''
        title = info.get('title','بينترست') if info else 'بينترست'

        try:
            fp, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
            if fp and os.path.exists(fp):
                await wm.edit_text("📤 جاري الرفع...")
                ext = fp.rsplit('.',1)[-1].lower()
                if ext in ('mp4','webm','mkv'):
                    with open(fp,'rb') as f: await send_safe(ctx.bot.send_video(cid,f,caption=f"📌 {title[:60]}",supports_streaming=True))
                else:
                    with open(fp,'rb') as f: await ctx.bot.send_photo(cid,f,caption=f"📌 {title[:60]}")
                return await wm.delete()
        except Exception as e2:
            logger.warning(f"[Pinterest] dl failed: {e2}")

        # fallback — صورة من الـ thumbnail
        if thumb:
            headers = {'User-Agent':'Mozilla/5.0','Referer':'https://www.pinterest.com/'}
            hq = re.sub(r'/\d+x/', '/originals/', thumb)
            for img_url in [hq, thumb]:
                try:
                    r = requests.get(img_url, headers=headers, timeout=15)
                    if r.status_code == 200 and len(r.content) > 1000:
                        await ctx.bot.send_photo(cid, r.content, caption=f"📌 {title[:60]}")
                        return await wm.delete()
                except Exception: pass

        await send_error(
            ctx, cid, msg.from_user,
            dev_msg=f"⚙️ [DEV] بينترست — لا فيديو ولا صورة قابلة للتحميل:\n<code>{url[:200]}</code>",
            user_msg="❌ ما قدرت أحمل من هذا الرابط. تأكد أن الـ Pin عام.",
            target_message=wm
        )
    except Exception as e:
        logger.error(f"[Pinterest] {e}")
        await send_error(
            ctx, cid, msg.from_user,
            dev_msg=f"⚙️ [DEV] خطأ بينترست:\n<code>{str(e)[:400]}</code>",
            user_msg="❌ فشل التحميل من بينترست.",
            target_message=wm
        )
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def music_handler(upd, ctx, url, cid, platform="🎵"):
    """تحميل صوت بأعلى جودة (320kbps MP3)"""
    if await platform_blocked(upd, 'soundcloud' if 'soundcloud' in url else 'youtube'): return
    msg = upd.message
    wm = await msg.reply_text(f"{platform} جاري تحميل الصوت بأعلى جودة...")
    tmp = tempfile.mkdtemp()
    is_yt = bool(re.search(r'(youtube\.com|youtu\.be|music\.youtube\.com)', url))
    opts = {
        'outtmpl': os.path.join(tmp,'%(title)s.%(ext)s'),
        'quiet':True,'nocheckcertificate':True,'geo_bypass':True,
        'ffmpeg_location':FFMPEG,
        'format':'bestaudio/best',
        'writethumbnail': True,  # تحميل صورة الغلاف
        'postprocessors': [
            {'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'320'},
            {'key':'FFmpegMetadata','add_metadata':True},   # اسم + مغني + ألبوم
            {'key':'EmbedThumbnail'},                       # صورة الغلاف داخل MP3
        ],
        'http_headers':{'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'},
    }
    if is_yt:
        opts['extractor_args'] = {'youtube': {'player_client': ['tv_embedded', 'ios', 'android']}}
    def _dl():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp):
                if f.endswith('.mp3'): return os.path.join(tmp,f), info.get('title',''), info.get('uploader','') or info.get('artist','') or info.get('creator','')
        return None,'',''
    try:
        fp,title,artist = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if fp and os.path.exists(fp) and os.path.getsize(fp) > TG_MAX_BYTES:
            await wm.edit_text("❌ الملف أكبر من 50MB (حد تيليقرام للبوتات).\n• جرب مقطع أقصر")
        elif fp and os.path.exists(fp):
            await wm.edit_text("📤 جاري الرفع...")
            with open(fp,'rb') as f:
                await ctx.bot.send_audio(
                    cid, f,
                    title=title or "audio",
                    performer=artist or "Unknown",
                    caption=f"{platform} <b>{title[:60]}</b>" if title else platform,
                    parse_mode="HTML"
                )
            await wm.delete()
        else:
            await wm.edit_text("❌ فشل التحميل.")
    except Exception as e:
        err = str(e)
        logger.error(f"[Music] {err}")
        if 'sign in' in err.lower() or 'bot' in err.lower():
            has_yt_c = 'youtube.com' in open('cookies.txt').read() if os.path.exists('cookies.txt') else False
            if not has_yt_c:
                await wm.edit_text(
                    "❌ يوتيوب يطلب تسجيل دخول.\n\n"
                    "🍪 أضف كوكيز يوتيوب لـ COOKIES_DATA\n"
                    "(نفس طريقة X — من youtube.com أو music.youtube.com)"
                )
            else:
                await wm.edit_text("❌ يوتيوب يرفض الكوكيز. جدّدها.")
        else:
            await wm.edit_text(f"❌ فشل التحميل: {err[:100]}")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def spotify_handler(upd, ctx, url, cid):
    """سبوتيفاي — تحميل عبر yt-dlp مباشرة (لا يحتاج Deno)"""
    if await platform_blocked(upd, 'spotify'): return
    msg = upd.message
    wm = await msg.reply_text("🎧 جاري التحميل من سبوتيفاي...")
    tmp = tempfile.mkdtemp()

    def _dl():
        import sys, shutil as _sh
        # spotdl مع --audio youtube-music يستخدم yt-dlp ولا يحتاج Deno
        spotdl = _sh.which('spotdl') or None
        if not spotdl:
            spotdl = os.path.join(os.path.dirname(sys.executable), 'spotdl')
        if not spotdl or not os.path.exists(spotdl):
            # fallback: شغّله كـ module
            spotdl = None

        env = os.environ.copy()
        env['PATH'] = os.path.dirname(FFMPEG) + os.pathsep + env.get('PATH', '')

        base_cmd = (
            [spotdl, url, '--output', tmp, '--format', 'mp3', '--bitrate', '320k', '--threads', '1']
            if spotdl else
            [sys.executable, '-m', 'spotdl', url, '--output', tmp,
             '--format', 'mp3', '--bitrate', '320k', '--threads', '1']
        )
        # جرب عدة مصادر: youtube-music أولاً ثم soundcloud
        last_stderr = ''
        for audio_src in ['youtube-music', 'soundcloud', 'youtube']:
            try:
                cmd = base_cmd + ['--audio', audio_src]
                logger.info(f"[spotdl] trying {audio_src}")
                r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True,
                                   timeout=240, env=env)
                files_now = [os.path.join(tmp, f) for f in os.listdir(tmp)
                             if f.endswith(('.mp3', '.m4a', '.ogg'))]
                if files_now:
                    logger.info(f"[spotdl] success with {audio_src}")
                    return files_now, r.stdout, r.stderr
                last_stderr = r.stderr
            except Exception as e:
                logger.warning(f"[spotdl] {audio_src} failed: {e}")
                last_stderr = str(e)
        return [], '', last_stderr

    try:
        files, stdout, stderr = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if not files:
            await send_error(
                ctx, cid, msg.from_user,
                dev_msg=f"⚙️ [DEV] سبوتيفاي فشل — stderr:\n<code>{(stderr or '')[:400]}</code>",
                user_msg=("❌ فشل التحميل من سبوتيفاي.\n\n"
                          "💡 جرب البحث عن الأغنية بيوتيوب ميوزك وأرسل رابطها 🎵"),
                target_message=wm
            )
            return
        await wm.edit_text(f"📤 جاري الرفع {len(files)} مقطع...")
        for fp in files[:10]:
            name = os.path.basename(fp).rsplit('.', 1)[0]
            with open(fp, 'rb') as f:
                await ctx.bot.send_audio(cid, f,
                    title=name[:64], caption=f"🎧 {name[:60]}")
        await wm.delete()
    except Exception as e:
        logger.error(f"[Spotify] {e}")
        await send_error(
            ctx, cid, msg.from_user,
            dev_msg=f"⚙️ [DEV] خطأ سبوتيفاي:\n<code>{str(e)[:400]}</code>",
            user_msg="❌ حدث خطأ، حاول مرة أخرى لاحقاً.",
            target_message=wm
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def tiktok_user_info(upd, ctx, username, cid):
    """معلومات حساب تيك توك — بأسلوب بطاقة (اسم/يوزر/صورة/ID) مثل بطاقة مستخدم جديد"""
    msg = upd.message
    username = username.lstrip('@').strip()

    if not username:
        return await msg.reply_text("❗ مثال: <code>تيك codexpert</code>", parse_mode="HTML")

    wm = await msg.reply_text(f"🔍 جاري جلب معلومات @{username}...")

    def _code_to_flag(cc: str) -> str:
        """حوّل أي كود ISO ثنائي (مثل IQ) لعلمه 🇮🇶 تلقائياً — بدون قائمة محدودة"""
        cc = (cc or '').strip().upper()
        if len(cc) != 2 or not cc.isalpha():
            return ''
        try:
            return ''.join(chr(0x1F1E6 + ord(ch) - ord('A')) for ch in cc)
        except Exception:
            return ''

    # أسماء دول كاملة (بالإنجليزي/بالعربي) قد يرجعها الـ API أحياناً بدل الكود الثنائي
    COUNTRY_NAME_TO_CODE = {
        'iraq':'IQ','العراق':'IQ','saudi arabia':'SA','السعودية':'SA',
        'united states':'US','usa':'US','united kingdom':'GB','uk':'GB',
        'uae':'AE','united arab emirates':'AE','الامارات':'AE','مصر':'EG','egypt':'EG',
        'turkey':'TR','تركيا':'TR','iran':'IR','ايران':'IR','russia':'RU','روسيا':'RU',
        'germany':'DE','المانيا':'DE','france':'FR','فرنسا':'FR','india':'IN','الهند':'IN',
        'china':'CN','الصين':'CN','japan':'JP','اليابان':'JP','south korea':'KR','كوريا الجنوبية':'KR',
        'brazil':'BR','البرازيل':'BR','kuwait':'KW','الكويت':'KW','qatar':'QA','قطر':'QA',
        'bahrain':'BH','البحرين':'BH','oman':'OM','عمان':'OM','jordan':'JO','الاردن':'JO',
        'syria':'SY','سوريا':'SY','lebanon':'LB','لبنان':'LB','yemen':'YE','اليمن':'YE',
        'libya':'LY','ليبيا':'LY','tunisia':'TN','تونس':'TN','algeria':'DZ','الجزائر':'DZ',
        'morocco':'MA','المغرب':'MA','sudan':'SD','السودان':'SD','pakistan':'PK','باكستان':'PK',
    }

    def _resolve_country_flag(raw: str):
        """يرجع (flag_emoji, display_code_or_name) من قيمة region/location مهما كان شكلها"""
        raw = (raw or '').strip()
        if not raw:
            return '', ''
        # حالة 1: كود ثنائي مباشر (IQ, SA...)
        flag = _code_to_flag(raw)
        if flag:
            return flag, raw.upper()
        # حالة 2: اسم دولة كامل (عربي أو إنجليزي)
        code = COUNTRY_NAME_TO_CODE.get(raw.lower().strip())
        if code:
            return _code_to_flag(code), raw
        # حالة 3: ما قدرنا نطابقها — أرجع بدون علم لكن نعرض القيمة الخام بدل "غير معروف"
        return '🌍', raw

    def _fetch_tikwm():
        """محاولة عبر tikwm (endpoints متعددة، بعضها معطّل حالياً فنجرب أكثر من واحد)"""
        endpoints = [
            f"https://www.tikwm.com/api/user/info?unique_id={username}&count=1",
            f"https://tikwm.com/api/user/info?unique_id={username}",
            f"https://www.tikwm.com/api/user/info/?unique_id={username}",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
            "Referer": "https://www.tikwm.com/",
            "Accept": "application/json",
        }
        for ep in endpoints:
            try:
                r = requests.get(ep, headers=headers, timeout=20)
                data = r.json()
                if data.get('code') == 0 and data.get('data'):
                    return data
            except Exception as e:
                logger.warning(f"[TT info tikwm] {ep}: {e}")
                continue
        return None

    def _fetch_ytdlp():
        """fallback: استخدم yt-dlp لجلب أول فيديو من صفحة المستخدم واستخراج بياناته"""
        try:
            opts = {
                'quiet': True, 'nocheckcertificate': True, 'geo_bypass': True,
                'skip_download': True, 'playlist_items': '1',
                'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0'},
            }
            if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.tiktok.com/@{username}", download=False)
                entry = info
                if info and info.get('entries'):
                    ents = list(info['entries'])
                    entry = ents[0] if ents else info
                if not entry: return None
                return {
                    'code': 0,
                    'data': {
                        'user': {
                            'nickname': entry.get('uploader') or username,
                            'id': entry.get('uploader_id') or entry.get('channel_id') or '',
                            'signature': entry.get('description', '') or '',
                            'avatarLarger': entry.get('uploader_url', '') and entry.get('thumbnail', ''),
                            'avatarThumb': entry.get('thumbnail', ''),
                            'verified': False,
                        },
                        'stats': {
                            'followerCount': entry.get('channel_follower_count') or 0,
                        }
                    }
                }
        except Exception as e:
            logger.warning(f"[TT info yt-dlp fallback] {e}")
            return None

    def _fetch():
        data = _fetch_tikwm()
        if data: return data, 'tikwm'
        data = _fetch_ytdlp()
        if data: return data, 'ytdlp'
        return None, None

    try:
        data, source = await asyncio.get_running_loop().run_in_executor(None, _fetch)

        if not data or not data.get('data'):
            await wm.edit_text(
                f"❌ ما لقيت حساب @{username}.\n"
                "تأكد من اليوزرنيم."
            )
            return

        d = data['data']
        u = d.get('user', d)
        stats = d.get('stats', u)

        name = u.get('nickname') or u.get('name') or username
        uid_str = str(u.get('id', '—')) or '—'
        followers = (stats.get('followerCount') or u.get('followerCount') or d.get('fans') or 0)
        following = (stats.get('followingCount') or u.get('followingCount') or d.get('following') or 0)
        likes = (stats.get('heartCount') or u.get('heartCount') or stats.get('diggCount') or d.get('heart') or 0)
        videos_count = (stats.get('videoCount') or u.get('videoCount') or d.get('video') or 0)
        bio = u.get('signature', '') or '—'
        verified = "✅ موثق" if (u.get('verified') or u.get('isVerified')) else "❌ غير موثق"
        private = "🔒 خاص" if (u.get('privateAccount') or u.get('secret')) else "🌐 عام"
        avatar = u.get('avatarLarger') or u.get('avatarMedium') or u.get('avatarThumb') or u.get('avatar', '')
        raw_region = u.get('region') or u.get('location') or ''
        flag_emoji, display_region = _resolve_country_flag(raw_region)
        country_str = f"{flag_emoji} {display_region}" if display_region else "🌍 غير معروف"

        create_ts = u.get('createTime') or u.get('createtime') or 0
        joined_str = ""
        if create_ts:
            try:
                import datetime
                joined_str = "\n📅 <b>تاريخ الانضمام:</b> " + datetime.datetime.fromtimestamp(int(create_ts)).strftime('%Y/%m/%d')
            except Exception: pass

        # بطاقة على طراز "مستخدم جديد": الاسم، اليوزر، الصورة، الـ ID بارزين بالأعلى
        txt = (
            f"🆕 <b>بطاقة مستخدم تيك توك</b>\n\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"📛 <b>اليوزر:</b> @{username}\n"
            f"🆔 <b>الآيدي:</b> <code>{uid_str}</code>\n"
            f"───────────────\n"
            f"🌍 <b>الدولة:</b> {country_str}\n"
            f"✅ <b>التوثيق:</b> {verified}\n"
            f"🔒 <b>الحساب:</b> {private}\n"
            f"👥 <b>المتابعون:</b> {followers:,}\n"
            f"➡️ <b>يتابع:</b> {following:,}\n"
            f"❤️ <b>الإعجابات:</b> {likes:,}\n"
            f"🎬 <b>الفيديوهات:</b> {videos_count:,}\n"
            f"📝 <b>البايو:</b> {bio[:150]}"
            f"{joined_str}\n\n"
            f"🔗 <a href='https://www.tiktok.com/@{username}'>فتح الحساب</a>"
        )
        if source == 'ytdlp':
            txt += "\n\n<i>ℹ️ بعض الإحصائيات قد تكون غير مكتملة (مصدر بديل)</i>"

        await wm.delete()
        if avatar:
            try:
                await ctx.bot.send_photo(cid, avatar, caption=txt, parse_mode="HTML")
                return
            except Exception as e:
                logger.warning(f"[TT info avatar] {e}")
        await msg.reply_text(txt, parse_mode="HTML")

    except Exception as e:
        logger.error(f"[TT info] {e}")
        await wm.edit_text(f"❌ خطأ: {str(e)[:100]}")


async def cmd_admin(upd, ctx):
    """لوحة تحكم المطور — للمطور فقط"""
    msg = upd.message
    if not is_dev(msg.from_user):
        return await msg.reply_text("❌ هذا الأمر للمطور فقط.")
    await register_user(upd, ctx)   # للمطور: يحفظ chat_id حتى توصله إشعارات المستخدمين الجدد
    text, markup = admin_main(ctx.bot.username)
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)

async def cmd_help(upd, ctx):
    """أمر المساعدة"""
    msg = upd.message
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 تواصل مع المطور", url="https://t.me/snh_1")
    ]])
    await msg.reply_text(
        "❓ <b>مساعدة ودعم</b>\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📥 <b>التحميل:</b>\n"
        "فقط أرسل الرابط مباشرة وسيتم التحميل تلقائياً\n\n"
        "🔧 <b>أوامر عامة:</b>\n"
        "• قريبا... — الذكاء الاصطناعي\n"
        "• <code>ترجمة [نص]</code> — ترجمة لعربي\n"
        "• <code>حساب [عملية]</code> — حاسبة\n"
        "• <code>تيك @username</code> — معلومات تيك توك\n"
        "• <code>تحويل</code> — رد على فيديو لتحويله لصوت\n"
        "• <code>نرد</code> / <code>عملة</code> / <code>نكتة</code> / <code>ري</code>\n\n"
        "👥 <b>أوامر المجموعات:</b>\n"
        "• اكتب <code>الاوامر</code> في الكروب\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>واجهت مشكلة؟</b>\n"
        "تواصل مع المطور مباشرة 👇",
        parse_mode="HTML",
        reply_markup=markup
    )

async def cmd_ping(upd, ctx):
    """فحص حالة البوت"""
    import time
    t = time.time()
    m = await upd.message.reply_text("🏓 ...")
    ms = round((time.time() - t) * 1000)
    await m.edit_text(
        f"🏓 <b>البوت شغّال!</b>\n"
        f"⚡ Ping: <code>{ms}ms</code>\n"
        f"🤖 @{ctx.bot.username}",
        parse_mode="HTML"
    )

async def cmd_id(upd, ctx):
    """أمر /id للحصول على المعرف"""
    msg = upd.message
    target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
    lines = [
        f"🆔 <b>معرفك:</b> <code>{target.id}</code>",
        f"👤 <b>الاسم:</b> {target.first_name}",
    ]
    if msg.chat.type != 'private':
        lines.append(f"👥 <b>معرف الكروب:</b> <code>{msg.chat_id}</code>")
    await msg.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_start(upd, ctx):
    msg = upd.message
    await register_user(upd, ctx)
    if msg.chat.type == 'private' and msg.text.startswith('/start w_'):
        try:
            parts = msg.text.replace('/start w_','').split('_')
            sender_id,target_id = int(parts[0]),int(parts[1])
            chat_id = int(parts[2].replace('m','-'))
            if msg.from_user.id != sender_id:
                return await msg.reply_text("الرابط مو إلك! ❌")
            ctx.user_data.update({'wt':target_id,'wc':chat_id})
            await msg.reply_text("🔒 *أرسل همستك الآن:*\n_(سيتم إرسالها للكروب تلقائياً)_ 🤫", parse_mode="Markdown")
        except Exception: await msg.reply_text("خطأ في رابط الهمسة.")
    else:
        name = msg.from_user.first_name
        await msg.reply_text(T('start_private', name=_esc(name)), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# 9. معالج الأزرار
# ═══════════════════════════════════════════════════════════════════
async def btn_cb(upd, ctx):
    q = upd.callback_query
    d = q.data

    # همسة
    if d.startswith('show_w_'):
        w = db_get(f"whispers/{d[7:]}")
        if w:
            if q.from_user.id in [w['target'],w['sender']]:
                await q.answer(f"💬 الهمسة:\n\n{w['text']}", show_alert=True)
            else: await q.answer("الهمسة مو إلك! ❌", show_alert=True)
        else: await q.answer("الهمسة قديمة.", show_alert=True)
        return

    # قوائم
    if d.startswith("cmd_"):
        await q.answer()
        m = {"cmd_main":(TEXT_MAIN,mk_main()),"cmd_admin":(TEXT_ADMIN,mk_back()),
             "cmd_fun":(TEXT_FUN,mk_back()),"cmd_dl":(TEXT_DL,mk_back())}
        if d in m: await q.edit_message_text(m[d][0], parse_mode="HTML", reply_markup=m[d][1])
        return

    # تحميل
    if d.startswith("dl_"):
        parts = d.split('_',3)
        if len(parts)<4: return await q.answer()
        action,uid,uhash = parts[1],parts[2],parts[3]
        if str(q.from_user.id) != uid:
            return await q.answer("الأزرار لشخص ثاني! 🚫", show_alert=True)
        await q.answer()
        raw = ctx.bot_data.get(uhash)
        url = raw[0] if isinstance(raw,tuple) else raw
        is_fb = isinstance(raw,tuple) and raw[1]=='facebook'
        is_photo = bool(q.message.photo)
        async def em(t):
            try:
                if is_photo: await q.edit_message_caption(t)
                else: await q.edit_message_text(t)
            except Exception: pass
        if not url: return await em("❌ الرابط منتهي. أعد إرساله.")
        await em("⏳ جاري تحضير الملف...")
        mt = "audio" if action=="audio" else "video"
        ql = action.replace("v","") if action.startswith("v") and action!="video" else "720"

        # إعدادات خاصة لفيس بوك (video+audio merge للجودة الصحيحة)
        if is_fb:
            from yt_dlp import YoutubeDL as YDL
            h = int(ql) if ql.isdigit() else 720
            tmp = tempfile.mkdtemp()
            opts = _base_opts(q.message.message_id)
            opts['outtmpl'] = os.path.join(tmp,'%(id)s.%(ext)s')
            # دمج الفيديو والصوت للحصول على الجودة الصحيحة
            opts['format'] = (f'bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/'
                              f'bestvideo[height<={h}]+bestaudio/'
                              f'best[height<={h}][ext=mp4]/best[height<={h}]/best')
            opts['merge_output_format'] = 'mp4'
            opts['http_headers']['User-Agent'] = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36'
            opts['http_headers']['Referer'] = 'https://www.facebook.com/'
            def _fb_dl():
                with YDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    for f in sorted(os.listdir(tmp), key=lambda x: os.path.getsize(os.path.join(tmp,x)), reverse=True):
                        if f.endswith(('.mp4','.webm','.mkv')): return os.path.join(tmp,f), info.get('title','')
                return None,None
            try:
                fp,title = await asyncio.get_running_loop().run_in_executor(None, _fb_dl)
            except Exception as e:
                logger.error(f"[fb dl] {e}")
                fp,title = None,None
        else:
            fp,title,tmp = await do_download(url,mt,ql,q.message.message_id,q.message.chat_id,ctx,q.message.message_id,is_photo)

        if fp and os.path.exists(fp) and os.path.getsize(fp) > TG_MAX_BYTES:
            await em(f"❌ الملف أكبر من 50MB ({os.path.getsize(fp) // 1048576}MB) — حد تيليقرام للبوتات.\n• جرب جودة أقل")
        elif fp and os.path.exists(fp):
            await em("📤 جاري الرفع...")
            try:
                with open(fp,'rb') as f:
                    if mt=="audio": await ctx.bot.send_audio(q.message.chat_id,f,title=title or "audio")
                    else: await send_safe(ctx.bot.send_video(q.message.chat_id,f,caption=f"✅ {(title or '')[:200]}",supports_streaming=True))
                await q.message.delete()
            except Exception as e: await em(f"❌ فشل الرفع: {str(e)[:80]}")
        else:
            await em("❌ فشل التحميل.\n• جرب جودة أقل\n• أو جرب لاحقاً")
        if tmp: shutil.rmtree(tmp, ignore_errors=True)
        return

    # تحويل فيديو لصوت (من الخاص)
    if d.startswith("convert_audio_"):
        mid = int(d.split("_")[-1])
        await q.answer()
        await q.edit_message_text("🔄 جاري الاستخراج...")
        # البوت يحتاج يجيب الفيديو من الرسالة الأصلية
        try:
            msg_obj = q.message.reply_to_message
            if msg_obj:
                media = msg_obj.video or msg_obj.document
                if media:
                    tf = await media.get_file()
                    inp = f"/tmp/conv_{mid}.mp4"; out = f"/tmp/conv_{mid}.mp3"
                    await tf.download_to_drive(custom_path=inp)
                    subprocess.run([FFMPEG,"-i",inp,"-q:a","0","-map","a",out,"-y"],capture_output=True,timeout=180)
                    if os.path.exists(out):
                        with open(out,'rb') as f: await ctx.bot.send_audio(q.message.chat_id,f,title="audio")
                        await q.message.delete()
                    else: await q.edit_message_text("❌ الملف ما يحتوي صوت.")
                    for p in [inp,out]:
                        try: os.remove(p)
                        except Exception: pass
                else: await q.edit_message_text("❌ ما لقيت الفيديو.")
            else: await q.edit_message_text("❌ ما لقيت الفيديو الأصلي.")
        except Exception as e: await q.edit_message_text(f"❌ خطأ: {str(e)[:80]}")
        return
    if d == "convert_cancel":
        await q.answer("تم الإلغاء")
        await q.message.delete()
        return

    # ── أزرار لوحة المطور ──
    if d.startswith("adm_"):
        if not is_dev(q.from_user):
            return await q.answer("❌ للمطور فقط!", show_alert=True)
        action = d[4:]
        if action.startswith("toggle_"):
            platform = action[7:]
            if platform in _DISABLED_PLATFORMS:
                _DISABLED_PLATFORMS.discard(platform)
                _save_disabled()
                await q.answer(f"✅ {platform} مفعّل")
            else:
                _DISABLED_PLATFORMS.add(platform)
                _save_disabled()
                await q.answer(f"🔴 {platform} موقوف")
            # تحديث الرسالة
            await cmd_admin_refresh(q, ctx)
            return
        if action == "refresh":
            await q.answer("🔄 تم التحديث")
            await cmd_admin_refresh(q, ctx)
            return
        if action == "cookies":
            if os.path.exists('cookies.txt'):
                try:
                    with open('cookies.txt','r') as f: c = f.read()
                    lines = [l for l in c.splitlines() if l and not l.startswith('#') and '\t' in l]
                    domains = set(l.split('\t')[0].lstrip('.') for l in lines)
                    await q.answer(f"✅ {len(lines)} cookies\n{', '.join(sorted(domains))}", show_alert=True)
                except Exception as e:
                    await q.answer(f"❌ {e}", show_alert=True)
            else:
                raw = os.environ.get('COOKIES_DATA','')
                await q.answer(f"❌ cookies.txt غير موجود\nCOOKIES_DATA: {'موجود' if raw else 'مو موجود'} ({len(raw)} حرف)", show_alert=True)
            return
        # ── تعديل الرسائل ──
        if action == "texts":
            await q.answer()
            rows = [[InlineKeyboardButton(("✏️ " if db_get(f"texts/{k}") else "") + m['label'], callback_data=f"adm_t_{k}")]
                    for k, m in TEXTS.items()]
            rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_refresh")])
            try:
                await q.edit_message_text("✏️ <b>تعديل الرسائل</b>\n\nاختر الرسالة اللي تريد تعدلها.\n(✏️ = معدّلة عن الافتراضي)",
                                          parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
            except Exception as e: logger.info(f"[adm_texts] {e}")
            return
        if action.startswith("t_"):
            key = action[2:]
            if key not in TEXTS: return await q.answer("❌ رسالة غير معروفة", show_alert=True)
            await q.answer(); await admin_show_text(q, key); return
        if action.startswith("tr_"):
            key = action[3:]
            if key not in TEXTS: return await q.answer("❌ رسالة غير معروفة", show_alert=True)
            db_set(f"texts/{key}", None)
            await q.answer("↩️ رجعت للنص الافتراضي"); await admin_show_text(q, key); return
        if action.startswith("te_"):
            key = action[3:]
            if key not in TEXTS: return await q.answer("❌ رسالة غير معروفة", show_alert=True)
            ctx.user_data['adm_wait'] = {'kind': 'text', 'key': key, 'ts': time.time()}
            await q.answer()
            vars_line = ("\n<b>الحقول:</b> " + "، ".join(f"<code>{{{k}}}</code> = {d}" for k, d in TEXTS[key]['vars'].items())) if TEXTS[key]['vars'] else ""
            try:
                await q.edit_message_text(
                    f"✏️ <b>{TEXTS[key]['label']}</b>\n\nأرسل <b>النص الجديد</b> الآن بالرسالة الجاية.\n"
                    "تقدر تنسّقه بخيارات تيليجرام (غامق/مائل/كود).{vars_line}\n\n"
                    "اكتب <code>الغاء</code> للإلغاء.".replace("{vars_line}", vars_line),
                    parse_mode="HTML")
            except Exception as e: logger.info(f"[adm_te] {e}")
            return
        # ── مدة حفظ الرسائل ──
        if action == "ret":
            await q.answer(); await admin_show_retention(q); return
        if action.startswith("retset_"):
            try: h = int(action[7:])
            except ValueError: return await q.answer("❌", show_alert=True)
            if not 1 <= h <= 720: return await q.answer("❌ خارج الحد", show_alert=True)
            cfg_set('msg_retention_hours', h)
            await q.answer(f"✅ صارت المدة {_fmt_hours(h)}")
            await admin_show_retention(q); return
        if action == "retcustom":
            ctx.user_data['adm_wait'] = {'kind': 'retention', 'ts': time.time()}
            await q.answer()
            try:
                await q.edit_message_text("✏️ أرسل <b>عدد الساعات</b> (من 1 إلى 720).\nمثال: <code>36</code>\n\nاكتب <code>الغاء</code> للإلغاء.",
                                          parse_mode="HTML")
            except Exception as e: logger.info(f"[adm_retcustom] {e}")
            return
        # ── إشعار المستخدمين الجدد ──
        if action == "newuser":
            on = not cfg_get('notify_new_users', True)
            cfg_set('notify_new_users', on)
            await q.answer("🔔 الإشعارات شغالة" if on else "🔕 الإشعارات موقوفة")
            await cmd_admin_refresh(q, ctx); return
        return

    # ── أزرار ستوريات انستغرام ──
    if d.startswith("ist_"):
        parts = d.split('_')
        action = parts[1]   # one أو all
        shash  = parts[2]
        data   = ctx.bot_data.get(f'ist_{shash}')
        if not data:
            return await q.answer("انتهت صلاحية الأزرار. أرسل الرابط مجدداً.", show_alert=True)

        await q.answer()
        cid_q = q.message.chat_id
        wm    = await q.message.edit_text("⏳ جاري التحميل...")

        url      = data['url']      # رابط الستوري المحدد (أو الكل)
        all_url  = data['all_url']  # رابط كل الستوريات
        uname    = data['uname']

        if action == 'one':
            await _insta_download_and_send(ctx, cid_q, url, wm,
                                           username=uname, download_all=False, is_story=True, user=q.from_user)
        else:
            await _insta_download_and_send(ctx, cid_q, all_url, wm,
                                           username=uname, download_all=True, is_story=True, user=q.from_user)
        ctx.bot_data.pop(f'ist_{shash}', None)
        return

    # إكس أو
    if d.startswith("ttt_"):
        parts = d.split('_')
        if len(parts)<2: return await q.answer()

        if parts[1]=='noop': return await q.answer("الخلية مشغولة! ❌")

        # ضد البوت
        if parts[1]=='vsbot' and len(parts)>=3:
            gid=parts[2]; game=ctx.bot_data.get(f'ttt_{gid}')
            if not game: return await q.answer("اللعبة انتهت!")
            if q.from_user.id != game['players']['X']:
                return await q.answer("مو أنت اللي بدأ!", show_alert=True)
            game['mode']='bot'
            await q.answer(); await q.edit_message_text(
                f"🎮 <b>إكس أو</b>\n👤 {q.from_user.first_name} ❌ vs 🤖 البوت ⭕\n\nدورك! اضغط خلية 👇",
                parse_mode="HTML", reply_markup=ttt_kb(game['board'],gid)); return

        # ضد لاعب مفتوح
        if parts[1]=='vspvp' and len(parts)>=3:
            gid=parts[2]; game=ctx.bot_data.get(f'ttt_{gid}')
            if not game: return await q.answer("اللعبة انتهت!")
            if q.from_user.id != game['players']['X']:
                return await q.answer("مو أنت اللي بدأ!", show_alert=True)
            game['mode']='pvp_open'
            await q.answer(); await q.edit_message_text(
                f"🎮 <b>إكس أو</b>\n❌ {q.from_user.first_name} ينتظر خصم!\n\nاضغط للانضمام 👇",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🙋 انضم كـ ⭕",callback_data=f"ttt_join_{gid}")]])); return

        # انضمام / قبول تحدي
        if parts[1]=='join' and len(parts)>=3:
            gid=parts[2]; game=ctx.bot_data.get(f'ttt_{gid}')
            if not game: return await q.answer("اللعبة انتهت!", show_alert=True)
            jid=q.from_user.id; mode=game.get('mode')
            if mode=='pvp_pending':
                if jid!=game['players']['O']: return await q.answer("التحدي مو إلك! 😅",show_alert=True)
                game['mode']='pvp'
            elif mode=='pvp_open':
                if jid==game['players']['X']: return await q.answer("ما تلعب ضد نفسك! 😂",show_alert=True)
                game['players']['O']=jid; game['mode']='pvp'
            else: return await q.answer("اللعبة بدأت بالفعل!",show_alert=True)
            try:
                xm=await ctx.bot.get_chat_member(q.message.chat_id,game['players']['X'])
                xn=xm.user.first_name
            except Exception: xn="اللاعب الأول"
            await q.answer("✅ قبلت التحدي! ابدأوا!")
            await q.edit_message_text(
                f"🎮 <b>إكس أو PvP</b>\n❌ {xn} vs ⭕ {q.from_user.first_name}\n\nدور ❌ {xn}!",
                parse_mode="HTML", reply_markup=ttt_kb(game['board'],gid)); return

        # رفض
        if parts[1]=='reject' and len(parts)>=3:
            gid=parts[2]; game=ctx.bot_data.get(f'ttt_{gid}')
            if game:
                if q.from_user.id!=game['players'].get('O'):
                    return await q.answer("مو إلك ترفض!",show_alert=True)
                ctx.bot_data.pop(f'ttt_{gid}',None)
            await q.answer("رفضت التحدي!")
            await q.edit_message_text(f"❌ {q.from_user.first_name} رفض التحدي! 😅"); return

        # إعادة
        if parts[1]=='reset' and len(parts)>=3:
            gid=parts[2]
            ctx.bot_data[f'ttt_{gid}']={'board':['']* 9,'turn':'X','players':{'X':None,'O':None},'mode':'bot'}
            await q.answer("لعبة جديدة! 🎮")
            await q.edit_message_text("🎮 <b>إكس أو — جديدة!</b>\n\nاضغط أي خلية ❌",
                parse_mode="HTML",reply_markup=ttt_kb(['']*9,gid)); return

        if len(parts)<3: return await q.answer()
        gid=parts[1]
        try: cell=int(parts[2])
        except Exception: return await q.answer()
        game=ctx.bot_data.get(f'ttt_{gid}')
        if not game: return await q.answer("اللعبة انتهت! ابدأ جديدة 🎮",show_alert=True)

        pid=q.from_user.id
        if game['players'].get('X') is None: game['players']['X']=pid
        cur=game['turn']
        exp=game['players'].get(cur)
        if exp and exp!=pid: return await q.answer(f"مو دورك! دور {'❌' if cur=='X' else '⭕'}",show_alert=True)
        if game.get('mode')=='pvp' and pid not in [game['players'].get('X'),game['players'].get('O')]:
            return await q.answer("أنت مو من هاللعبة! 😅",show_alert=True)
        if game['board'][cell]!='': return await q.answer("الخلية مشغولة!",show_alert=True)

        game['board'][cell]=cur
        w=ttt_winner(game['board'])
        if w:
            sym='❌' if w=='X' else '⭕'
            await q.answer(f"🏆 {sym} فاز!"); 
            await q.edit_message_text(f"🎮 <b>إكس أو</b>\n\n🏆 فاز {sym} <b>{q.from_user.first_name}</b>! 🎉",
                parse_mode="HTML",reply_markup=ttt_kb(game['board'],gid))
            ctx.bot_data.pop(f'ttt_{gid}',None); return
        if '' not in game['board']:
            await q.answer("تعادل! 🤝")
            await q.edit_message_text("🎮 <b>إكس أو</b>\n\n🤝 تعادل!",parse_mode="HTML",reply_markup=ttt_kb(game['board'],gid))
            ctx.bot_data.pop(f'ttt_{gid}',None); return

        game['turn']='O' if cur=='X' else 'X'
        if game.get('mode')=='bot' and game['turn']=='O':
            await asyncio.sleep(0.6)
            mv=ttt_bot(game['board'])
            if mv is not None:
                game['board'][mv]='O'
                w=ttt_winner(game['board'])
                if w:
                    await q.answer("البوت فاز! 🤖")
                    await q.edit_message_text("🎮 <b>إكس أو</b>\n\n🤖 البوت فاز ⭕! حاول ثاني!",
                        parse_mode="HTML",reply_markup=ttt_kb(game['board'],gid))
                    ctx.bot_data.pop(f'ttt_{gid}',None); return
                if '' not in game['board']:
                    await q.answer("تعادل! 🤝")
                    await q.edit_message_text("🎮 إكس أو\n\n🤝 تعادل!",reply_markup=ttt_kb(game['board'],gid))
                    ctx.bot_data.pop(f'ttt_{gid}',None); return
            game['turn']='X'
        await q.answer()
        try: await q.edit_message_reply_markup(ttt_kb(game['board'],gid))
        except Exception: pass
        return

# ═══════════════════════════════════════════════════════════════════
# 10. معالجات متنوعة
# ═══════════════════════════════════════════════════════════════════
async def cmd_admin_refresh(q, ctx=None):
    """تحديث رسالة لوحة المطور"""
    text, markup = admin_main(ctx.bot.username if ctx else None)
    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.info(f"[admin_refresh] {e}")

async def welcome_handler(upd, ctx):
    for m in upd.message.new_chat_members:
        if m.id == ctx.bot.id:
            await upd.message.reply_text(T('group_added'), parse_mode="HTML")
            continue
        if m.is_bot: continue
        s=get_settings(upd.message.chat.id)
        if not s.get("welcome",True): continue
        name=f'<a href="tg://user?id={m.id}">{m.first_name} {m.last_name or ""}</a>'.strip()
        uname = f"@{m.username}" if m.username else "لا يوجد"
        # عدّاد إجمالي الأعضاء بالمجموعة
        try:
            member_count = await ctx.bot.get_chat_member_count(upd.message.chat.id)
            count_line = f"👥 <b>الإجمالي:</b> [{member_count}]\n"
        except Exception:
            count_line = ""
        # بطاقة مستخدم جديد: الاسم، اليوزر، الآيدي، العدّاد
        txt = (
            f"🆕 <b>مستخدم جديد!</b>\n"
            f"{count_line}\n"
            f"👤 <b>الاسم:</b> {name}\n"
            f"📛 <b>اليوزر:</b> {uname}\n"
            f"🆔 <b>الآيدي:</b> <code>{m.id}</code>\n\n" + T('member_welcome')
        )
        try:
            p=await ctx.bot.get_user_profile_photos(m.id,limit=1)
            if p.total_count>0: await ctx.bot.send_photo(upd.message.chat.id,p.photos[0][-1].file_id,caption=txt,parse_mode="HTML")
            else: await upd.message.reply_text(txt,parse_mode="HTML")
        except Exception: await upd.message.reply_text(txt,parse_mode="HTML")

async def edit_handler(upd, ctx):
    if not upd.edited_message: return
    cid,mid=upd.edited_message.chat.id,upd.edited_message.message_id
    if not get_settings(cid).get("edit_notify",True): return
    new=upd.edited_message.text or "[ميديا]"
    old=await msg_get(cid, mid) or "[غير متوفر]"
    await msg_save(cid, mid, new)
    await ctx.bot.send_message(cid,
        f"✏️ <b>تعديل رسالة</b>\n👤 {upd.edited_message.from_user.first_name}\n❌ <code>{old[:200]}</code>\n✅ <code>{new[:200]}</code>",
        parse_mode="HTML")

async def media_filter(upd, ctx):
    msg=upd.message
    if not msg: return
    s=get_settings(msg.chat_id)
    reason=None
    if msg.sticker and s.get("ban_stickers"): reason="الملصقات"
    elif msg.animation and s.get("ban_gifs"): reason="الـ GIF"
    elif msg.video and s.get("ban_videos"): reason="المقاطع"
    elif msg.photo and s.get("ban_photos"): reason="الصور"
    if reason:
        try: await msg.delete()
        except Exception: pass
        try:
            nm=await ctx.bot.send_message(msg.chat_id,f"🚫 {msg.from_user.first_name}، إرسال {reason} ممنوع هنا!")
            await asyncio.sleep(4); await nm.delete()
        except Exception: pass

async def track_msg(upd, ctx):
    if not upd.message or not upd.message.text or upd.message.text.startswith('/'): return
    await msg_save(upd.message.chat.id, upd.message.message_id, upd.message.text)

# ═══════════════════════════════════════════════════════════════════
# 11. المعالج الرئيسي
# ═══════════════════════════════════════════════════════════════════
async def handle_msg(upd, ctx):
    if not upd.message: return
    msg=upd.message; text=(msg.text or "").strip()
    cid=msg.chat_id; uid=msg.from_user.id
    if not text: return

    # ══ خاص ══
    if msg.chat.type=='private':
        wait = ctx.user_data.get('adm_wait')
        if wait and is_dev(msg.from_user):
            return await admin_wait_input(upd, ctx, wait)
        if ctx.user_data.get('wt'):
            # همسة بالخاص
            tid=ctx.user_data.pop('wt'); wc=ctx.user_data.pop('wc',None)
            wid=str(random.randint(100000,999999))
            db_set(f"whispers/{wid}",{'text':text,'sender':uid,'target':tid})
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔒 اقرأ الهمسة",callback_data=f"show_w_{wid}")]])
            try:
                m=await ctx.bot.get_chat_member(wc,tid); tn=m.user.first_name
            except Exception: tn="العضو"
            await ctx.bot.send_message(wc,
                f"🤫 *همسة سرية!*\n👤 من: {msg.from_user.first_name}\n📨 إلى: {tn}\n\n_فقط المستهدف يقدر يقرأها_ 👇",
                reply_markup=markup,parse_mode="Markdown")
            await msg.reply_text("✅ أُرسلت الهمسة بنجاح! 🎉"); return

        # تشغيل/ايقاف الذكاء الاصطناعي
        if text == "تشغيل سيك":
            ctx.user_data['ai'] = True
            return await msg.reply_text("🤖 <b>تم تفعيل الذكاء الاصطناعي!</b>\nكلمني بأي شيء 😊\n\nاكتب <code>ايقاف سيك</code> لإيقافه.", parse_mode="HTML")
        if text == "ايقاف سيك":
            ctx.user_data['ai'] = False
            return await msg.reply_text("😴 تم إيقاف الذكاء الاصطناعي.\nاكتب <code>تشغيل سيك</code> لتفعيله.", parse_mode="HTML")

        # معلومات تيك توك
        mt = re.match(r'^تيك\s+@?(\S+)', text, re.I)
        if mt: await tiktok_user_info(upd, ctx, mt.group(1), cid); return

        # روابط بالخاص
        url = find_url(text)
        if url:
            if host_in(url,'music.youtube.com'): await music_handler(upd,ctx,url,cid,"🎵"); return
            if host_in(url,'soundcloud.com'): await music_handler(upd,ctx,url,cid,"🎶"); return
            if host_in(url,'spotify.com'): await spotify_handler(upd,ctx,url,cid); return
            if host_in(url,'threads.net'): await auto_download(upd,ctx,url,cid,"🧵"); return
            if host_in(url,'youtube.com','youtu.be'): await yt_handler(upd,ctx,url,uid); return
            if host_in(url,'x.com','twitter.com'): await x_handler(upd,ctx,url,uid); return
            if host_in(url,'tiktok.com','douyin.com'): await tiktok_handler(upd,ctx,url,cid,msg.message_id); return
            if host_in(url,'facebook.com','fb.watch','fb.com'): await fb_handler(upd,ctx,url,uid); return
            if host_in(url,'pinterest.com','pin.it'): await pinterest_handler(upd,ctx,url,cid); return  # auto best
        m=re.match(r'^ستوري\s+@?(\S+)',text,re.I)
        if m: await insta_stories_handler(upd,ctx,m.group(1),cid); return
        if url and host_in(url,'instagram.com'): await insta_handler(upd,ctx,url,cid); return

        # تحويل فيديو لصوت بالخاص
        if text == "تحويل":
            rm = msg.reply_to_message
            if not rm:
                return await msg.reply_text(
                    "❗ رد على مقطع فيديو لتحويله لصوت.\n"
                    "أو أرسل الفيديو مباشرة وسأطلب منك التأكيد 🎵"
                )
            media = rm.video or rm.document
            if not media:
                return await msg.reply_text("❗ رد على فيديو أو ملف فيديو.")
            wm = await msg.reply_text("🔄 جاري استخراج الصوت...")
            try:
                tf = await media.get_file()
                inp = f"/tmp/vi_{msg.message_id}.mp4"
                out = f"/tmp/ao_{msg.message_id}.mp3"
                await tf.download_to_drive(custom_path=inp)
                subprocess.run([FFMPEG,"-i",inp,"-q:a","0","-map","a",out,"-y"], capture_output=True, timeout=180)
                if os.path.exists(out):
                    fn = getattr(media,'file_name',None) or f"audio_{msg.message_id}"
                    with open(out,'rb') as a: await msg.reply_audio(a, title=fn.rsplit('.',1)[0])
                    await wm.delete()
                else:
                    await wm.edit_text("❌ الملف ما يحتوي صوت.")
            except subprocess.TimeoutExpired:
                await wm.edit_text("❌ الملف كبير جداً.")
            except Exception as e:
                await wm.edit_text(f"❌ فشل: {str(e)[:100]}")
            finally:
                for p in [inp, out]:
                    try:
                        if os.path.exists(p): os.remove(p)
                    except Exception: pass
            return

        # ترجمة + حاسبة بالخاص
        if text.startswith("ترجمة "):
            src = text[6:].strip()
            if src:
                await ctx.bot.send_chat_action(cid,'typing')
                def _tr():
                    r = requests.get("https://api.mymemory.translated.net/get",
                        params={"q":src,"langpair":"autodetect|ar"}, timeout=10)
                    return r.json().get("responseData",{}).get("translatedText","فشلت الترجمة")
                result = await asyncio.get_running_loop().run_in_executor(None, _tr)
                return await msg.reply_text(f"🌐 <b>الترجمة:</b>\n{result}", parse_mode="HTML")

        if text.startswith("حساب "):
            expr = text[5:].strip()
            try:
                allowed = set('0123456789+-*/.() %')
                if len(expr) <= 50 and '**' not in expr and all(c in allowed or c.isspace() for c in expr):
                    res = eval(expr,{"__builtins__":{}},{"sqrt":math.sqrt,"pi":math.pi,"abs":abs})
                    return await msg.reply_text(f"🔢 <code>{expr}</code> = <b>{res}</b>", parse_mode="HTML")
                return await msg.reply_text("❗ أرقام وعمليات فقط (+، -، *، /) بدون أس، وبحد أقصى 50 حرف.")
            except Exception: return await msg.reply_text("❌ معادلة غلط. مثال: <code>حساب 15 * 3 + 7</code>", parse_mode="HTML")

        if not text.startswith('/'):
            if ctx.user_data.get('ai', False):
                await ctx.bot.send_chat_action(cid,'typing')
                await msg.reply_text(await ask_ai(text))
            else:
                await msg.reply_text(
                    "💡 <b>شو أقدر أسويلك؟</b>\n\n"
                    "📥 أرسل رابط للتحميل (يوتيوب، تيك توك، X، فيس بوك، انستغرام، بينترست)\n"
                    "🎵 يوتيوب ميوزك / ساوند كلاود — أرسل الرابط مباشرة\n"
                    "🤖 <code>الذكاء الاصطناعي — قريبا...\n"
                    "🌐 <code>ترجمة [نص]</code> — ترجمة للعربي\n"
                    "🔢 <code>حساب 5*5+2</code> — حاسبة\n"
                    "🎵 <code>تيك @username</code> — معلومات تيك توك",
                    parse_mode="HTML"
                )
        return

    # ══ كروب ══
    s=get_settings(cid)
    priv_own=await is_priv(upd,ctx,ROLE_OWNER)
    priv_mgr=await is_priv(upd,ctx,ROLE_MGR)

    # ردود تلقائية
    for tr,rp in get_replies(cid):
        if tr.lower() in text.lower(): await msg.reply_text(rp); return

    # كلمات ممنوعة
    for w in s.get("banned_words",[]):
        if w and w.lower() in text.lower():
            try: await msg.delete()
            except Exception: pass
            try:
                nm=await ctx.bot.send_message(cid,f"⚠️ {msg.from_user.first_name}، الرسالة تحتوي كلمة ممنوعة.")
                await asyncio.sleep(4); await nm.delete()
            except Exception: pass
            return

    # ══ أوامر عامة ══
    if text=="الاوامر": return await msg.reply_text(TEXT_MAIN,parse_mode="HTML",reply_markup=mk_main())

    if text=="نسبة الحب" and msg.reply_to_message:
        p=random.randint(0,100)
        bar="💖"*(p//20)+"🤍"*(5-p//20)
        return await msg.reply_text(f"💘 {msg.from_user.first_name} & {msg.reply_to_message.from_user.first_name}\n{bar} <b>{p}%</b>",parse_mode="HTML")

    if text in ("ري","وعد"): return await msg.reply_text(random.choice(WA3ED_LIST))
    if text=="لو خيروك": return await msg.reply_text(random.choice(KHAYROK_LIST))
    if text=="نكتة": return await msg.reply_text(random.choice(JOKES_LIST))
    if text=="نرد": return await msg.reply_text(f"🎲 طاح: <b>{random.randint(1,6)}</b>",parse_mode="HTML")
    if text=="عملة": return await msg.reply_text("🪙 " + random.choice(["صورة! 👑","كتابة! 📝"]))

    if text.startswith("ترجمة "):
        src=text[6:].strip()
        if src:
            await ctx.bot.send_chat_action(cid,'typing')
            def _tr():
                r=requests.get("https://api.mymemory.translated.net/get",params={"q":src,"langpair":"autodetect|ar"},timeout=10)
                return r.json().get("responseData",{}).get("translatedText","فشلت الترجمة")
            result=await asyncio.get_running_loop().run_in_executor(None,_tr)
            return await msg.reply_text(f"🌐 <b>الترجمة:</b>\n{result}",parse_mode="HTML")

    if text.startswith("حساب "):
        expr=text[5:].strip()
        try:
            allowed=set('0123456789+-*/.() %')
            if len(expr) <= 50 and '**' not in expr and all(c in allowed or c.isspace() for c in expr):
                res=eval(expr,{"__builtins__":{}},{"sqrt":math.sqrt,"pi":math.pi})
                return await msg.reply_text(f"🔢 <code>{expr}</code> = <b>{res}</b>",parse_mode="HTML")
            else: return await msg.reply_text("❗ أرقام وعمليات فقط (+، -، *، /) بدون أس، وبحد أقصى 50 حرف.")
        except Exception: return await msg.reply_text("❌ معادلة غلط. مثال: <code>حساب 15 * 3 + 7</code>",parse_mode="HTML")

    if text=="افتار":
        t=msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        p=await t.get_profile_photos(limit=1)
        if p and p.total_count>0: return await msg.reply_photo(p.photos[0][-1].file_id,caption=f"🖼 افتار {t.first_name}")
        return await msg.reply_text("ما حاط صورة بروفايل! 😅")

    if text=="ايدي":
        t=msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
        lang=t.language_code or '?'
        flag=LANG_FLAG.get(lang,'🌐')
        return await msg.reply_text(
            f"📋 <b>معلومات العضو</b>\n\n"
            f"👤 <b>الاسم:</b> {t.first_name} {t.last_name or ''}\n"
            f"🆔 <b>ID:</b> <code>{t.id}</code>\n"
            f"📛 <b>يوزر:</b> {'@'+t.username if t.username else 'لا يوجد'}\n"
            f"🌐 <b>اللغة:</b> {flag} {lang}\n"
            f"💎 <b>بريميوم:</b> {'✅' if getattr(t,'is_premium',False) else '❌'}\n"
            f"🔖 <b>النوع:</b> {'🤖 بوت' if t.is_bot else '👤 مستخدم'}",
            parse_mode="HTML")

    if text=="همسة" and msg.reply_to_message:
        t=msg.reply_to_message.from_user
        if t.is_bot: return await msg.reply_text("ما تهمس لبوت! 😂")
        link=f"t.me/{ctx.bot.username}?start=w_{uid}_{t.id}_{str(cid).replace('-','m')}"
        return await msg.reply_text(f"يا {msg.from_user.first_name}، اضغط واكتب همستك 🤫",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔒 اكتب الهمسة",url=link)]]))

    if text=="تحويل":
        rm=msg.reply_to_message
        if not rm: return await msg.reply_text("❗ رد على مقطع فيديو.")
        media=rm.video or rm.document
        if not media: return await msg.reply_text("❗ رد على فيديو أو ملف.")
        wm=await msg.reply_text("🔄 جاري استخراج الصوت...")
        try:
            tf=await media.get_file()
            inp=f"/tmp/vi_{msg.message_id}.mp4"; out=f"/tmp/ao_{msg.message_id}.mp3"
            await tf.download_to_drive(custom_path=inp)
            subprocess.run([FFMPEG,"-i",inp,"-q:a","0","-map","a",out,"-y"],capture_output=True,timeout=180)
            if os.path.exists(out):
                fn=getattr(media,'file_name',None) or f"audio_{msg.message_id}"
                with open(out,'rb') as a: await msg.reply_audio(a,title=fn.rsplit('.',1)[0])
                await wm.delete()
            else: await wm.edit_text("❌ الملف ما يحتوي صوت.")
        except subprocess.TimeoutExpired: await wm.edit_text("❌ الملف كبير جداً.")
        except Exception as e: await wm.edit_text(f"❌ فشل: {str(e)[:100]}")
        finally:
            for p in [inp,out]:
                if os.path.exists(p): os.remove(p)
        return

    # إكس أو
    if text in ("اكس او","اكسو","لعبة","إكس أو"):
        gid=str(random.randint(10000,99999))
        challenged=None
        if msg.reply_to_message and not msg.reply_to_message.from_user.is_bot:
            challenged=msg.reply_to_message.from_user
        elif msg.entities:
            for e in msg.entities:
                if e.type=="text_mention" and e.user and not e.user.is_bot:
                    challenged=e.user; break
        if challenged and challenged.id!=uid:
            ctx.bot_data[f'ttt_{gid}']={'board':['']*9,'turn':'X','players':{'X':uid,'O':challenged.id},'mode':'pvp_pending'}
            return await msg.reply_text(
                f"⚔️ <b>تحدي إكس أو!</b>\n❌ {msg.from_user.first_name} يتحدى ⭕ {challenged.first_name}!\n\nهل تقبل؟ 🤔",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ قبول",callback_data=f"ttt_join_{gid}"),
                    InlineKeyboardButton("❌ رفض",callback_data=f"ttt_reject_{gid}")
                ]]))
        else:
            ctx.bot_data[f'ttt_{gid}']={'board':['']*9,'turn':'X','players':{'X':uid,'O':None},'mode':'selecting'}
            return await msg.reply_text(
                f"🎮 <b>إكس أو</b> — {msg.from_user.first_name}\nاختار طريقة اللعب:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🤖 ضد البوت",callback_data=f"ttt_vsbot_{gid}"),
                    InlineKeyboardButton("👥 ضد لاعب",callback_data=f"ttt_vspvp_{gid}")
                ]]))

    # زواج
    if text=="زواج" and msg.reply_to_message:
        t=msg.reply_to_message.from_user
        if t.is_bot or t.id==uid: return await msg.reply_text("ما ينفع! 😅")
        if db_get(f"marriages/{cid}/{uid}"): return await msg.reply_text("أنت متزوج! اكتب 'طلاق' أولاً.")
        db_set(f"marriages/{cid}/{uid}",t.id); db_set(f"marriages/{cid}/{t.id}",uid)
        return await msg.reply_text(f"💍 تم الزواج بين <b>{msg.from_user.first_name}</b> و <b>{t.first_name}</b>! 🎊",parse_mode="HTML")
    if text=="طلاق":
        pid=db_get(f"marriages/{cid}/{uid}")
        if not pid: return await msg.reply_text("أنت مو متزوج! 😅")
        db_set(f"marriages/{cid}/{uid}",None); db_set(f"marriages/{cid}/{pid}",None)
        return await msg.reply_text(f"💔 تم الطلاق. {msg.from_user.first_name} أصبح حراً.")
    if text=="شريكي":
        pid=db_get(f"marriages/{cid}/{uid}")
        if not pid: return await msg.reply_text("ما عندك شريك 😢")
        try:
            m=await ctx.bot.get_chat_member(cid,pid)
            return await msg.reply_text(f"💑 شريكك: <b>{m.user.first_name}</b>",parse_mode="HTML")
        except Exception: return await msg.reply_text("شريكك غادر المجموعة 😔")

    # ══ إدارة (مدير+) ══
    if priv_mgr:
        if text=="تحذير" and msg.reply_to_message:
            t=msg.reply_to_message.from_user
            w=db_get(f"warns/{cid}/{t.id}",0)+1; db_set(f"warns/{cid}/{t.id}",w)
            if w>=3:
                try: await ctx.bot.ban_chat_member(cid,t.id)
                except Exception: pass
                return await msg.reply_text(f"🚫 <b>{t.first_name}</b> تحذير 3/3 — تم الحظر!",parse_mode="HTML")
            return await msg.reply_text(f"⚠️ تحذير <b>{w}/3</b> لـ {t.first_name}",parse_mode="HTML")
        if text=="الغاء تحذير" and msg.reply_to_message:
            t=msg.reply_to_message.from_user
            w=max(0,db_get(f"warns/{cid}/{t.id}",0)-1); db_set(f"warns/{cid}/{t.id}",w)
            return await msg.reply_text(f"✅ تم إلغاء تحذير. {t.first_name}: {w}/3")
        if text=="تحذيراتي":
            return await msg.reply_text(f"⚠️ تحذيراتك: <b>{db_get(f'warns/{cid}/{uid}',0)}/3</b>",parse_mode="HTML")
        if text=="قفل الشات":
            try:
                await ctx.bot.set_chat_permissions(cid,ChatPermissions(can_send_messages=False))
                s["locked"]=True; save_settings(cid,s)
                return await msg.reply_text("🔒 تم قفل الشات.")
            except Exception as e: return await msg.reply_text(f"❌ {e}")
        if text=="فتح الشات":
            try:
                perms=ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,
                    can_send_photos=True,can_send_videos=True,can_send_video_notes=True,
                    can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True)
                await ctx.bot.set_chat_permissions(cid,perms); s["locked"]=False; save_settings(cid,s)
                return await msg.reply_text("🔓 تم فتح الشات.")
            except Exception as e: return await msg.reply_text(f"❌ {e}")
        BAN_MAP={"منع ملصقات":"ban_stickers","منع قيف":"ban_gifs","منع مقاطع":"ban_videos","منع صور":"ban_photos"}
        UNB_MAP={"تفعيل ملصقات":"ban_stickers","تفعيل قيف":"ban_gifs","تفعيل مقاطع":"ban_videos","تفعيل صور":"ban_photos"}
        NMS={"ban_stickers":"الملصقات","ban_gifs":"الـ GIF","ban_videos":"المقاطع","ban_photos":"الصور"}
        if text in BAN_MAP:
            k=BAN_MAP[text]; s[k]=True; save_settings(cid,s)
            return await msg.reply_text(f"🚫 تم منع {NMS[k]}.")
        if text in UNB_MAP:
            k=UNB_MAP[text]; s[k]=False; save_settings(cid,s)
            return await msg.reply_text(f"✅ تم تفعيل {NMS[k]}.")
        if text=="الترحيب تشغيل": s["welcome"]=True; save_settings(cid,s); return await msg.reply_text("✅ الترحيب شغّال.")
        if text=="الترحيب ايقاف": s["welcome"]=False; save_settings(cid,s); return await msg.reply_text("✅ الترحيب موقوف.")
        if text=="تعديل تشغيل": s["edit_notify"]=True; save_settings(cid,s); return await msg.reply_text("✅ إشعار التعديل شغّال.")
        if text=="تعديل ايقاف": s["edit_notify"]=False; save_settings(cid,s); return await msg.reply_text("✅ إشعار التعديل موقوف.")
        if text.startswith("منع كلمة "):
            w=text[9:].strip()
            if w:
                ws=s.get("banned_words",[]); ws.append(w) if w not in ws else None
                s["banned_words"]=ws; save_settings(cid,s)
                return await msg.reply_text(f"✅ تمت إضافة: <code>{w}</code>",parse_mode="HTML")
        if text.startswith("حذف كلمة "):
            w=text[9:].strip(); ws=s.get("banned_words",[])
            if w in ws: ws.remove(w)
            s["banned_words"]=ws; save_settings(cid,s)
            return await msg.reply_text(f"✅ تمت إزالة: <code>{w}</code>",parse_mode="HTML")
        if text=="الكلمات":
            ws=s.get("banned_words",[])
            return await msg.reply_text("📋 <b>الكلمات الممنوعة:</b>\n"+"\n".join(f"• <code>{w}</code>" for w in ws) if ws else "لا توجد كلمات ممنوعة.",parse_mode="HTML")
        if text.startswith("مسح "):
            try:
                count=min(int(text[4:].strip()),100)
                start=msg.reply_to_message.message_id if msg.reply_to_message else msg.message_id-1
                dl=0
                for mid in range(start,start+count+1):
                    try: await ctx.bot.delete_message(cid,mid); dl+=1
                    except Exception: pass
                try: await msg.delete()
                except Exception: pass
                nm=await ctx.bot.send_message(cid,f"🗑 تم حذف {dl} رسالة.")
                await asyncio.sleep(3); await nm.delete()
            except ValueError: await msg.reply_text("❗ مثال: <code>مسح 10</code>",parse_mode="HTML")
            return
        if text.startswith("اضافة رد ") and "|" in text:
            p=text[9:].split("|",1)
            tr,rp=p[0].strip(),p[1].strip()
            if tr and rp:
                store_reply(cid,tr,rp)
                return await msg.reply_text(f"✅ <b>رد تلقائي:</b>\n<code>{tr}</code> ← {rp}",parse_mode="HTML")
            return await msg.reply_text("❗ مثال: <code>اضافة رد السلام عليكم | وعليكم السلام</code>",parse_mode="HTML")
        if text.startswith("حذف رد "):
            tr=text[7:].strip(); delete_reply(cid,tr)
            return await msg.reply_text(f"✅ تم حذف رد: <code>{tr}</code>",parse_mode="HTML")
        if text=="قائمة الردود":
            rs=get_replies(cid)
            return await msg.reply_text("📋 <b>الردود:</b>\n"+"\n".join(f"• <code>{t}</code> ← {r}" for t,r in rs) if rs else "لا توجد ردود.",parse_mode="HTML")
        if text=="طرد":
            t=await get_target(upd,ctx)
            if t: await ctx.bot.ban_chat_member(cid,t.id); await ctx.bot.unban_chat_member(cid,t.id); await msg.reply_text(f"👢 تم طرد {t.first_name}.")
            return
        if text=="حظر":
            t=await get_target(upd,ctx)
            if t: await ctx.bot.ban_chat_member(cid,t.id); await msg.reply_text(f"🚫 تم حظر {t.first_name}.")
            return
        if text=="فك حظر":
            t=await get_target(upd,ctx)
            if t: await ctx.bot.unban_chat_member(cid,t.id,only_if_banned=True); await msg.reply_text(f"✅ فك حظر {t.first_name}.")
            return
        if text=="كتم":
            t=await get_target(upd,ctx)
            if t: await ctx.bot.restrict_chat_member(cid,t.id,ChatPermissions(can_send_messages=False)); await msg.reply_text(f"🔇 تم كتم {t.first_name}.")
            return
        if text=="الغاء كتم":
            t=await get_target(upd,ctx)
            if t:
                p=ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,
                    can_send_photos=True,can_send_videos=True,can_send_video_notes=True,
                    can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True)
                await ctx.bot.restrict_chat_member(cid,t.id,permissions=p); await msg.reply_text(f"🔊 رُفع كتم {t.first_name}.")
            return
        if text.startswith("تثبيت") and msg.reply_to_message:
            await ctx.bot.pin_chat_message(cid,msg.reply_to_message.message_id); return
        if text.startswith("الغاء تثبيت") and msg.reply_to_message:
            await ctx.bot.unpin_chat_message(cid,msg.reply_to_message.message_id); return

    if priv_own:
        RM={"رفع مالك":ROLE_OWNER,"رفع مدير":ROLE_MGR,"رفع مميز":ROLE_VIP}
        if text in RM:
            t=await get_target(upd,ctx)
            if t: set_role(cid,t.id,RM[text]); await msg.reply_text(f"✅ {t.first_name} صار {ROLE_LABEL[RM[text]]}.")
            return
        if text=="تنزيل رتبة":
            t=await get_target(upd,ctx)
            if t: rm_role(cid,t.id); await msg.reply_text(f"✅ رتبة {t.first_name} أُزيلت.")
            return
        if text=="تشغيل سيك": s["ai_mode"]=True; save_settings(cid,s); return await msg.reply_text("🤖 الذكاء الاصطناعي شغّال في الكروب!")
        if text=="ايقاف سيك": s["ai_mode"]=False; save_settings(cid,s); return await msg.reply_text("😴 الذكاء الاصطناعي موقوف.")

    # روابط في الكروب
    mt = re.match(r'^تيك\s+@?(\S+)', text, re.I)
    if mt: await tiktok_user_info(upd, ctx, mt.group(1), cid); return
    url = find_url(text)
    if url:
        if host_in(url,'youtube.com','youtu.be'): await yt_handler(upd,ctx,url,uid); return
        if host_in(url,'x.com','twitter.com'): await x_handler(upd,ctx,url,uid); return
        if host_in(url,'tiktok.com','douyin.com'): await tiktok_handler(upd,ctx,url,cid,msg.message_id); return
        if host_in(url,'facebook.com','fb.watch','fb.com'): await fb_handler(upd,ctx,url,uid); return
        if host_in(url,'pinterest.com','pin.it'): await pinterest_handler(upd,ctx,url,cid); return
    m=re.match(r'^ستوري\s+@?(\S+)',text,re.I)
    if m: await insta_stories_handler(upd,ctx,m.group(1),cid); return
    if url and host_in(url,'instagram.com'): await insta_handler(upd,ctx,url,cid); return

    # ذكاء اصطناعي في الكروب
    if s.get("ai_mode"):
        skip=('رفع','تنزيل','طرد','حظر','كتم','قفل','فتح','منع','تفعيل','اضافة','حذف','مسح','تحذير','الترحيب','تعديل')
        if not any(text.startswith(c) for c in skip):
            await ctx.bot.send_chat_action(cid,'typing')
            return await msg.reply_text(await ask_ai(text))

# ═══════════════════════════════════════════════════════════════════
# 12. تشغيل البوت
# ═══════════════════════════════════════════════════════════════════

async def _keep_alive(app):
    """يمنع Render من تنويم البوت — ping كل 10 دقائق"""
    url = os.environ.get('RENDER_EXTERNAL_URL', '').strip()
    if not url:
        logger.info("ℹ️ RENDER_EXTERNAL_URL not set — keep_alive disabled")
        return
    logger.info(f"✅ keep_alive started → {url}")
    while True:
        await asyncio.sleep(600)  # 10 دقائق
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=15)
            )
            logger.info("[keep_alive] ping OK")
        except Exception as e:
            logger.warning(f"[keep_alive] ping failed: {e}")

def _start_health_server():
    """سيرفر HTTP بسيط لـ Render health check على port 10000"""
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - Bot is running!")
        def log_message(self, *a): pass  # أوقف logs الـ HTTP
    port = int(os.environ.get('PORT', 10000))
    try:
        srv = HTTPServer(('0.0.0.0', port), _H)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        logger.info(f"✅ Health server started on port {port}")
    except Exception as e:
        logger.warning(f"⚠️ Health server failed: {e}")

def main():
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        logger.error("❌ BOT_TOKEN not set! Add it as environment variable.")
        return
    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(120)
        .write_timeout(300)   # الأهم: رفع الملفات
        .pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start",cmd_start))
    app.add_handler(CommandHandler("admin",cmd_admin))
    app.add_handler(CommandHandler("help",cmd_help))
    app.add_handler(CommandHandler("ping",cmd_ping))
    app.add_handler(CommandHandler("id",cmd_id))
    app.add_handler(CallbackQueryHandler(btn_cb,pattern=r"^(show_w_|cmd_|dl_|ttt_|convert_|ist_|adm_)"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS,welcome_handler))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT,edit_handler))
    # تحويل الفيديو المُرسل مباشرة بالخاص
    async def _private_video_handler(upd, ctx):
        msg = upd.message
        if msg.chat.type != 'private': return
        media = msg.video or msg.document
        if not media: return
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎵 تحويل لصوت MP3", callback_data=f"convert_audio_{msg.message_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="convert_cancel")
        ]])
        await msg.reply_text("📹 استلمت الفيديو! شو تريد؟", reply_markup=markup)

    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.VIDEO | filters.Document.VIDEO),
        _private_video_handler), group=0)
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & (filters.Sticker.ALL | filters.ANIMATION | filters.VIDEO | filters.PHOTO),
        media_filter), group=0)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,track_msg), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_msg), group=2)
    logger.info("🚀 Bot started!")
    # شغّل HTTP health server لـ Render
    _start_health_server()
    # شغّل keep_alive
    async def _post_init(app):
        asyncio.create_task(_keep_alive(app))
    app.post_init = _post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
