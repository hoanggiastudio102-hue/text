# -*- coding: utf-8 -*-
"""
Dữ liệu quốc gia/ngôn ngữ bản địa + bộ dựng prompt viết lại & bản địa hoá + chia đoạn.

File này KHÔNG phụ thuộc Playwright/Flask nên test được độc lập.
"""
import re

# ---------------------------------------------------------------------------
# DANH SÁCH QUỐC GIA
#   code      : mã dùng trong giao diện + tên file đầu ra (VD: BR -> bai_BR.txt)
#   language  : ngôn ngữ + biến thể sẽ yêu cầu Gemini viết
#   notes     : quy ước bản địa (xưng hô, tiền tệ, định dạng, từ vựng) đưa vào prompt
# ---------------------------------------------------------------------------
COUNTRIES = [
    # --- Anh ngữ ---
    {"code": "US", "flag": "🇺🇸", "name_vi": "Mỹ", "language": "American English", "locale": "en-US",
     "notes": "American spelling and vocabulary (color, apartment). Currency USD ($). Dates MM/DD/YYYY. Imperial units (miles, °F, pounds) where natural."},
    {"code": "GB", "flag": "🇬🇧", "name_vi": "Anh", "language": "British English", "locale": "en-GB",
     "notes": "British spelling and vocabulary (colour, flat). Currency GBP (£). Dates DD/MM/YYYY. Miles and °C are normal in everyday text."},
    {"code": "AU", "flag": "🇦🇺", "name_vi": "Úc", "language": "Australian English", "locale": "en-AU",
     "notes": "Australian/British spelling (colour, organise). Currency AUD (A$). Dates DD/MM/YYYY. Metric units."},
    # --- Đông Á ---
    {"code": "VN", "flag": "🇻🇳", "name_vi": "Việt Nam", "language": "Vietnamese", "locale": "vi-VN",
     "notes": "Natural Vietnamese as written by a native journalist/blogger. Currency VND (₫, thousand separator '.'). Dates DD/MM/YYYY. Metric units."},
    {"code": "JP", "flag": "🇯🇵", "name_vi": "Nhật Bản", "language": "Japanese", "locale": "ja-JP",
     "notes": "Natural Japanese (kanji/kana mix). Polite です・ます style by default unless the style guide asks otherwise. Currency JPY (円/¥). Dates YYYY年M月D日. Use 万/億 number grouping. Metric units."},
    {"code": "KR", "flag": "🇰🇷", "name_vi": "Hàn Quốc", "language": "Korean", "locale": "ko-KR",
     "notes": "Natural Korean (Hangul). Polite register: 합니다체 for articles, 해요체 for casual styles. Currency KRW (원/₩). Dates YYYY년 M월 D일. Use 만/억 number grouping. Metric units."},
    {"code": "CN", "flag": "🇨🇳", "name_vi": "Trung Quốc (đại lục)", "language": "Simplified Chinese (Mainland China)", "locale": "zh-CN",
     "notes": "Simplified characters with Mainland vocabulary (e.g. 软件, 视频, 手机). Currency CNY (元/人民币). Dates YYYY年M月D日. Use 万/亿 number grouping. Metric units."},
    {"code": "TW", "flag": "🇹🇼", "name_vi": "Đài Loan", "language": "Traditional Chinese (Taiwan)", "locale": "zh-TW",
     "notes": "Traditional characters with Taiwan vocabulary (e.g. 軟體, 影片, 手機). Currency TWD (NT$/元). Dates YYYY年M月D日. Use 萬/億 number grouping. Metric units."},
    {"code": "HK", "flag": "🇭🇰", "name_vi": "Hồng Kông", "language": "Traditional Chinese (Hong Kong written style)", "locale": "zh-HK",
     "notes": "Traditional characters in Hong Kong written Chinese (standard written style, not colloquial Cantonese unless the style guide asks). Currency HKD (HK$/港元). Metric units."},
    # --- Đông Nam Á & Nam Á ---
    {"code": "TH", "flag": "🇹🇭", "name_vi": "Thái Lan", "language": "Thai", "locale": "th-TH",
     "notes": "Natural Thai with a polite register; use ครับ/ค่ะ only for conversational styles. Currency THB (บาท/฿). Gregorian years are fine; Buddhist Era (พ.ศ.) only in formal/official contexts. Metric units."},
    {"code": "ID", "flag": "🇮🇩", "name_vi": "Indonesia", "language": "Indonesian (Bahasa Indonesia)", "locale": "id-ID",
     "notes": "Standard modern Indonesian; 'Anda' for formal address, 'kamu' for casual styles. Currency IDR (Rp). Decimal comma, thousand separator '.'. Dates DD-MM-YYYY. Metric units."},
    {"code": "MY", "flag": "🇲🇾", "name_vi": "Malaysia", "language": "Malay (Bahasa Malaysia)", "locale": "ms-MY",
     "notes": "Standard Malaysian Malay (not Indonesian vocabulary). Currency MYR (RM). Dates DD/MM/YYYY. Metric units."},
    {"code": "PH", "flag": "🇵🇭", "name_vi": "Philippines", "language": "Filipino (Tagalog-based)", "locale": "fil-PH",
     "notes": "Natural Filipino as used in Philippine media; light Taglish is acceptable for casual/social styles. Currency PHP (₱). Dates MM/DD/YYYY. Metric units."},
    {"code": "IN", "flag": "🇮🇳", "name_vi": "Ấn Độ (Hindi)", "language": "Hindi (Devanagari script)", "locale": "hi-IN",
     "notes": "Natural Hindi in Devanagari, common English loanwords allowed where Indians normally use them. Currency INR (₹). Indian number grouping (lakh, crore). Dates DD/MM/YYYY. Metric units."},
    # --- Châu Âu ---
    {"code": "DE", "flag": "🇩🇪", "name_vi": "Đức", "language": "German", "locale": "de-DE",
     "notes": "Natural German; formal 'Sie' by default, 'du' for casual/social styles. Currency EUR (€, written after the amount). Decimal comma, thousand separator '.'. Dates DD.MM.YYYY. Metric units."},
    {"code": "FR", "flag": "🇫🇷", "name_vi": "Pháp", "language": "French (France)", "locale": "fr-FR",
     "notes": "Natural French; 'vous' by default, 'tu' for casual/social styles. Currency EUR (€). Decimal comma, space as thousand separator. Dates DD/MM/YYYY. Metric units. French quotation marks « »."},
    {"code": "ES", "flag": "🇪🇸", "name_vi": "Tây Ban Nha", "language": "Spanish (Spain)", "locale": "es-ES",
     "notes": "Peninsular Spanish vocabulary (ordenador, móvil); 'usted' for formal, 'tú' (and 'vosotros') for casual. Currency EUR (€). Dates DD/MM/YYYY. Metric units."},
    {"code": "IT", "flag": "🇮🇹", "name_vi": "Ý", "language": "Italian", "locale": "it-IT",
     "notes": "Natural Italian; formal 'Lei' by default, 'tu' for casual styles. Currency EUR (€). Decimal comma. Dates DD/MM/YYYY. Metric units."},
    {"code": "PT", "flag": "🇵🇹", "name_vi": "Bồ Đào Nha", "language": "European Portuguese", "locale": "pt-PT",
     "notes": "European Portuguese spelling and vocabulary (not Brazilian). Currency EUR (€). Dates DD/MM/YYYY. Metric units."},
    {"code": "NL", "flag": "🇳🇱", "name_vi": "Hà Lan", "language": "Dutch (Netherlands)", "locale": "nl-NL",
     "notes": "Natural Dutch as used in the Netherlands; 'u' for formal, 'je' for casual. Currency EUR (€). Decimal comma. Dates DD-MM-YYYY. Metric units."},
    {"code": "PL", "flag": "🇵🇱", "name_vi": "Ba Lan", "language": "Polish", "locale": "pl-PL",
     "notes": "Natural Polish; 'Pan/Pani' for formal address. Currency PLN (zł). Decimal comma. Dates DD.MM.YYYY. Metric units."},
    {"code": "SE", "flag": "🇸🇪", "name_vi": "Thụy Điển", "language": "Swedish", "locale": "sv-SE",
     "notes": "Natural Swedish; 'du' is standard even in formal writing. Currency SEK (kr). Decimal comma. Dates YYYY-MM-DD. Metric units."},
    {"code": "CZ", "flag": "🇨🇿", "name_vi": "Séc", "language": "Czech", "locale": "cs-CZ",
     "notes": "Natural Czech; 'vy' for formal address. Currency CZK (Kč). Decimal comma. Dates D. M. YYYY. Metric units."},
    {"code": "RO", "flag": "🇷🇴", "name_vi": "Romania", "language": "Romanian", "locale": "ro-RO",
     "notes": "Natural Romanian with correct diacritics (ă, â, î, ș, ț); 'dumneavoastră' for formal address. Currency RON (lei). Decimal comma. Dates DD.MM.YYYY. Metric units."},
    {"code": "GR", "flag": "🇬🇷", "name_vi": "Hy Lạp", "language": "Greek", "locale": "el-GR",
     "notes": "Modern Greek (Demotic) in Greek script; formal plural address by default. Currency EUR (€). Decimal comma. Dates DD/MM/YYYY. Metric units."},
    {"code": "RU", "flag": "🇷🇺", "name_vi": "Nga", "language": "Russian", "locale": "ru-RU",
     "notes": "Natural Russian in Cyrillic; 'вы' for formal address. Currency RUB (₽). Decimal comma, space as thousand separator. Dates DD.MM.YYYY. Metric units."},
    {"code": "UA", "flag": "🇺🇦", "name_vi": "Ukraina", "language": "Ukrainian", "locale": "uk-UA",
     "notes": "Natural Ukrainian in Cyrillic with genuinely Ukrainian vocabulary (avoid Russianisms); 'ви' for formal address. Currency UAH (₴). Decimal comma. Dates DD.MM.YYYY. Metric units."},
    {"code": "TR", "flag": "🇹🇷", "name_vi": "Thổ Nhĩ Kỳ", "language": "Turkish", "locale": "tr-TR",
     "notes": "Natural Turkish; 'siz' for formal address. Currency TRY (₺). Decimal comma, thousand separator '.'. Dates DD.MM.YYYY. Metric units."},
    # --- Mỹ Latin ---
    {"code": "MX", "flag": "🇲🇽", "name_vi": "Mexico", "language": "Mexican Spanish", "locale": "es-MX",
     "notes": "Mexican Spanish vocabulary; 'ustedes' (never 'vosotros'); 'usted' for formal, 'tú' for casual. Currency MXN ($). Dates DD/MM/YYYY. Metric units."},
    {"code": "AR", "flag": "🇦🇷", "name_vi": "Argentina", "language": "Argentine Spanish (Rioplatense)", "locale": "es-AR",
     "notes": "Rioplatense Spanish: voseo ('vos') for casual styles, 'usted' for formal; 'ustedes' for plural. Currency ARS ($). Decimal comma. Dates DD/MM/YYYY. Metric units."},
    {"code": "BR", "flag": "🇧🇷", "name_vi": "Brazil", "language": "Brazilian Portuguese", "locale": "pt-BR",
     "notes": "Brazilian Portuguese spelling and vocabulary (not European); 'você' for address. Currency BRL (R$). Decimal comma, thousand separator '.'. Dates DD/MM/YYYY. Metric units."},
    # --- Trung Đông ---
    {"code": "SA", "flag": "🇸🇦", "name_vi": "Ả Rập Xê Út", "language": "Modern Standard Arabic (Gulf-appropriate vocabulary)", "locale": "ar-SA",
     "notes": "Modern Standard Arabic, right-to-left, with vocabulary and examples suitable for Saudi/Gulf readers. Currency SAR (ريال). Gregorian dates are fine. Metric units. Western digits 0-9 unless the style guide asks otherwise."},
    {"code": "EG", "flag": "🇪🇬", "name_vi": "Ai Cập", "language": "Modern Standard Arabic (Egyptian-familiar vocabulary)", "locale": "ar-EG",
     "notes": "Modern Standard Arabic, right-to-left, with vocabulary and examples familiar to Egyptian readers. Currency EGP (جنيه). Gregorian dates. Metric units. Western digits 0-9 unless the style guide asks otherwise."},
]

