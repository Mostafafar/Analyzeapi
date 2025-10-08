import telebot
import requests
import json
import os
import fitz  # PyMuPDF
import re
from collections import defaultdict
import pytesseract
from PIL import Image
import io
import tempfile

# توکن‌ها
TELEGRAM_BOT_TOKEN = "8316442002:AAHkjQxfSzyla3ycKWXFGSV5M3piIXrJMk0"
HF_API_TOKEN = os.environ.get('HF_API_TOKEN', '')

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# دیکشنری برای ذخیره سوالات کاربران
user_questions = defaultdict(dict)

def extract_text_with_ocr(pdf_path):
    """استخراج متن از PDF با استفاده از OCR"""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # ابتدا سعی می‌کنیم متن مستقیم استخراج کنیم
            text = page.get_text()
            if text.strip():  # اگر متن مستقیم وجود داشت
                full_text += text + "\n"
            else:
                # اگر متن مستقیم نبود، از OCR استفاده می‌کنیم
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # افزایش کیفیت
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data))
                
                # استفاده از OCR برای فارسی
                custom_config = r'--oem 3 --psm 6 -l fas+eng'
                ocr_text = pytesseract.image_to_string(image, config=custom_config)
                full_text += ocr_text + "\n"
        
        doc.close()
        return full_text
        
    except Exception as e:
        print(f"خطا در OCR: {e}")
        return ""

def extract_questions_from_pdf(pdf_path):
    """استخراج سوالات از فایل PDF"""
    try:
        # ابتدا متن مستقیم استخراج می‌شود
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            full_text += page.get_text()
        
        doc.close()
        
        print(f"متن مستقیم استخراج شده: {len(full_text)} کاراکتر")
        
        # اگر متن مستقیم کافی نبود، از OCR استفاده می‌کنیم
        if len(full_text.strip()) < 100:
            print("استفاده از OCR...")
            full_text = extract_text_with_ocr(pdf_path)
            print(f"متن OCR شده: {len(full_text)} کاراکتر")
        
        # نمایش نمونه متن برای دیباگ
        sample = full_text[:500].replace('\n', ' ')
        print(f"نمونه متن: {sample}")
        
        # الگوهای استخراج سوالات
        questions = {}
        
        # الگوهای مختلف برای سوالات فارسی
        patterns = [
            r'(\d+)[\-\.\)]\s*(.*?)(?=\d+[\-\.\)]|$)',
            r'سوال\s*(\d+)[\:\-]?\s*(.*?)(?=سوال\s*\d+|\d+[\-\.\)]|$)',
            r'\(\s*(\d+)\s*\)\s*(.*?)(?=\(\s*\d+\s*\)|\d+[\-\.\)]|$)',
            r'(\d+)\s*-\s*(.*?)(?=\d+\s*-|\d+[\-\.\)]|$)'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, full_text, re.DOTALL)
            for match in matches:
                try:
                    q_num = int(match.group(1))
                    q_text = match.group(2).strip()
                    
                    # پاک‌سازی متن
                    q_text = re.sub(r'[\n\r\t]+', ' ', q_text)
                    q_text = re.sub(r'\s+', ' ', q_text)
                    q_text = q_text.strip()
                    
                    # فیلترهای کیفیت
                    if (len(q_text) > 30 and 
                        not any(word in q_text.lower() for word in ['www.', 'http', '.com', '.ir']) and
                        not q_text.replace(' ', '').replace('.', '').isdigit()):
                        
                        # محدود کردن طول متن
                        if len(q_text) > 500:
                            q_text = q_text[:500] + "..."
                            
                        questions[q_num] = q_text
                        print(f"✅ سوال {q_num} یافت شد")
                        
                except (ValueError, IndexError) as e:
                    continue
        
        # اگر هنوز سوالی پیدا نکردیم، روش ساده‌تر
        if not questions:
            print("استفاده از روش ساده‌تر...")
            lines = full_text.split('\n')
            current_q = None
            current_text = ""
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                # تشخیص سوال جدید
                q_match = re.match(r'^(\d+)[\-\.\)]\s*(.*)', line)
                if q_match:
                    if current_q is not None and current_text.strip():
                        questions[current_q] = current_text.strip()
                    
                    current_q = int(q_match.group(1))
                    current_text = q_match.group(2)
                elif current_q is not None and line:
                    # ادامه سوال جاری
                    if (not line.startswith('www.') and 
                        not line.startswith('http') and
                        len(line) > 5):
                        current_text += " " + line
                
                # اگر خط خالی است و متن زیادی جمع شده، سوال را ذخیره کن
                elif current_q is not None and not line and len(current_text) > 50:
                    questions[current_q] = current_text.strip()
                    current_q = None
                    current_text = ""
            
            # آخرین سوال
            if current_q is not None and current_text.strip():
                questions[current_q] = current_text.strip()
        
        print(f"🎯 تعداد سوالات استخراج شده: {len(questions)}")
        return questions
        
    except Exception as e:
        print(f"❌ خطا در استخراج PDF: {e}")
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
    {text[:1000]}
    
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

# هندلرهای ربات (همانند قبل)
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🤖 **ربات تحلیل سوالات PDF**

📚 **قابلیت‌های جدید:**
• پشتیبانی از PDFهای اسکن شده (تصویری)
• استخراج متن با OCR
• نمایش و تحلیل سوالات

