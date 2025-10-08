import telebot
import requests
import json
import os
import logging

# تنظیمات امن
TELEGRAM_BOT_TOKEN = "8316442002:AAHkjQxfSzyla3ycKWXFGSV5M3piIXrJMk0"
HF_API_TOKEN = os.environ.get('HF_API_TOKEN', '')  # امن‌تر

# لاگ‌گیری برای دیباگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

MODELS = {
    "mistral": "mistralai/Mistral-7B-Instruct-v0.1",
}

def analyze_with_hf(file_content, filename):
    """ارسال محتوای فایل به Hugging Face API"""
    
    if not HF_API_TOKEN:
        return "❌ توکن API تنظیم نشده است. لطفاً توکن Hugging Face را تنظیم کنید."
    
    model = MODELS["mistral"]
    api_url = f"https://api-inference.huggingface.co/models/{model}"
    
    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # محدود کردن محتوا
    content_preview = file_content[:1500] + "..." if len(file_content) > 1500 else file_content
    
    prompt = f"""
    تحلیل محتوای فایل {filename} به زبان فارسی:
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
        logger.info("ارسال درخواست به Hugging Face API")
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                generated_text = result[0].get('generated_text', '')
                # پاک‌سازی خروجی
                if prompt.strip() in generated_text:
                    generated_text = generated_text.replace(prompt.strip(), "").strip()
                return generated_text if generated_text else "❌ پاسخ خالی دریافت شد."
            return "❌ پاسخ نامعتبر از API"
            
        elif response.status_code == 503:
            return "⏳ مدل در حال بارگذاری است. لطفاً ۳۰ ثانیه دیگر تلاش کنید."
        elif response.status_code == 401:
            return "❌ توکن نامعتبر یا منقضی شده است."
        elif response.status_code == 429:
            return "❌ محدودیت تعداد درخواست. لطفاً کمی صبر کنید."
        else:
            return f"❌ خطای API: {response.status_code}"
            
    except Exception as e:
        return f"❌ خطا در اتصال: {str(e)}"

# هندلرهای دیگر بدون تغییر...
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🤖 ربات تحلیل فایل فعال است!")

@bot.message_handler(commands=['test'])
def test_api(message):
    bot.send_message(message.chat.id, "🔍 تست اتصال به API...")
    
    if not HF_API_TOKEN:
        bot.send_message(message.chat.id, "❌ توکن HF_API_TOKEN تنظیم نشده است!")
        return
        
    test_result = analyze_with_hf("متن تست", "test.txt")
    bot.send_message(message.chat.id, f"نتایج تست:\n{test_result}")

# هندلر فایل و متن بدون تغییر...

if __name__ == "__main__":
    print("🤖 ربات در حال راه‌اندازی...")
    if not HF_API_TOKEN:
        print("⚠️  هشدار: HF_API_TOKEN تنظیم نشده است!")
    bot.polling()
