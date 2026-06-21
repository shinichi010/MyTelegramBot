import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import os
import subprocess

# جلب التوكن من متغيرات البيئة في ريلواي
TOKEN = os.getenv('BOT_TOKEN')

# تأكد أن التوكن موجود حتى ما يصير كراش
if not TOKEN:
    raise ValueError("لازم تضيف BOT_TOKEN بمتغيرات البيئة (Variables) في Railway!")

bot = telebot.TeleBot(TOKEN)

# مسارات ملفات الكوكيز (لازم ترفعها وي المشروع على GitHub)
IG_COOKIES = 'ig_cookies.txt'
X_COOKIES = 'x_cookies.txt'

def download_media(url, format_type='best', cookies_file=None):
    ydl_opts = {
        'outtmpl': '%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
    }
    
    # تحديد الصيغ بناءً على الطلب
    if format_type == 'audio':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
        })
    elif format_type == '720p':
        ydl_opts.update({'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'})
    else:
        # لبقية المنصات (تيكتوك، فيسبوك، الخ)
        ydl_opts.update({'format': 'best'})
    
    # دمج الكوكيز إذا تم تمريرها وموجودة كملف
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts['cookiefile'] = cookies_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        # تصحيح اسم الملف في حال تم تحويله الى mp3
        if format_type == 'audio' and not filename.endswith('.mp3'):
            filename = filename.rsplit('.', 1)[0] + '.mp3'
            
        return filename, info

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "هلا بيك! دزلي أي رابط (يوتيوب، تيك توك، انستا، اكس، سبوتيفاي، الخ) وأني أحمله إلك.")

@bot.message_handler(func=lambda message: 'http' in message.text)
def handle_url(message):
    url = message.text
    chat_id = message.chat.id
    msg = bot.reply_to(message, "جاري المعالجة وتحليل الرابط... ⏳")

    try:
        # معالجة روابط اليوتيوب (تخيير المستخدم)
        if 'youtube.com' in url or 'youtu.be' in url:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("فيديو 720p 🎬", callback_data=f"yt_vid|{url}"),
                InlineKeyboardButton("مقطع صوتي 🎵", callback_data=f"yt_aud|{url}")
            )
            
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'مقطع يوتيوب')
            
            bot.edit_message_text(f"معلومات المقطع:\n*{title}*\n\nشنو تحب تحمل؟", 
                                  chat_id, msg.message_id, reply_markup=markup, parse_mode="Markdown")
            return

        # معالجة روابط سبوتيفاي عبر SpotDL لجلب اعلى جودة مع الغلاف والمعلومات
        if 'spotify.com' in url:
            bot.edit_message_text("جاري تحميل مسار سبوتيفاي بأعلى جودة... 🎵", chat_id, msg.message_id)
            output_name = f"{chat_id}_spotify.mp3"
            # استدعاء أداة spotdl
            subprocess.run(['spotdl', url, '--output', output_name], stdout=subprocess.DEVNULL)
            
            if os.path.exists(output_name):
                with open(output_name, 'rb') as f:
                    bot.send_audio(chat_id, f)
                os.remove(output_name)
                bot.delete_message(chat_id, msg.message_id)
            else:
                bot.edit_message_text("فشل تحميل مسار سبوتيفاي.", chat_id, msg.message_id)
            return

        # تحديد ملف الكوكيز المناسب لباقي المنصات
        cookies = None
        if 'instagram.com' in url:
            cookies = IG_COOKIES
        elif 'twitter.com' in url or 'x.com' in url:
            cookies = X_COOKIES

        # التحميل لباقي المنصات
        filename, info = download_media(url, format_type='best', cookies_file=cookies)
        
        bot.edit_message_text("جاري الرفع للتيليجرام... 🚀", chat_id, msg.message_id)
        
        # إرسال الملف بناءً على صيغته
        with open(filename, 'rb') as f:
            if filename.endswith(('.mp3', '.m4a', '.wav')):
                bot.send_audio(chat_id, f, title=info.get('title'), performer=info.get('uploader'))
            elif filename.endswith(('.mp4', '.webm', '.mkv')):
                bot.send_video(chat_id, f)
            elif filename.endswith(('.jpg', '.png', '.jpeg')):
                bot.send_photo(chat_id, f)
            else:
                bot.send_document(chat_id, f)
        
        # تنظيف الملفات بعد الإرسال
        os.remove(filename)
        bot.delete_message(chat_id, msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"عذراً، صار خطأ: {str(e)}", chat_id, msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('yt_'))
def yt_callback(call):
    action, url = call.data.split('|', 1)
    chat_id = call.message.chat.id
    
    bot.edit_message_text("جاري التحميل من يوتيوب... ⏳", chat_id, call.message.message_id)
    
    try:
        format_type = '720p' if action == 'yt_vid' else 'audio'
        filename, info = download_media(url, format_type=format_type)
        
        bot.edit_message_text("جاري الرفع... 🚀", chat_id, call.message.message_id)
        
        with open(filename, 'rb') as f:
            if format_type == 'audio':
                bot.send_audio(chat_id, f, title=info.get('title'), performer=info.get('uploader'))
            else:
                bot.send_video(chat_id, f)
        
        os.remove(filename)
        bot.delete_message(chat_id, call.message.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"صار خطأ بالتحميل: {str(e)}", chat_id, call.message.message_id)

print("البوت شغال الآن وينتظر الروابط...")
bot.infinity_polling()
