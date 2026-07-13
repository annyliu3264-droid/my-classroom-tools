import os
import fitz
import sys
import re
import json
import time
from PIL import Image
from image_trim import trim_right_whitespace
import io

sys.stdout.reconfigure(encoding='utf-8')

DB_FILE = 'questions.json'
PDF_DIR = 'pdfs'
CROPPED_DIR = os.path.join('static', 'cropped')

os.makedirs(CROPPED_DIR, exist_ok=True)

# 7大題型定義
TYPE_BOPOMOFO_WRITE = "注音_書寫"
TYPE_WORD_WRITE     = "字詞_書寫"
TYPE_BOPOMOFO_MATCH = "注音_拼音"
TYPE_WORD_RECOG     = "字詞_認識"
TYPE_WORD_APPLY     = "字詞_應用"
TYPE_SENTENCE_READ  = "句段_閱讀"
TYPE_PASSAGE_READ   = "篇章_閱讀"

GRADE_QUESTION_RULES = {
    "三年級": {
        "type_ranges": [(1, 7, TYPE_WORD_RECOG), (8, 12, TYPE_WORD_APPLY), (13, 19, TYPE_SENTENCE_READ), (20, 25, TYPE_PASSAGE_READ)],
        "reading_groups": [(20, 22), (23, 25)],
    },
    "四年級": {
        "type_ranges": [(1, 7, TYPE_WORD_RECOG), (8, 12, TYPE_WORD_APPLY), (13, 19, TYPE_SENTENCE_READ), (20, 25, TYPE_PASSAGE_READ)],
        "reading_groups": [(20, 22), (23, 25)],
    },
    "五年級": {
        "type_ranges": [(1, 5, TYPE_WORD_RECOG), (6, 10, TYPE_WORD_APPLY), (11, 17, TYPE_SENTENCE_READ), (18, 25, TYPE_PASSAGE_READ)],
        "reading_groups": [(18, 20), (21, 23), (24, 25)],
    },
    "六年級": {
        "type_ranges": [(1, 5, TYPE_WORD_RECOG), (6, 10, TYPE_WORD_APPLY), (11, 17, TYPE_SENTENCE_READ), (18, 25, TYPE_PASSAGE_READ)],
        "reading_groups": [(18, 20), (21, 23), (24, 25)],
    },
}


def get_reading_groups(grade):
    rule = GRADE_QUESTION_RULES.get(grade)
    return rule["reading_groups"] if rule else []


def is_reading_question(grade, q_num):
    return any(start <= q_num <= end for start, end in get_reading_groups(grade))


def parse_filename(filename):
    match = re.match(r'^(\d+)', filename)
    if match:
        num_str = match.group(1)
        if len(num_str) == 5:
            year = num_str[:3]
        else:
            year = num_str
    else:
        year = "114"
    
    subject = "國語"
    if "數學" in filename:
        subject = "數學"
        
    grade = "一年級"
    if "1年級" in filename or "一年級" in filename:
        grade = "一年級"
    elif "2年級" in filename or "二年級" in filename:
        grade = "二年級"
    elif "3年級" in filename or "三年級" in filename:
        grade = "三年級"
    elif "4年級" in filename or "四年級" in filename:
        grade = "四年級"
    elif "5年級" in filename or "五年級" in filename:
        grade = "五年級"
    elif "6年級" in filename or "六年級" in filename:
        grade = "六年級"
        
    return year, subject, grade

def get_question_type(q_num, grade, year):
    if grade == "二年級":
        if year == "108":
            if 1 <= q_num <= 4:
                return TYPE_BOPOMOFO_WRITE
            elif 5 <= q_num <= 8:
                return TYPE_WORD_WRITE
            elif 9 <= q_num <= 12:
                return TYPE_WORD_RECOG
            elif 13 <= q_num <= 18:
                return TYPE_WORD_APPLY
            elif 19 <= q_num <= 22:
                return TYPE_SENTENCE_READ
            else:
                return TYPE_PASSAGE_READ
        else:
            if 1 <= q_num <= 5:
                return TYPE_WORD_WRITE
            elif 6 <= q_num <= 11:
                return TYPE_WORD_RECOG
            elif 12 <= q_num <= 17:
                return TYPE_WORD_APPLY
            elif 18 <= q_num <= 22:
                return TYPE_SENTENCE_READ
            else:
                return TYPE_PASSAGE_READ
    elif grade in GRADE_QUESTION_RULES:
        for start_num, end_num, question_type in GRADE_QUESTION_RULES[grade]["type_ranges"]:
            if start_num <= q_num <= end_num:
                return question_type
        return TYPE_PASSAGE_READ
    else:
        if 1 <= q_num <= 4:
            return TYPE_BOPOMOFO_WRITE
        elif 5 <= q_num <= 8:
            return TYPE_WORD_WRITE
        elif 9 <= q_num <= 10:
            return TYPE_BOPOMOFO_MATCH
        elif 11 <= q_num <= 12:
            return TYPE_WORD_RECOG
        elif 13 <= q_num <= 18:
            return TYPE_WORD_APPLY
        elif 19 <= q_num <= 22:
            return TYPE_SENTENCE_READ
        else:
            return TYPE_PASSAGE_READ

