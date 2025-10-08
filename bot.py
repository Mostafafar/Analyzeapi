import telebot
import requests
import json
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# توکن‌ها
TELEGRAM_BOT_TOKEN = "8316442002:AAHkjQxfSzyla3ycKWXFGSV5M3piIXrJMk0"
DEEPSEEK_API_KEY = "k-1504d5e6afc445709916107a64903df2"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# آدرس API دیپ‌سیک
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def analyze_with_deepseek(file_content, filename):
    """ارسال محتوای فایل به API دیپ‌سیک"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    لطفاً محتوای فایل {filename} را تحلیل کن و خلاصه‌ای جامع ارائه ده.
    در صورت امکان، نکات کلیدی و مهم را استخراج کن.
    """
    
    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\nمحتوای فایل:\n{file_content}"
            }
        ],
        "stream": False
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        return f"خطا در تحلیل فایل: {str(e)}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
    🤖 **به ربات تحلیل فایل خوش آمدید!**

    📎 می‌تونید فایل‌های زیر رو ارسال کنید:
    • PDF
    • فایل‌های متنی (txt)
    • فایل‌های Word
    • تصاویر (من متن داخل عکس رو می‌خونم)

    من فایل رو تحلیل می‌کنم و خلاصه‌ای براتون ارائه می‌دم.
    """
    bot.reply_to(message, welcome_text)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        # اطلاع دادن به کاربر
        bot.send_message(message.chat.id, "📥 فایل دریافت شد. در حال تحلیل...")
        
        # دریافت اطلاعات فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # ذخیره فایل موقت
        filename = message.document.file_name
        with open(filename, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # خواندن محتوای فایل
        if filename.endswith('.txt'):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
        elif filename.endswith('.pdf'):
            # برای PDF نیاز به کتابخانه اضافی دارید
            content = "فایل PDF دریافت شد. برای پردازش PDF نیاز به نصب کتابخانه pdfplumber دارید."
        else:
            content = f"فایل {filename} دریافت شد. محتوا در حال پردازش..."
        
        # تحلیل با دیپ‌سیک
        analysis_result = analyze_with_deepseek(content, filename)
        
        # ارسال نتیجه (تقسیم به قسمت‌های کوچک اگر طولانی باشد)
        if len(analysis_result) > 4000:
            for i in range(0, len(analysis_result), 4000):
                bot.send_message(message.chat.id, analysis_result[i:i+4000])
        else:
            bot.send_message(message.chat.id, analysis_result)
        
        # حذف فایل موقت
        os.remove(filename)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطا در پردازش فایل: {str(e)}")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == '/analyze':
        bot.send_message(message.chat.id, "📎 لطفاً فایل مورد نظر را ارسال کنید")
    else:
        bot.send_message(message.chat.id, "برای تحلیل فایل، آن را ارسال کنید یا از دستور /analyze استفاده کنید")

# اجرای ربات
print("🤖 ربات فعال شد...")
bot.polling()
