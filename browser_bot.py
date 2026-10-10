import time
import os
import argparse
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

import json

def run(source_lang="auto", target_lang="en", gdoc_url="", text_file="", profile_name="default", open_only=False, mode="single", batch_dir="", output_dir="", prompt_id="default", chunk_size="auto", detail_level="expand", selected_prompts="[]"):
    print("="*50)
    print(f"🚀 TOOL TRANSLATOR - AUTO CHAT GEMINI ({source_lang.upper()} -> {target_lang.upper()}) 🚀")
    print("="*50)
    
    if profile_name and profile_name != "default":
        base_dir = os.path.dirname(os.path.abspath(__file__))
        user_data_dir = os.path.join(base_dir, "profiles", profile_name)
        print(f"Đang sử dụng tài khoản ảo: {profile_name}")
        os.makedirs(user_data_dir, exist_ok=True)
    else:
        user_data_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        print("Đang sử dụng trình duyệt Chrome gốc của máy.")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir,
                channel="chrome",
                headless=False,
                accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            print(f"❌ LỖI KHỞI ĐỘNG TRÌNH DUYỆT: {e}")
            return

        page = browser.pages[0] if browser.pages else browser.new_page()
        
        if open_only:
            print("Đang mở trang đăng nhập Gemini...")
            page.goto("https://gemini.google.com/app", timeout=60000)
            print("Hãy thao tác đăng nhập rồi TẮT HẲN trình duyệt để lưu.")
            try:
                page.wait_for_event("close", timeout=0)
            except Exception: pass
            return

        output_filename = "output_content.txt"
        if os.path.exists(output_filename):
            os.remove(output_filename)

        all_doc_text = ""

        # Lấy text từ file (backend app.py đã gộp URL và file vào 1 file text_file)
        if text_file and os.path.exists(text_file):
            with open(text_file, "r", encoding="utf-8") as f:
                all_doc_text = f.read().strip()

        if mode != "batch" and not all_doc_text.strip():
            print("❌ LỖI: Không có văn bản nào để xử lý.")
            browser.close()
            return

        print(f"Tổng hợp xong văn bản: {len(all_doc_text)} ký tự.")
        
        print(f"Tổng hợp xong văn bản: {len(all_doc_text)} ký tự.")
        
        # Đọc Prompt Template từ prompts.json
        prompt_template = ""
        prompts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts.json")
        
        if mode == "creative":
            prompt_list_text = ""
            try:
                selected_prompt_ids = json.loads(selected_prompts)
            except:
                selected_prompt_ids = []
                
            if os.path.exists(prompts_file):
                with open(prompts_file, "r", encoding="utf-8") as f:
                    prompts_data = json.load(f)
                    idx = 1
                    for p in prompts_data:
                        if not selected_prompt_ids or p["id"] in selected_prompt_ids:
                            raw_content = p['content'].replace("[SOURCE_LANG]", source_lang.upper()).replace("[TARGET_LANG]", target_lang.upper())
                            prompt_list_text += f"\n--- Mẫu {idx} (Tên: {p['name']}) ---\n{raw_content}\n"
                            idx += 1
            
            detail_instruction = ""
            if detail_level == "expand":
                detail_instruction = "- CAM KẾT: Phân tích thật sâu sắc, diễn giải chi tiết, bổ sung tư duy. Bài viết ĐẦU RA PHẢI DÀI HƠN HOẶC BẰNG dung lượng của bản gốc. Tuyệt đối không tóm tắt ngắn đi!"
            elif detail_level == "normal":
                detail_instruction = "- CAM KẾT: Giữ nguyên dung lượng (độ dài) tương đương với bản gốc."
            elif detail_level == "summarize":
                detail_instruction = "- CAM KẾT: Tóm tắt ngắn gọn, súc tích, chỉ lọc ý chính, loại bỏ các chi tiết rườm rà."

            prompt_template = f"""Bạn là một AI Nhà Văn siêu việt. Dưới đây là danh sách các "Mẫu hành văn" (Prompts) mà hệ thống đang có:

{prompt_list_text}
------------------------------

NHIỆM VỤ CỦA BẠN:
1. Đọc và phân tích phân đoạn nội dung (Ngôn ngữ gốc: {source_lang.upper()}) dưới đây.
2. TỰ ĐỘNG CHỌN RA 1 mẫu hành văn PHÙ HỢP NHẤT với sắc thái của phân đoạn này.
3. SÁNG TẠO và VIẾT LẠI phân đoạn này bằng NGÔN NGỮ ĐÍCH là: {target_lang.upper()}, tuân thủ tuyệt đối nguyên tắc của mẫu hành văn bạn vừa chọn.
4. TUYỆT ĐỐI CHỈ TRẢ VỀ nội dung bài viết đã hoàn thiện. KHÔNG giải thích, KHÔNG đưa ra kết luận, KHÔNG nói bạn chọn mẫu nào.
{detail_instruction}

--- PHÂN ĐOẠN NỘI DUNG CẦN VIẾT LẠI ---
[TEXT]"""
            def build_prompt(text):
                return prompt_template.replace("[TEXT]", text)
                
        else:
            if os.path.exists(prompts_file):
                with open(prompts_file, "r", encoding="utf-8") as f:
                    prompts_data = json.load(f)
                    for p in prompts_data:
                        if p["id"] == prompt_id:
                            prompt_template = p["content"]
                            break
            
            if not prompt_template:
                if mode == "image":
                    prompt_template = "[TEXT]"
                else:
                    prompt_template = """Bạn là chuyên gia dịch thuật. Hãy dịch đoạn văn bản sau từ ngôn ngữ của quốc gia có mã [SOURCE_LANG] sang ngôn ngữ của quốc gia có mã: [TARGET_LANG].
Yêu cầu QUAN TRỌNG:
- TUYỆT ĐỐI KHÔNG thêm câu mở đầu (như 'Dưới đây là...'), KHÔNG kết luận, KHÔNG giải thích.
- CHỈ TRẢ VỀ DUY NHẤT nội dung đã dịch, không kèm số từ hay văn bản thừa.
- Dịch HOÀN TOÀN sang ngôn ngữ đích (bao gồm cả Tên riêng, Địa danh, Thuật ngữ). TUYỆT ĐỐI KHÔNG để sót lại bất kỳ từ Tiếng Anh hay ngôn ngữ gốc nào (Phải dịch hoặc phiên âm toàn bộ).
- Giữ nguyên định dạng gốc (xuống dòng, đoạn văn).
- Dịch tự nhiên, chuẩn văn phong bản địa.

Nội dung cần dịch:
[TEXT]"""

            def build_prompt(text):
                return prompt_template.replace("[SOURCE_LANG]", source_lang.upper()).replace("[TARGET_LANG]", target_lang.upper()).replace("[TEXT]", text)

        # =======================
        # GỬI CHO GEMINI
        # =======================
        print("Đang truy cập gemini.google.com...")
        page.goto("https://gemini.google.com/app", timeout=60000)
        chat_box_selector = "rich-textarea"
        
        try:
            page.wait_for_selector(chat_box_selector, timeout=30000)
        except Exception:
            print("❌ LỖI: Không tìm thấy khung chat. Kiểm tra lại đăng nhập hoặc tài khoản Gemini.")
            browser.close()
            return

        # Chọn model Gemini đã cấu hình (mặc định 3.1 Pro). Lỗi ở bước này chỉ cảnh báo để tab cũ vẫn chạy.
        if mode != "image":
            try:
                import gemini_client
                gemini_client.apply_model_to_page(page, log=print)
            except Exception as e:
                print(f"⚠️ Không chọn được model Gemini ({e}). Tiếp tục với model đang bật trên trang.")

        response_selector = "message-content"

        def split_text_into_chunks(text, max_length=25000):
            import re
            chunks = []
            
            # Tách theo các đoạn nhỏ (paragraph)
            paragraphs = re.split(r'\n{2,}', text.replace('\r\n', '\n'))
            
            current_chunk = ""
            for p in paragraphs:
                p = p.strip()
                if not p: continue
                
                # Detect if 'p' is a strong semantic boundary (Header, Chương, Phần, ---, ***)
                is_boundary = bool(re.match(r'^(?:#+\s|(?i:chương|phần|bài)\s+\d+|[-*]{3,})', p))
                
                # Nếu gặp điểm cắt đẹp (boundary) và chunk hiện tại đã khá dài (ví dụ > 5000 ký tự)
                # thì ưu tiên cắt ngay tại đây để bảo toàn mạch nội dung
                if is_boundary and len(current_chunk) > 5000:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                if len(current_chunk) + len(p) + 2 <= max_length:
                    current_chunk += (p + "\n\n") if current_chunk else p
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = ""
                    
                    if len(p) > max_length:
                        sentences = re.split(r'(?<=[.!?])\s+', p)
                        for s in sentences:
                            if len(current_chunk) + len(s) + 1 <= max_length:
                                current_chunk += (s + " ") if current_chunk else s
                            else:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                    current_chunk = ""
                                if len(s) > max_length:
                                    for i in range(0, len(s), max_length):
                                        chunks.append(s[i:i+max_length])
                                else:
                                    current_chunk = s + " "
                    else:
                        current_chunk = p + "\n\n"
            if current_chunk:
                chunks.append(current_chunk.strip())
            return chunks

        def process_text(text, filename):
            if not text.strip(): return
            
            try:
                max_len = 25000 if str(chunk_size).lower() == "auto" else int(chunk_size)
            except:
                max_len = 25000
                
            chunks = split_text_into_chunks(text, max_length=max_len)
            
            output_filepath = os.path.join(output_dir if mode == "batch" else "", f"{os.path.splitext(filename)[0]}_{target_lang.upper()}.txt") if mode == "batch" else output_filename
            
            with open(output_filepath, "w" if mode == "batch" else "a", encoding="utf-8") as f_out:
                print(f"\n{'='*40}")
                print(f"▶ BẮT ĐẦU XỬ LÝ: {filename} (Tổng cộng {len(chunks)} phần)")
                print(f"{'='*40}")
                
                for idx, chunk in enumerate(chunks):
                    print(f"\n--- Đang dịch phần {idx+1}/{len(chunks)} ---")
                    
                    full_prompt = build_prompt(chunk)
                    if len(chunks) > 1:
                        if mode == "creative":
                            full_prompt += f"\n\n[LƯU Ý: Đây là phân đoạn thứ {idx+1}/{len(chunks)} của toàn bộ nội dung. BẮT BUỘC chỉ in ra bản sáng tác, KHÔNG được nhận xét, KHÔNG thêm câu mở đầu hay kết luận.]"
                        else:
                            full_prompt += f"\n\n[LƯU Ý: Đây là phần {idx+1}/{len(chunks)} của tài liệu. BẮT BUỘC chỉ in ra bản dịch, KHÔNG được nhận xét, KHÔNG thêm câu mở đầu hay kết luận.]"
                    
                    print("⏳ Đang dán nội dung vào khung chat...")
                    page.click(chat_box_selector)
                    time.sleep(0.5)
                    page.keyboard.insert_text(full_prompt)
                    time.sleep(1)
                
                    prev_responses_count = len(page.query_selector_all(response_selector))
                    page.keyboard.press("Enter")
                    print("📤 Đã gửi yêu cầu! Bắt đầu đếm ngược thời gian phản hồi...")
                
                    start_time = time.time()
                    try:
                        page.wait_for_function(f"document.querySelectorAll('{response_selector}').length > {prev_responses_count}", timeout=45000)
                    except Exception:
                        print("⚠️ Gemini phản hồi chậm, vẫn đang tiếp tục theo dõi...")
                
                    print("✍️ Gemini đang tiến hành viết nội dung. Đang theo dõi tiến độ...")
                    last_text_length = 0
                    unchanged_count = 0
                    spawn_wait = 0
                    max_spawn_wait = 60 # 120s max to wait for the first character
                
                    while unchanged_count < 8: # Wait 16s of no change to consider finished
                        time.sleep(2)
                        elements = page.query_selector_all(response_selector)
                    
                        if len(elements) <= prev_responses_count:
                            spawn_wait += 1
                            if spawn_wait > max_spawn_wait:
                                print("❌ LỖI: Quá thời gian, Gemini không tạo ra câu trả lời mới.")
                                break
                            continue
                        
                        current_response = elements[-1].inner_text()
                    
                        if len(current_response) > last_text_length:
                            print(f"   + Đang viết... (Đã được {len(current_response)} ký tự)")
                            last_text_length = len(current_response)
                            unchanged_count = 0
                        elif len(current_response) == last_text_length and len(current_response) > 0:
                            unchanged_count += 1
                            print(f"   - Không có thay đổi ({unchanged_count}/8)...")
                        else:
                            # Case len == 0 (Gemini rendered the box but no text yet)
                            pass
                
                    end_time = time.time()
                    elapsed_time = round(end_time - start_time, 1)
                
                    final_elements = page.query_selector_all(response_selector)
                    content = final_elements[-1].inner_text()
                
                    print(f"✅ ĐÃ HOÀN THÀNH PHẦN {idx+1}/{len(chunks)}")
                    print(f"⏱️ Thời gian xử lý: {elapsed_time} giây.")
                    print(f"📄 Khối lượng kết quả: {len(content)} ký tự.")
                
                    f_out.write(content + "\n\n")
                
                    print("✔️ Lưu thành công phần này!")
                    time.sleep(3)
                
            print(f"🎉 ĐÃ HOÀN THÀNH TOÀN BỘ FILE: {filename}")

        
        def process_image(prompt, output_dir):
            print(f"\n{'='*40}")
            print(f"▶ BẮT ĐẦU TẠO ẢNH")
            print(f"{'='*40}")
            
            full_prompt = prompt
            print("⏳ Đang gửi lệnh tạo ảnh cho Gemini...")
            page.click(chat_box_selector)
            time.sleep(0.5)
            page.keyboard.insert_text(full_prompt)
            time.sleep(1)
            
            prev_responses_count = len(page.query_selector_all(response_selector))
            page.keyboard.press("Enter")
            
            print("📤 Đã gửi yêu cầu tạo ảnh. Vui lòng chờ (Có thể mất 20-60 giây)...")
            start_time = time.time()
            
            try:
                page.wait_for_function(f"document.querySelectorAll('{response_selector}').length > {prev_responses_count}", timeout=90000)
            except Exception:
                print("⚠️ Gemini phản hồi quá chậm.")
            
            # Wait for text generation to stop changing, which also means image generation is likely done.
            # But images might take a bit longer to load. Let's wait for a bit of stability.
            unchanged_count = 0
            last_text_length = 0
            
            while unchanged_count < 10:
                time.sleep(3)
                elements = page.query_selector_all(response_selector)
                if len(elements) <= prev_responses_count: continue
                current_response = elements[-1].inner_text()
                if len(current_response) > last_text_length:
                    last_text_length = len(current_response)
                    unchanged_count = 0
                else:
                    unchanged_count += 1
            
            print("✅ Đã nhận được phản hồi. Bắt đầu tìm kiếm hình ảnh...")
            # Allow some extra time for images to render
            time.sleep(5)
            
            final_elements = page.query_selector_all(response_selector)
            last_msg = final_elements[-1]
            
            # Find images inside the last message
            img_elements = last_msg.query_selector_all("img")
            downloaded = 0
            
            os.makedirs(output_dir, exist_ok=True)
            
            for idx, img in enumerate(img_elements):
                src = img.get_attribute("src")
                if not src: continue
                # Skip small icons like avatar
                if "avatar" in src.lower() or img.evaluate("el => el.width < 100"): continue
                
                print(f"📥 Đang tải ảnh thứ {idx+1}...")
                
                # Use evaluate to fetch the image as base64
                js_fetch = """
                async (imgEl) => {
                    try {
                        let url = imgEl.src;
                        if (url.startsWith('data:image')) return url;
                        const res = await fetch(url);
                        const blob = await res.blob();
                        return new Promise((resolve) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        });
                    } catch (e) {
                        return null;
                    }
                }
                """
                
                base64_data = img.evaluate(js_fetch)
                if base64_data and "," in base64_data:
                    import base64
                    header, data = base64_data.split(",", 1)
                    ext = "jpg"
                    if "png" in header: ext = "png"
                    
                    import uuid
                    filename = f"image_{uuid.uuid4().hex[:8]}.{ext}"
                    filepath = os.path.join(output_dir, filename)
                    
                    with open(filepath, "wb") as f_img:
                        f_img.write(base64.b64decode(data))
                    print(f"✔️ Đã lưu ảnh: {filename}")
                    downloaded += 1
            
            if downloaded == 0:
                print("❌ Không tìm thấy ảnh nào được tạo ra.")

        if mode == "batch":
            files = [f for f in os.listdir(batch_dir) if os.path.isfile(os.path.join(batch_dir, f))]
            print(f"Tìm thấy {len(files)} file cần xử lý hàng loạt.")
            for i, f_name in enumerate(files):
                print(f"\n--- Đang xử lý file {i+1}/{len(files)}: {f_name} ---")
                with open(os.path.join(batch_dir, f_name), "r", encoding="utf-8") as f:
                    content = f.read()
                process_text(content, f_name)
        elif mode == "image":
            process_image(all_doc_text, output_dir)
        else:
            process_text(all_doc_text, "single_output.txt")

        print("\n" + "="*50)
        print(f"🎉 HOÀN THÀNH!")
        print("="*50)
        
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=str, default="default")
    parser.add_argument("--open-only", action="store_true")
    parser.add_argument("--source-lang", type=str, default="auto")
    parser.add_argument("--target-lang", type=str, default="en")
    parser.add_argument("--url", type=str, default="")
    parser.add_argument("--text-file", type=str, default="")
    parser.add_argument("--mode", type=str, default="single")
    parser.add_argument("--batch-dir", type=str, default="")
    parser.add_argument("--output-dir", type=str, default="")
    parser.add_argument("--prompt-id", type=str, default="default")
    parser.add_argument("--chunk-size", type=str, default="auto")
    parser.add_argument("--detail-level", type=str, default="expand")
    parser.add_argument("--selected-prompts", type=str, default="[]")
    args = parser.parse_args()
    
    run(source_lang=args.source_lang, target_lang=args.target_lang, gdoc_url=args.url, text_file=args.text_file, profile_name=args.profile, open_only=args.open_only, mode=args.mode, batch_dir=args.batch_dir, output_dir=args.output_dir, prompt_id=args.prompt_id, chunk_size=args.chunk_size, detail_level=args.detail_level, selected_prompts=args.selected_prompts)
