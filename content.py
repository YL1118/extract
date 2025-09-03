import re

# 允許的條列： (一)(二)(三)...（全形括號也可）
ALLOW_BULLET = re.compile(r'^\s*[（(][一二三四五六七八九十]+[）)]\s*')

# 明確排除：一、二、 / 1. 2. / 1) 2) / • 等
DISALLOW_BULLETS = [
    re.compile(r'^\s*[一二三四五六七八九十]+[、]\s*'),      # 一、二、三、
    re.compile(r'^\s*\d+[\.、)]\s*'),                       # 1. 2. / 1、 / 1)
    re.compile(r'^\s*[•●○\-]\s+'),                          # 圓點/破折
]

STOP_HEAD = re.compile(r'^(主旨|說明|附件|抄送|結語|此致|敬請|承辦|署名)[:：]?\s*$')

def is_allowed_bullet(line: str) -> bool:
    """只接受 (一)(二)… 條列；其他一律視為不續收"""
    # 先擋掉明確不接受的樣式
    for pat in DISALLOW_BULLETS:
        if pat.match(line):
            return False
    # 允許括號式中文數字
    return bool(ALLOW_BULLET.match(line))

def should_continue(prev_line: str, cur_line: str, already_has_content: bool) -> bool:
    """是否應該把當前行併入『提供內容』段"""
    if STOP_HEAD.match(cur_line):
        return False
    # 若是允許的 (一)(二)… 條列 → 續收
    if is_allowed_bullet(cur_line):
        return True
    # 若上一行以冒號/頓號/逗號等結尾 → 視為同段續行
    if re.search(r'[,:;、：，；]$', prev_line):
        return True
    # 若已經開始收，且本行像是自然續行（不是新段落標題且夠長） → 續收
    if already_has_content and not STOP_HEAD.match(cur_line) and len(cur_line) >= 8:
        # 但若是不允許的條列（如「一、」「1.」等）→ 不收
        if any(p.match(cur_line) for p in DISALLOW_BULLETS):
            return False
        return True
    return False

def extract_hencha_from_txt_lines(lines):
    """給已正規化的行列表 lines，抽取『提供→內容』"""
    trigger = re.compile(r'(惠請|敬請|請)?(.*?)(提供)(如下|下列|如次|資料|清單)?')
    results = []
    for i, line in enumerate(lines):
        if '提供' not in line:
            continue
        if not trigger.search(line):
            continue

        chunk = []
        # 同行冒號後優先收
        post = None
        if ':' in line:
            post = line.split(':', 1)[-1].strip()
        elif '：' in line:
            post = line.split('：', 1)[-1].strip()
        if post:
            chunk.append(post)

        # 向下續收（依你的規則）
        j = i + 1
        while j < len(lines):
            cur = lines[j]
            prev = lines[j-1] if j-1 >= 0 else ''
            if not should_continue(prev, cur, already_has_content=bool(chunk)):
                break
            chunk.append(cur)
            j += 1

        if chunk:
            results.append('\n'.join(chunk).strip())

    return results[0] if results else None
