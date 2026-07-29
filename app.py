import os
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
import subprocess
import threading
import json
import shutil
import uuid
import re
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

def extract_youtube_transcript(url):
    if "youtube.com" not in url and "youtu.be" not in url:
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not match:
            return None
        video_id = match.group(1)
        api_instance = YouTubeTranscriptApi()
        transcript_list = api_instance.list(video_id)
        
        try:
            transcript = transcript_list.find_transcript(['vi', 'en'])
        except:
            keys = list(transcript_list._manually_created_transcripts.keys()) + list(transcript_list._generated_transcripts.keys())
            if not keys:
                return None
            transcript = transcript_list.find_transcript(keys)
            
        text_data = transcript.fetch()
        full_text = " ".join([t.text if hasattr(t, 'text') else t['text'] for t in text_data])
        return full_text
    except Exception as e:
        return f"[LỖI TRÍCH XUẤT YOUTUBE: {str(e)}]"

app = Flask(__name__)

# Thư mục chứa files
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
PROMPTS_FILE = 'prompts.json'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def save_metadata(filename, processing_time):
    meta_path = os.path.join(OUTPUT_FOLDER, "metadata.json")
    data = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass
    data[filename] = {"processing_time": processing_time}
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f)


DEFAULT_PROMPT = """Bạn là chuyên gia dịch thuật. Hãy dịch đoạn văn bản sau từ ngôn ngữ của quốc gia có mã [SOURCE_LANG] sang ngôn ngữ của quốc gia có mã: [TARGET_LANG].
Yêu cầu QUAN TRỌNG:
- TUYỆT ĐỐI KHÔNG thêm câu mở đầu (như 'Dưới đây là...'), KHÔNG kết luận, KHÔNG giải thích.
- CHỈ TRẢ VỀ DUY NHẤT nội dung đã dịch, không kèm số từ hay văn bản thừa.
- Giữ nguyên định dạng gốc (xuống dòng, đoạn văn).
- Dịch tự nhiên, chuẩn văn phong bản địa.

Nội dung cần dịch:
[TEXT]"""

def get_prompts():
    if not os.path.exists(PROMPTS_FILE):
        return [{"id": "default", "name": "Mặc định (Dịch Chuẩn)", "content": DEFAULT_PROMPT}]
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_prompts(prompts):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=4)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    try:
        profiles = []
        for d in os.listdir(os.getcwd()):
            if os.path.isdir(d) and d.startswith("chrome_profile_"):
                profiles.append(d.replace("chrome_profile_", ""))
        # ensure default exists in list if none
        if not profiles:
            profiles = ["gemini_profile"]
        return jsonify({"status": "success", "data": profiles})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/logout", methods=["POST"])