# Tên tiếng Anh của quốc gia để đưa vào prompt (Gemini hiểu rõ nhất)
NAME_EN = {'US': 'the United States', 'GB': 'the United Kingdom', 'AU': 'Australia', 'VN': 'Vietnam', 'JP': 'Japan', 'KR': 'South Korea', 'CN': 'mainland China', 'TW': 'Taiwan', 'HK': 'Hong Kong', 'TH': 'Thailand', 'ID': 'Indonesia', 'MY': 'Malaysia', 'PH': 'the Philippines', 'IN': 'India', 'DE': 'Germany', 'FR': 'France', 'ES': 'Spain', 'IT': 'Italy', 'PT': 'Portugal', 'NL': 'the Netherlands', 'PL': 'Poland', 'SE': 'Sweden', 'CZ': 'the Czech Republic', 'RO': 'Romania', 'GR': 'Greece', 'RU': 'Russia', 'UA': 'Ukraine', 'TR': 'Turkey', 'MX': 'Mexico', 'AR': 'Argentina', 'BR': 'Brazil', 'SA': 'Saudi Arabia', 'EG': 'Egypt', 'SAME': 'the original audience'}

# Lựa chọn đặc biệt: giữ nguyên ngôn ngữ gốc, chỉ viết lại.
SAME_COUNTRY = {
    "code": "SAME", "flag": "📝", "name_vi": "Giữ ngôn ngữ gốc (chỉ viết lại)",
    "language": "the SAME language as the source article", "locale": "same",
    "notes": "Keep the original language, spelling variant, currency and units of the source article. Do not localize to another country.",
}

