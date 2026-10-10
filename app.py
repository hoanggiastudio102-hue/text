import os
import time
import sys
if sys.stdout is None or sys.stderr is None:   # pythonw (chay ngam, khong cua so): ghi log ra file
    os.makedirs("logs", exist_ok=True)
    _lf = open(os.path.join("logs", "server.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _lf
    sys.stderr = sys.stderr or _lf
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
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
        return [{"id": "default", "name": "Mặc định (Sáng Tạo Chuẩn)", "content": DEFAULT_PROMPT}]
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_prompts(prompts):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=4)

@app.context_processor
def _asset_version():
    """Gắn ?v=<thời điểm sửa file> vào css/js để trình duyệt và Cloudflare không giữ bản cũ."""
    try:
        sd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        v = max(int(os.path.getmtime(os.path.join(sd, f))) for f in os.listdir(sd))
    except Exception:
        v = int(time.time())
    return {"asset_v": v}


@app.after_request
def _no_stale_cache(resp):
    if request.path.startswith("/static/") or request.path == "/":
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


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
    new_prompt = {"id": new_id, "name": name, "content": content, "type": prompt_type, "targetLang": target_lang, "code": code}
    if prompt_type == "rewrite":
        new_prompt["mode"] = data.get("mode") if data.get("mode") in ("localize", "analyze") else "rewrite"
    prompts.append(new_prompt)
    save_prompts(prompts)
    
    return jsonify({"status": "success", "message": "Đã lưu Mẫu Prompt thành công!"})

@app.route("/api/prompts/<prompt_id>", methods=["PUT"])
def api_update_prompt(prompt_id):
    data = request.json or {}
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    if not name or not content:
        return jsonify({"status": "error", "message": "Vui lòng nhập đủ Tên và Nội dung."}), 400
    prompts = get_prompts()
    for p in prompts:
        if p.get("id") == prompt_id:
            p["name"], p["content"] = name, content
            if p.get("type") == "rewrite":
                p["mode"] = data.get("mode") if data.get("mode") in ("localize", "analyze") else "rewrite"
            save_prompts(prompts)
            return jsonify({"status": "success", "message": "Đã cập nhật."})
    return jsonify({"status": "error", "message": "Không tìm thấy mẫu."}), 404


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


# =====================================================================
#  VIẾT LẠI & BẢN ĐỊA HOÁ  (nhiều bài × nhiều quốc gia, chạy nền)
# =====================================================================
import re as _re
import zipfile as _zipfile
import locales
import gemini_client
from localize_bot import read_json as _read_json, write_json_atomic as _write_json

JOBS_DIR = os.path.join(OUTPUT_FOLDER, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
_JOB_PROCS = {}          # job_id -> Popen (chỉ các job do tiến trình server này mở)
_JOB_ID_RE = _re.compile(r"^[0-9a-f]{12,32}$")
MAX_UNITS = 200          # bài × quốc gia tối đa trong 1 job
STALE_SECONDS = 150      # quá ngần này giây không có nhịp tim -> coi như bot đã chết


def _job_dir(job_id):
    if not _JOB_ID_RE.match(job_id or ""):
        return None
    d = os.path.join(JOBS_DIR, job_id)
    return d if os.path.isdir(d) else None


def _read_text_upload(file_storage):
    raw = file_storage.read()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _safe_name(name, fallback="bai_viet"):
    base = os.path.splitext(os.path.basename(name or ""))[0]
    keep = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in base).strip("_")
    return keep[:50] or fallback


def _collect_articles(form, files):
    """Gom đầu vào thành danh sách bài riêng: mỗi file .txt, mỗi link YouTube, và phần văn bản dán."""
    articles = []
    raw_text = (form.get("rawText") or "").strip()
    per_line = form.get("perLine") in ("1", "true", "on")
    if raw_text and per_line:
        # chế độ hàng loạt chủ đề: mỗi dòng là một chủ đề/bài riêng
        for line in raw_text.splitlines():
            line = line.strip()
            if line:
                articles.append({"name": _safe_name(line, "chu_de"), "text": line})
    elif raw_text:
        custom = (form.get("customFilename") or "").strip()
        one_line = "\n" not in raw_text and len(raw_text) <= 100
        fallback = _safe_name(raw_text, "bai_dan") if one_line else "bai_dan"
        articles.append({"name": _safe_name(custom, fallback) if custom else fallback, "text": raw_text})
    for f in files.getlist("files[]"):
        if f and f.filename:
            text = _read_text_upload(f).strip()
            if text:
                articles.append({"name": _safe_name(f.filename), "text": text})
    for link in (form.get("ytUrl") or "").splitlines():
        link = link.strip()
        if not link:
            continue
        transcript = extract_youtube_transcript(link)
        if transcript and not transcript.startswith("[LỖI"):
            m = _re.search(r"(?:v=|youtu\.be/)([0-9A-Za-z_-]{11})", link)
            articles.append({"name": f"youtube_{m.group(1) if m else len(articles) + 1}", "text": transcript})
    # tên không trùng nhau
    seen = {}
    for a in articles:
        n = seen.get(a["name"], 0)
        seen[a["name"]] = n + 1
        if n:
            a["name"] = f"{a['name']}_{n + 1}"
    for i, a in enumerate(articles, start=1):
        a["id"] = f"a{i}"
    return articles


def _resolve_style(form):
    """Trả (style_text, mode) theo mẫu đã chọn."""
    pid = (form.get("promptId") or "").strip()
    for p in get_prompts():
        if p.get("id") == pid and p.get("type") == "rewrite":
            return p.get("content", ""), p.get("mode", "rewrite")
    return "", "rewrite"


def _parse_countries(form):
    try:
        codes = json.loads(form.get("countries") or "[]")
    except ValueError:
        codes = []
    out = []
    for c in codes:
        c = str(c).upper()
        try:
            locales.get_country(c)
        except KeyError:
            continue
        if c not in out:
            out.append(c)
    return out


def _job_alive(job_id, data):
    """Bot còn chạy không? (dựa vào tiến trình đã mở, nếu không thì dựa vào nhịp tim)."""
    proc = _JOB_PROCS.get(job_id)
    if proc is not None:
        return proc.poll() is None
    return (time.time() - float(data.get("heartbeat") or 0)) < STALE_SECONDS


def _reconcile(job_id, data):
    """Nếu file nói 'running' nhưng bot đã chết -> sửa trạng thái cho đúng."""
    if data.get("state") == "running" and not _job_alive(job_id, data):
        for r in data.get("results", {}).values():
            if r.get("status") in ("running", "pending"):
                r["status"] = "error"
                r["error"] = r.get("error") or "Bot dừng đột ngột."
        data["state"] = "partial" if any(r.get("status") == "done" for r in data.get("results", {}).values()) else "error"
        data["error"] = data.get("error") or "Bot dừng đột ngột (có thể bị đóng cửa sổ hoặc lỗi trình duyệt). Bấm 'Tiếp tục' để chạy lại phần còn thiếu."
        try:
            _write_json(os.path.join(JOBS_DIR, job_id, "job.json"), data)
        except Exception:
            pass
    return data


def _active_job_id():
    for jid in os.listdir(JOBS_DIR) if os.path.isdir(JOBS_DIR) else []:
        try:
            data = _read_json(os.path.join(JOBS_DIR, jid, "job.json"))
        except Exception:
            continue
        if data.get("state") == "running" and _job_alive(jid, data):
            return jid
    return None


def _launch_job(job_id):
    job_dir = os.path.join(JOBS_DIR, job_id)
    with open("bot_status.log", "w", encoding="utf-8") as f:
        f.write("⏳ Đang khởi động tiến trình Sáng tạo & Bản địa hoá...\n")
    log_file = open("bot_status.log", "a", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, os.path.join(APP_DIR, "localize_bot.py"), "--job-dir", job_dir],
                            cwd=APP_DIR, stdout=log_file, stderr=subprocess.STDOUT)
    _JOB_PROCS[job_id] = proc
    # đánh dấu đang chạy ngay để giao diện không thấy trạng thái cũ
    try:
        data = _read_json(os.path.join(job_dir, "job.json"))
        data["state"] = "running"
        data["heartbeat"] = time.time()
        _write_json(os.path.join(job_dir, "job.json"), data)
    except Exception:
        pass


