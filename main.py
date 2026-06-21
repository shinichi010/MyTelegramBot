import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import os
import subprocess
import glob
import shutil
import uuid

TOKEN = os.getenv('BOT_TOKEN')

if not TOKEN:
    raise ValueError("لازم تضيف BOT_TOKEN بمتغيرات البيئة (Variables) في Railway!")

bot = telebot.TeleBot(TOKEN)

# مسارات ملفات الكوكيز
IG_COOKIES = 'ig_cookies.txt'
X_COOKIES = 'x_cookies.txt'
YT_COOKIES = 'yt_cookies.txt'

# Fix #1: تخزين الـ URLs بدل تمريرها مباشرة بـ callback_data (حد تيليجرام 64 بايت)
url_store = {}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB حد تيليجرام


def store_url(url):
    key = str(uuid.uuid4())[:8]
    url_store[key] = url
    return key


def get_url(key):
    return url_store.get(key)


# Fix #4 + #6: حذف الملف وأي thumbnail مرتبط فيه
def cleanup_file(filename):
    if not filename:
        return
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except Exception:
            pass
    base = filename.rsplit('.', 1)[0]
    for thumb in glob.glob(f"{base}.*"):
        if thumb != filename:
            try:
                os.remove(thumb)
            except Exception:
                pass


# Fix #5: فحص حجم الملف قبل الرفع
def check_file_size(filename):
    if filename and os.path.exists(filename):
        return os.path.getsize(filename) <= MAX_FILE_SIZE
    return False


def download_media(url, format_type='best', cookies_file=None):
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
    }

    if format_type == 'audio':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'writethumbnail': True,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                },
                {'key': 'EmbedThumbnail'},
                {'key': 'FFmpegMetadata'},
            ],
        })
    elif format_type == '720p':
        # Fix #3: format string صحيح
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best',
            'merge_output_format': 'mp4',
        })
    else:
        ydl_opts.update({'format': 'best'})

    if cookies_file and os.path.exists(cookies_file):
        ydl_opts['cookiefile'] = cookies_file
    elif ('youtube.com' in url or 'youtu.be' in url) and os.path.exists(YT_COOKIES):
        ydl_opts['cookiefile'] = YT_COOKIES

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        if format_type == 'audio' and not filename.endswith('.mp3'):
            filename = filename.rsplit('.', 1)[0] + '.mp3'

        if format_type == '720p' and not os.path.exists(filename):
            filename = filename.rsplit('.', 1)[0] + '.mp4'

        return filename, info


@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "هلا بيك بـ REI! دزلي أي رابط (يوتيوب، تيك توك، انستا، اكس، سبوتيفاي، يوتيوب ميوزك) وأني بالخدمة.")