_BY_CODE = {c["code"]: c for c in COUNTRIES}
_BY_CODE["SAME"] = SAME_COUNTRY


def name_en(country):
    return NAME_EN.get(country["code"], country["name_vi"])


def get_country(code):
    c = _BY_CODE.get(str(code).upper())
    if not c:
        raise KeyError(f"Mã quốc gia không hợp lệ: {code}")
    return c


def list_countries():
    """Danh sách trả cho giao diện (có mục 'giữ ngôn ngữ gốc' đứng đầu)."""
    return [SAME_COUNTRY] + COUNTRIES


# ---------------------------------------------------------------------------
# TUỲ CHỌN ĐỘ DÀI
# ---------------------------------------------------------------------------
LENGTH_RULES = {
    "same": "Keep roughly the same length as the source (within about ±10%).",
    "longer": "Make it richer and about 30-50% longer than the source by adding smoother transitions, clearer explanations and relevant context drawn ONLY from the source. Never invent facts, numbers or quotes.",
    "shorter": "Condense it to about 60-70% of the source length. Keep every key fact, number and argument; cut repetition and filler.",
}


CJK_TARGETS = {"JP": 1.0, "CN": 1.0, "TW": 1.0, "HK": 1.0, "KR": 1.0}


def _volume(text):
    """Ước lượng khối lượng nội dung của bài nguồn theo 'số từ tiếng Anh tương đương'."""
    hangul = len(re.findall(r"[\uac00-\ud7a3]", text))
    han = len(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff]", text))
    other = len(re.findall(r"\b\w+\b", re.sub(r"[\uac00-\ud7a3\u4e00-\u9fff\u3040-\u30ff]", " ", text)))
    return int(hangul * 0.4 + han * 0.6 + other)


