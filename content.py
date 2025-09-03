import re
from typing import List, Dict, Optional

TRIGGER = re.compile(r'(?:惠請|敬請)?(?:.*?)(?:請)?(?:.*?)(提供)(?:.*?(如下|下列|如次|資料|清單))?')
STOP_HEAD = re.compile(r'^(主旨|說明|理由|辦法|注意事項|附件|抄送|結語|此致|敬請|承辦|署名)[:：]?\s*$')

ALLOW_BULLET = re.compile(r'^\s*[（(][一二三四五六七八九十]+[）)]\s*')  # (一)(二)…
DISALLOW_BULLETS = [
    re.compile(r'^\s*[一二三四五六七八九十]+[、]\s*'),      # 一、二、三、
    re.compile(r'^\s*\d+[\.、)]\s*'),                       # 1. / 1、 / 1)
    re.compile(r'^\s*[•●○\-]\s+'),                          # 圓點/破折等
]

def normalize_text(s: str) -> str:
    repl = {
        '：':':','﹕':':','∶':':','　':' ',
        '提 供':'提供','拖供':'提供','體供':'提供',
        '下 列':'下列','成列':'下列','列下':'下列',
    }
    for k,v in repl.items():
        s = s.replace(k,v)
    # 把多空白壓成一個，但保留原本的換行（你已經按行讀了）
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def is_disallowed_bullet(line: str) -> bool:
    return any(p.match(line) for p in DISALLOW_BULLETS)

def should_soft_stop(line: str) -> bool:
    # 這些都是「結尾訊號」，只結束當前段，繼續掃描文件
    if STOP_HEAD.match(line):
        return True
    if is_disallowed_bullet(line):
        return True
    # 客套句或結語也視為結尾
    if re.search(r'(請.*?(查照|核示|覆|辦理|配合))', line):
        return True
    return False

def tail_after_provide(line: str) -> str:
    """
    取出『提供』後的同一行尾巴（不一定有冒號），作為起始內容。
    例如：'敬請提供下列資料：A、B' → 'A、B'
         '請提供 A 與 B' → 'A 與 B'
    """
    if '提供' not in line:
        return ''
    # 切到「提供」之後
    post = line.split('提供', 1)[-1]
    # 去掉常見連接詞/提示詞
    post = re.sub(r'^(如下|下列|如次|資料|清單)[:：]?', '', post).lstrip(' :：、，,；;')
    return post.strip()

def extract_hencha_from_txt_lines(lines: List[str]) -> Dict[str, Optional[str]]:
    # 前處理
    lines = [normalize_text(l) for l in lines if l and l.strip()]
    n = len(lines)
    results: List[Dict] = []

    i = 0
    while i < n:
        line = lines[i]
        if '提供' in line and TRIGGER.search(line):
            chunk: List[str] = []
            # 先吃同行「提供」後的尾巴（若有）
            post = tail_after_provide(line)
            if post:
                chunk.append(post)

            j = i + 1
            while j < n:
                cur = lines[j]

                # 允許的括號式條列 → 直接續收
                if ALLOW_BULLET.match(cur):
                    chunk.append(cur)
                    j += 1
                    continue

                # 結尾訊號（soft stop）
                if should_soft_stop(cur):
                    # 若已經有內容，結束當前段；若還沒有內容，放棄這次觸發
                    break

                # 自然續行規則：上一行以冒號/頓號/逗號/分號結尾，或本行夠長且不像標題
                prev = lines[j-1] if j-1 >= 0 else ''
                if re.search(r'[,:;、：，；]$', prev) or (len(cur) >= 8 and not STOP_HEAD.match(cur)):
                    # 但如果是不允許的條列（例如「一、」「1.」），則視為結尾，不再續收
                    if is_disallowed_bullet(cur):
                        break
                    chunk.append(cur)
                    j += 1
                    continue

                # 其他情況 → 不續收，結束當前段
                break

            # 只在有實質內容時才記錄；若第一個遇到的就是結尾訊號，直接略過本次觸發
            if chunk:
                results.append({
                    'start_line': i,
                    'end_line': j-1,
                    'value': '\n'.join(chunk).strip()
                })

            # 無論有沒有內容，都**不中止整體掃描**；繼續從 j 繼續掃（避免卡住）
            i = j
            continue

        i += 1

    if not results:
        return {'value': None, 'alternatives': []}

    # 你也可以在這裡做排序與信心打分；暫時回第一個
    return {
        'value': results[0]['value'],
        'alternatives': results[1:3]
    }