def logout_profile():
    try:
        data = request.json
        profile_name = data.get("profileName", "gemini_profile").strip()
        if not profile_name:
            return jsonify({"status": "error", "message": "Tên tài khoản không hợp lệ."}), 400
            
        profile_dir = f"chrome_profile_{profile_name}"
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir)
            return jsonify({"status": "success", "message": f"Đã xoá dữ liệu đăng nhập tài khoản {profile_name}."})
        else:
            return jsonify({"status": "error", "message": "Không tìm thấy thư mục tài khoản này."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/login", methods=["POST"])
def login_gemini():
    try:
        data = request.json
        profile_name = data.get("profileName", "gemini_profile").strip()
        if not profile_name:
            profile_name = "gemini_profile"
            
        cmd = [sys.executable, "browser_bot.py", "--open-only", "--profile", profile_name]
        process = subprocess.Popen(cmd)
        process.wait()
        return jsonify({"status": "success", "message": f"Đã lưu phiên đăng nhập cho tài khoản {profile_name}!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi mở trình duyệt: {str(e)}"}), 500

@app.route("/api/creative", methods=["POST"])
def creative_writer():
    start_time = time.time()
    
    # 1. Thu thập dữ liệu
    data = request.form
    gdoc_url = data.get("gdocUrl", "")
    yt_url = data.get("ytUrl", "")
    raw_text = data.get("rawText", "")
    custom_filename = data.get("customFilename", "").strip()
    profile_name = data.get("profileName", "gemini_profile").strip() or "gemini_profile"
    chunk_size = data.get("chunkSize", "auto")
    detail_level = data.get("detailLevel", "expand")
    selected_prompts_json = data.get("selectedPrompts", "[]")
    
    source_lang = data.get("sourceLang", "auto")
    target_lang = data.get("targetLang", "en")
    
    file_contents = ""
    first_filename = "creative_story"
    
    # Xử lý file tải lên (nếu có)
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            content = file.read().decode('utf-8')
            file_contents += f"\n--- {file.filename} ---\n{content}\n"
            first_filename = os.path.splitext(file.filename)[0]
                
    combined_input = f"{raw_text}\n{file_contents}".strip()
    
    if not gdoc_url and not yt_url and not combined_input:
        return jsonify({"status": "error", "message": "Vui lòng cung cấp ít nhất một nội dung đầu vào (Link, File hoặc Text)!"}), 400

    if gdoc_url:
        combined_input += f"\n\n[Google Doc URL cần xử lý: {gdoc_url}]"
        
    if yt_url:
        transcript = extract_youtube_transcript(yt_url)
        if transcript and not transcript.startswith("[LỖI"):
            combined_input += f"\n\n{transcript}\n"
        else:
            combined_input += f"\n\n[YouTube Video URL cần xử lý: {yt_url}]\n{transcript or ''}"
        
    # Lưu combined input ra file cho browser_bot đọc
    input_file_path = "input_raw.txt"
    with open(input_file_path, "w", encoding="utf-8") as f:
        f.write(combined_input)
    
    # Ghi đè log mới
    with open("bot_status.log", "w", encoding="utf-8") as f:
        f.write("⏳ Đang khởi động AI Creative Writer...\n")
        
    if os.path.exists("output_content.txt"):
        os.remove("output_content.txt")
        
    if custom_filename:
        output_filename = f"{custom_filename}.txt"
        if not output_filename.endswith('.txt'): output_filename += '.txt'
    else:
        output_filename = f"{first_filename}_CREATIVE.txt"
        
    output_filename = secure_filename(output_filename)
    
    # Gọi browser_bot.py
    try:
        cmd = [
            sys.executable, "browser_bot.py", 
            "--mode", "creative",
            "--text-file", input_file_path,
            "--profile", profile_name,
            "--chunk-size", chunk_size,
            "--detail-level", detail_level,
            "--selected-prompts", selected_prompts_json,
            "--source-lang", source_lang,
            "--target-lang", target_lang
        ]
        
        with open("bot_status.log", "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                cmd, 
                stdout=log_file, 
                stderr=subprocess.STDOUT
            )
            process.wait() # Chờ chạy xong
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi chạy Bot: {str(e)}"}), 500
        
    # Đọc kết quả từ file output_content.txt của bot
    if os.path.exists("output_content.txt"):
        with open("output_content.txt", "r", encoding="utf-8") as f:
            translated_content = f.read().strip()
            
        if not translated_content:
            os.remove("output_content.txt")
            return jsonify({"status": "error", "message": "Bot bị lỗi giữa chừng (File 0 Byte). Vui lòng xem tab Nhật Ký để biết chi tiết."}), 500
            
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(translated_content)
            
        # Xóa file tạm
        os.remove("output_content.txt")
        
        processing_time = int(time.time() - start_time)
        save_metadata(output_filename, processing_time)
        
        return jsonify({
            "status": "success",
            "filename": output_filename,
            "preview": translated_content[:1500] + ("..." if len(translated_content)>1500 else ""),
            "processing_time": processing_time
        })
    else:
        return jsonify({"status": "error", "message": "Bot không trả về kết quả. Vui lòng kiểm tra log."}), 500

@app.route("/api/translate/single", methods=["POST"])
def translate_single():
    start_time = time.time()
    
    # 1. Thu thập dữ liệu
    data = request.form
    target_lang = data.get("targetLang", "ko")
    gdoc_url = data.get("gdocUrl", "")
    yt_url = data.get("ytUrl", "")
    raw_text = data.get("rawText", "")
    custom_filename = data.get("customFilename", "").strip()
    profile_name = data.get("profileName", "gemini_profile").strip() or "gemini_profile"
    
    file_contents = ""
    first_filename = "translated"
    
    # Xử lý file tải lên (nếu có)
    if 'files[]' in request.files:
        files = request.files.getlist('files[]')
        for idx, file in enumerate(files):
            if file.filename != '':
                content = file.read().decode('utf-8')
                file_contents += f"\n--- {file.filename} ---\n{content}\n"
                if idx == 0:
                    first_filename = os.path.splitext(file.filename)[0]
                
    combined_input = f"{raw_text}\n{file_contents}".strip()
    
    if not gdoc_url and not yt_url and not combined_input:
        return jsonify({"status": "error", "message": "Vui lòng cung cấp ít nhất một nội dung đầu vào (Link, File hoặc Text)!"}), 400

    if gdoc_url:
        combined_input += f"\n\n[Google Doc URL cần xử lý: {gdoc_url}]"
        
    if yt_url:
        transcript = extract_youtube_transcript(yt_url)
        if transcript and not transcript.startswith("[LỖI"):
            combined_input += f"\n\n{transcript}\n"
        else:
            combined_input += f"\n\n[YouTube Video URL cần xử lý: {yt_url}]\n{transcript or ''}"
        
    # Lưu combined input ra file cho browser_bot đọc
    input_file_path = "input_raw.txt"
    with open(input_file_path, "w", encoding="utf-8") as f:
        f.write(combined_input)
    
    source_lang = data.get("sourceLang", "auto")
    prompt_id = data.get("promptId", "default")
    chunk_size = data.get("chunkSize", "auto")
    
    # Ghi đè log mới
    with open("bot_status.log", "w", encoding="utf-8") as f:
        f.write("⏳ Đang khởi động Playwright Bot...\n")
        
    if os.path.exists("output_content.txt"):
        os.remove("output_content.txt")
        
    if custom_filename:
        output_filename = f"{custom_filename}.txt"
        if not output_filename.endswith('.txt'): output_filename += '.txt'
    else:
        output_filename = f"{first_filename}_{target_lang.upper()}.txt"
        
    output_filename = secure_filename(output_filename)
    
    # Gọi browser_bot.py
    try:
        cmd = [
            sys.executable, "browser_bot.py", 
            "--source-lang", source_lang,
            "--target-lang", target_lang,
            "--text-file", input_file_path,
            "--profile", profile_name,
            "--prompt-id", prompt_id,
            "--chunk-size", chunk_size
        ]
        
        # Mở subprocess và redirect output ra file log
        with open("bot_status.log", "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                cmd, 
                stdout=log_file, 
                stderr=subprocess.STDOUT
            )
            process.wait() # Chờ chạy xong
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi chạy Bot: {str(e)}"}), 500
        
    # Đọc kết quả từ file output_content.txt của bot
    if os.path.exists("output_content.txt"):
        with open("output_content.txt", "r", encoding="utf-8") as f:
            translated_content = f.read().strip()
            
        if not translated_content:
            os.remove("output_content.txt")
            return jsonify({"status": "error", "message": "Bot bị lỗi giữa chừng (File 0 Byte). Vui lòng xem tab Nhật Ký để biết chi tiết."}), 500
            
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(translated_content)
            
        # Xóa file tạm
        os.remove("output_content.txt")
        
        processing_time = int(time.time() - start_time)
        save_metadata(output_filename, processing_time)
        
        return jsonify({
            "status": "success",
            "filename": output_filename,
            "preview": translated_content[:1500] + ("..." if len(translated_content)>1500 else ""),
            "processing_time": processing_time
        })
    else:
        return jsonify({"status": "error", "message": "Bot không trả về kết quả. Vui lòng kiểm tra log."}), 500

@app.route("/api/translate_batch", methods=["POST"])
def translate_batch():
    start_time = time.time()
    source_lang = request.form.get("sourceLang", "auto")
    profile_name = request.form.get("profileName", "gemini_profile").strip() or "gemini_profile"
    target_lang = request.form.get("targetLang", "en")
    prompt_id = request.form.get("promptId", "default")
    chunk_size = request.form.get("chunkSize", "auto")
    batch_links = request.form.get("batchLinks", "").strip().split("\n")
    
    batch_id = str(uuid.uuid4())
    batch_input_dir = os.path.join(UPLOAD_FOLDER, f"batch_{batch_id}")
    batch_output_dir = os.path.join(OUTPUT_FOLDER, f"batch_{batch_id}")
    
    os.makedirs(batch_input_dir, exist_ok=True)
    os.makedirs(batch_output_dir, exist_ok=True)
    
    inputs_list = []
    
    # Process links
    for idx, link in enumerate(batch_links):
        link = link.strip()
        if link:
            filename = f"link_{idx+1}.txt"
            filepath = os.path.join(batch_input_dir, filename)
            
            transcript = extract_youtube_transcript(link)
            if transcript and not transcript.startswith("[LỖI"):
                content = f"{transcript}\n"
            else:
                content = f"[URL cần xử lý: {link}]\n{transcript or ''}"
                
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            inputs_list.append({"name": filename, "path": filepath})
            
    # Process files
    if 'files[]' in request.files:
        files = request.files.getlist('files[]')
        for file in files:
            if file.filename != '':
                filename = secure_filename(file.filename)
                filepath = os.path.join(batch_input_dir, filename)
                file.save(filepath)
                inputs_list.append({"name": filename, "path": filepath})
                
    if not inputs_list:
        return jsonify({"status": "error", "message": "Không có dữ liệu đầu vào!"}), 400
        
    with open("bot_status.log", "w", encoding="utf-8") as f:
        f.write(f"⏳ Bắt đầu xử lý hàng loạt {len(inputs_list)} mục...\n")
        
    try:
        cmd = [
            sys.executable, "browser_bot.py", 
            "--mode", "batch",
            "--source-lang", source_lang,
            "--target-lang", target_lang,
            "--batch-dir", batch_input_dir,
            "--output-dir", batch_output_dir,
            "--profile", profile_name,
            "--prompt-id", prompt_id,
            "--chunk-size", chunk_size
        ]
        
        with open("bot_status.log", "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            process.wait()
            
        # Zip output directory
        zip_filename = f"KetQuaDichHangLoat_{target_lang.upper()}.zip"
        zip_path = os.path.join(OUTPUT_FOLDER, zip_filename.replace('.zip', ''))
        shutil.make_archive(zip_path, 'zip', batch_output_dir)
        
        processing_time = int(time.time() - start_time)
        save_metadata(zip_filename, processing_time)
        
        return jsonify({
            "status": "success",
            "filename": zip_filename
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi chạy Bot Hàng Loạt: {str(e)}"}), 500

@app.route("/api/logs")
def get_logs():
    if os.path.exists("bot_status.log"):
        with open("bot_status.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-15:])
    return "Đang chờ log..."

import datetime
@app.route("/api/history")
def get_history():
    files = []
    
    meta_path = os.path.join(OUTPUT_FOLDER, "metadata.json")
    metadata = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except:
            pass
            
    if os.path.exists(OUTPUT_FOLDER):
        for f in os.listdir(OUTPUT_FOLDER):
            if f.endswith(".txt") or f.endswith(".zip"):
                path = os.path.join(OUTPUT_FOLDER, f)
                size = os.path.getsize(path)
                ctime = os.path.getctime(path)
                dt = datetime.datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M:%S')
                
                proc_time = ""
                if f in metadata and "processing_time" in metadata[f]:
                    proc_time = f"{metadata[f]['processing_time']}s"
                
                files.append({
                    "name": f,
                    "size": round(size / 1024, 2), # KB
                    "time": dt,
                    "timestamp": ctime,
                    "processing_time": proc_time
                })
    # Sắp xếp mới nhất lên đầu
    files.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify({"status": "success", "data": files})

@app.route("/api/prompts", methods=["GET"])
def api_get_prompts():
    return jsonify({"status": "success", "data": get_prompts()})

@app.route('/api/generate_image', methods=['POST'])
def api_generate_image():
    try:
        with open("bot_status.log", "w", encoding="utf-8") as f:
            f.write("Khởi động Bot tạo ảnh...\n")
            
        data = request.json
        prompt_content = data.get("promptContent", "").strip()
        profile_name = data.get("profileName", "gemini_profile").strip() or "gemini_profile"
        prompt_id = data.get("imagePromptId", "default").strip()
        character_sync = data.get("imageCharacterSync", "").strip()
        
        if not prompt_content:
            return jsonify({"status": "error", "message": "Nội dung prompt tạo ảnh trống."}), 400
            
        # Construct full prompt
        final_prompt = ""
        
        # 1. Apply Prompt Template if not default
        if prompt_id != "default":
            prompts = get_prompts()
            for p in prompts:
                if p["id"] == prompt_id:
                    # The template usually has [TEXT]. We replace it.
                    final_prompt = p["content"].replace("[TEXT]", prompt_content)
                    break
        
        if not final_prompt:
            final_prompt = prompt_content
            
        # 2. Prepend Character Sync if provided
        if character_sync:
            final_prompt = f"Character reference (Must strictly maintain this appearance): {character_sync}\n\nAction/Scene: {final_prompt}"
            
        # Write prompt to temp file
        temp_file = "temp_image_prompt.txt"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(final_prompt)
            
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "images")
        os.makedirs(output_dir, exist_ok=True)
        
        cmd = [
            sys.executable, "browser_bot.py",
            "--mode", "image",
            "--text-file", temp_file,
            "--output-dir", output_dir,
            "--profile", profile_name
        ]
        
        with open("bot_status.log", "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            process.wait()
            
        # After process completes, get the most recently created images
        if not os.path.exists(output_dir):
            return jsonify({"status": "error", "message": "Không tìm thấy thư mục lưu ảnh."}), 500
            
        # Find all files in outputs/images created in the last 2 minutes
        import time
        now = time.time()
        generated_images = []
        for f in os.listdir(output_dir):
            if f.endswith((".png", ".jpg")):
                fpath = os.path.join(output_dir, f)
                if now - os.path.getctime(fpath) < 120:
                    generated_images.append(f)
                    
        if not generated_images:
            return jsonify({"status": "error", "message": "Tiến trình chạy xong nhưng không tìm thấy ảnh nào. Xem Nhật ký (Log) để biết chi tiết."}), 500
            
        return jsonify({
            "status": "success",
            "message": f"Tạo ảnh thành công! ({len(generated_images)} ảnh)",
            "images": generated_images
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi tạo ảnh: {str(e)}"}), 500

@app.route('/outputs/images/<filename>')
def serve_image(filename):
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "images")
    return send_from_directory(output_dir, filename)

@app.route("/api/prompts", methods=["POST"])
def api_save_prompt():
    data = request.json
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    prompt_type = data.get("type", "translate").strip()
    target_lang = data.get("targetLang", "all").strip()
    code = data.get("code", "").strip()
    
    if not name or not content:
        return jsonify({"status": "error", "message": "Vui lòng nhập đủ Tên và Nội dung Prompt."}), 400
        
    prompts = get_prompts()
    new_id = str(uuid.uuid4())
    prompts.append({"id": new_id, "name": name, "content": content, "type": prompt_type, "targetLang": target_lang, "code": code})
    save_prompts(prompts)
    
    return jsonify({"status": "success", "message": "Đã lưu Mẫu Prompt thành công!"})

@app.route("/api/prompts/<prompt_id>", methods=["DELETE"])
def api_delete_prompt(prompt_id):
    if prompt_id == "default":
        return jsonify({"status": "error", "message": "Không thể xóa Prompt Mặc Định."}), 400
        
    prompts = get_prompts()
    prompts = [p for p in prompts if p["id"] != prompt_id]
    save_prompts(prompts)
    
    return jsonify({"status": "success", "message": "Đã xóa Prompt."})

@app.route("/api/download/<filename>")
def download_file(filename):
    file_path = os.path.join(OUTPUT_FOLDER, secure_filename(filename))
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

if __name__ == "__main__":
    print("Khởi động server thành công tại http://localhost:5002")
    app.run(debug=True, port=5002)
