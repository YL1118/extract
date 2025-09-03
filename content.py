import re
from typing import List, Dict, Optional

TRIGGER = re.compile(r'(?:惠請|敬請)?(?:.*?)(?:請)?(?:.*?)(提供)(?:.*?(如下|下列|如次|資料|清單))?')
STOP_HEAD = re.compile(r'^(主旨|說明|理由|辦法|注意事項|附件|抄送|結語|此致|敬請|承辦|署名)[:：]?\s*$')

# 允許的 (一)(二)…
ALLOW_BULLET = re.compile(r'^\s*[（(][一二三四五六七八九十]+[）)]\s*')
# 不允許的條列（當結尾訊號用）
DISALLOW_BULLETS = [
    re.compile(r'^\s*[一二三四五六七八九十]+[、]\s*'),
    re.compile(r'^\s*\d+[\.、)]\s*'),
    re.compile(r'^\s*[•●○\-]\s+'),
]

def normalize_text(s: str) -> str:
    repl = {
        '：':':','﹕':':','∶':':','　':' ',
        '提 供':'提供','拖供':'提供','體供':'提供',
        '下 列':'下列','成列':'下列','列下':'下列',
    }
    for k,v in repl.items():
        s = s.replace(k,v)
    return re.sub(r'\s+', ' ', s).strip()

def is_disallowed_bullet(line: str) -> bool:
    return any(p.match(line) for p in DISALLOW_BULLETS)

def should_soft_stop(line: str) -> bool:
    if STOP_HEAD.match(line): return True
    if is_disallowed_bullet(line): return True
    if re.search(r'(請.*?(查照|核示|覆|辦理|配合))', line):
        return True
    return False

def tail_after_provide(line: str) -> str:
    if '提供' not in line: return ''
    post = line.split('提供', 1)[-1]
    post = re.sub(r'^(如下|下列|如次|資料|清單)[:：]?', '', post).lstrip(' :：、，,；;')
    return post.strip()

def extract_hencha_from_txt_lines(lines: List[str]) -> Dict[str, Optional[str]]:
    lines = [normalize_text(l) for l in lines if l and l.strip()]
    n = len(lines)
    results: List[Dict] = []
    i = 0

    while i < n:
        line = lines[i]
        if '提供' in line and TRIGGER.search(line):
            chunk: List[str] = []
            post = tail_after_provide(line)
            if post: chunk.append(post)

            j = i + 1
            while j < n:
                cur = lines[j]
                if ALLOW_BULLET.match(cur):
                    chunk.append(cur); j += 1; continue
                if should_soft_stop(cur):
                    break
                prev = lines[j-1] if j-1 >= 0 else ''
                if re.search(r'[,:;、：，；]$', prev) or (len(cur) >= 8 and not STOP_HEAD.match(cur)):
                    if is_disallowed_bullet(cur): break
                    chunk.append(cur); j += 1; continue
                break

            if chunk:
                results.append({
                    'start_line': i,
                    'end_line': j-1,
                    'value': '\n'.join(chunk).strip()
                })
            i = j
            continue
        i += 1

    if not results:
        return {'value': None, 'alternatives': []}
    return {'value': results[0]['value'], 'alternatives': [r['value'] for r in results[1:3]]}
