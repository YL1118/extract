import re

def normalize_text(s: str) -> str:
    repl = {
        '：':':','﹕':':','∶':':',
        '提 供':'提供','拖供':'提供','體供':'提供'
    }
    for k,v in repl.items():
        s = s.replace(k,v)
    return re.sub(r'\s+', ' ', s).strip()

def extract_hencha_from_txt(path: str):
    with open(path, encoding="utf-8") as f:
        lines = [normalize_text(l) for l in f if l.strip()]

    trigger = re.compile(r'(惠請|敬請|請)?(.*?)(提供)(如下|下列|如次|資料|清單)?')
    stop = re.compile(r'^(主旨|說明|附件|抄送|結語|此致|敬請|承辦|署名)[:：]?$')
    bullet = re.compile(r'^\s*(\(?[一二三四五六七八九十]+\)?|[0-9]+[\.、)]|[•●○\-])\s+')

    results = []
    for i, line in enumerate(lines):
        if "提供" in line and trigger.search(line):
            chunk = []
            # 同行冒號後
            if ":" in line:
                chunk.append(line.split(":",1)[-1].strip())
            # 向下延伸
            j = i+1
            while j < len(lines):
                if stop.match(lines[j]):
                    break
                if bullet.match(lines[j]) or chunk:
                    chunk.append(lines[j])
                    j += 1
                else:
                    break
            if chunk:
                results.append("\n".join(chunk).strip())

    return results[0] if results else None

# 使用方式
hencha = extract_hencha_from_txt("gongwen.txt")
print("函查內容：", hencha)