def find_question_header_block(blocks, q_num, col_idx, col_width, page_idx):
    pattern = rf'^\s*({q_num})\s*[\.\uFF0E\u3001]\s*'
    min_y = 170 if page_idx == 0 else 30
    
    candidates = []
    for b in blocks:
        x0, y0, x1, y1, text, block_no, block_type = b
        text = text.strip()
        if not text or y0 < min_y:
            continue
        if col_idx == 0 and x0 >= col_width:
            continue
        if col_idx == 1 and x0 < col_width:
            continue
            
        lines = text.split('\n')
        for line in lines:
            line_str = line.strip()
            if line_str.startswith('(') or line_str.startswith('（'):
                continue
            if re.match(pattern, line_str):
                candidates.append(b)
                break
                
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1])
    return candidates[0]

def find_reading_header_block_in_col(blocks, col_idx, col_width):
    for b in blocks:
        x0, y0, x1, y1, text, block_no, block_type = b
        text = text.strip()
        
        # 欄位隔離過濾，確保大題標題確實在該欄內
        if col_idx == 0 and x0 >= col_width:
            continue
        if col_idx == 1 and x0 < col_width:
            continue
            
        # 匹配常見的閱讀大題標題或引導字樣，放寬至包含任何欄位 (Col 0/1) 的適配
        if "閱讀" in text and ("回答" in text or "題" in text):
            return b
        if "閱讀測驗" in text or "閱讀下面的故事" in text or "閱讀下文" in text or "閱讀文章" in text or "閱讀圖文" in text:
            return b
    return None

def is_section_header_or_instruction(text):
    text = text.strip()
    # 匹配「一、」、「二、」等中文大題號，包含可能的中間空白，以及括號中文數字如 (一)、（二）
    if re.match(r'^[一二三四五六七八九十]+\s*[、\.\s]', text) or re.match(r'^[(（][一二三四五六七八九十]+\s*[)）]', text):
        return True
    # 匹配大題指導語或範例
    if text.startswith('※') or text.startswith('＊') or text.startswith('範例：') or text.startswith('*'):
        return True
    # 匹配學生基本資料（防 Page 2 Column 1 頂部干擾）
    if text.startswith('學校：') or text.startswith('班級：') or text.startswith('座號：') or text.startswith('姓名：'):
        return True
    return False

def is_page_footer(text):
    text = text.strip()
    if "評量" in text or "試卷" in text or "教育部" in text:
        return True
    if re.match(r'^第\s*\d+\s*頁', text):
        return True
    return False

def find_first_noise_block(col_blocks, y_start, y_end):
    for b in col_blocks:
        b_x0, b_y0, b_x1, b_y1, b_text, b_no, b_type = b
        if b_y0 >= y_start - 2 and b_y0 < y_end + 2:
            if is_section_header_or_instruction(b_text) or is_page_footer(b_text):
                return b
    return None