@app.route("/api/locales")
def api_locales():
    return jsonify({
        "status": "success",
        "data": [{k: c[k] for k in ("code", "flag", "name_vi", "language", "locale")} for c in locales.list_countries()],
        "model": gemini_client.get_model_name(),
        "thinking": gemini_client.get_thinking_level(),
        "rewrite_prompts": [p for p in get_prompts() if p.get("type") == "rewrite"],
    })


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        update = {}
        if "model" in data:
            m = str(data["model"]).strip()
            if not m:
                return jsonify({"status": "error", "message": "Tên model không được để trống."}), 400
            update["model"] = m[:60]
        if "thinking" in data:
            update["thinking"] = str(data["thinking"]).strip()[:30]
        gemini_client.save_settings(update)
    return jsonify({"status": "success", "model": gemini_client.get_model_name(),
                    "thinking": gemini_client.get_thinking_level()})


@app.route("/api/gemini/check", methods=["POST"])
def api_gemini_check():
    """Mở Gemini bằng tài khoản đã đăng nhập, liệt kê menu model và thử chọn model cấu hình."""
    if _active_job_id():
        return jsonify({"status": "error", "message": "Đang có một job chạy. Hãy đợi job xong rồi kiểm tra."}), 409
    profile = (request.get_json(silent=True) or {}).get("profileName") or "gemini_profile"
    try:
        proc = subprocess.run([sys.executable, os.path.join(APP_DIR, "gemini_client.py"), "--check",
                               "--profile", profile], cwd=APP_DIR, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=240)
        output = (proc.stdout or "") + (proc.stderr or "")
        return jsonify({"status": "success" if proc.returncode == 0 else "error",
                        "message": "Chọn được model." if proc.returncode == 0 else "Chưa chọn được model.",
                        "output": output.strip()[-3000:]})
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Quá thời gian chờ khi kiểm tra Gemini."}), 500


