import telebot
from telebot.types import Message

# التوكين مالتك
TOKEN = '8159446452:AAGtFNGAfMxoC2iPwE06Z0gnW0IUUvmAEa0'
bot = telebot.TeleBot(TOKEN)

# قاموس لحفظ بيانات الكروبات (الرتب والاعدادات)
groups_data = {}

def get_group_data(chat_id):
    if chat_id not in groups_data:
        groups_data[chat_id] = {
            'locked': False, 
            'welcome': True, 
            'anti_links': False,
            'admins': [], 
            'vips': []
        }
    return groups_data[chat_id]

# --- دوال التحقق من الرتب ---
def is_owner(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status == 'creator'
    except:
        return False

def is_admin(chat_id, user_id):
    if is_owner(chat_id, user_id): return True
    return user_id in get_group_data(chat_id)['admins']

def is_vip(chat_id, user_id):
    if is_admin(chat_id, user_id): return True
    return user_id in get_group_data(chat_id)['vips']

# --- الترحيب بالاعضاء الجدد ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(message: Message):
    data = get_group_data(message.chat.id)
    if data['welcome']:
        for new_member in message.new_chat_members:
            bot.reply_to(message, f"نورت الكروب يا {new_member.first_name}! 🌹")

# --- اوامر التفعيل والتعطيل (للمالك والمدراء فقط) ---
@bot.message_handler(commands=['تفعيل_الترحيب', 'تعطيل_الترحيب', 'قفل_الشات', 'فتح_الشات'])
def toggle_settings(message: Message):
    if not is_admin(message.chat.id, message.from_user.id):
        return bot.reply_to(message, "عذراً، هذا الأمر للمدراء فقط.")
    
    data = get_group_data(message.chat.id)
    cmd = message.text.replace('/', '')

    if cmd == 'تفعيل_الترحيب':
        data['welcome'] = True
        bot.reply_to(message, "✅ تم تفعيل الترحيب.")
    elif cmd == 'تعطيل_الترحيب':
        data['welcome'] = False
        bot.reply_to(message, "❌ تم تعطيل الترحيب.")
    elif cmd == 'قفل_الشات':
        data['locked'] = True
        bot.reply_to(message, "🔒 تم قفل الشات. فقط المميزين والمدراء يكدرون يراسلون.")
    elif cmd == 'فتح_الشات':
        data['locked'] = False
        bot.reply_to(message, "🔓 تم فتح الشات للكل.")

# --- رفع وتنزيل الرتب (بالرد على الرسالة) ---
@bot.message_handler(func=lambda m: m.text in ['رفع مدير', 'تنزيل مدير', 'رفع مميز', 'تنزيل مميز'] and m.reply_to_message)
def manage_roles(message: Message):
    if not is_owner(message.chat.id, message.from_user.id) and 'مدير' in message.text:
        return bot.reply_to(message, "عذراً، فقط المالك يكدر يرفع مدراء.")
    
    if not is_admin(message.chat.id, message.from_user.id) and 'مميز' in message.text:
        return bot.reply_to(message, "عذراً، هذا الأمر للمدراء والمالك.")

    target_user_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.first_name
    data = get_group_data(message.chat.id)

    if message.text == 'رفع مدير':
        if target_user_id not in data['admins']: data['admins'].append(target_user_id)
        bot.reply_to(message, f"✅ تم رفع {target_name} كـ مدير.")
    elif message.text == 'تنزيل مدير':
        if target_user_id in data['admins']: data['admins'].remove(target_user_id)
        bot.reply_to(message, f"❌ تم تنزيل {target_name} من الإدارة.")
    elif message.text == 'رفع مميز':
        if target_user_id not in data['vips']: data['vips'].append(target_user_id)
        bot.reply_to(message, f"✅ تم رفع {target_name} كـ مميز.")
    elif message.text == 'تنزيل مميز':
        if target_user_id in data['vips']: data['vips'].remove(target_user_id)
        bot.reply_to(message, f"❌ تم تنزيل {target_name} من المميزين.")

# --- أمر مسح الرسائل ---
@bot.message_handler(func=lambda m: m.text and m.text.startswith('مسح '))
def purge_messages(message: Message):
    if not is_admin(message.chat.id, message.from_user.id):
        return
    
    try:
        count = int(message.text.split(' ')[1])
        if count <= 0 or count > 100:
            return bot.reply_to(message, "الرجاء تحديد رقم بين 1 و 100.")
        
        message_id = message.message_id
        # نحذف رسالة الامر والرسائل اللي قبلها
        for i in range(count):
            try:
                bot.delete_message(message.chat.id, message_id - i)
            except:
                pass 
    except ValueError:
        bot.reply_to(message, "اكتب الأمر هيج: مسح 10")

# --- مراقب الشات (حذف رسائل الشات المقفول) ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'document', 'sticker', 'voice'])
def chat_monitor(message: Message):
    data = get_group_data(message.chat.id)
    
    # التحقق من قفل الشات
    if data['locked']:
        if not is_vip(message.chat.id, message.from_user.id):
            bot.delete_message(message.chat.id, message.message_id)

print("Bot is running...")
bot.infinity_polling()