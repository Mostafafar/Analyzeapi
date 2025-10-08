import telebot
import requests
import json
import os
import fitz  # PyMuPDF برای خواندن PDF
import re
from collections import defaultdict

# توکن‌ها
TELEGRAM_BOT_TOKEN = "8316442002:AAHkjQxfSzyla3ycKWXFGSV5M3piIXrJMk0"
HF_API_TOKEN = os.environ.get('HF_API_TOKEN', '')

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# دیکشنری برای ذخیره سوالات کاربران
user_questions = defaultdict(dict)

def extract_questions_from_pdf(pdf_path):
    """استخراج سوالات از فایل PDF"""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            full_text += page.get_text()
        
        doc.close()
        
        # استخراج سوالات با الگوهای مختلف
        questions = {}
        
        # الگوی سوالات عددی (سوال ۱, سوال ۲, ...)
        patterns = [
            r'سوال\s*(\d+)[:\-]?\s*(.*?)(?=سوال\s*\d+|$)',
            r'question\s*(\d+)[:\-]?\s*(.*?)(?=question\s*\d+|$)',
            r'(\d+)\.\s*(.*?)(?=\d+\.\s*|$)',
            r'\(\s*(\d+)\s*\)\s*(.*?)(?=\(\s*\d+\s*\)\s*|$)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                q_num = int(match[0])
                q_text = match[1].strip()
                if q_text and len(q_text) > 10:  # حداقل طول برای سوال
                    questions[q_num] = q_text
        
        # اگر الگو کار نکرد، خطوط را به صورت ساده تقسیم کنیم
        if not questions:
            lines = full_text.split('\n')
            current_question = None
            current_text = ""
            
            for line in lines:
                line = line.strip()
                if re.match(r'^(سوال\s*\d+|question\s*\d+|\d+\.)', line, re.IGNORECASE):
                    if current_question is not None:
                        questions[current_question] = current_text.strip()
                    
                    # استخراج شماره سوال
                    q_match = re.search(r'(\d+)', line)
                    if q_match:
                        current_question = int(q_match.group(1))
                        current_text = line
                    else:
                        current_question = None
                elif current_question is not None:
                    current_text += " " + line
            
            if current_question is not None:
                questions[current_question] = current_text.strip()
        
        return questions
        
    except Exception as e:
        print(f"خطا در استخراج PDF: {e}")
        return {}

def analyze_with_hf(text, context=""):
    """تحلیل متن با Hugging Face"""
    if not HF_API_TOKEN:
        return "❌ توکن API تنظیم نشده است."
    
    api_url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1"
    
    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    {context}
    
    متن:
    {text[:2000]}
    
    تحلیل به زبان فارسی:
    """
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 300,
            "temperature": 0.7,
            "do_sample": True,
            "return_full_text": False
        }
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get('generated_text', '❌ پاسخ خالی دریافت شد.')
        else:
            return f"❌ خطای API: {response.status_code}"
            
    except Exception as e:
        return f"❌ خطا در اتصال: {str(e)}"
    
    return "❌ پاسخ نامعتبر"

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🤖 **ربات تحلیل سوالات PDF**

📚 **قابلیت‌ها:**
• دریافت فایل‌های PDF حاوی سوالات
• استخراج خودکار سوالات
• نمایش سوالات خاص
• تحلیل سوالات با هوش مصنوعی

📋 **دستورات:**
/start - راهنمایی
/list - نمایش لیست سوالات
/question [عدد] - نمایش سوال خاص
/analyze [عدد] - تحلیل سوال با AI
/clear - پاک کردن سوالات ذخیره شده

📁 **فایل PDF خود را ارسال کنید**
    """
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['list'])
def show_questions_list(message):
    """نمایش لیست سوالات استخراج شده"""
    user_id = message.from_user.id
    
    if user_id not in user_questions or not user_questions[user_id]:
        bot.reply_to(message, "❌ هیچ سوالی ذخیره نشده است. ابتدا یک فایل PDF ارسال کنید.")
        return
    
    questions = user_questions[user_id]
    sorted_questions = sorted(questions.items())
    
    response = f"📋 **لیست سوالات** ({len(questions)} سوال)\n\n"
    
    for q_num, q_text in sorted_questions:
        preview = q_text[:100] + "..." if len(q_text) > 100 else q_text
        response += f"**سوال {q_num}:** {preview}\n\n"
    
    response += "➡️ برای نمایش کامل یک سوال: /question [عدد]"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['question'])
def show_specific_question(message):
    """نمایش سوال خاص"""
    user_id = message.from_user.id
    
    if user_id not in user_questions or not user_questions[user_id]:
        bot.reply_to(message, "❌ هیچ سوالی ذخیره نشده است.")
        return
    
    try:
        # استخراج شماره سوال از پیام
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, "❌ لطفاً شماره سوال را وارد کنید:\n/question 5")
            return
        
        q_number = int(command_parts[1])
        questions = user_questions[user_id]
        
        if q_number in questions:
            response = f"**سوال {q_number}:**\n\n{questions[q_number]}"
            
            # اضافه کردن دکمه‌های سریع
            markup = telebot.types.InlineKeyboardMarkup()
            analyze_btn = telebot.types.InlineKeyboardButton(
                f"تحلیل سوال {q_number}", 
                callback_data=f"analyze_{q_number}"
            )
            markup.add(analyze_btn)
            
            bot.reply_to(message, response, reply_markup=markup)
        else:
            bot.reply_to(message, f"❌ سوال {q_number} یافت نشد.")
            
    except ValueError:
        bot.reply_to(message, "❌ شماره سوال باید یک عدد باشد.")
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