@app.route("/api/localize/preview", methods=["POST"])
def api_localize_preview():
    articles = _collect_articles(request.form, request.files)
    countries = _parse_countries(request.form)
    if not articles:
        return jsonify({"status": "error", "message": "Chưa có bài nào để xem trước."}), 400
    if not countries:
        return jsonify({"status": "error", "message": "Hãy chọn ít nhất một quốc gia."}), 400
    style_text, mode = _resolve_style(request.form)
    try:
        chunk_size = int(request.form.get("chunkSize") or 12000)
    except ValueError:
        chunk_size = 12000
    if mode == "analyze":
        chunk_size = max(chunk_size, 60000)
    chunks = locales.split_text(articles[0]["text"], chunk_size)
    prompt = locales.build_prompt(
        chunks[0], locales.get_country(countries[0]), style_text, mode=mode,
        audience=request.form.get("audience", ""), length=request.form.get("length", "same"),
        keywords=request.form.get("keywords", ""), glossary=request.form.get("glossary", ""),
        extra=request.form.get("extra", ""), part=1, parts=len(chunks))
    return jsonify({"status": "success", "prompt": prompt, "chunks": len(chunks),
                    "article": articles[0]["name"], "country": countries[0]})


@app.route("/api/localize", methods=["POST"])
def api_localize_start():
    active = _active_job_id()
    if active:
        return jsonify({"status": "error", "message": "Đang có một job chạy. Hãy đợi xong hoặc bấm Huỷ trước.",
                        "job_id": active}), 409
    form = request.form
    articles = _collect_articles(form, request.files)
    countries = _parse_countries(form)
    if not articles:
        return jsonify({"status": "error", "message": "Vui lòng dán bài, tải file .txt hoặc nhập link YouTube!"}), 400
    if not countries:
        return jsonify({"status": "error", "message": "Hãy chọn ít nhất một quốc gia."}), 400
    if len(articles) * len(countries) > MAX_UNITS:
        return jsonify({"status": "error",
                        "message": f"Quá nhiều mục ({len(articles)} bài × {len(countries)} nước). Tối đa {MAX_UNITS}."}), 400

    style_text, mode = _resolve_style(form)
    job_id = uuid.uuid4().hex[:16]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(os.path.join(job_dir, "sources"), exist_ok=True)
    meta_articles = []
    for a in articles:
        fname = f"{a['id']}.txt"
        with open(os.path.join(job_dir, "sources", fname), "w", encoding="utf-8") as f:
            f.write(a["text"])
        meta_articles.append({"id": a["id"], "name": a["name"], "file": fname, "chars": len(a["text"])})

    try:
        chunk_size = max(2000, min(40000, int(form.get("chunkSize") or 12000)))
    except ValueError:
        chunk_size = 12000
    length = form.get("length", "same")
    job = {
        "id": job_id, "created_at": time.time(), "state": "queued", "error": "",
        "base_name": _safe_name(form.get("customFilename"), meta_articles[0]["name"]) if len(meta_articles) == 1
                     else (_safe_name(form.get("customFilename"), "BaiViet")),
        "articles": meta_articles, "countries": countries, "results": {},
        "style_id": form.get("promptId", ""), "style_text": style_text, "mode": mode,
        "audience": form.get("audience", "").strip(), "length": length if length in locales.LENGTH_RULES else "same",
        "keywords": form.get("keywords", ""), "glossary": form.get("glossary", ""),
        "extra": form.get("extra", "").strip(), "review": form.get("review") in ("1", "true", "on"),
        "chunk_size": chunk_size, "profile": (form.get("profileName") or "gemini_profile").strip() or "gemini_profile",
        "model": gemini_client.get_model_name(), "thinking": gemini_client.get_thinking_level(),
        "dry_run": form.get("dryRun") in ("1", "true", "on"),
        "zip": None, "current": None,
    }
    for a in meta_articles:
        for c in countries:
            job["results"][f"{a['id']}:{c}"] = {"status": "pending"}
    _write_json(os.path.join(job_dir, "job.json"), job)
    _launch_job(job_id)
    return jsonify({"status": "success", "job_id": job_id, "units": len(meta_articles) * len(countries)})


