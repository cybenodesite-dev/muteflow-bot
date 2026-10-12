import os
import time
import requests
import subprocess

# 1. تثبيت FFmpeg و Demucs والمكتبات
subprocess.run(["apt-get", "update"], stdout=subprocess.DEVNULL)
subprocess.run(["apt-get", "install", "-y", "ffmpeg"], stdout=subprocess.DEVNULL)
subprocess.run(["pip", "install", "demucs", "requests"], stdout=subprocess.DEVNULL)

TOKEN = "8985962353:AAFaVUGz_fG0TiQahL2pKS06eMlogK_bQw0"
FIREBASE_URL = "https://muteflow-41579-default-rtdb.firebaseio.com"
API_URL = f"https://api.telegram.org/bot{TOKEN}"

WATERMARK_IMG = "watermark.png"

# إعداد قائمة الأوامر الرسمية الموضحة في الصورة (Bot Commands Menu)
def setup_bot_commands():
    commands = [
        {"command": "start", "description": "رسالة البدء"},
        {"command": "help", "description": "الدعم والمعلومات"}
    ]
    try:
        requests.post(f"{API_URL}/setMyCommands", json={"commands": commands})
        print("Bot commands menu initialized successfully!")
    except Exception as e:
        print(f"Failed to set bot commands: {e}")

# الأزرار المدمجة بالرسائل (Inline Keyboard)
INLINE_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "💛 ادعمنا", "url": "https://muteflow.web.app/help"}],
        [{"text": "🌐 زيارة الموقع الرسمي", "url": "https://muteflow.web.app/"}],
        [{"text": "👨‍💻 المطور", "url": "https://t.me/X7OUD3"}]
    ]
}

def save_user(user_id, first_name, username):
    try:
        user_data = {
            "id": user_id,
            "name": first_name or "بدون اسم",
            "username": f"@{username}" if username else "لا يوجد",
            "last_active": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        requests.patch(f"{FIREBASE_URL}/users/{user_id}.json", json=user_data)
    except Exception as e:
        print(f"User log error: {e}")

def log_stats():
    try:
        res = requests.get(f"{FIREBASE_URL}/stats/total_processed.json").json() or 0
        requests.put(f"{FIREBASE_URL}/stats/total_processed.json", json=res + 1)
    except Exception as e:
        print(f"Stats error: {e}")

def process_media_with_outro(input_path, output_path, is_audio_only=False):
    temp_wav = "temp_audio.wav"
    vocals_wav = "separated/htdemucs/temp_audio/vocals.wav"
    clean_video = "clean_video.mp4"
    outro_video = "outro.mp4"
    
    # 1. استخراج الصوت بأعلى جودة
    subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", temp_wav], check=True)
    
    # 2. فصل الموسيقى باستخدام Demucs
    subprocess.run(["demucs", "--two-stems=vocals", "-n", "htdemucs", temp_wav], check=True)
    
    if is_audio_only:
        subprocess.run(["ffmpeg", "-y", "-i", vocals_wav, "-b:a", "192k", output_path], check=True)
    else:
        # 3. دمج الصوت النظيف مع الفيديو الأصلي
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path, "-i", vocals_wav,
            "-c:v", "libx264", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", clean_video
        ], check=True)

        # 4. إضافة صورة الختام لـ 3 ثوانٍ فقط في نهاية الفيديو
        if os.path.exists(WATERMARK_IMG):
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-loop", "1", "-i", WATERMARK_IMG, "-i", clean_video,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-filter_complex", "[0:v][1:v]scale2ref=w=iw:h=ih[outro][main]",
                    "-map", "[outro]", "-map", "2:a", "-t", "3",
                    "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", outro_video
                ], check=True)

                concat_list = "concat_list.txt"
                with open(concat_list, "w") as f:
                    f.write(f"file '{clean_video}'\nfile '{outro_video}'\n")

                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
                    "-c", "copy", output_path
                ], check=True)

                for p in [outro_video, concat_list]:
                    if os.path.exists(p): os.remove(p)

            except Exception as e:
                print(f"Outro error: {e}")
                os.rename(clean_video, output_path)
        else:
            os.rename(clean_video, output_path)

    for p in [temp_wav, clean_video]:
        if os.path.exists(p): os.remove(p)

def send_message(chat_id, text, inline_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if inline_markup:
        payload["reply_markup"] = inline_markup
    return requests.post(f"{API_URL}/sendMessage", json=payload).json()

def edit_message(chat_id, message_id, text):
    requests.post(f"{API_URL}/editMessageText", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    })