📋 **دستورات:**
/start - راهنمایی
/list - نمایش لیست سوالات  
/question [عدد] - نمایش سوال خاص
/analyze [عدد] - تحلیل سوال با AI
/clear - پاک کردن سوالات

📁 **فایل PDF خود را ارسال کنید**
(حتی اگر اسکن تصویری باشد)
    """
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['list'])
def show_questions_list(message):
    user_id = message.from_user.id
    if user_id not in user_questions or not user_questions[user_id]:
        bot.reply_to(message, "❌ هیچ سوالی ذخیره نشده است.")
        return
    
    questions = user_questions[user_id]
    sorted_questions = sorted(questions.items())
    
    response = f"📋 **لیست سوالات** ({len(questions)} سوال)\n\n"
    for q_num, q_text in sorted_questions[:10]:  # فقط 10 سوال اول
        preview = q_text[:60] + "..." if len(q_text) > 60 else q_text
        response += f"**سوال {q_num}:** {preview}\n\n"
    
    if len(questions) > 10:
        response += f"📖 ... و {len(questions) - 10} سوال دیگر\n"
    
    response += "➡️ برای نمایش کامل: /question [عدد]"
    bot.reply_to(message, response)

@bot.message_handler(commands=['question'])
def show_specific_question(message):
    user_id = message.from_user.id
    if user_id not in user_questions or not user_questions[user_id]:
        bot.reply_to(message, "❌ هیچ سوالی ذخیره نشده است.")
        return
    
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, "❌ لطفاً شماره سوال را وارد کنید:\n/question 5")
            return
        
        q_number = int(command_parts[1])
        questions = user_questions[user_id]
        
        if q_number in questions:
            response = f"**سوال {q_number}:**\n\n{questions[q_number]}"
            bot.reply_to(message, response)
        else:
            available = list(questions.keys())
            bot.reply_to(message, f"❌ سوال {q_number} یافت نشد. سوالات موجود: {min(available)}-{max(available)}")
            
    except ValueError:
        bot.reply_to(message, "❌ شماره سوال باید عدد باشد.")

@bot.message_handler(commands=['analyze'])
def analyze_question(message):
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
            bot.send_message(message.chat.id, f"🔍 تحلیل سوال {q_number}...")
            analysis = analyze_with_hf(questions[q_number], "این سوال زیست شناسی است. تحلیل کن:")
            response = f"**تحلیل سوال {q_number}:**\n\n{analysis}"
            bot.reply_to(message, response)
        else:
            bot.reply_to(message, f"❌ سوال {q_number} یافت نشد.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

@bot.message_handler(commands=['clear'])
def clear_questions(message):
    user_id = message.from_user.id
    user_questions[user_id] = {}
    bot.reply_to(message, "✅ سوالات پاک شدند.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        user_id = message.from_user.id
        
        if not message.document.file_name.lower().endswith('.pdf'):
            bot.reply_to(message, "❌ فقط فایل PDF ارسال کنید.")
            return
        
        bot.send_message(message.chat.id, "📥 دریافت فایل...")
        
        # دریافت فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # ذخیره موقت
        filename = f"temp_{user_id}.pdf"
        with open(filename, 'wb') as f:
            f.write(downloaded_file)
        
        # استخراج سوالات
        bot.send_message(message.chat.id, "🔍 در حال استخراج سوالات...")
        questions = extract_questions_from_pdf(filename)
        
        # حذف فایل موقت
        os.remove(filename)
        
        if not questions:
            bot.reply_to(message, """❌ سوالی استخراج نشد.

🔧 **راه‌حل‌ها:**
1. مطمئن شوید فایل قفل نباشد
2. سوالات با شماره واضح باشند (مثلاً: ۱- متن سوال)
3. فایل متن قابل انتخاب داشته باشد

📤 فایل دیگری ارسال کنید""")
            return
        
        # ذخیره سوالات
        user_questions[user_id] = questions
        
        # نمایش نتایج
        response = f"✅ **استخراج موفق**\n\n"
        response += f"📊 تعداد سوالات: {len(questions)}\n"
        response += f"🔢 محدوده: {min(questions.keys())}-{max(questions.keys())}\n\n"
        response += "**دستورات:**\n"
        response += "/list - نمایش لیست\n"
        response += "/question 5 - نمایش سوال 5\n"
        response += "/analyze 5 - تحلیل سوال 5\n"
        response += "یا عدد سوال را تایپ کنید"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text.startswith('/'):
        return
    
    try:
        q_number = int(message.text.strip())
        user_id = message.from_user.id
        
        if user_id in user_questions and q_number in user_questions[user_id]:
            fake_message = type('obj', (object,), {
                'from_user': message.from_user,
                'chat': message.chat,
                'text': f'/question {q_number}'
            })
            show_specific_question(fake_message)
        else:
            bot.reply_to(message, f"❌ سوال {q_number} یافت نشد. از /list استفاده کنید.")
            
    except ValueError:
        bot.reply_to(message, """
📚 راهنمایی:
1. PDF ارسال کنید
2. از دستورات استفاده کنید

/list - لیست سوالات
/question 5 - نمایش سوال  
/analyze 5 - تحلیل سوال
        """)

if __name__ == "__main__":
    print("🤖 ربات فعال شد...")
    bot.polling()