@app.route("/api/localize/<job_id>")
def api_localize_status(job_id):
    d = _job_dir(job_id)
    if not d:
        return jsonify({"status": "error", "message": "Không tìm thấy job."}), 404
    try:
        data = _reconcile(job_id, _read_json(os.path.join(d, "job.json")))
    except Exception:
        return jsonify({"status": "error", "message": "Đang ghi dữ liệu, thử lại sau giây lát."}), 503
    tail = ""
    try:
        with open(os.path.join(d, "run.log"), "r", encoding="utf-8") as f:
            tail = "".join(f.readlines()[-14:])
    except OSError:
        pass
    # không trả style_text/keywords... dài dòng về giao diện
    slim = {k: data.get(k) for k in ("id", "state", "error", "articles", "countries", "results", "current",
                                     "zip", "review", "dry_run", "model", "thinking", "mode",
                                     "started_at", "finished_at", "created_at")}
    slim["log_tail"] = tail
    return jsonify({"status": "success", "job": slim})


@app.route("/api/localize/<job_id>/cancel", methods=["POST"])
def api_localize_cancel(job_id):
    d = _job_dir(job_id)
    if not d:
        return jsonify({"status": "error", "message": "Không tìm thấy job."}), 404
    open(os.path.join(d, "cancel.flag"), "w").close()
    return jsonify({"status": "success", "message": "Đã gửi lệnh huỷ — Tool sẽ dừng sau phần đang xử lý."})


@app.route("/api/localize/<job_id>/resume", methods=["POST"])
def api_localize_resume(job_id):
    d = _job_dir(job_id)
    if not d:
        return jsonify({"status": "error", "message": "Không tìm thấy job."}), 404
    active = _active_job_id()
    if active:
        return jsonify({"status": "error", "message": "Đang có một job chạy.", "job_id": active}), 409
    _launch_job(job_id)
    return jsonify({"status": "success", "job_id": job_id})


@app.route("/api/localize/<job_id>/file")
def api_localize_file(job_id):
    d = _job_dir(job_id)
    rel = (request.args.get("f") or "").replace("\\", "/")
    parts = [secure_filename(p) for p in rel.split("/") if p]
    if not d or len(parts) != 2 or not all(parts):
        return "File not found", 404
    path = os.path.join(d, "files", parts[0], parts[1])
    if os.path.isfile(path):
        return send_file(path, as_attachment=True, download_name=parts[1])
    return "File not found", 404


@app.route("/api/localize/<job_id>/text")
def api_localize_text(job_id):
    """Xem trước nội dung 1 kết quả trong giao diện."""
    d = _job_dir(job_id)
    rel = (request.args.get("f") or "").replace("\\", "/")
    parts = [secure_filename(p) for p in rel.split("/") if p]
    if not d or len(parts) != 2 or not all(parts):
        return jsonify({"status": "error", "message": "Không tìm thấy file."}), 404
    path = os.path.join(d, "files", parts[0], parts[1])
    if not os.path.isfile(path):
        return jsonify({"status": "error", "message": "Không tìm thấy file."}), 404
    with open(path, "r", encoding="utf-8") as f:
        return jsonify({"status": "success", "text": f.read()})


