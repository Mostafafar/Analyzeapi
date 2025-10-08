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
    """استخراج سوالات از فایل PDF با فرمت آزمون‌های ایرانی"""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            full_text += page.get_text()
        
        doc.close()
        
        print(f"متن استخراج شده: {full_text[:500]}...")  # برای دیباگ
        
        # الگوهای مختلف برای سوالات آزمون‌های ایرانی
        questions = {}
        
        # الگوی اصلی: شماره سوال به صورت عدد و متن سوال
        # مثال: "۱- در خصوص انواع یاخته‌ها..."
        pattern1 = r'(\d+)[\-\.\)]\s*(.*?)(?=\d+[\-\.\)]|\Z)'
        matches1 = re.findall(pattern1, full_text, re.DOTALL)
        
        # الگوی جایگزین: سوال‌هایی که با عدد و خط تیره شروع می‌شوند
        pattern2 = r'(\d+)\-\s*(.*?)(?=\d+\-|\Z)'
        matches2 = re.findall(pattern2, full_text, re.DOTALL)
        
        # الگوی برای سوالات داخل کادر یا فرمت خاص
        pattern3 = r'سوال\s*(\d+)[\:\-]?\s*(.*?)(?=سوال\s*\d+|\d+[\-\.\)]|\Z)'
        matches3 = re.findall(pattern3, full_text, re.DOTALL | re.IGNORECASE)
        
        # ترکیب همه matches
        all_matches = matches1 + matches2 + matches3
        
        for match in all_matches:
            try:
                q_num = int(match[0])
                q_text = match[1].strip()
                
                # پاک‌سازی متن سوال
                q_text = re.sub(r'[\n\r]+', ' ', q_text)  # حذف خطوط جدید
                q_text = re.sub(r'\s+', ' ', q_text)  # جایگزینی فاصله‌های متعدد
                
                # فیلتر کردن متن�های خیلی کوتاه
                if len(q_text) > 20 and not q_text.startswith('www.') and not q_text.startswith('http'):
                    questions[q_num] = q_text
                    print(f"سوال {q_num} یافت شد: {q_text[:50]}...")
            except ValueError:
                continue
        
        # اگر هنوز سوالی پیدا نکردیم، از روش ساده‌تر استفاده می‌کنیم
        if not questions:
            print("استفاده از روش ساده‌تر برای استخراج سوالات...")
            lines = full_text.split('\n')
            current_q = None
            current_text = ""
            
            for line in lines:
                line = line.strip()
                # تشخیص شروع سوال جدید
                q_match = re.match(r'^(\d+)[\-\.\)]\s*(.*)', line)
                if q_match:
                    if current_q is not None and current_text.strip():
                        questions[current_q] = current_text.strip()
                    
                    current_q = int(q_match.group(1))
                    current_text = q_match.group(2)
                elif current_q is not None:
                    # اگر خط جدید بخشی از سوال جاری است
                    if line and not line.startswith('www.') and not line.startswith('http'):
                        current_text += " " + line
            
            # اضافه کردن آخرین سوال
            if current_q is not None and current_text.strip():
                questions[current_q] = current_text.strip()
        
        print(f"تعداد سوالات استخراج شده: {len(questions)}")
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
    {text[:1500]}
    
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
        preview = q_text[:80] + "..." if len(q_text) > 80 else q_text
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
            available = list(questions.keys())
            bot.reply_to(message, f"❌ سوال {q_number} یافت نشد. سوالات موجود: {min(available)} تا {max(available)}")
            
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
                "این یک سوال زیست شناسی است. لطفاً آن را تحلیل کرده و نکات کلیدی را استخراج کن:"
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
                    "این یک سوال زیست شناسی است. لطفاً آن را تحلیل کن:"
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
            bot.reply_to(message, """❌ هیچ سوالی در فایل پیدا نشد.

📝 **راهنمایی:**
- مطمئن شوید فایل PDF قابل انتخاب باشد (اسکن تصویری نباشد)
- سوالات باید با فرمت استاندارد باشند (مثلاً: '۱- متن سوال...')
- فایل ممکن است قفل باشد یا محافظت شده باشد

🔄 لطفاً فایل PDF دیگری ارسال کنید.""")
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
        response += "یا عدد سوال را مستقیم تایپ کنید (مثلاً: 5)"
        
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
            # ایجاد پیام دستوری برای نمایش سوال
            fake_message = type('obj', (object,), {
                'from_user': message.from_user,
                'chat': message.chat,
                'text': f'/question {q_number}'
            })
            show_specific_question(fake_message)
            return
        else:
            bot.reply_to(message, f"❌ سوال {q_number} یافت نشد. از /list برای دیدن سوالات موجود استفاده کنید.")
            
    except ValueError:
        # اگر عدد نبود، راهنمایی نمایش بده
        bot.reply_to(message, """
📚 برای استفاده:
1. فایل PDF سوالات را ارسال کنید
2. از دستورات استفاده کنید:

/list - نمایش لیست سوالات  
/question 5 - نمایش سوال 5
/analyze 5 - تحلیل سوال 5
/clear - پاک کردن سوالات

یا عدد سوال را مستقیم تایپ کنید (مثلاً: 5)
        """)

# اجرای ربات
if __name__ == "__main__":
    print("🤖 ربات سوالات PDF فعال شد...")
    print("📚 آماده دریافت فایل‌های PDF...")
    bot.polling()
