import telebot
import requests
import json
import os

# توکن‌ها - اینجا رو پر کنید
TELEGRAM_BOT_TOKEN = "8316442002:AAHkjQxfSzyla3ycKWXFGSV5M3piIXrJMk0"  # از @BotFather بگیرید
HF_API_TOKEN = "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"  # توکن Hugging Face شما

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# مدل‌های رایگان Hugging Face
MODELS = {
    "mistral": "mistralai/Mistral-7B-Instruct-v0.1",
    "llama": "meta-llama/Llama-2-7b-chat-hf", 
    "bloom": "bigscience/bloomz-7b1",
    "falcon": "tiiuae/falcon-7b-instruct"
}

def analyze_with_hf(file_content, filename):
    """ارسال محتوای فایل به Hugging Face API"""
    
    model = MODELS["mistral"]  # مدل پیشفرض
    api_url = f"https://api-inference.huggingface.co/models/{model}"
    
    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # محدود کردن محتوا اگر طولانی باشد
    if len(file_content) > 1500:
        content_preview = file_content[:1500] + "..."
    else:
        content_preview = file_content
    
    prompt = f"""
    لطفاً محتوای فایل {filename} را تحلیل و خلاصه کن.
    نکات کلیدی و مهم را به زبان فارسی استخراج کن.
    
    محتوای فایل:
    {content_preview}
    
    تحلیل و خلاصه:
    """
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 500,
            "temperature": 0.7,
            "do_sample": True,
            "return_full_text": False
        }
    }
    
    try:
        print(f"📡 در حال ارسال درخواست به Hugging Face...")
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        print(f"📊 وضعیت پاسخ: {response.status_code}")
        
        if response.status_code == 503:
            # مدل در حال لود است
            estimate_time = 30
            try:
                error_data = response.json()
                estimate_time = error_data.get('estimated_time', 30)
            except:
                pass
            return f"⏳ مدل در حال بارگذاری است. لطفاً {int(estimate_time)} ثانیه دیگر تلاش کنید."
        elif response.status_code == 429:
            return "❌ محدودیت تعداد درخواست. لطفاً ۱ دقیقه صبر کنید."
        elif response.status_code != 200:
            return f"❌ خطای API: {response.status_code} - {response.text[:100]}"
        
        result = response.json()
        
        if isinstance(result, list) and len(result) > 0:
            if 'generated_text' in result[0]:
                generated_text = result[0]['generated_text']
                # حذف prompt تکراری اگر وجود دارد
                if prompt.strip() in generated_text:
                    generated_text = generated_text.replace(prompt.strip(), "").strip()
                return generated_text if generated_text else "❌ پاسخ خالی دریافت شد."
            else:
                return str(result[0])
        else:
            return "❌ پاسخ نامعتبر از API دریافت شد."
            
    except requests.exceptions.Timeout:
        return "❌ خطای timeout: سرور پاسخ نداده است."
    except Exception as e:
        return f"❌ خطا در تحلیل فایل: {str(e)}"

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🤖 **به ربات تحلیل فایل خوش آمدید!**

📎 می‌تونید فایل‌های متنی (txt) رو ارسال کنید.
من فایل رو با هوش مصنوعی تحلیل می‌کنم.

🆓 **این سرویس کاملاً رایگان است!**

📋 **دستورات:**
/start - نمایش این پیام
/models - نمایش مدل‌های موجود
/test - تست اتصال به API
/status - وضعیت ربات

📁 **فقط فایل‌های txt پذیرفته می‌شوند.**
    """
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['models'])
def show_models(message):
    models_text = """
🤖 **مدل‌های موجود:**

• mistral - Mistral 7B (پیشفرض)
• llama - Llama 2 7B  
• bloom - BLOOMZ 7B
• falcon - Falcon 7B

🔄 ممکن است اولین درخواست ۲۰-۳۰ ثانیه طول بکشد.
    """
    bot.reply_to(message, models_text)

@bot.message_handler(commands=['test'])
def test_api(message):
    """تست اتصال به Hugging Face API"""
    bot.send_message(message.chat.id, "🔍 در حال تست اتصال به API...")
    
    test_content = "این یک متن تستی برای بررسی عملکرد ربات است. لطفاً آن را تحلیل کن."
    test_result = analyze_with_hf(test_content, "test.txt")
    
    if "خطا" not in test_result and "Error" not in test_result:
        bot.send_message(message.chat.id, f"✅ اتصال موفق!\n\n{test_result}")
    else:
        bot.send_message(message.chat.id, f"❌ مشکل در اتصال:\n{test_result}")

@bot.message_handler(commands=['status'])
def show_status(message):
    """نمایش وضعیت ربات"""
    status_text = """
🟢 **ربات فعال است**

🔑 Hugging Face API: متصل
🆓 سرویس: رایگان
📊 مدل: Mistral 7B

✅ آماده دریافت فایل‌های txt
    """
    bot.reply_to(message, status_text)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        if not message.document.file_name.endswith('.txt'):
            bot.reply_to(message, "❌ لطفاً فقط فایل‌های متنی (txt) ارسال کنید.")
            return
        
        bot.send_message(message.chat.id, "📥 فایل دریافت شد. در حال تحلیل... (لطفاً شکیبا باشید - ممکن است ۳۰ ثانیه طول بکشد)")
        
        # دریافت فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # ذخیره موقت
        filename = message.document.file_name
        with open(filename, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # خواندن محتوا
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            try:
                with open(filename, 'r', encoding='latin-1') as f:
                    content = f.read()
            except:
                bot.send_message(message.chat.id, "❌ خطا در خواندن فایل. از encoding استاندارد استفاده کنید.")
                os.remove(filename)
                return
        
        if not content.strip():
            bot.send_message(message.chat.id, "❌ فایل خالی است.")
            os.remove(filename)
            return
        
        if len(content) > 50000:
            bot.send_message(message.chat.id, "❌ فایل خیلی بزرگ است. حداکثر ۵۰,۰۰۰ کاراکتر مجاز است.")
            os.remove(filename)
            return
        
        # تحلیل محتوا
        analysis_result = analyze_with_hf(content, filename)
        
        # ارسال نتیجه
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
    if message.text.startswith('/'):
        return
    bot.send_message(message.chat.id, "📎 برای تحلیل فایل، یک فایل txt ارسال کنید یا از /help استفاده کنید.")

# اجرای ربات
if __name__ == "__main__":
    print("🤖 ربات Hugging Face فعال شد...")
    print("🔑 توکن: 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")
    print("🆓 این سرویس کاملاً رایگان است!")
    print("🚀 برای شروع، از دستور /test استفاده کنید")
    print("⏹️ برای خروج: Ctrl+C")
    bot.polling()