@bot.message_handler(commands=['analyze'])
def analyze_question(message):
    """تحلیل سوال با هوش مصنوعی"""
    user_id = message.from_user.id
    
    if user_id not in user_questions or not user_questions[user_id]:
        bot.reply_to(message, "❌ هیچ سوالی ذخیره نشده است.")
        return
    
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, "❌ لطفاً شماره سوال را وارد کنید:\n/analyze 5")
            return
        
        q_number = int(command_parts[1])
        questions = user_questions[user_id]
        
        if q_number in questions:
            bot.send_message(message.chat.id, f"🔍 در حال تحلیل سوال {q_number}...")
            
            analysis = analyze_with_hf(
                questions[q_number], 
                "این یک سوال درسی است. لطفاً آن را تحلیل کرده و نکات کلیدی را استخراج کن:"
            )
            
            response = f"**تحلیل سوال {q_number}:**\n\n{analysis}"
            bot.reply_to(message, response)
        else:
            bot.reply_to(message, f"❌ سوال {q_number} یافت نشد.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ خطا در تحلیل: {str(e)}")

@bot.message_handler(commands=['clear'])
def clear_questions(message):
    """پاک کردن سوالات ذخیره شده"""
    user_id = message.from_user.id
    user_questions[user_id] = {}
    bot.reply_to(message, "✅ سوالات ذخیره شده پاک شدند.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """مدیریت کلیک روی دکمه‌های اینلاین"""
    user_id = call.from_user.id
    
    if call.data.startswith('analyze_'):
        try:
            q_number = int(call.data.split('_')[1])
            
            if user_id in user_questions and q_number in user_questions[user_id]:
                bot.answer_callback_query(call.id, "در حال تحلیل...")
                
                analysis = analyze_with_hf(
                    user_questions[user_id][q_number],
                    "این یک سوال درسی است. لطفاً آن را تحلیل کن:"
                )
                
                response = f"**تحلیل سوال {q_number}:**\n\n{analysis}"
                bot.send_message(call.message.chat.id, response)
            else:
                bot.answer_callback_query(call.id, "سوال یافت نشد!")
                
        except Exception as e:
            bot.answer_callback_query(call.id, "خطا در تحلیل!")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """مدیریت دریافت فایل PDF"""
    try:
        user_id = message.from_user.id
        
        if not message.document.file_name.lower().endswith('.pdf'):
            bot.reply_to(message, "❌ لطفاً فقط فایل PDF ارسال کنید.")
            return
        
        bot.send_message(message.chat.id, "📥 فایل PDF دریافت شد. در حال استخراج سوالات...")
        
        # دریافت فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # ذخیره موقت
        filename = f"temp_{user_id}.pdf"
        with open(filename, 'wb') as f:
            f.write(downloaded_file)
        
        # استخراج سوالات
        questions = extract_questions_from_pdf(filename)
        
        # حذف فایل موقت
        os.remove(filename)
        
        if not questions:
            bot.reply_to(message, "❌ هیچ سوالی در فایل پیدا نشد. از فرمت استاندارد استفاده کنید.")
            return
        
        # ذخیره سوالات
        user_questions[user_id] = questions
        
        # نمایش نتایج
        response = f"✅ **استخراج موفق**\n\n"
        response += f"📊 تعداد سوالات یافت شده: {len(questions)}\n"
        response += f"🔢 محدوده سوالات: {min(questions.keys())} تا {max(questions.keys())}\n\n"
        response += "**دستورات قابل استفاده:**\n"
        response += "/list - نمایش لیست سوالات\n"
        response += "/question [عدد] - نمایش سوال خاص\n"
        response += "/analyze [عدد] - تحلیل سوال\n"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        bot.reply_to(message, f"❌ خطا در پردازش فایل: {str(e)}")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    """مدیریت پیام‌های متنی"""
    if message.text.startswith('/'):
        return
    
    # اگر کاربر عدد وارد کرد، سوال مربوطه را نشان بده
    try:
        q_number = int(message.text.strip())
        user_id = message.from_user.id
        
        if user_id in user_questions and q_number in user_questions[user_id]:
            show_specific_question(message)
            return
    except ValueError:
        pass
    
    bot.reply_to(message, """
📚 برای استفاده:
1. فایل PDF سوالات را ارسال کنید
2. از دستورات استفاده کنید:

/list - نمایش لیست سوالات
/question 5 - نمایش سوال 5
/analyze 5 - تحلیل سوال 5
/clear - پاک کردن سوالات
    """)

# اجرای ربات
if __name__ == "__main__":
    print("🤖 ربات سوالات PDF فعال شد...")
    print("📚 آماده دریافت فایل‌های PDF...")
    bot.polling()