@bot.message_handler(func=lambda message: 'http' in message.text)
def handle_url(message):
    url = message.text
    chat_id = message.chat.id
    msg = bot.reply_to(message, "جاري المعالجة وتحليل الرابط... ⏳")
    filename = None

    try:
        # يوتيوب ميوزك
        if 'music.youtube.com' in url:
            bot.edit_message_text("جاري جلب الأغنية من يوتيوب ميوزك بأعلى جودة... 🎵", chat_id, msg.message_id)
            filename, info = download_media(url, format_type='audio')

            # Fix #5
            if not check_file_size(filename):
                bot.edit_message_text("الملف أكبر من 50MB، ما أقدر أرفعه لتيليجرام.", chat_id, msg.message_id)
                return

            bot.edit_message_text("جاري الرفع... 🚀", chat_id, msg.message_id)
            with open(filename, 'rb') as f:
                bot.send_audio(chat_id, f,
                               title=info.get('title'),
                               performer=info.get('artist') or info.get('uploader'))
            bot.delete_message(chat_id, msg.message_id)
            return

        # يوتيوب عادي
        if 'youtube.com' in url or 'youtu.be' in url:
            # Fix #1: مفتاح قصير بدل الـ URL
            key = store_url(url)
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("فيديو 720p 🎬", callback_data=f"yt_vid|{key}"),
                InlineKeyboardButton("مقطع صوتي 🎵", callback_data=f"yt_aud|{key}")
            )

            ydl_info_opts = {'quiet': True}
            if os.path.exists(YT_COOKIES):
                ydl_info_opts['cookiefile'] = YT_COOKIES

            with yt_dlp.YoutubeDL(ydl_info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'مقطع يوتيوب')

            bot.edit_message_text(f"معلومات المقطع:\n*{title}*\n\nشنو تحب تحمل؟",
                                  chat_id, msg.message_id, reply_markup=markup, parse_mode="Markdown")
            return

        # سبوتيفاي
        if 'spotify.com' in url:
            bot.edit_message_text("جاري تحميل مسار سبوتيفاي بأعلى جودة والمعلومات... 🎵", chat_id, msg.message_id)

            # Fix #2: مجلد مؤقت + glob للقاء الملف بعد التحميل
            temp_dir = f"spotify_{chat_id}"
            os.makedirs(temp_dir, exist_ok=True)

            try:
                subprocess.run(
                    ['spotdl', url, '--output', temp_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                mp3_files = glob.glob(os.path.join(temp_dir, '*.mp3'))

                if mp3_files:
                    spotify_file = mp3_files[0]

                    # Fix #5
                    if not check_file_size(spotify_file):
                        bot.edit_message_text("الملف أكبر من 50MB، ما أقدر أرفعه لتيليجرام.", chat_id, msg.message_id)
                        return

                    with open(spotify_file, 'rb') as f:
                        bot.send_audio(chat_id, f)
                    bot.delete_message(chat_id, msg.message_id)
                else:
                    bot.edit_message_text("فشل تحميل مسار سبوتيفاي.", chat_id, msg.message_id)
            finally:
                # Fix #6: تنظيف المجلد المؤقت دايماً
                shutil.rmtree(temp_dir, ignore_errors=True)
            return

        # باقي المنصات
        cookies = None
        if 'instagram.com' in url:
            cookies = IG_COOKIES
        elif 'twitter.com' in url or 'x.com' in url:
            cookies = X_COOKIES

        filename, info = download_media(url, format_type='best', cookies_file=cookies)

        # Fix #5
        if not check_file_size(filename):
            bot.edit_message_text("الملف أكبر من 50MB، ما أقدر أرفعه لتيليجرام.", chat_id, msg.message_id)
            return

        bot.edit_message_text("جاري الرفع للتيليجرام... 🚀", chat_id, msg.message_id)

        with open(filename, 'rb') as f:
            if filename.endswith(('.mp3', '.m4a', '.wav')):
                bot.send_audio(chat_id, f, title=info.get('title'), performer=info.get('uploader'))
            elif filename.endswith(('.mp4', '.webm', '.mkv')):
                bot.send_video(chat_id, f)
            elif filename.endswith(('.jpg', '.png', '.jpeg')):
                bot.send_photo(chat_id, f)
            else:
                bot.send_document(chat_id, f)

        bot.delete_message(chat_id, msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"عذراً، صار خطأ: {str(e)}", chat_id, msg.message_id)
    finally:
        # Fix #6: تنظيف الملفات دايماً حتى عند الخطأ
        cleanup_file(filename)


@bot.callback_query_handler(func=lambda call: call.data.startswith('yt_'))
def yt_callback(call):
    action, key = call.data.split('|', 1)
    chat_id = call.message.chat.id
    filename = None

    # Fix #1: جلب الـ URL من الـ store
    url = get_url(key)
    if not url:
        bot.edit_message_text("الرابط انتهت صلاحيته، أعد إرسال الرابط.", chat_id, call.message.message_id)
        return

    bot.edit_message_text("جاري التحميل من يوتيوب... ⏳", chat_id, call.message.message_id)

    try:
        format_type = '720p' if action == 'yt_vid' else 'audio'
        filename, info = download_media(url, format_type=format_type)

        # Fix #5
        if not check_file_size(filename):
            bot.edit_message_text("الملف أكبر من 50MB، ما أقدر أرفعه لتيليجرام.", chat_id, call.message.message_id)
            return

        bot.edit_message_text("جاري الرفع... 🚀", chat_id, call.message.message_id)

        with open(filename, 'rb') as f:
            if format_type == 'audio':
                bot.send_audio(chat_id, f,
                               title=info.get('title'),
                               performer=info.get('artist') or info.get('uploader'))
            else:
                bot.send_video(chat_id, f)

        bot.delete_message(chat_id, call.message.message_id)

    except Exception as e:
        bot.edit_message_text(f"صار خطأ بالتحميل: {str(e)}", chat_id, call.message.message_id)
    finally:
        # Fix #6: تنظيف الملفات دايماً حتى عند الخطأ
        cleanup_file(filename)


print("الملكة REI جاهزة للعمل... 🚀")
bot.infinity_polling()
