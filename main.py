import os
import requests
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8985962353:AAFaVUGz_fG0TiQahL2pKS06eMlogK_bQw0"
FIREBASE_DB_URL = "https://muteflow-41579-default-rtdb.firebaseio.com"

def log_stats(user_id):
    try:
        requests.patch(f"{FIREBASE_DB_URL}/stats.json", json={"last_user": user_id})
        res = requests.get(f"{FIREBASE_DB_URL}/stats/total_processed.json").json() or 0
        requests.put(f"{FIREBASE_DB_URL}/stats/total_processed.json", json=res + 1)
    except Exception as e:
        print(f"Database error: {e}")

def process_video(input_path, output_path):
    audio_path = "temp_audio.wav"
    # 1. استخراج الصوت من الفيديو
    subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", audio_path], check=True)
    
    # 2. فصل الموسيقى باستخدام Demucs
    subprocess.run(["demucs", "--two-stems=vocals", "-n", "htdemucs", audio_path], check=True)
    
    vocals_path = "separated/htdemucs/temp_audio/vocals.wav"
    
    # 3. دمج الصوت النظيف مع الفيديو الأصلي
    subprocess.run(["ffmpeg", "-y", "-i", input_path, "-i", vocals_path, "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", output_path], check=True)

    if os.path.exists(audio_path): os.remove(audio_path)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحباً بك في MuteFlow Bot 🎧!\nأرسل لي أي فيديو وسيتم إزالة الموسيقى منه فوراً.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري تحميل الفيديو...")
    user_id = update.message.from_user.id
    input_file = f"input_{user_id}.mp4"
    output_file = f"output_{user_id}.mp4"

    try:
        video = await update.message.video.get_file()
        await video.download_to_drive(input_file)
        
        await msg.edit_text("⚡ جاري فصل الموسيقى باستخدام الذكاء الاصطناعي... قد يستغرق ذلك دقيقة أو دقيقتين.")
        process_video(input_file, output_file)
        
        await msg.edit_text("📤 جاري إرسال الفيديو النظيف...")
        with open(output_file, 'rb') as v:
            await update.message.reply_video(video=v, caption="تمت إزالة الموسيقى بنجاح عبر @MuteFlow_bot ✨")
        
        log_stats(user_id)
        await msg.delete()
    except Exception as e:
        await msg.edit_text("❌ حدث خطأ أثناء معالجة الفيديو، تأكد من حجم وثواني الفيديو وحاول مرة أخرى.")
    finally:
        for p in [input_file, output_file]:
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    print("Bot is running...")
    app.run_polling()
