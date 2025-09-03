#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抽取「函查內容」（以「提供」為觸發）的極簡可執行腳本
用法：
  python extract_hencha.py --input gongwen.txt
  python extract_hencha.py --input gongwen.txt --output result.json --verbose
  python extract_hencha.py --demo --verbose
"""
import re, json, argparse, sys
from typing import List, Dict, Optional

# ---------- 規則設定 ----------
TRIGGER = re.compile(r'(?:惠請|敬請)?(?:.*?)(?:請)?(?:.*?)(提供)(?:.*?(如下|下列|如次|資料|清單))?')
STOP_HEAD = re.compile(r'^(主旨|說明|理由|辦法|注意事項|附件|抄送|結語|此致|敬請|承辦|署名)[:：]?\s*$')

# 允許續收的條列：(一)(二)(三)（含全形括號）
ALLOW_BULLET = re.compile(r'^\s*[（(][一二三四五六七八九十]+[）)]\s*')
# 當作「結尾訊號」的條列：一、二、 / 1. / 1) / 圓點等
DISALLOW_BULLETS = [
    re.compile(r'^\s*[一二三四五六七八九十]+[、]\s*'),
    re.compile(r'^\s*\d+[\.、)]\s*'),
    re.compile(r'^\s*[•●○\-]\s+'),
]

NEGATION = re.compile(r'(不得提供|無需提供|毋需提供|不需提供)')

def normalize_text(s: str) -> str:
    """單行正規化：全半形、常見 OCR 混淆、空白壓縮"""
    repl = {
        '：':':','﹕':':','∶':':','　':' ',
        '提 供':'提供','拖供':'提供','體供':'提供',
        '下 列':'下列','成列':'下列','列下':'下列',
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    # 保留行結構，所以只壓縮行內空白
    s = re.sub(r'[ \t]+', ' ', s).strip()
    return s

def is_disallowed_bullet(line: str) -> bool:
    return any(p.match(line) for p in DISALLOW_BULLETS)

def should_soft_stop(line: str) -> bool:
    if STOP_HEAD.match(line): return True
    if is_disallowed_bullet(line): return True
    if re.search(r'(請.*?(查照|核示|覆|辦理|配合))', line):
        return True
    return False

def tail_after_provide(line: str) -> str:
    """取出『提供』後的同行尾巴（不一定有冒號）"""
    if '提供' not in line: return ''
    post = line.split('提供', 1)[-1]
    post = re.sub(r'^(如下|下列|如次|資料|清單)[:：]?', '', post).lstrip(' :：、，,；;')
    return post.strip()

def extract_hencha_from_lines(lines: List[str], verbose=False) -> Dict[str, Optional[str]]:
    lines = [normalize_text(l.rstrip("\r\n")) for l in lines if l and l.strip()]
    n = len(lines)
    results: List[Dict] = []
    i = 0

    while i < n:
        line = lines[i]
        if verbose:
            print(f"[scan] {i:04d}: {line}", file=sys.stderr)
        if '提供' in line and TRIGGER.search(line) and not NEGATION.search(line):
            if verbose:
                print(f"  -> trigger at line {i}", file=sys.stderr)
            chunk: List[str] = []
            post = tail_after_provide(line)
            if post:
                chunk.append(post)
                if verbose:
                    print(f"     + inline tail: {post}", file=sys.stderr)

            j = i + 1
            while j < n:
                cur = lines[j]

                # 允許的括號條列 → 續收
                if ALLOW_BULLET.match(cur):
                    chunk.append(cur)
                    if verbose:
                        print(f"     + allow bullet {j}: {cur}", file=sys.stderr)
                    j += 1
                    continue

                # 結尾訊號（soft stop）
                if should_soft_stop(cur):
                    if verbose:
                        why = "STOP_HEAD" if STOP_HEAD.match(cur) else "DISALLOW_BULLET/closing"
                        print(f"     x soft stop at {j} ({why}): {cur}", file=sys.stderr)
                    break

                prev = lines[j-1] if j-1 >= 0 else ''
                # 自然續行：上一行結尾是逗號/冒號/頓號/分號；或本行夠長且不像標題
                if re.search(r'[,:;、：，；]$', prev) or (len(cur) >= 8 and not STOP_HEAD.match(cur)):
                    if is_disallowed_bullet(cur):
                        if verbose:
                            print(f"     x end by disallowed bullet at {j}: {cur}", file=sys.stderr)
                        break
                    chunk.append(cur)
                    if verbose:
                        print(f"     + continue {j}: {cur}", file=sys.stderr)
                    j += 1
                    continue

                # 其他情況：結束本段
                if verbose:
                    print(f"     x end segment at {j}: {cur}", file=sys.stderr)
                break

            if chunk:
                seg = {
                    'start_line': i,
                    'end_line': j-1,
                    'value': '\n'.join(chunk).strip()
                }
                results.append(seg)
                if verbose:
                    print(f"  => segment [{seg['start_line']}..{seg['end_line']}], len={len(seg['value'])}", file=sys.stderr)
            # 繼續掃描，不中斷整體
            i = j
            continue
        i += 1

    if not results:
        return {'value': None, 'alternatives': [], 'segments': []}

    # 簡單：取第一段為主，其他做備選
    return {
        'value': results[0]['value'],
        'alternatives': [r['value'] for r in results[1:3]],
        'segments': results  # 全部段落（含行號），方便你回看
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", help="輸入的 txt 檔路徑（與 --demo 擇一）")
    ap.add_argument("--output", "-o", help="輸出的 JSON 檔路徑（若不給則印到 stdout）")
    ap.add_argument("--encoding", default="utf-8", help="讀檔編碼，預設 utf-8，可試 big5 或 cp950")
    ap.add_argument("--demo", action="store_true", help="使用內建示例文本跑一遍")
    ap.add_argument("--verbose", action="store_true", help="印出偵錯過程到 stderr")
    args = ap.parse_args()

    if args.demo:
        demo_text = """
主旨：函請提供下列資料
說明：
一、為辦理相關業務，敬請貴單位提供如下：
（一）近三年度財務報表影本
（二）內控稽核報告
注意事項：
1. 請於9/20前回覆。
        """.strip("\n")
        lines = demo_text.splitlines()
    else:
        if not args.input:
            print("請提供 --input 檔案或使用 --demo", file=sys.stderr)
            sys.exit(2)
        try:
            with open(args.input, "r", encoding=args.encoding, errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"讀檔失敗：{e}", file=sys.stderr)
            sys.exit(1)

    result = extract_hencha_from_lines(lines, verbose=args.verbose)
    out = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as g:
                g.write(out + "\n")
            print(f"已輸出到 {args.output}")
        except Exception as e:
            print(f"寫檔失敗：{e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(out)

if __name__ == "__main__":
    main()