@app.route("/api/localize/latest")
def api_localize_latest():
    """Job gần nhất (để giao diện tự nối lại tiến độ sau khi tải lại trang)."""
    best, best_t = None, 0
    for jid in os.listdir(JOBS_DIR):
        p = os.path.join(JOBS_DIR, jid, "job.json")
        if os.path.isfile(p):
            t = os.path.getmtime(p)
            if t > best_t:
                best, best_t = jid, t
    return jsonify({"status": "success", "job_id": best})


# ======================================================================
#  ĐỘI MÁY: máy chủ (sếp) nhận sản phẩm/báo cáo từ máy nhân viên
# ======================================================================
import fleet
import platform as _platform
import socket as _socket

app.config["MAX_CONTENT_LENGTH"] = max(app.config.get("MAX_CONTENT_LENGTH") or 0, fleet.MAX_UPLOAD + 5 * 1024 * 1024)


def _bearer():
    h = request.headers.get("Authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else ""


def _admin_only():
    """Quản trị chỉ mở cho chính máy chủ (localhost, không qua tunnel)."""
    if not fleet.is_local_request(request):
        return jsonify({"status": "error", "message": "Chỉ thao tác được trên chính máy chủ (localhost)."}), 403
    return None


# ---- máy nhân viên gọi (cần token)
@app.route("/api/fleet/pair", methods=["POST"])
def fleet_pair():
    data = request.get_json(silent=True) or {}
    res = fleet.redeem_pair_code(data.get("code"), data.get("hostname", ""))
    if not res:
        return jsonify({"status": "error", "message": "Mã ghép sai hoặc đã hết hạn. Nhờ sếp cấp mã mới."}), 400
    dev_id, token = res
    name = (fleet._read(fleet.DEVICES_FILE, {}).get(dev_id) or {}).get("name", "")
    return jsonify({"status": "success", "device_id": dev_id, "token": token, "name": name})


@app.route("/api/fleet/heartbeat", methods=["POST"])
def fleet_heartbeat():
    dev = fleet.auth_device(_bearer())
    if not dev:
        return jsonify({"status": "error", "message": "Token không hợp lệ."}), 401
    fleet.heartbeat(dev["id"], request.get_json(silent=True) or {})
    return jsonify({"status": "success"})


@app.route("/api/fleet/report", methods=["POST"])
def fleet_report():
    dev = fleet.auth_device(_bearer())
    if not dev:
        return jsonify({"status": "error", "message": "Token không hợp lệ."}), 401
    try:
        meta = json.loads(request.form.get("meta", "{}"))
    except ValueError:
        return jsonify({"status": "error", "message": "Báo cáo sai định dạng."}), 400
    rep = fleet.save_report(dev, meta, request.files.get("file"))
    return jsonify({"status": "success", "job_id": rep["job_id"]})


# ---- quản trị trên máy chủ
@app.route("/api/fleet/admin/overview")
def fleet_overview():
    deny = _admin_only()
    if deny:
        return deny
    try:
        days = int(request.args.get("days", 7))
    except ValueError:
        days = 7
    since = time.time() - days * 86400 if days else 0
    reports = [r for r in fleet.list_reports(limit=500) if r.get("received", 0) >= since]
    return jsonify({"status": "success", "devices": fleet.list_devices(), "reports": reports,
                    "summary": fleet.summary(days)})


@app.route("/api/fleet/admin/pair-code", methods=["POST"])
def fleet_new_code():
    deny = _admin_only()
    if deny:
        return deny
    data = request.get_json(silent=True) or {}
    return jsonify({"status": "success", **fleet.create_pair_code(data.get("name"))})


@app.route("/api/fleet/admin/device/<dev_id>", methods=["DELETE"])
def fleet_device_delete(dev_id):
    deny = _admin_only()
    if deny:
        return deny
    mode = request.args.get("mode", "revoke")
    ok = fleet.forget_device(dev_id) if mode == "forget" else fleet.revoke_device(dev_id)
    return jsonify({"status": "success" if ok else "error"})


@app.route("/api/fleet/admin/report/<dev_id>/<job_id>/file")
def fleet_report_file(dev_id, job_id):
    deny = _admin_only()
    if deny:
        return deny
    p = fleet.report_file_path(dev_id, job_id)
    if not p:
        return jsonify({"status": "error", "message": "Báo cáo này không có file."}), 404
    return send_file(p, as_attachment=True)


# ---- máy nhân viên: cấu hình kết nối tới máy chủ
@app.route("/api/fleet/agent", methods=["GET"])
def fleet_agent_status():
    cfg = fleet.agent_config()
    ob = fleet.outbox()
    return jsonify({"status": "success", "paired": bool(cfg.get("token")),
                    "hub_url": cfg.get("hub_url", ""), "name": cfg.get("name", ""),
                    "last_ping": _AGENT_STATE.get("last_ping"), "last_error": _AGENT_STATE.get("error", ""),
                    "sent": sum(1 for v in ob.values() if v.get("sent")),
                    "failed": sum(1 for v in ob.values() if not v.get("sent"))})


@app.route("/api/fleet/agent/pair", methods=["POST"])
def fleet_agent_pair():
    deny = _admin_only()
    if deny:
        return deny
    d = request.get_json(silent=True) or {}
    try:
        cfg = fleet.agent_pair(d.get("hub_url"), d.get("code"), d.get("name", ""), d.get("cf_id", ""),
                               d.get("cf_secret", ""), hostname=_socket.gethostname())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    _AGENT_STATE["error"] = ""
    _AGENT_WAKE.set()
    return jsonify({"status": "success", "name": cfg.get("name")})


@app.route("/api/fleet/agent/unpair", methods=["POST"])
def fleet_agent_unpair():
    deny = _admin_only()
    if deny:
        return deny
    fleet.agent_unpair()
    return jsonify({"status": "success"})


@app.route("/api/fleet/agent/sync", methods=["POST"])
def fleet_agent_sync():
    deny = _admin_only()
    if deny:
        return deny
    _AGENT_WAKE.set()
    return jsonify({"status": "success"})


_AGENT_STATE = {}
_AGENT_WAKE = threading.Event()


def _agent_loop():
    """Luồng nền trên máy nhân viên: báo 'còn sống' + gửi sản phẩm mới về máy chủ."""
    while True:
        try:
            cfg = fleet.agent_config()
            if cfg.get("token"):
                jid = _active_job_id()
                prof = os.path.join(APP_DIR, "profiles", gemini_client.DEFAULT_PROFILE
                                    if hasattr(gemini_client, "DEFAULT_PROFILE") else "gemini_profile")
                state = {"job": jid, "model": gemini_client.get_model_name(),
                         "gemini_logged_in": os.path.isdir(prof) and bool(os.listdir(prof)),
                         "os": _platform.system(), "version": "2"}
                fleet.agent_ping(state)
                _AGENT_STATE["last_ping"] = time.time()
                _AGENT_STATE["error"] = ""
                for jd in fleet.pending_jobs(JOBS_DIR):
                    jid2 = os.path.basename(jd)
                    try:
                        ok = fleet.agent_upload_job(jd)
                        fleet.outbox_mark(jid2, ok, "" if ok else "Máy chủ báo lỗi")
                    except PermissionError:
                        raise
                    except Exception as e:
                        fleet.outbox_mark(jid2, False, str(e))
                        _AGENT_STATE["error"] = f"Gửi sản phẩm lỗi: {e}"
        except PermissionError as e:
            _AGENT_STATE["error"] = str(e)
        except Exception as e:
            _AGENT_STATE["error"] = f"Không nối được máy chủ: {e}"
        _AGENT_WAKE.wait(30)
        _AGENT_WAKE.clear()


def _start_agent_thread():
    # Flask debug chạy 2 tiến trình: chỉ bật luồng ở tiến trình thật
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        threading.Thread(target=_agent_loop, daemon=True, name="fleet-agent").start()


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:   # chay bang pythonw (khong co cua so) -> ghi log ra file
        os.makedirs("logs", exist_ok=True)
        _lf = open(os.path.join("logs", "server.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or _lf
        sys.stderr = sys.stderr or _lf
    print("Khởi động server thành công tại http://localhost:5002")
    # AUTOGEMINI_DEBUG=0 -> chay ngam (khong tu nap lai code); mac dinh giu nhu cu
    _debug = os.environ.get("AUTOGEMINI_DEBUG", "1") != "0"
    app.debug = _debug
    _start_agent_thread()
    app.run(debug=_debug, port=5002, use_reloader=_debug)
