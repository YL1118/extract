#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批次抽取「函查內容」（以「提供」為觸發）— 支援資料夾多個 .txt 檔
- 會把「提供」兩字一併輸出（從觸發行第一個『提供』開始）
- 條列規則：
    * （一）（二）（三）… → 視為同段續收
    * 一、二、 / 1. 2. / 1) / • 等 → 視為本段『結尾訊號』（soft stop），不中斷整體掃描
- 段落標題（主旨/說明/附件/此致…） → 結尾訊號
- 可設定輸入資料夾、檔名過濾、輸入編碼；輸出為 JSONL（每檔一行）或單一 JSON

用法：
  python extract_hencha_batch.py --input-dir ./docs --output out.jsonl --verbose
  python extract_hencha_batch.py --input-dir ./docs --pattern "**/*.txt" --encoding utf-8 --output out.json
  python extract_hencha_batch.py --demo --verbose
"""
import re, json, argparse, sys, os
from pathlib import Path
from typing import List, Dict, Optional, Tuple

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

# ---------- 工具函式 ----------

def normalize_text(s: str) -> str:
    """單行正規化：全半形、常見 OCR 混淆、空白壓縮（保留換行結構）"""
    repl = {
        '：':':','﹕':':','∶':':','　':' ',
        '提 供':'提供','拖供':'提供','體供':'提供',
        '下 列':'下列','成列':'下列','列下':'下列',
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    # 僅壓縮行內空白
    s = re.sub(r'[ \t]+', ' ', s).strip()
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

def split_provide(line: str) -> Tuple[str, str]:
    """回傳 (包含『提供』起始的子字串, 該子字串之後的 tail)
    例如：'敬請提供下列資料：A、B' → ('提供下列資料：A、B', '下列資料：A、B')
          '請提供 A 與 B' → ('提供 A 與 B', 'A 與 B')
    若無『提供』→ ('', '')
    """
    if '提供' not in line:
        return '', ''
    idx = line.find('提供')
    sub = line[idx:]  # 從『提供』起
    # tail 移除提示詞後的實質內容
    tail = sub[len('提供'):]
    tail = re.sub(r'^(如下|下列|如次|資料|清單)[:：]?', '', tail).lstrip(' :：、，,；;')
    return sub.strip(), tail.strip()

# ---------- 核心抽取 ----------

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

            # 從『提供』開始納入輸出，並且把提供後的 tail 當作起始內容
            sub, tail = split_provide(line)
            if sub:
                # 1) 先把『提供…(含同行剩餘)』整段放進去（滿足「連同提供兩字一起輸出」）
                chunk.append(sub)
                if verbose:
                    print(f"     + include trigger line from 提供: {sub}", file=sys.stderr)
            # 2) 若要把 tail 再次加入可會重複，因為 sub 已含 tail；因此這裡不再額外 append tail

            j = i + 1
            while j < n:
                cur = lines[j]

                # 允許的括號條列 → 直接續收
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
                if re.search(r'[,,:;、：，；]$', prev) or (len(cur) >= 8 and not STOP_HEAD.match(cur)):
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
                    'value': '\n'.join(chunk).strip()  # 第一行已含『提供…』
                }
                results.append(seg)
                if verbose:
                    print(f"  => segment [{seg['start_line']}..{seg['end_line']}], len={len(seg['value'])}", file=sys.stderr)
            # 繼續掃描下一段（不中斷整體）
            i = j
            continue
        i += 1

    if not results:
        return {'value': None, 'alternatives': [], 'segments': []}

    return {
        'value': results[0]['value'],
        'alternatives': [r['value'] for r in results[1:3]],
        'segments': results
    }

# ---------- 檔案 I/O ----------

def read_text_file(path: Path, encoding_hint: str = 'utf-8') -> List[str]:
    encodings = [encoding_hint, 'utf-8', 'cp950', 'big5'] if encoding_hint else ['utf-8', 'cp950', 'big5']
    last_err = None
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc, errors='ignore') as f:
                return f.readlines()
        except Exception as e:
            last_err = e
            continue
    raise last_err or IOError(f"Unable to read {path}")

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-dir', '-d', type=str, help='輸入資料夾（掃描多個 .txt）')
    ap.add_argument('--pattern', '-p', type=str, default='*.txt', help='glob 過濾（預設 *.txt，可用 **/*.txt 遞迴）')
    ap.add_argument('--input', '-i', type=str, help='單一 txt 檔路徑（與 --input-dir 擇一）')
    ap.add_argument('--output', '-o', type=str, help='輸出路徑（.jsonl 或 .json 皆可）')
    ap.add_argument('--encoding', default='utf-8', help='讀檔編碼提示，預設 utf-8，可試 big5/cp950')
    ap.add_argument('--demo', action='store_true', help='跑內建示例')
    ap.add_argument('--verbose', action='store_true', help='偵錯輸出到 stderr')
    args = ap.parse_args()

    records: List[Dict] = []

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
        rec = extract_hencha_from_lines(lines, verbose=args.verbose)
        rec.update({'source': 'DEMO'})
        records.append(rec)
    else:
        paths: List[Path] = []
        if args.input:
            paths = [Path(args.input)]
        elif args.input_dir:
            root = Path(args.input_dir)
            # 支援 ** 遞迴
            paths = sorted(root.glob(args.pattern)) if '**' in args.pattern else sorted(root.rglob(args.pattern))
            # 若使用 glob() 非遞迴：改為 rglob 以支援 **
            if '**' in args.pattern:
                pass
            else:
                # 使用 rglob 以確保遞迴能力（pattern 不含 ** 也可）
                paths = sorted(root.rglob(args.pattern))
        else:
            print('請提供 --input 或 --input-dir', file=sys.stderr)
            sys.exit(2)

        if not paths:
            print('找不到任何符合的 txt 檔案', file=sys.stderr)
            sys.exit(1)

        for p in paths:
            try:
                lines = read_text_file(p, encoding_hint=args.encoding)
                rec = extract_hencha_from_lines(lines, verbose=args.verbose)
                rec.update({'source': str(p)})
                records.append(rec)
            except Exception as e:
                err = {'source': str(p), 'error': str(e), 'value': None, 'alternatives': [], 'segments': []}
                records.append(err)
                if args.verbose:
                    print(f'[error] {p}: {e}', file=sys.stderr)

    # ---------- 輸出 ----------
    if not args.output:
        # 預設印到 stdout（輸出 JSON 陣列）
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return

    out_path = Path(args.output)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    if out_path.suffix.lower() == '.jsonl':
        with open(out_path, 'w', encoding='utf-8') as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print(f'已輸出 {len(records)} 筆到 {out_path} (JSONL)')
    else:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
        print(f'已輸出 {len(records)} 筆到 {out_path} (JSON)')

if __name__ == '__main__':
    main()