def check_broadcast():
    try:
        broadcast = requests.get(f"{FIREBASE_URL}/broadcast.json").json()
        if broadcast and broadcast.get("status") == "pending":
            msg = broadcast.get("message")
            users = requests.get(f"{FIREBASE_URL}/users.json").json() or {}
            for u_id in users:
                send_message(u_id, f"📢 <b>تنويه عام من الإدارة:</b>\n\n{msg}")
            requests.patch(f"{FIREBASE_URL}/broadcast.json", json={"status": "done"})
    except Exception as e:
        print(f"Broadcast error: {e}")

# تفعيل قائمة الأوامر فور تشغيل الكود
setup_bot_commands()

print("Bot MuteFlow is fully active...")
last_update_id = 0

while True:
    try:
        check_broadcast()
        
        res = requests.get(f"{API_URL}/getUpdates", params={"offset": last_update_id + 1, "timeout": 10}).json()
        for update in res.get("result", []):
            last_update_id = update["update_id"]
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            from_user = message.get("from", {})
            user_id = from_user.get("id")
            
            if not chat_id:
                continue

            save_user(user_id, from_user.get("first_name"), from_user.get("username"))
            text = message.get("text", "")

            if text == "/start":
                start_msg = (
                    "<b>أهلاً بك في MuteFlow Bot 🎧!</b>\n\n"
                    "أرسل لي أي فيديو أو ملف صوتي وسيتم فصل الموسيقى وإبقاؤها بدون صوت الموسيقى تماماً ✨.\n\n"
                    "إذا أعجبتك الخدمة، ادعمنا بنشرها أو قم بزيارة موقعنا ⬇️"
                )
                send_message(chat_id, start_msg, inline_markup=INLINE_KEYBOARD)
                continue

            elif text == "/help":
                help_msg = (
                    "💛 <b>الخدمة مجانية بالكامل ونغطي تكاليفها بأنفسنا.</b>\n\n"
                    "إذا حابب تدعمنا أو تجرّب الخصائص الإضافية يمكنك زيارة رابط الدعم:\n"
                    "https://muteflow.web.app/help"
                )
                send_message(chat_id, help_msg, inline_markup=INLINE_KEYBOARD)
                continue

            if message.get("photo"):
                send_message(
                    chat_id, 
                    "❌ <b>عذراً، هذا الملف عبارة عن صورة!</b>\n\nيرجى إرسال مقطع فيديو أو ملف صوتي فقط لكي يتمكن البوت من فصل الموسيقى عنه.",
                    inline_markup=INLINE_KEYBOARD
                )
                continue

            video = message.get("video")
            audio = message.get("audio")
            voice = message.get("voice")
            document = message.get("document")

            media_obj = video or audio or voice
            is_audio_only = bool(audio or voice)

            if not media_obj and document:
                mime = document.get("mime_type", "")
                if "video" in mime:
                    media_obj = document
                    is_audio_only = False
                elif "audio" in mime:
                    media_obj = document
                    is_audio_only = True

            if media_obj:
                status_res = send_message(chat_id, "⏳ جاري تحميل الملف...")
                msg_id = status_res.get("result", {}).get("message_id")

                file_id = media_obj["file_id"]
                file_info = requests.get(f"{API_URL}/getFile", params={"file_id": file_id}).json()
                file_path = file_info["result"]["file_path"]
                
                ext = "mp3" if is_audio_only else "mp4"
                input_file = f"input_{user_id}.{ext}"
                output_file = f"output_{user_id}.{ext}"

                media_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
                with open(input_file, "wb") as f:
                    f.write(requests.get(media_url).content)

                if msg_id:
                    edit_message(chat_id, msg_id, "⚡ جاري فصل الموسيقى بالذكاء الاصطناعي...")

                process_media_with_outro(input_file, output_file, is_audio_only=is_audio_only)

                caption = (
                    "شلت لك الموسيقى. الحين تقدر تنشره وأنت مرتاح 👍\n\n"
                    "إذا أعجبتك الخدمة، ادعمنا بنشرها في الجروبات اللي عندك عبر هذا الرابط واكسب الأجر 🌟\n"
                    "https://muteflow.web.app/help"
                )

                if msg_id:
                    requests.post(f"{API_URL}/deleteMessage", json={"chat_id": chat_id, "message_id": msg_id})

                with open(output_file, 'rb') as f:
                    endpoint = "sendAudio" if is_audio_only else "sendVideo"
                    field = "audio" if is_audio_only else "video"
                    requests.post(
                        f"{API_URL}/{endpoint}",
                        data={"chat_id": chat_id, "caption": caption, "reply_markup": requests.compat.json.dumps(INLINE_KEYBOARD)},
                        files={field: f}
                    )

                log_stats()

                for p in [input_file, output_file]:
                    if os.path.exists(p):
                        os.remove(p)

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(2)