def find_split_row_pil(gray_img, x0, x1, y_start, y_end):
    width, height = gray_img.size
    y_start = max(0, min(height - 1, int(y_start)))
    y_end = max(0, min(height - 1, int(y_end)))
    x0 = max(0, min(width - 1, int(x0)))
    x1 = max(0, min(width - 1, int(x1)))
    
    # 縮窄 X 軸以避開外框線與中央分隔線 (X軸左右各縮減 40, 15 像素，防範被邊緣框線干擾)
    scan_x0 = x0 + 40
    scan_x1 = x1 - 15
    if scan_x0 >= scan_x1:
        scan_x0 = x0
        scan_x1 = x1
        
    if y_start >= y_end:
        return int((y_start + y_end) // 2)
        
    # 1. 計算每一行的暗色像素數量
    row_dark_counts = {}
    for y in range(y_start, y_end):
        dark_count = 0
        for x in range(scan_x0, scan_x1):
            if gray_img.getpixel((x, y)) < 248:
                dark_count += 1
        row_dark_counts[y] = dark_count
        
    # 2. 找出最少暗色像素數（最佳分割行）
    min_dark = min(row_dark_counts.values())
    
    # 3. 找出所有達到這個最小值或浮動範圍內的最優分割行
    best_rows = [y for y, count in row_dark_counts.items() if count <= min_dark + 1]
    
    # 4. 尋找連續行中最長的一段，並取其中間值作為分割點
    runs = []
    current_run = []
    for y in sorted(best_rows):
        if not current_run or y == current_run[-1] + 1:
            current_run.append(y)
        else:
            runs.append(current_run)
            current_run = [y]
    if current_run:
        runs.append(current_run)
        
    if runs:
        longest_run = max(runs, key=len)
        return longest_run[len(longest_run) // 2]
    else:
        return int((y_start + y_end) // 2)

def snap_to_white(gray_img, x0, x1, y_target, window=24):
    y_start = max(0, int(y_target - window))
    y_end = int(y_target + window)
    return find_split_row_pil(gray_img, x0, x1, y_start, y_end)

def scan_physical_bottom(gray_img, x0, x1, y_start_pt, max_y_pt, scale_factor=2):
    width, height = gray_img.size
    scan_x0 = max(0, min(width - 1, int(x0 + 40)))
    scan_x1 = max(0, min(width - 1, int(x1 - 15)))
    if scan_x0 >= scan_x1:
        scan_x0 = int(x0)
        scan_x1 = int(x1)
        
    start_y = int(y_start_pt * scale_factor)
    end_y = int(max_y_pt * scale_factor)
    start_y = max(0, min(height - 1, start_y))
    end_y = max(0, min(height - 1, end_y))
    
    white_run = 0
    target_run = 6 # 3 points of whitespace rows at scale 2
    
    for y in range(start_y, end_y):
        dark_count = 0
        for x in range(scan_x0, scan_x1):
            if gray_img.getpixel((x, y)) < 248:
                dark_count += 1
        if dark_count <= 1:
            white_run += 1
            if white_run >= target_run:
                # Return the Y at the start of this white run
                return (y - white_run + 2) / scale_factor
        else:
            white_run = 0
            
    return end_y / scale_factor

def track_question_sequence(doc, grade):
    col_width = doc[0].rect.width / 2
    w, h = doc[0].rect.width, doc[0].rect.height
    
    # 1. Find candidate header blocks for all questions on each page/column
    candidates_by_q = {}
    for q_num in range(1, 26):
        candidates_by_q[q_num] = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            blocks = page.get_text("blocks")
            for col_idx in [0, 1]:
                cands = find_question_header_block(blocks, q_num, col_idx, col_width, page_idx)
                if cands:
                    candidates_by_q[q_num].append({
                        'page_idx': page_idx,
                        'col_idx': col_idx,
                        'block': cands
                    })
                    
    # Establish base sequence headers
    header_sequence = {}
    q1_candidates = [c for c in candidates_by_q.get(1, []) if c['page_idx'] == 0 and c['col_idx'] == 0]
    if q1_candidates:
        header_sequence[1] = min(q1_candidates, key=lambda x: x['block'][1])
    else:
        header_sequence[1] = {
            'page_idx': 0, 'col_idx': 0, 'block': (30, 210, 400, 300, '1.', 0, 0)
        }
        
    for q_num in range(2, 26):
        prev = header_sequence[q_num - 1]
        cands = candidates_by_q.get(q_num, [])
        
        valid_cands = []
        for c in cands:
            if c['page_idx'] < prev['page_idx']:
                continue
            if c['page_idx'] == prev['page_idx']:
                if c['col_idx'] < prev['col_idx']:
                    continue
                if c['col_idx'] == prev['col_idx']:
                    if c['block'][1] < prev['block'][1] - 15:
                        continue
            valid_cands.append(c)
            
        if valid_cands:
            valid_cands.sort(key=lambda x: (x['page_idx'], x['col_idx'], x['block'][1]))
            header_sequence[q_num] = valid_cands[0]
        else:
            # 五、六年級的篇章題固定從第 18 題開始；若順序過濾誤排除了真實題號，
            # 優先取第 3 頁對應欄位的真實文字區塊，不使用低年級估算座標。
            if grade in ["五年級", "六年級"] and 18 <= q_num <= 23 and cands:
                expected_col = 0 if q_num <= 20 else 1
                expected = [c for c in cands if c['page_idx'] == 2 and c['col_idx'] == expected_col]
                if expected:
                    expected.sort(key=lambda x: x['block'][1])
                    header_sequence[q_num] = expected[0]
                    continue

            if grade == "三年級":
                if q_num <= 6:
                    est_page = 0
                elif 7 <= q_num <= 16:
                    est_page = 1
                elif 17 <= q_num <= 19:
                    est_page = 2
                else:
                    est_page = 3
                    
                if est_page == 0:
                    est_col = 0 if q_num <= 3 else 1
                elif est_page == 1:
                    est_col = 0 if q_num <= 11 else 1
                elif est_page == 2:
                    est_col = 0
                else:
                    est_col = 0 if q_num <= 22 else 1
            else:
                est_page = 0 if q_num <= 12 else 1
                est_col = 0 if q_num in (1,2,3,4,5,6,7,8,15,16,17,18,19,20,21) else 1
                
            est_y = prev['block'][3] + 50 if (est_page == prev['page_idx'] and est_col == prev['col_idx']) else 200
            header_sequence[q_num] = {
                'page_idx': est_page,
                'col_idx': est_col,
                'block': (15 if est_col == 0 else col_width + 15, est_y, col_width - 15 if est_col == 0 else w - 15, est_y + 80, f"{q_num}.", 0, 0)
            }
            
    # 2. Merge overlapping and between-header blocks to build final coordinates
    merged_sequence = {}
    for q_num, info in header_sequence.items():
        page_idx = info['page_idx']
        col_idx = info['col_idx']
        b_header = info['block']
        
        box = list(b_header[:4])
        text_parts = [b_header[4]]
        
        page = doc[page_idx]
        blocks = page.get_text("blocks")
        col_blocks = [b for b in blocks if (col_idx == 0 and b[0] < col_width) or (col_idx == 1 and b[0] >= col_width)]
        
        col_headers = []
        for other_q, other_info in header_sequence.items():
            if other_info['page_idx'] == page_idx and other_info['col_idx'] == col_idx:
                col_headers.append((other_q, other_info['block']))
        col_headers.sort(key=lambda x: x[1][1])
        
        header_idx = next(i for i, x in enumerate(col_headers) if x[0] == q_num)
        
        limit_top = 170 if page_idx == 0 else 30
        if header_idx > 0:
            limit_top = col_headers[header_idx - 1][1][3]
            
        limit_bottom = h - 45
        if header_idx < len(col_headers) - 1:
            limit_bottom = col_headers[header_idx + 1][1][1]
            
        # 尋找當前題和下邊界之間的大題標題，作為物理邊界限制，防止把下一大題的說明和範例吃進來
        noise_blocks = []
        for b in col_blocks:
            if b[1] >= b_header[3] - 2 and b[3] <= limit_bottom + 2:
                if is_section_header_or_instruction(b[4]):
                    noise_blocks.append(b)
        if noise_blocks:
            noise_blocks.sort(key=lambda x: x[1])
            limit_bottom = min(limit_bottom, noise_blocks[0][1])
        
        for b in col_blocks:
            if is_section_header_or_instruction(b[4]) or is_page_footer(b[4]):
                continue
            if any(b[5] == h_block[5] for _, h_block in col_headers):
                continue
                
            # Check if this block spans vertically across multiple headers
            overlap_count = 0
            for _, h_block in col_headers:
                if max(b[1], h_block[1]) < min(b[3], h_block[3]):
                    overlap_count += 1
            if overlap_count > 1:
                # Skip merging to protect Y boundaries
                continue
                
            overlap = max(b[1], b_header[1]) < min(b[3], b_header[3])
            
            is_between = False
            if not overlap:
                below_this = (b[1] >= b_header[3] - 2)
                above_next = (b[3] <= limit_bottom + 2)
                is_between = below_this and above_next
                
            if overlap or is_between:
                box[0] = min(box[0], b[0])
                box[1] = min(box[1], b[1])
                box[2] = max(box[2], b[2])
                box[3] = max(box[3], b[3])
                text_parts.append(b[4])
                
        merged_sequence[q_num] = {
            'page_idx': page_idx,
            'col_idx': col_idx,
            'box': tuple(box),
            'text': "".join(text_parts)
        }
        
    return merged_sequence

def auto_crop_pdf(pdf_name, db_dict):
    pdf_path = os.path.join(PDF_DIR, pdf_name)
    year, subject, grade = parse_filename(pdf_name)
    
    print(f"👉 正在進行智慧定位裁切: {pdf_name} ({year}年, {subject}, {grade})")
    
    # 清除資料庫中屬於該年份/科目/年級的舊紀錄，防止 duplicate / obsolete 污染
    keys_to_delete = [k for k, v in db_dict.items() if v.get('year') == year and v.get('subject') == subject and v.get('grade') == grade]
    for k in keys_to_delete:
        del db_dict[k]
    
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"❌ 無法打開 PDF: {e}")
        return 0
        
    pdf_tag = pdf_name.replace('.pdf', '')
    sequence = track_question_sequence(doc, grade)
    
    reading_articles_list = []
    reading_questions_list = []
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        rect = page.rect
        w, h = rect.width, rect.height
        col_width = w / 2
        
        scale_factor = 2.5
        pix = page.get_pixmap(matrix=fitz.Matrix(scale_factor, scale_factor))
        page_img = Image.open(io.BytesIO(pix.tobytes("png")))
        gray_img = page_img.convert('L')
        
        blocks = page.get_text("blocks")
        for col_idx in [0, 1]:
            col_items = []
            for q_num, info in sequence.items():
                if info['page_idx'] == page_idx and info['col_idx'] == col_idx:
                    col_items.append({
                        'is_reading': False,
                        'num': q_num,
                        'box': info['box'],
                        'text': info['text']
                    })
            
            # 在欄位內尋找閱讀引導語 block
            read_m = find_reading_header_block_in_col(blocks, col_idx, col_width)
            if read_m:
                # 尋找在本欄中，位於引導語下方的所有題目
                below_qs = [item for item in col_items if not item['is_reading'] and item['box'][1] >= read_m[1] - 5]
                if below_qs:
                    # 尋找 Y0 最小的那個題目（第一題）
                    first_q = min(below_qs, key=lambda x: x['box'][1])
                    # 文章底部設為該題頂部上方 4 pt
                    y_end = first_q['box'][1] - 4
                else:
                    y_end = h - 60
                    
                reading_box = (read_m[0], read_m[1], read_m[2], max(read_m[3], y_end))
                reading_text = read_m[4]

                col_items.append({
                    'is_reading': True,
                    'num': 99,
                    'box': reading_box,
                    'text': reading_text
                })
                
            col_items.sort(key=lambda x: x['box'][1])
            
            if not col_items:
                continue
                
            c_x0 = 10 if col_idx == 0 else col_width + 2
            c_x1 = col_width - 2 if col_idx == 0 else w - 10
            px_x0 = int(c_x0 * scale_factor)
            px_x1 = int(c_x1 * scale_factor)
            
            # 第一階段：計算每題的實際內容底部 (排除大題指導語和頁尾)
            for i, item in enumerate(col_items):
                text_y_top = item['box'][1]
                y_start_bound = text_y_top
                y_end_bound = h - 60 if i == len(col_items) - 1 else col_items[i+1]['box'][1]
                
                col_blocks = [b for b in blocks if (col_idx == 0 and b[0] < col_width) or (col_idx == 1 and b[0] >= col_width)]
                col_blocks = [b for b in col_blocks if b[1] >= (170 if page_idx == 0 else 30) and b[3] < h - 45]
                col_blocks.sort(key=lambda x: x[1])
                
                # 遍歷該題區間內的所有 blocks，遇到大題號或指示即停止掃描
                item_blocks = []
                for b in col_blocks:
                    b_x0, b_y0, b_x1, b_y1, b_text, b_no, b_type = b
                    b_text = b_text.strip()
                    if not b_text:
                        continue
                    # 確保該 block 頂部小於下一題頂部，且底部不侵入下一題頂部下方 10 pt 以上
                    if b_y0 >= y_start_bound - 5 and b_y0 < y_end_bound - 2 and b_y1 <= y_end_bound + 10:
                        # 對於一般題目，遇到國字大題標題、指示語或學生基本欄位就 break 停止
                        if not item.get('is_reading') and (is_section_header_or_instruction(b_text) or is_page_footer(b_text)):
                            break
                        # 對於閱讀題組，我們不 break 大題標題，但 break 頁尾
                        if item.get('is_reading') and is_page_footer(b_text):
                            break
                        item_blocks.append(b)
                
                if item_blocks:
                    item['y_content_bottom'] = max(b[3] for b in item_blocks)
                else:
                    item['y_content_bottom'] = item['box'][3]
                item['blocks'] = item_blocks
            
            # 第二階段：執行投影分割與裁切
            for i, item in enumerate(col_items):
                text_y_top = item['box'][1]
                y_content_bottom = item['y_content_bottom']
                
                # 重新計算當前題目的 px_x0, px_x1 (將邊緣起點縮進到 20 pt，裁掉左右邊緣的黑色定位長方形)
                is_reading_group_item = item.get('is_reading') or is_reading_question(grade, item['num'])
                
                if col_idx == 0:
                    c_x0 = 20
                else:
                    # 閱讀題組（文章及題目）的 X0 起點只向右移動 1 pt，以防切到最左側文字；一般單題移 2 pt
                    c_x0 = col_width + 1.0 if is_reading_group_item else col_width + 2.0
                    
                c_x1 = col_width - 2 if col_idx == 0 else w - 20
                px_x0 = int(c_x0 * scale_factor)
                px_x1 = int(c_x1 * scale_factor)
                
                # 如果是右半欄的一般單題，我們額外再向右縮進 20 像素以剔除中線
                if col_idx == 1 and not is_reading_group_item:
                    px_x0 = px_x0 + 20
                
                # 獲取該列的所有 blocks (已排序)
                col_blocks = [b for b in blocks if (col_idx == 0 and b[0] < col_width) or (col_idx == 1 and b[0] >= col_width)]
                col_blocks.sort(key=lambda x: x[1])
                
                # 計算上邊界 py_start
                # 計算上邊界 py_start
                if i == 0:
                    if not item.get('is_reading') and item['num'] <= 5:
                        # 尋找 Q1 上方的區塊（例題或大題標題）
                        above_blocks = [b for b in col_blocks if b[3] < text_y_top]
                        # 尋找是否有大題標題
                        section_headers = [b for b in above_blocks if is_section_header_or_instruction(b[4])]
                        if section_headers:
                            # 如果上方有大題標題，我們絕對不能跨越它，起點設為大題標題的底部
                            b_header = max(section_headers, key=lambda x: x[3])
                            y_s = b_header[3]
                            y_e = text_y_top
                            py_start = find_split_row_pil(gray_img, px_x0, px_x1, y_s * scale_factor, y_e * scale_factor)
                        elif above_blocks:
                            b_above = max(above_blocks, key=lambda x: x[3])
                            # 在例題底部與 Q1 本文頂部之間的 Gap 尋找純白分割線
                            y_s = b_above[3]
                            y_e = text_y_top
                            if y_e - y_s < 15:
                                y_s = max(170 if page_idx == 0 else 40, text_y_top - 50)
                            py_start = find_split_row_pil(gray_img, px_x0, px_x1, y_s * scale_factor, y_e * scale_factor)
                        else:
                            py_start = find_split_row_pil(gray_img, px_x0, px_x1,
                                max(170 if page_idx == 0 else 40, text_y_top - 50) * scale_factor,
                                text_y_top * scale_factor)
                    else:
                        # 尋找本題上方 80 像素內是否有大題號或指導語
                        above_noise = []
                        for b in col_blocks:
                            b_y0, b_y1 = b[1], b[3]
                            if b_y1 < text_y_top + 2 and b_y1 >= text_y_top - 80:
                                if is_section_header_or_instruction(b[4]):
                                    above_noise.append(b)
                        if above_noise:
                            y_s = max(b[3] for b in above_noise)
                            y_e = text_y_top
                            if y_e - y_s < 5:
                                y_s = text_y_top - 5
                            py_start = find_split_row_pil(gray_img, px_x0, px_x1, y_s * scale_factor, y_e * scale_factor)
                        else:
                            py_start = find_split_row_pil(gray_img, px_x0, px_x1, 
                                max(170 if page_idx == 0 else 40, text_y_top - 12) * scale_factor, 
                                text_y_top * scale_factor)
                else:
                    prev_item = col_items[i-1]
                    # 尋找前題底部與本題頂部之間是否有大題號或說明
                    y_s = prev_item['y_content_bottom']
                    y_e = text_y_top
                    
                    # 掃描前題底部與本題頂部之間是否有大題號或指導語
                    mid_noise = []
                    for b in col_blocks:
                        b_y0, b_y1 = b[1], b[3]
                        if b_y0 >= y_s - 10 and b_y1 <= y_e + 10:
                            if is_section_header_or_instruction(b[4]):
                                mid_noise.append(b)
                    if mid_noise:
                        # 如果中間有大題說明，我們將搜尋起點限制在大題說明底部之下，避開大題標題
                        y_s = max(b[3] for b in mid_noise)
                        
                    if y_e - y_s < 10:
                        y_s = max(170 if page_idx == 0 else 40, text_y_top - 15)
                    py_start = find_split_row_pil(gray_img, px_x0, px_x1, y_s * scale_factor, y_e * scale_factor)
                
                # 三年級全局起點 Override 規則 (文字往上 10 像素，2022年第24題、2021年第20題除外)
                if grade == "三年級":
                    if year == "111" and item['num'] == 24:
                        # 2022年第24題：文字往上 5 像素
                        py_start = int(item['box'][1] * scale_factor) - 5
                    elif year == "110" and item['num'] == 20:
                        # 2021年第20題：文字往上 5 像素 (強制文字起點為 522.0 pt)
                        py_start = int(522.0 * scale_factor) - 5
                    else:
                        # 全局 1-25 題與文章：文字往上 10 像素
                        py_start = int(item['box'][1] * scale_factor) - 10
                        
                    if py_start < 0:
                        py_start = 0
                            
                # 計算下邊界 py_end
                if i == len(col_items) - 1:
                    b_noise = find_first_noise_block(col_blocks, y_content_bottom, h - 45)
                    max_y = b_noise[1] - 1 if b_noise else h - 55
                    if not item.get('is_reading') and item['num'] <= 8:
                        y_search_start_down = y_content_bottom
                        y_search_end_down = max_y
                        if y_search_start_down >= y_search_end_down:
                            y_search_end_down = y_search_start_down + 15
                        py_end = find_split_row_pil(gray_img, px_x0, px_x1, y_search_start_down * scale_factor, y_search_end_down * scale_factor)
                    elif item.get('is_reading') or item['num'] in [23, 24]:
                        # 閱讀文章與 23-24 題：強制延伸至 max_y，保留粗黑底線與紅色框線
                        py_end = int(max_y * scale_factor)
                    elif item['num'] == 25:
                        # 第 25 題：幾何 Fallback 限制 (如找不到紅框線則以此為準，避免大片空白)
                        padding_pt = 24
                        target_y = min(y_content_bottom + padding_pt, max_y)
                        py_end = int(target_y * scale_factor)
                    else:
                        # 9-25 題使用自適應物理底部掃描，加入至少 24pt 的安全 Padding 以防基線與注音被截斷
                        scanned_end_pt = scan_physical_bottom(gray_img, px_x0 / 2, px_x1 / 2, y_content_bottom + 24, max_y, scale_factor=scale_factor)
                        py_end = int(scanned_end_pt * scale_factor)
                else:
                    next_item = col_items[i+1]
                    b_noise = find_first_noise_block(col_blocks, y_content_bottom, next_item['box'][1])
                    max_y = b_noise[1] - 1 if b_noise else next_item['box'][1] - 2
                    
                    if not item.get('is_reading') and item['num'] <= 8:
                        # 每一年的1-8題採用中線分割，限制不得越過大題/噪訊邊界 max_y
                        mid_y = (y_content_bottom + next_item['box'][1]) / 2
                        target_y = min(mid_y, max_y)
                        py_end = snap_to_white(gray_img, px_x0, px_x1, target_y * scale_factor, window=10 * scale_factor)
                    elif item.get('is_reading') or item['num'] >= 23:
                        # 閱讀文章與 23-25 題：強制延伸至 max_y，保留粗黑底線與紅色框線
                        py_end = int(max_y * scale_factor)
                    else:
                        gap = next_item['box'][1] - y_content_bottom
                        if gap < 24:
                            # 兩題距離極近，將分割點設在下一題頂部上方 3 pt 處，保留最大安全空間
                            target_y = next_item['box'][1] - 3
                            py_end = int(target_y * scale_factor)
                        else:
                            # 9-25 題使用自適應物理底部掃描，加入至少 24pt 的安全 Padding 以防基線與注音被截斷
                            scanned_end_pt = scan_physical_bottom(gray_img, px_x0 / 2, px_x1 / 2, y_content_bottom + 24, max_y, scale_factor=scale_factor)
                            py_end = int(scanned_end_pt * scale_factor)

                # 專用人工精細修正 Override 規則
                # 1. 2019 (Year 108) Q8：去除 "三、選擇題..." 以下字樣
                if year == "108" and item['num'] == 8:
                    py_end = int(738.0 * scale_factor)
                
                # 2. 所有年份的 Q11 與 Q12：下面被裁掉太多，強制延伸至極大邊界 max_y
                if item['num'] in [11, 12]:
                    py_end = int(max_y * scale_factor)
                
                # 3. 2022 (Year 111) Q10：下面被裁掉太多，強制延伸至 Q11 的頂部
                if year == "111" and item['num'] == 10:
                    py_end = int(max_y * scale_factor)

                # 4. 2019 (Year 108) Q15：Option (3) 精確底框線裁切 (避開下方空文字塊與留白)

                # 5. 2020 (Year 109) Q14：Option (3) 精確底框線裁切 (避開下方空文字塊與留白)
                pass

                # 6. 2020 (Year 109) Q20：Option (3) 精確底框線裁切 (避開下方空文字塊與留白)
                pass

                # 7. 2024 (Year 113) Q21：Option (3) 精確底框線裁切 (避開下方空文字塊與留白)
                pass
                
                # 8. 2020 (Year 109) Q21, Q22：最下面多切掉一點紅框線，強制延伸至 max_y
                if year == "109" and item['num'] in [21, 22]:
                    py_end = int(max_y * scale_factor)

                # 9. 2023 (Year 112) Q21, Q22：最下面多切掉一點紅框線，強制延伸至 max_y
                if year == "112" and item['num'] in [21, 22]:
                    py_end = int(max_y * scale_factor)

                # 10. 2024 (Year 113) Q22：根據使用者要求「以文字往下15像素即可」
                if year == "113" and item['num'] == 22:
                    py_end = int(item['y_content_bottom'] * scale_factor) + 15

                # 11. 2025 (Year 114) Q19, Q22：最下面多切掉一點紅框線，強制延伸
                if year == "114" and item['num'] == 19:
                    py_end = int((max_y + 2.5) * scale_factor)
                if year == "114" and item['num'] == 22:
                    py_end = int(max_y * scale_factor)

                # 12. 2019 (Year 108) Q23：根據使用者要求「以文字往下15像素即可」
                if year == "108" and item['num'] == 23:
                    py_end = int(item['y_content_bottom'] * scale_factor) + 15
                    
                # 13. 2023 (Year 112) Q23：鴕鳥插圖在 Y = 945 pt 結束，以插圖底往下15像素即可
                if year == "112" and item['num'] == 23:
                    py_end = int(945 * scale_factor) + 15
                
                # 三年級全局終點 Override 規則 (文章往下 10 像素，單題往下 15 像素)
                if grade == "三年級":
                    if item.get('is_reading'):
                        # 文章：以文字往下 10 像素 (110年第一篇除外，改為往下 5 像素)
                        if year == "110" and page_idx == 2:
                            py_end = int(512.0 * scale_factor) + 5
                        else:
                            py_end = int(item['box'][3] * scale_factor) + 10
                    else:
                        # 排除特定的強制延伸大題 (如 Q11, Q12, 111年Q10, 114年Q19等) 與 112年Q23鴕鳥插圖
                        # 根據使用者要求，部分大題不再強制延伸，直接改為「文字往上10像素，往下15像素」
                        is_excluded_from_extension = (
                            (year == "108" and item['num'] == 11) or
                            (year == "110" and item['num'] == 12) or
                            (year == "111" and item['num'] == 11) or
                            (year == "113" and item['num'] == 11) or
                            (year == "114" and item['num'] in [12, 19]) or
                            (year == "110" and item['num'] == 20)
                        )
                        
                        is_special_extended = False
                        if not is_excluded_from_extension:
                            is_special_extended = (item['num'] in [11, 12]) or \
                                                  (year == "111" and item['num'] == 10) or \
                                                  (year == "114" and item['num'] in [19, 22]) or \
                                                  (year == "109" and item['num'] in [21, 22]) or \
                                                  (year == "112" and item['num'] in [21, 22])
                        
                        is_ostrich = (year == "112" and item['num'] == 23)
                        
                        if year == "110" and item['num'] == 20:
                            # 2021年第20題：文字往下 10 像素
                            py_end = int(item['y_content_bottom'] * scale_factor) + 10
                        elif not is_special_extended and not is_ostrich:
                            py_end = int(item['y_content_bottom'] * scale_factor) + 15
                            
                # 通用紅線檢測與自適應裁剪：
                # 如果裁剪範圍內有紅色框線，且紅框線下沒有該題的其他文字 block，就裁剪到紅線下方 10 像素
                py_content_bottom = int(y_content_bottom * scale_factor)
                start_y = max(py_start, py_content_bottom - 150)
                end_y = py_end
                
                last_red_y = None
                if not item.get('is_reading') and start_y < end_y:
                    scan_x0 = int(px_x0 + (px_x1 - px_x0) * 0.15)
                    scan_x1 = int(px_x0 + (px_x1 - px_x0) * 0.85)
                    
                    for y in range(start_y, end_y):
                        red_count = 0
                        for x in range(scan_x0, scan_x1):
                            r, g, b = page_img.getpixel((x, y))
                            if r > 150 and r - g > 30 and r - b > 30:
                                red_count += 1
                        if red_count >= 3:
                            last_red_y = y
                
                if last_red_y is not None:
                    # 檢查紅線下方是否已無該題目的任何 text block (即沒有任何一個 block 的 bottom 超過紅線下 10 像素)
                    has_text_below = False
                    item_blocks = item.get('blocks', [])
                    for b in item_blocks:
                        b_y1_px = int(b[3] * scale_factor)
                        # 如果有 text block 的底邊大於 last_red_y + 10，就代表紅線下還有該題的字
                        if b_y1_px > last_red_y + 10:
                            if b[4].strip():
                                has_text_below = True
                                break
                    
                    if not has_text_below:
                        # 紅框線下方沒有其他有效字，裁剪至紅線下 10 像素
                        py_end = last_red_y + 10
                
                min_crop_height = int(80 * scale_factor)
                if py_end - py_start < min_crop_height:
                    fallback_start = max(0, int(item['box'][1] * scale_factor) - 10)
                    fallback_end = min(page_img.height, int(item['box'][3] * scale_factor) + 15)
                    if fallback_end - fallback_start >= min_crop_height:
                        py_start, py_end = fallback_start, fallback_end
                    else:
                        py_end = min(page_img.height, py_start + min_crop_height)
                    
                cropped_img = page_img.crop((px_x0, py_start, px_x1, py_end))
                cropped_img = trim_right_whitespace(cropped_img)
                
                if item['is_reading']:
                    filename = f"q_{year}_{subject}_{grade}_reading_{page_idx+1}_{col_idx}.png"
                    # 原則五：快取破壞微調
                    if year == "110" and page_idx == 2:
                        filename = f"q_{year}_{subject}_{grade}_reading_{page_idx+1}_{col_idx}_v4.png"
                else:
                    filename = f"q_{year}_{subject}_{grade}_{item['num']}.png"
                    # 原則五：快取破壞微調
                    if year == "110" and item['num'] == 20:
                        filename = f"q_{year}_{subject}_{grade}_{item['num']}_v4.png"
                    
                filename = re.sub(r'[^\w\.-]', '_', filename)
                filepath = os.path.join(CROPPED_DIR, filename)
                cropped_img.save(filepath)
                
                if item['is_reading']:
                    reading_articles_list.append((page_idx, col_idx, item['box'][1], f"/static/cropped/{filename}"))
                elif is_reading_question(grade, item['num']):
                    reading_questions_list.append((item['num'], f"/static/cropped/{filename}"))
                else:
                    q_type = get_question_type(item['num'], grade, year)
                    db_dict[f"q_{year}_{subject}_{grade}_{item['num']}"] = {
                        'id': f"q_{year}_{subject}_{grade}_{item['num']}",
                        'imagePaths': [f"/static/cropped/{filename}"],
                        'year': year,
                        'subject': subject,
                        'grade': grade,
                        'type': q_type,
                        'tags': ['自動裁切', pdf_tag],
                        'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    }
                    
    # 打包篇章閱讀題組
    reading_articles_list.sort(key=lambda x: (x[0], x[1], x[2]))
    reading_questions_list.sort(key=lambda x: x[0])
    
    reading_groups = get_reading_groups(grade)
    used_article_indexes = set()
    if reading_groups and len(reading_articles_list) >= len(reading_groups):
        for group_index, (start_num, end_num) in enumerate(reading_groups, start=1):
            first_question = sequence.get(start_num, {})
            same_column = [
                (idx, article) for idx, article in enumerate(reading_articles_list)
                if idx not in used_article_indexes
                and article[0] == first_question.get('page_idx')
                and article[1] == first_question.get('col_idx')
                and article[2] <= first_question.get('box', (0, float('inf')))[1]
            ]
            if same_column:
                article_index, article = same_column[-1]
            else:
                fallback = [(idx, article) for idx, article in enumerate(reading_articles_list) if idx not in used_article_indexes]
                if not fallback:
                    continue
                article_index, article = fallback[0]
            used_article_indexes.add(article_index)
            article_path = article[3]
            q_paths = [path for num, path in reading_questions_list if start_num <= num <= end_num]
            if not q_paths:
                continue
            group_id = f"q_{year}_{subject}_{grade}_reading_group_{group_index}"
            db_dict[group_id] = {
                'id': group_id,
                'imagePaths': [article_path] + q_paths,
                'year': year,
                'subject': subject,
                'grade': grade,
                'type': TYPE_PASSAGE_READ,
                'tags': ['自動裁切', f'閱讀測驗組{group_index}', pdf_tag],
                'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
    else:
        # 低年級或文章數量不足時，保留舊版單一題組行為。
        if reading_articles_list:
            article = reading_articles_list[0][3]
            q_paths = [path for num, path in reading_questions_list]
            if q_paths:
                group_id = f"q_{year}_{subject}_{grade}_reading_group"
                db_dict[group_id] = {
                    'id': group_id,
                    'imagePaths': [article] + q_paths,
                    'year': year,
                    'subject': subject,
                    'grade': grade,
                    'type': TYPE_PASSAGE_READ,
                    'tags': ['自動裁切', '閱讀測驗組', pdf_tag],
                    'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }
            
    return len(sequence)

def main():
    print("==========================================")
    print("Start auto_crop.py v3.2 (Excluding Chinese numeral headers)")
    print("==========================================")
    
    # 載入現有 questions.json，完整保留並鎖定已定稿的一、二年級舊數據，防止其被覆寫
    db_dict = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                old_list = json.load(f)
                for item in old_list:
                    if item.get('grade') in ["一年級", "二年級"]:
                        db_dict[item['id']] = item
        except Exception as e:
            print(f"Error loading questions.json: {e}")
            
    if not os.path.exists(PDF_DIR):
        os.makedirs(PDF_DIR)
        return
        
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf')]
    pdf_files = [f for f in pdf_files if any(g in f for g in ["3年級", "三年級"])]
    # 排除答案、解答、解答等 PDF，只留試卷
    pdf_files = [f for f in pdf_files if not any(ans in f for ans in ["答案", "解答", "ת", "ר", "-解", "ans"])]
    for pdf in pdf_files:
        auto_crop_pdf(pdf, db_dict)
        
    # 排序並寫回資料庫
    db_list = list(db_dict.values())
    db_list.sort(key=lambda x: x['id'])
    
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db_list, f, ensure_ascii=False, indent=2)
        
    print("==========================================")
    print(f"Auto crop completed! Total {len(db_list)} items in database.")
    print("==========================================")

if __name__ == '__main__':
    main()