def target_size(src, code, factor=1.0):
    """Mục tiêu độ dài cụ thể (chữ/ký tự) cho ngôn ngữ đích, tính từ bài nguồn."""
    words = max(1, int(_volume(src) * factor))
    if code in CJK_TARGETS:
        per = 2.2 if code == "KR" else 1.8
        n = int(words * per)
        return f"about {n:,} characters (at least {int(n * 0.9):,})"
    return f"about {words:,} words (at least {int(words * 0.9):,})"


def _lines(value):
    """Tách textarea thành danh sách dòng không rỗng."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [ln.strip() for ln in str(value).splitlines() if ln.strip()]


def fill_template_vars(template, country, audience=""):
    """Thay các biến [COUNTRY] [LANGUAGE] [AUDIENCE] nếu mẫu lệnh có dùng."""
    out = template or ""
    out = out.replace("[COUNTRY]", name_en(country))
    out = out.replace("[LANGUAGE]", country["language"])
    out = out.replace("[AUDIENCE]", audience or "general readers")
    return out


def build_prompt(chunk, country, style_text, mode="rewrite", audience="", length="same",
                 keywords="", glossary="", extra="", part=1, parts=1,
                 outline="", outline_use="strict", source_use="fresh"):
    """
    Dựng prompt gửi Gemini cho 1 đoạn của bài, cho 1 quốc gia.

    mode: "rewrite"  = viết lại theo style guide + bản địa hoá
          "localize" = dịch sát ý, chỉ chỉnh cho tự nhiên với bản địa (không sáng tạo thêm)
    """
    is_same = country["code"] == "SAME"
    style_text = fill_template_vars(style_text, country, audience).strip()

    analyze = (mode == "analyze")
    outline = (outline or "").strip() if mode != "localize" else ""
    if analyze:
        lang_txt = "the same language as the input" if is_same else country["language"]
        task = (f"Using the INPUT below as the subject (it may be a full article, notes, or just a short topic / name / "
                f"event), write an original, in-depth analytical piece that follows the STYLE GUIDE exactly. Write it "
                f"in {lang_txt}" + ("" if is_same else f" for readers in {name_en(country)}") + ", as a senior "
                "analyst and writer would. Use the input's own facts first; where needed, add well-established, "
                "verifiable background knowledge, but clearly separate documented fact from your own inference or "
                "interpretation, and say so plainly when evidence is thin or historians disagree.")
    elif mode == "localize":
        if is_same:
            task = ("Lightly polish the source article in its own language: fix awkward phrasing and "
                    "flow while keeping the structure, wording and meaning as close to the source as possible.")
        else:
            task = (f"Translate the source article into {country['language']} for readers in {name_en(country)}. "
                    "Stay faithful to the meaning and structure of the source, but make it read as if it had been "
                    "written natively in that language: natural phrasing, local conventions, no word-for-word calques.")
    else:
        if is_same:
            task = ("Rewrite the source article in its own language, following the STYLE GUIDE. "
                    "Keep every fact, number and name accurate, but change the wording, sentence structure and flow "
                    "so that it reads as a fresh, original piece.")
        else:
            task = (f"Rewrite the source article following the STYLE GUIDE, and write it directly in "
                    f"{country['language']} for readers in {name_en(country)}, as a native writer and editor would. "
                    "This is NOT a word-for-word translation: re-express the ideas the way a local author would, "
                    "with natural idioms, local conventions, and examples adapted to local readers where this "
                    "does not change the meaning. Keep every fact, number and name accurate.")

    sections = []
    sections.append(
        f"You are a senior native-level editor and localization writer for {name_en(country)} "
        f"({country['language']}).\n\nTASK:\n{task}")

    if style_text:
        sections.append(f"STYLE GUIDE:\n{style_text}")

    if outline:
        if outline_use == "loose":
            ol_rule = ("Use the outline as the backbone of the new article. You may merge, reorder or add a section "
                       "only when the reference article contains important material that the outline misses; "
                       "never drop an outline topic.")
        else:
            ol_rule = ("Follow the outline strictly: cover EVERY item in the same order, using its headings (translated "
                       "naturally into the target language), and do not add major sections that are not in it. "
                       "Expand each item fully.")
        if source_use == "close":
            src_rule = ("Stay close to the reference article's content and ideas wherever the outline allows; "
                        "re-express the wording freshly.")
        else:
            src_rule = ("Treat the reference article as research material only: take its facts, data, names and key "
                        "ideas, but write every sentence fresh in new wording and a new structure. Do not copy "
                        "phrases longer than four words and do not mirror its paragraph order.")
        sections.append("OUTLINE (the structure of the new article):\n<<<\n" + outline + "\n>>>\n" + ol_rule +
                        "\n\nREFERENCE USE: " + src_rule +
                        "\nFacts may come from the reference article or from the outline; do not add facts from elsewhere.")
    if analyze:
        sections.append(
            "ACCURACY RULES FOR ANALYSIS (strict):\n"
            "- Never invent quotes, statistics, dates, sources, documents or events. If you are not sure of a detail, "
            "leave it out or mark it as uncertain.\n"
            "- Do not put made-up words in the mouth of a real person. Any simulation, imagined dialogue or "
            "'what if' scenario must be labelled clearly as imagination at the start, and must not be presented as a real "
            "statement or real history.\n"
            "- For living people, analyse only public, documented conduct and publicly stated views; no medical or "
            "clinical diagnosis, no speculation about private life.\n"
            "- Distinguish fact / contested claim / your interpretation. Present opposing views fairly.\n"
            "- Adapt names, terms, units and examples to readers in " + name_en(country) + " where natural.")
    elif not is_same:
        sections.append(f"LOCALIZATION RULES for {name_en(country)} ({country['locale']}):\n- {country['notes']}\n"
                        "- Convert currencies, units and date formats to local conventions only when the source uses "
                        "them as generic examples; keep exact figures, quotes and official names intact.\n"
                        "- Keep names of real people, brands and products recognisable (add the standard local "
                        "transliteration for non-Latin scripts when it is customary).\n"
                        "- Never add new facts, claims, statistics or sources that are not in " + ("the reference article or the outline." if outline else "the source."))
    else:
        sections.append(f"LANGUAGE RULES:\n- {country['notes']}\n"
                        "- Never add new facts, claims, statistics or sources that are not in " + ("the reference article or the outline." if outline else "the source."))

    aud = (audience or "").strip()
    if aud:
        sections.append(f"TARGET AUDIENCE: {aud}")

    if analyze:
        sections.append("LENGTH: " + {"longer": "Go deeper and longer: about 2,500-4,000 words.",
                                       "shorter": "Compact version: about 600-900 words."}.get(
            length, "Follow the style guide. If the input is short, produce a complete in-depth report of about "
                    "1,500-2,500 words; if the input is long, analyse it fully without padding."))
    elif length in ("same", "longer", "shorter") and not outline and len(chunk) > 1500:
        f = {"same": 1.0, "longer": 1.4, "shorter": 0.65}[length]
        sections.append("LENGTH: " + LENGTH_RULES[length] + " The source holds roughly the same information as "
                        + target_size(chunk, "EN", 1.0).replace("about ", "").split(" (")[0]
                        + " of English. Your output in " + country["language"] + " must be " + target_size(chunk, country["code"], f)
                        + ". Do NOT summarise, skip, merge or shorten sections: every paragraph, example, number and "
                        "argument of the source must appear. A shorter result is a failure.")
    elif outline and length == "same":
        sections.append("LENGTH: Let the outline decide: cover every item fully; the total should be roughly comparable "
                        "to the reference article (" + target_size(chunk, country["code"]) + ") unless the outline clearly calls for more. "
                        "Never summarise or compress: a shorter result is a failure.")
    else:
        sections.append(f"LENGTH: {LENGTH_RULES.get(length, LENGTH_RULES['same'])}")

    kw = _lines(keywords)
    if kw:
        sections.append("KEYWORDS TO WORK IN (express each with the phrasing local readers would actually "
                        "search for, weave them in naturally, never stuff):\n" + "\n".join(f"- {k}" for k in kw))

    gl = _lines(glossary)
    if gl:
        sections.append("GLOSSARY (apply EXACTLY wherever the left-hand term appears; format is 'source = target'):\n"
                        + "\n".join(f"- {g}" for g in gl))

    ex = (extra or "").strip()
    if ex:
        sections.append(f"EXTRA INSTRUCTIONS FROM THE CLIENT:\n{ex}")

    if parts > 1:
        sections.append(f"PART INFO: This is part {part} of {parts} of ONE article. Keep terminology, names, voice "
                        "and tone consistent with the earlier parts of this conversation. Output only the text of "
                        "this part, with no recap of earlier parts.")

    if analyze:
        sections.append(
            "OUTPUT RULES (strict):\n"
            "- Output ONLY the finished analysis. No preamble like 'Here is…', no notes about the style guide, "
            "no closing remarks, no code fences.\n"
            "- Use the structure the style guide asks for; write headings as plain lines, short paragraphs, "
            "lists or small tables only where they help.\n"
            "- Complete the whole piece; do not stop early.")
        sections.append("INPUT (subject / source material):\n<<<\n" + chunk.strip() + "\n>>>")
        return "\n\n".join(sections)

    sections.append(
        "OUTPUT RULES (strict):\n"
        "- Output ONLY the finished text. No preamble, no title like 'Here is…', no notes, no explanation, "
        "no word counts, no mention of the style guide, no closing remarks.\n"
        "- Do not wrap the text in code fences or quotation marks.\n"
        + ("- Use the structure of the OUTLINE (not the reference article's structure); write headings as plain lines.\n"
           if outline else
           "- Keep the source structure (headings, paragraphs, lists) unless the style guide requires otherwise; "
           "write headings as plain lines.\n") +
        "- The result must be complete: do not stop early, skip paragraphs or summarise unless asked.")

    label = "REFERENCE ARTICLE (source of facts and ideas):" if outline else "SOURCE ARTICLE:"
    sections.append(label + "\n<<<\n" + chunk.strip() + "\n>>>")
    return "\n\n".join(sections)


def build_review_prompt(country, mode="rewrite", part=1, parts=1, has_outline=False):
    """Bước 2 (tuỳ chọn): bắt Gemini tự soát lại đúng bản vừa viết trong cùng cuộc chat."""
    is_same = country["code"] == "SAME"
    if mode == "analyze":
        return ("Now act as a strict fact-checking editor and review the analysis you just wrote. Check for: "
                "1) invented or doubtful facts, dates, numbers, quotes or sources; 2) claims presented as fact that are "
                "really interpretation; 3) missing sections the style guide required; 4) one-sided treatment where "
                "balance was requested; 5) stiff, translated-sounding or padded phrasing. Fix every problem and output "
                "the COMPLETE corrected final text only, with no review notes.")
    lang_check = ("wrong language variant, spelling or register" if not is_same
                  else "changes of language")
    part_note = f" (part {part}/{parts})" if parts > 1 else ""
    return (
        f"Now act as a strict second editor and review the text you just produced{part_note}.\n"
        "Check against the source and the instructions for:\n"
        "1) omitted or distorted facts, numbers, names or sentences;\n"
        "2) invented content that is not in the source;\n"
        f"3) unnatural, stiff or translated-sounding phrasing, {lang_check}, wrong local conventions "
        "(address form, currency, units, dates);\n"
        "4) leftover words of the source language that should have been translated;\n"
        + ("5) every item of the OUTLINE is covered, in order, with no major off-outline sections, and no sentence "
           "copied from the reference article.\n" if has_outline else
           "5) formatting or structure that drifted from the source.\n") +
        "Fix every problem you find and output the COMPLETE corrected final text for this part. "
        "Output ONLY the final text: no review notes, no list of changes, no preamble."
    )


# ---------------------------------------------------------------------------
# CHIA ĐOẠN
# ---------------------------------------------------------------------------
_BOUNDARY = re.compile(r'^(?:#+\s|(?i:chương|phần|bài|chapter|part|section)\s+\d+|[-*_=]{3,}\s*$)', re.IGNORECASE)
_SENT_SPLIT = re.compile(r'(?<=[.!?。！？…])\s+|(?<=[。！？])')


def split_text(text, max_len=12000):
    """
    Chia bài dài thành các đoạn <= max_len ký tự, ưu tiên cắt ở ranh giới đoạn/tiêu đề,
    không cắt giữa câu trừ khi một câu dài hơn max_len.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) == 1:  # văn bản chỉ xuống dòng đơn
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    # Tách tiếp các đoạn quá dài thành câu, câu quá dài thành mảnh cứng.
    pieces = []
    for p in paragraphs:
        if len(p) <= max_len:
            pieces.append(p)
            continue
        for s in _SENT_SPLIT.split(p):
            s = s.strip()
            if not s:
                continue
            if len(s) <= max_len:
                pieces.append(s)
            else:
                pieces.extend(s[i:i + max_len] for i in range(0, len(s), max_len))

    chunks, cur = [], ""
    soft_min = max_len // 3  # gặp tiêu đề/chương và đoạn hiện tại đã đủ dài thì cắt luôn
    for piece in pieces:
        if cur and _BOUNDARY.match(piece) and len(cur) >= soft_min:
            chunks.append(cur)
            cur = ""
        if not cur:
            cur = piece
        elif len(cur) + 2 + len(piece) <= max_len:
            cur += "\n\n" + piece
        else:
            chunks.append(cur)
            cur = piece
    if cur:
        chunks.append(cur)
    return chunks
