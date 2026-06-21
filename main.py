import logging, os, asyncio, random, re, hashlib, requests
import tempfile, shutil, subprocess, sqlite3, json, threading, math
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from yt_dlp import YoutubeDL
import imageio_ffmpeg

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. القوائم والمحتوى
# ═══════════════════════════════════════════════════════════════════
WA3ED_LIST = [
    "عيونها السود والبيض 👀",
    " هلا بالحلو \ ة 🌸",
    "مالي خلقك 😏",
    "اتسرسح منا وليدي 😤",
    "وعد هسه مشغولة 😅",
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

# ═══════════════════════════════════════════════════════════════════
# 2. قاعدة البيانات SQLite (بديل Firebase — يشتغل على Railway)
# ═══════════════════════════════════════════════════════════════════
DB_PATH = os.environ.get('DB_PATH', 'bot_data.db')
_db_lock = threading.Lock()

def _init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute('CREATE TABLE IF NOT EXISTS kv (path TEXT PRIMARY KEY, value TEXT)')
        c.commit()
_init_db()

# ── تحميل cookies من متغير البيئة (لـ Railway) ──
def _load_cookies():
    import base64
    data = os.environ.get('COOKIES_DATA', '').strip()
    if not data:
        return
    try:
        content = base64.b64decode(data).decode('utf-8')
        with open('cookies.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info("✅ cookies.txt loaded from COOKIES_DATA")
    except Exception as e:
        logger.error(f"❌ Failed to load cookies: {e}")
_load_cookies()

def db_get(path: str, default=None):
    with _db_lock:
        try:
            with sqlite3.connect(DB_PATH) as c:
                row = c.execute('SELECT value FROM kv WHERE path=?', (path,)).fetchone()
                return json.loads(row[0]) if row else default
        except: return default

def db_set(path: str, value):
    with _db_lock:
        try:
            with sqlite3.connect(DB_PATH) as c:
                if value is None:
                    c.execute('DELETE FROM kv WHERE path=?', (path,))
                else:
                    c.execute('INSERT OR REPLACE INTO kv (path,value) VALUES (?,?)',
                              (path, json.dumps(value, ensure_ascii=False)))
                c.commit()
        except Exception as e: logger.error(f"DB error: {e}")

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
    except: return False

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
    api_key = os.environ.get("GEMINI_KEY")
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
            except: pass
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
    # normalize douyin URL
    api_urls = [
        f'https://www.tikwm.com/api/?url={requests.utils.quote(url)}&hd=1',
        f'https://tikwm.com/api/?url={requests.utils.quote(url)}',
        f'https://www.tikwm.com/api/?url={url}&hd=1',
    ]
    for api_url in api_urls:
        try:
            r = requests.get(api_url, timeout=25,
                headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
                         'Accept':'application/json','Referer':'https://www.tikwm.com/'}).json()
            if r.get('code') == 0 and 'data' in r:
                d = r['data']
                author_obj = d.get('author',{})
                author = author_obj.get('unique_id','') if isinstance(author_obj,dict) else str(author_obj)
                author = author or 'مجهول'
                music = d.get('music','')
                if isinstance(music, dict): music = music.get('play','')
                if d.get('images'): return {'type':'images','data':d['images'],'author':author,'music':music}
                vid = d.get('hdplay') or d.get('play') or d.get('wmplay')
                if vid: return {'type':'video','data':vid,'author':author,'music':music}
        except Exception as e: logger.error(f"[tikwm] {e}")
    return None

# ═══════════════════════════════════════════════════════════════════
# 6. معالجات الروابط
# ═══════════════════════════════════════════════════════════════════
async def yt_handler(upd, ctx, url, uid):
    msg = upd.message
    wm = await msg.reply_text("🔍 جاري جلب معلومات الفيديو من يوتيوب...")

    def _get_info():
        # tv_embedded يتجاوز bot detection بدون كوكيز
        clients = [
            ['tv_embedded'],
            ['ios'],
            ['android'],
            ['mweb'],
            ['web_embedded'],
        ]
        if os.path.exists('cookies.txt'):
            clients.insert(0, ['web'])  # web أفضل مع كوكيز
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
                    if info: return info
            except Exception as e:
                logger.warning(f"[YT] client {client}: {e}")
                continue
        return None

    info = await asyncio.get_running_loop().run_in_executor(None, _get_info)
    if not info:
        return await wm.edit_text(
            "❌ فشل جلب بيانات اليوتيوب.\n"
            "• شغّل: <code>pip install -U yt-dlp</code> على Railway\n"
            "• أو تأكد أن الرابط عام",
            parse_mode="HTML"
        )

    # بناء format_map من المعلومات
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

    dur = info.get('duration', 0)
    views = info.get('view_count', 0)
    cap = (
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
    except:
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
                [os.path.join(tmp, f) for f in os.listdir(tmp)
                 if f.endswith(('.mp4', '.webm', '.mkv'))],
                key=os.path.getsize, reverse=True
            )
            return files[0] if files else None, info.get('title', '')

    try:
        fp, title = await asyncio.get_running_loop().run_in_executor(None, _run)
        active_dl.pop(msg.message_id, None); prog_task.cancel()
        if fp and os.path.exists(fp):
            await wm.edit_text("📤 جاري الرفع...")
            with open(fp, 'rb') as f:
                await ctx.bot.send_video(
                    cid, f,
                    caption=f"{platform} {title[:60]}" if title else platform,
                    supports_streaming=True
                )
            await wm.delete()
        else:
            await wm.edit_text("❌ فشل التحميل. تأكد أن الرابط عام.")
    except Exception as e:
        active_dl.pop(msg.message_id, None); prog_task.cancel()
        logger.error(f"[auto_dl] {e}")
        await wm.edit_text(f"❌ فشل التحميل: {str(e)[:100]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

async def fb_handler(upd, ctx, url, uid):
    """فيس بوك — تحميل تلقائي بأعلى جودة"""
    await auto_download(upd, ctx, url, upd.message.chat_id, "📘")

async def x_handler(upd, ctx, url, uid):
    """X/Twitter — تحميل تلقائي بأعلى جودة"""
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
            except: pass
        return None, ''

    try:
        fp, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
        active_dl.pop(msg.message_id, None); prog.cancel()
        if fp and os.path.exists(fp):
            await wm.edit_text("📤 جاري الرفع...")
            with open(fp,'rb') as f:
                await ctx.bot.send_video(cid, f, caption=f"🐦 {title[:60]}" if title else "🐦 X", supports_streaming=True)
            await wm.delete()
        else:
            hint = "\n💡 تأكد من الكوكيز أو أن التغريدة عامة" if not has_cookies else ""
            await wm.edit_text(f"❌ فشل التحميل من X.{hint}")
    except Exception as e:
        active_dl.pop(msg.message_id, None); prog.cancel()
        await wm.edit_text(f"❌ خطأ: {str(e)[:80]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

async def tiktok_handler(upd, ctx, url, cid, reply_id):
    msg = upd.message
    wm = await msg.reply_text("⏳ جاري التحميل...")
    # محاولة 1: tikwm API (يدعم تيك توك + دوين)
    data = await asyncio.get_running_loop().run_in_executor(None, lambda: tiktok_api(url))
    if data:
        cap = f"👤 <b>@{data['author']}</b>"
        try:
            if data['type'] == 'images':
                # تحميل الصور أولاً لأن روابطها تحتاج headers
                def _dl_imgs():
                    result = []
                    headers = {'User-Agent':'Mozilla/5.0','Referer':'https://www.tiktok.com/'}
                    for img_url in data['data']:  # كل الصور بدون حد
                        try:
                            r = requests.get(img_url, headers=headers, timeout=15)
                            if r.status_code == 200: result.append(r.content)
                        except: pass
                    return result
                img_bytes = await asyncio.get_running_loop().run_in_executor(None, _dl_imgs)
                if img_bytes:
                    total = len(img_bytes)
                    # إرسال على دفعات (Telegram يقبل 10 كحد أقصى للمجموعة)
                    for i in range(0, total, 10):
                        batch = img_bytes[i:i+10]
                        media = [InputMediaPhoto(b) for b in batch]
                        await ctx.bot.send_media_group(cid, media, reply_to_message_id=reply_id)
                        if i+10 < total: await asyncio.sleep(1)
                    if data.get('music'):
                        await ctx.bot.send_audio(cid, data['music'], caption=f"{cap}\n🖼 {total} صورة", parse_mode="HTML")
                else:
                    return await wm.edit_text("❌ تعذر تحميل الصور من هذه الألبوم.")
            else:
                await ctx.bot.send_video(cid, data['data'], caption=cap, parse_mode="HTML",
                                         reply_to_message_id=reply_id, supports_streaming=True)
            return await wm.delete()
        except Exception as e: logger.error(f"[TikTok send] {e}")
    # محاولة 2: yt-dlp مباشرة (يدعم تيك توك + دوين)
    await wm.edit_text("⏳ محاولة بديلة...")
    is_douyin = 'douyin.com' in url

    def _dl_tiktok():
        tmp2 = tempfile.mkdtemp()
        opts = {
            'outtmpl': os.path.join(tmp2,'%(id)s.%(ext)s'),
            'quiet':True,'nocheckcertificate':True,'geo_bypass':True,
            'ffmpeg_location':FFMPEG,
            'format':'best[ext=mp4]/best',
            'merge_output_format':'mp4',
            'http_headers':{
                'User-Agent': (
                    'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 Chrome/91.0.4472.120 Mobile Safari/537.36'
                    if is_douyin else
                    'TikTok 26.2.0 rv:262018 (iPhone; iOS 14.4.2; en_US) Cronet'
                ),
            },
        }
        if is_douyin:
            opts['extractor_args'] = {'douyin': {'app_name': ['trill']}}
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp2):
                if f.endswith(('.mp4','.webm','.mkv')):
                    return os.path.join(tmp2,f), tmp2
        return None, tmp2

    fp, tmp = await asyncio.get_running_loop().run_in_executor(None, _dl_tiktok)
    if fp and os.path.exists(fp):
        emoji = "🇨🇳 دوين" if is_douyin else "✅ تيك توك 🎵"
        with open(fp,'rb') as f: await ctx.bot.send_video(cid, f, caption=emoji, supports_streaming=True)
        await wm.delete()
    else:
        await wm.edit_text(
            "❌ فشل التحميل.\n" + ("• دوين يحتاج أحياناً VPN 🇨🇳" if is_douyin else "• قد يكون الرابط منتهياً أو الحساب خاص")
        )
    if tmp: shutil.rmtree(tmp, ignore_errors=True)

async def insta_handler(upd, ctx, url, cid):
    """انستغرام — ريلز + صور + ستوريات (مع كوكيز)"""
    msg = upd.message
    has_cookies = os.path.exists('cookies.txt')
    is_story = '/stories/' in url

    # ستوريات بدون كوكيز
    if is_story and not has_cookies:
        return await msg.reply_text(
            "🔒 <b>تحميل الستوريات يحتاج كوكيز انستغرام</b>\n\n"
            "الكوكيز غير موجودة على السيرفر حالياً.\n"
            "تأكد من إضافة <code>COOKIES_DATA</code> بـ Railway وإعادة النشر.",
            parse_mode="HTML"
        )

    wm = await msg.reply_text("📸 جاري التحميل من انستغرام...")
    tmp = tempfile.mkdtemp()
    opts = {
        'outtmpl': os.path.join(tmp,'%(id)s_%(autonumber)s.%(ext)s'),
        'quiet':True,'noplaylist':False,'nocheckcertificate':True,
        'ffmpeg_location':FFMPEG,
        'format':'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format':'mp4',
        'http_headers':{'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'},
    }
    if has_cookies: opts['cookiefile'] = 'cookies.txt'

    def _dl():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            videos = sorted(
                [os.path.join(tmp,f) for f in os.listdir(tmp) if f.endswith(('.mp4','.webm','.mkv'))],
                key=os.path.getsize, reverse=True
            )
            images = [os.path.join(tmp,f) for f in os.listdir(tmp) if f.endswith(('.jpg','.jpeg','.png','.webp'))]
            return videos, images, info.get('title','انستغرام')

    try:
        videos, images, title = await asyncio.get_running_loop().run_in_executor(None, _dl)
        if not videos and not images:
            return await wm.edit_text("❌ ما لقيت محتوى.\nتأكد أن الحساب عام.")
        await wm.edit_text("📤 جاري الرفع...")
        for v in videos[:3]:
            with open(v,'rb') as f:
                await ctx.bot.send_video(cid, f, caption=f"📸 {title[:60]}", supports_streaming=True)
        if images:
            for i in range(0, len(images[:20]), 10):
                batch = images[i:i+10]
                handles = []; media = []
                for img in batch:
                    fh = open(img,'rb'); handles.append(fh)
                    media.append(InputMediaPhoto(fh))
                try: await ctx.bot.send_media_group(cid, media)
                finally:
                    for fh in handles: fh.close()
                if i+10 < len(images): await asyncio.sleep(1)
        await wm.delete()
    except Exception as e:
        logger.error(f"[Insta] {e}")
        hint = "\n💡 اذا تكررت المشكلة ارسلها للحساب @shn_1 " if not has_cookies else ""
        await wm.edit_text(f"❌ فشل التحميل من انستغرام.{hint}")
    finally: shutil.rmtree(tmp, ignore_errors=True)


async def insta_stories_handler(upd, ctx, username, cid):
    """ستوريات انستغرام بالـ cookies"""
    msg = upd.message
    username = username.lstrip('@').strip()
    has_cookies = os.path.exists('cookies.txt')

    if not has_cookies:
        return await msg.reply_text(
            "🔒 <b>تحميل الستوريات يحتاج كوكيز انستغرام</b>\n\n"
            "أضف <code>COOKIES_DATA</code> من انستغرام بنفس طريقة X.\n"
            "بعدها يشتغل تلقائياً! ✅",
            parse_mode="HTML"
        )

    url = f"https://www.instagram.com/stories/{username}/"
    wm = await msg.reply_text(f"📸 جاري تحميل ستوريات @{username}...")
    tmp = tempfile.mkdtemp()
    opts = {
        'outtmpl': os.path.join(tmp,'%(id)s_%(autonumber)s.%(ext)s'),
        'quiet': True, 'noplaylist': False, 'nocheckcertificate': True,
        'ffmpeg_location': FFMPEG,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'cookiefile': 'cookies.txt',
        'http_headers': {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'},
    }

    def _dl():
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            videos = sorted(
                [os.path.join(tmp,f) for f in os.listdir(tmp) if f.endswith(('.mp4','.webm','.mkv'))],
                key=os.path.getsize, reverse=True
            )
            images = [os.path.join(tmp,f) for f in os.listdir(tmp) if f.endswith(('.jpg','.jpeg','.png','.webp'))]
            return videos, images

    try:
        videos, images = await asyncio.get_running_loop().run_in_executor(None, _dl)
        total = len(videos) + len(images)
        if not total:
            return await wm.edit_text(
                f"❌ ما لقيت ستوريات لـ @{username}\n"
                "• الحساب خاص؟ تأكد أن الكوكيز من حساب يتابعه\n"
                "• الستوريات قد تكون منتهية"
            )
        await wm.edit_text(f"📤 جاري رفع {total} ستوري...")
        for v in videos[:5]:
            with open(v,'rb') as f:
                await ctx.bot.send_video(cid, f, caption=f"📸 @{username}", supports_streaming=True)
        if images:
            for i in range(0, min(len(images), 20), 10):
                batch = images[i:i+10]
                handles = []; media = []
                for img in batch:
                    fh = open(img,'rb'); handles.append(fh)
                    media.append(InputMediaPhoto(fh))
                try: await ctx.bot.send_media_group(cid, media)
                finally:
                    for fh in handles: fh.close()
                if i+10 < len(images): await asyncio.sleep(1)
        await wm.delete()
    except Exception as e:
        err = str(e)
        logger.error(f"[Stories] {err}")
        if 'login' in err.lower() or 'checkpoint' in err.lower() or 'authentication' in err.lower():
            await wm.edit_text(
                "🔒 <b>انستغرام يطلب تسجيل دخول</b>\n\n"
                "الكوكيز موجودة بس انستغرام يرفضها.\n"
                "جرب تجيب كوكيز جديدة من المتصفح بعد تسجيل الدخول مجدداً.",
                parse_mode="HTML"
            )
        elif 'private' in err.lower():
            await wm.edit_text("❌ هذا الحساب خاص ولا تتابعه.")
        elif 'not found' in err.lower() or '404' in err:
            await wm.edit_text("❌ ما لقيت هذه الستوريات — ربما انتهت أو الحساب مو موجود.")
        else:
            await wm.edit_text(f"❌ فشل تحميل الستوريات:\n<code>{err[:150]}</code>", parse_mode="HTML")
    finally: shutil.rmtree(tmp, ignore_errors=True)


async def pinterest_handler(upd, ctx, url, cid):
    """بينترست — فيديو وصور"""
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
                    with open(fp,'rb') as f: await ctx.bot.send_video(cid,f,caption=f"📌 {title[:60]}",supports_streaming=True)
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
                except: pass

        await wm.edit_text("❌ ما قدرت أحمل من هذا الرابط.\nتأكد أن الـ Pin عام.")
    except Exception as e:
        logger.error(f"[Pinterest] {e}")
        await wm.edit_text("❌ فشل التحميل من بينترست.")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def music_handler(upd, ctx, url, cid, platform="🎵"):
    """تحميل صوت بأعلى جودة (320kbps MP3)"""
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
        if fp and os.path.exists(fp):
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
        logger.error(f"[Music] {e}")
        await wm.edit_text(f"❌ فشل التحميل: {str(e)[:100]}")
    finally: shutil.rmtree(tmp, ignore_errors=True)

async def spotify_handler(upd, ctx, url, cid):
    """سبوتيفاي — تحميل عبر spotdl مع ربط ميكانيكي صريح لـ ffmpeg لمنع الـ FFmpegError"""
    import html  # مكتبة أساسية لتنظيف النصوص ومنع أخطاء تليجرام
    msg = upd.message
    wm = await msg.reply_text("🎧 جاري البحث عن المقطع وتحميله من سبوتيفاي...")
    tmp = tempfile.mkdtemp()

    def _dl():
        import sys, shutil as _shutil
        import imageio_ffmpeg  # استدعاء المكتبة للوصول للملف التنفيذي الأصلي
        
        # 1. حل مشكلة تسمية FFMPEG لـ spotdl جذرياً
        try:
            ffmpeg_real_path = imageio_ffmpeg.get_ffmpeg_exe()
            local_ffmpeg_path = os.path.join(tmp, 'ffmpeg')
            
            # إنشاء اختصار صريح باسم 'ffmpeg' داخل المجلد المؤقت ليطابق طلب الأداة
            if not os.path.exists(local_ffmpeg_path):
                try:
                    os.symlink(ffmpeg_real_path, local_ffmpeg_path)
                except Exception:
                    # حل بديل في حال لم يدعم السيرفر الـ Symlink نقوم بنسخه فوراً
                    _shutil.copy(ffmpeg_real_path, local_ffmpeg_path)
                # إعطاء صلاحيات التشغيل للملف
                os.chmod(local_ffmpeg_path, 0o755)
        except Exception as fe:
            logger.error(f"[Spotify FFMPEG Setup Error] {fe}")

        # 2. حقن المجلد المؤقت في بداية الـ PATH لكي ترى الأداة ملف الـ ffmpeg الجديد فوراً
        env = os.environ.copy()
        env["PATH"] = tmp + os.pathsep + env.get("PATH", "")

        # العثور على أداة spotdl بالسيرفر
        spotdl_bin = (
            _shutil.which('spotdl') or
            _shutil.which(os.path.join(os.path.dirname(sys.executable), 'spotdl')) or
            None
        )
        
        if spotdl_bin:
            cmd = [spotdl_bin, url]
        else:
            cmd = [sys.executable, '-m', 'spotdl', url]
            
        logger.info(f"[spotdl] cmd: {' '.join(cmd)}")
        
        # تشغيل الأداة بداخل المجلد المؤقت مع تمرير البيئة المحقونة
        result = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=300, env=env)
        
        # البحث عن الملفات الصوتية الناتجة بمختلف الامتدادات
        files = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(('.mp3', '.m4a', '.opus', '.wav', '.ogg'))]
        return files, result.returncode, result.stdout, result.stderr

    try:
        files, returncode, stdout, stderr = await asyncio.get_running_loop().run_in_executor(None, _dl)
        
        if not files:
            error_log = ""
            if stderr and stderr.strip():
                safe_stderr = html.escape(stderr.strip()[:1500])
                error_log += f"<b>⚙️ STDERR:</b>\n<code>{safe_stderr}</code>\n\n"
            if stdout and stdout.strip():
                safe_stdout = html.escape(stdout.strip()[:1500])
                error_log += f"<b>📊 STDOUT:</b>\n<code>{safe_stdout}</code>"
            
            if not error_log:
                error_log = "لم يتم استخراج أي ملفات صوتية (قد يكون الرابط خاصاً أو السيرفر محظوراً من يوتيوب)."

            return await wm.edit_text(
                f"❌ فشل التحميل من سبوتيفاي.\n\n"
                f"<b>تقرير الأداة الكامل للصيانة:</b>\n{error_log}\n\n"
                f"💡 إذا كان الخطأ متعلقاً بالـ Sign in أو الـ Block، تأكد من تحديث الكوكيز بـ COOKIES_DATA.",
                parse_mode="HTML"
            )
            
        await wm.edit_text(f"📤 جاري رفع {len(files)} مقطع...")
        for fp in files[:10]:
            name = os.path.basename(fp)
            for ext in ['.mp3', '.m4a', '.opus', '.wav', '.ogg']:
                if name.endswith(ext):
                    name = name.replace(ext, '')
                    break
            with open(fp, 'rb') as f:
                await ctx.bot.send_audio(cid, f, title=name[:64], caption=f"🎧 {name[:60]}")
        await wm.delete()
    except FileNotFoundError:
        await wm.edit_text(
            "❌ أداة spotdl غير مثبتة بالسيرفر!\n"
            "تأكد من إضافتها لملف <code>requirements.txt</code> الخاص بك.",
            parse_mode="HTML"
        )
    except subprocess.TimeoutExpired:
        await wm.edit_text("❌ انتهى الوقت المحدد (Timeout). المقطع قد يكون طويلاً جداً.")
    except Exception as e:
        logger.error(f"[Spotify] {e}")
        await wm.edit_text(f"❌ خطأ غير متوقع: {str(e)[:100]}")
    finally: 
        shutil.rmtree(tmp, ignore_errors=True)

async def tiktok_handler(upd, ctx, username, cid):
    """معلومات حساب تيك توك"""
    msg = upd.message

    username = username.lstrip('@').strip()

    if not username:

        return await msg.reply_text("❗ مثال: <code>تيك codexpert</code>", parse_mode="HTML")

    wm = await msg.reply_text(f"🔍 جاري جلب معلومات @{username}...")



    COUNTRY_FLAG = {

        'IQ':'🇮🇶','SA':'🇸🇦','US':'🇺🇸','GB':'🇬🇧','AE':'🇦🇪','EG':'🇪🇬',

        'TR':'🇹🇷','IR':'🇮🇷','RU':'🇷🇺','DE':'🇩🇪','FR':'🇫🇷','IN':'🇮🇳',

        'CN':'🇨🇳','JP':'🇯🇵','KR':'🇰🇷','BR':'🇧🇷','KW':'🇰🇼','QA':'🇶🇦',

        'BH':'🇧🇭','OM':'🇴🇲','JO':'🇯🇴','SY':'🇸🇾','LB':'🇱🇧','YE':'🇾🇪',

        'LY':'🇱🇾','TN':'🇹🇳','DZ':'🇩🇿','MA':'🇲🇦','SD':'🇸🇩','PK':'🇵🇰',

    }



    def _fetch():

        endpoints = [

            f"https://www.tikwm.com/api/user/info?unique_id={username}&count=1",

            f"https://tikwm.com/api/user/info?unique_id={username}",

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

                if data.get('code') == 0:

                    return data

            except: continue

        return {}



    try:

        data = await asyncio.get_running_loop().run_in_executor(None, _fetch)

        if data.get('code') == 0 and data.get('data'):

            d = data['data']

            u = d.get('user', d)

            stats = d.get('stats', u)

            name = u.get('nickname') or u.get('name', username)

            uid_str = str(u.get('id', '—'))

            followers = (stats.get('followerCount') or u.get('followerCount') or d.get('fans') or 0)

            following = (stats.get('followingCount') or u.get('followingCount') or d.get('following') or 0)

            likes = (stats.get('heartCount') or u.get('heartCount') or stats.get('diggCount') or d.get('heart') or 0)

            videos = (stats.get('videoCount') or u.get('videoCount') or d.get('video') or 0)

            bio = u.get('signature','') or '—'

            verified = "✅ موثق" if (u.get('verified') or u.get('isVerified')) else "❌ غير موثق"

            private = "🔒 خاص" if (u.get('privateAccount') or u.get('secret')) else "🌐 عام"

            avatar = u.get('avatarLarger') or u.get('avatarMedium') or u.get('avatarThumb') or u.get('avatar','')

            region = (u.get('region') or u.get('location') or '').upper()

            country_str = f"{COUNTRY_FLAG.get(region,'🌍')} {region}" if region else "🌍 غير معروف"

            create_ts = u.get('createTime') or u.get('createtime') or 0

            joined_str = ""

            if create_ts:

                try:

                    import datetime

                    joined_str = "\n📅 <b>تاريخ الانضمام:</b> " + datetime.datetime.fromtimestamp(int(create_ts)).strftime('%Y/%m/%d')

                except: pass

            txt = (

                f"🎵 <b>معلومات تيك توك</b>\n\n"

                f"👤 <b>الاسم:</b> {name}\n"

                f"📛 <b>اليوزر:</b> @{username}\n"

                f"🆔 <b>ID:</b> <code>{uid_str}</code>\n"

                f"🌍 <b>الدولة:</b> {country_str}\n"

                f"✅ <b>التوثيق:</b> {verified}\n"

                f"🔒 <b>الحساب:</b> {private}\n"

                f"👥 <b>المتابعون:</b> {followers:,}\n"

                f"➡️ <b>يتابع:</b> {following:,}\n"

                f"❤️ <b>الإعجابات:</b> {likes:,}\n"

                f"🎬 <b>الفيديوهات:</b> {videos:,}\n"

                f"📝 <b>البايو:</b> {bio[:150]}"

                f"{joined_str}\n\n"

                f"🔗 <a href='https://www.tiktok.com/@{username}'>فتح الحساب</a>"

            )

            await wm.delete()

            if avatar:

                try:

                    await ctx.bot.send_photo(cid, avatar, caption=txt, parse_mode="HTML")

                    return

                except: pass

            await msg.reply_text(txt, parse_mode="HTML")

        else:

            await wm.edit_text(f"❌ ما لقيت حساب @{username}.\nتأكد من اليوزرنيم.")
    except Exception as e:
        logger.error(f"[TT info] {e}")
        await wm.edit_text(f"❌ خطأ: {str(e)[:100]}")
        
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
    if msg.chat.type == 'private' and msg.text.startswith('/start w_'):
        try:
            parts = msg.text.replace('/start w_','').split('_')
            sender_id,target_id = int(parts[0]),int(parts[1])
            chat_id = int(parts[2].replace('m','-'))
            if msg.from_user.id != sender_id:
                return await msg.reply_text("الرابط مو إلك! ❌")
            ctx.user_data.update({'wt':target_id,'wc':chat_id})
            await msg.reply_text("🔒 *أرسل همستك الآن:*\n_(سيتم إرسالها للكروب تلقائياً)_ 🤫", parse_mode="Markdown")
        except: await msg.reply_text("خطأ في رابط الهمسة.")
    else:
        name = msg.from_user.first_name
        await msg.reply_text(
            f"أهلاً <b>{name}</b>! 👋\n\n"
            "📥 <b>المواقع المدعومة:</b>\n"
            "🎬 يوتيوب  🐦 X/تويتر  🎵 تيك توك\n"
            "🇨🇳 دوين  📘 فيس بوك  📸 انستغرام\n"
            "📌 بينترست  🎵 ساوند كلاود  🎵 يوتيوب ميوزك\n""🎧 سبوتيفاي  🧵 ثريدز\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <code>ترجمة [نص]</code> — ترجمة للعربي\n"
            "🔢 <code>حساب [عملية]</code> — حاسبة\n"
            "🎵 <code>تيك @username</code> — معلومات تيك توك\n"
            "🔄 <code>تحويل</code> — رد على فيديو لتحويله لصوت\n\n"
            "👥 للمجموعات: أضفني مشرفاً واكتب <code>الاوامر</code>\n\n"
            "💡 أرسل أي رابط وأنا أتكفله! 🚀\n"
            "❓ /help — مساعدة",
            parse_mode="HTML"
        )

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
            except: pass
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
            fp,title = await asyncio.get_running_loop().run_in_executor(None, _fb_dl)
        else:
            fp,title,tmp = await do_download(url,mt,ql,q.message.message_id,q.message.chat_id,ctx,q.message.message_id,is_photo)

        if fp and os.path.exists(fp):
            await em("📤 جاري الرفع...")
            try:
                with open(fp,'rb') as f:
                    if mt=="audio": await ctx.bot.send_audio(q.message.chat_id,f,title=title or "audio")
                    else: await ctx.bot.send_video(q.message.chat_id,f,caption=f"✅ {(title or '')[:200]}",supports_streaming=True)
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
                        except: pass
                else: await q.edit_message_text("❌ ما لقيت الفيديو.")
            else: await q.edit_message_text("❌ ما لقيت الفيديو الأصلي.")
        except Exception as e: await q.edit_message_text(f"❌ خطأ: {str(e)[:80]}")
        return
    if d == "convert_cancel":
        await q.answer("تم الإلغاء")
        await q.message.delete()
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

        # ضد لاعع مفتوح
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
            except: xn="اللاعع الأول"
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
        except: return await q.answer()
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
        except: pass
        return

# ═══════════════════════════════════════════════════════════════════
# 10. معالجات متنوعة
# ═══════════════════════════════════════════════════════════════════
async def welcome_handler(upd, ctx):
    for m in upd.message.new_chat_members:
        if m.id == ctx.bot.id:
            await upd.message.reply_text(
                "👋 <b>أهلاً! تم إضافتي للمجموعة!</b>\n\n"
                "⚠️ <b>لكي أعمل بشكل كامل:</b>\n"
                "1️⃣ اجعلني <b>مشرفاً</b> في المجموعة\n"
                "2️⃣ اكتب <code>الاوامر</code> لقائمة الأوامر الكاملة 📋\n",
                parse_mode="HTML"
            )
            continue
        if m.is_bot: continue
        s=get_settings(upd.message.chat.id)
        if not s.get("welcome",True): continue
        name=f'<a href="tg://user?id={m.id}">{m.first_name}</a>'
        txt=f"👋 أهلاً {name} في المجموعة! 🎉\nنتمنى لك وقتاً ممتعاً 😊"
        try:
            p=await ctx.bot.get_user_profile_photos(m.id,limit=1)
            if p.total_count>0: await ctx.bot.send_photo(upd.message.chat.id,p.photos[0][-1].file_id,caption=txt,parse_mode="HTML")
            else: await upd.message.reply_text(txt,parse_mode="HTML")
        except: await upd.message.reply_text(txt,parse_mode="HTML")

async def edit_handler(upd, ctx):
    if not upd.edited_message: return
    cid,mid=upd.edited_message.chat.id,upd.edited_message.message_id
    if not get_settings(cid).get("edit_notify",True): return
    new=upd.edited_message.text or "[ميديا]"
    old=db_get(f"messages/{cid}/{mid}/text","[غير متوفر]")
    db_set(f"messages/{cid}/{mid}",{"text":new})
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
        except: pass
        try:
            nm=await ctx.bot.send_message(msg.chat_id,f"🚫 {msg.from_user.first_name}، إرسال {reason} ممنوع هنا!")
            await asyncio.sleep(4); await nm.delete()
        except: pass

async def track_msg(upd, ctx):
    if not upd.message or not upd.message.text or upd.message.text.startswith('/'): return
    db_set(f"messages/{upd.message.chat.id}/{upd.message.message_id}",{"text":upd.message.text})

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
        if ctx.user_data.get('wt'):
            # همسة بالخاص
            tid=ctx.user_data.pop('wt'); wc=ctx.user_data.pop('wc',None)
            wid=str(random.randint(100000,999999))
            db_set(f"whispers/{wid}",{'text':text,'sender':uid,'target':tid})
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔒 اقرأ الهمسة",callback_data=f"show_w_{wid}")]])
            try:
                m=await ctx.bot.get_chat_member(wc,tid); tn=m.user.first_name
            except: tn="العضو"
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
        if re.search(r'music\.youtube\.com',text,re.I): await music_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid,"🎵"); return
        if re.search(r'soundcloud\.com',text,re.I): await music_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid,"🎶"); return
        if re.search(r'spotify\.com',text,re.I): await spotify_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid); return
        if re.search(r'threads\.net',text,re.I): await auto_download(upd,ctx,re.search(r'https?://\S+',text).group(),cid,"🧵"); return
        if re.search(r'(youtube\.com|youtu\.be|shorts)',text,re.I): await yt_handler(upd,ctx,re.search(r'https?://\S+',text).group(),uid); return
        if re.search(r'(x\.com|twitter\.com)',text,re.I): await x_handler(upd,ctx,re.search(r'https?://\S+',text).group(),uid); return
        if re.search(r'(tiktok\.com|vm\.tiktok\.com|douyin\.com)',text,re.I): await tiktok_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid,msg.message_id); return
        if re.search(r'(facebook\.com|fb\.watch|fb\.com)',text,re.I): await fb_handler(upd,ctx,re.search(r'https?://\S+',text).group(),uid); return
        if re.search(r'(pinterest\.com|pin\.it)',text,re.I): await pinterest_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid); return  # auto best
        m=re.match(r'^ستوري\s+@?(\S+)',text,re.I)
        if m: await insta_stories_handler(upd,ctx,m.group(1),cid); return
        if re.search(r'instagram\.com',text,re.I): await insta_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid); return

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
                    except: pass
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
                if all(c in allowed or c.isspace() for c in expr):
                    res = eval(expr,{"__builtins__":{}},{"sqrt":math.sqrt,"pi":math.pi,"abs":abs})
                    return await msg.reply_text(f"🔢 <code>{expr}</code> = <b>{res}</b>", parse_mode="HTML")
                return await msg.reply_text("❗ أرقام وعمليات فقط (+، -، *، /)")
            except: return await msg.reply_text("❌ معادلة غلط. مثال: <code>حساب 15 * 3 + 7</code>", parse_mode="HTML")

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
            except: pass
            try:
                nm=await ctx.bot.send_message(cid,f"⚠️ {msg.from_user.first_name}، الرسالة تحتوي كلمة ممنوعة.")
                await asyncio.sleep(4); await nm.delete()
            except: pass
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
                r=requests.get(f"https://api.mymemory.translated.net/get",params={"q":src,"langpair":"autodetect|ar"},timeout=10)
                return r.json().get("responseData",{}).get("translatedText","فشلت الترجمة")
            result=await asyncio.get_running_loop().run_in_executor(None,_tr)
            return await msg.reply_text(f"🌐 <b>الترجمة:</b>\n{result}",parse_mode="HTML")

    if text.startswith("حساب "):
        expr=text[5:].strip()
        try:
            allowed=set('0123456789+-*/.() %')
            if all(c in allowed or c.isspace() for c in expr):
                res=eval(expr,{"__builtins__":{}},{"sqrt":math.sqrt,"pi":math.pi})
                return await msg.reply_text(f"🔢 <code>{expr}</code> = <b>{res}</b>",parse_mode="HTML")
            else: return await msg.reply_text("❗ أرقام وعمليات فقط (+، -، *، /، ^)")
        except: return await msg.reply_text("❌ معادلة غلط. مثال: <code>حساب 15 * 3 + 7</code>",parse_mode="HTML")

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
                    InlineKeyboardButton("👥 ضد لاعع",callback_data=f"ttt_vspvp_{gid}")
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
        except: return await msg.reply_text("شريكك غادر المجموعة 😔")

    # ══ إدارة (مدير+) ══
    if priv_mgr:
        if text=="تحذير" and msg.reply_to_message:
            t=msg.reply_to_message.from_user
            w=db_get(f"warns/{cid}/{t.id}",0)+1; db_set(f"warns/{cid}/{t.id}",w)
            if w>=3:
                try: await ctx.bot.ban_chat_member(cid,t.id)
                except: pass
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
                    except: pass
                try: await msg.delete()
                except: pass
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
    if re.search(r'(youtube\.com|youtu\.be|shorts)',text,re.I): await yt_handler(upd,ctx,re.search(r'https?://\S+',text).group(),uid); return
    if re.search(r'(x\.com|twitter\.com)',text,re.I): await x_handler(upd,ctx,re.search(r'https?://\S+',text).group(),uid); return
    if re.search(r'(tiktok\.com|vm\.tiktok\.com|douyin\.com)',text,re.I): await tiktok_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid,msg.message_id); return
    if re.search(r'(facebook\.com|fb\.watch|fb\.com)',text,re.I): await fb_handler(upd,ctx,re.search(r'https?://\S+',text).group(),uid); return
    if re.search(r'(pinterest\.com|pin\.it)',text,re.I): await pinterest_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid); return
    m=re.match(r'^ستوري\s+@?(\S+)',text,re.I)
    if m: await insta_stories_handler(upd,ctx,m.group(1),cid); return
    if re.search(r'instagram\.com',text,re.I): await insta_handler(upd,ctx,re.search(r'https?://\S+',text).group(),cid); return

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
    import aiohttp
    url = os.environ.get('RENDER_EXTERNAL_URL', '')
    if not url:
        return  # مو على Render، ما نحتاجه
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(url, timeout=aiohttp.ClientTimeout(total=10))
        except: pass
        await asyncio.sleep(600)

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",cmd_start))
    app.add_handler(CommandHandler("help",cmd_help))
    app.add_handler(CommandHandler("ping",cmd_ping))
    app.add_handler(CommandHandler("id",cmd_id))
    app.add_handler(CallbackQueryHandler(btn_cb,pattern=r"^(show_w_|cmd_|dl_|ttt_|convert_)"))
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
    # شغّل keep_alive لـ Render
    loop = asyncio.get_event_loop()
    loop.create_task(_keep_alive(app))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
