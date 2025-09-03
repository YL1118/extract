#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批次抽取『扣押/效力』相關句子（句界=前一個句號到下一個句號）
— 支援資料夾多個 .txt 檔，輸出 JSON/JSONL

要抓的關鍵詞（任一出現即抽該句）：
- 扣押範圍不含
- 本命令之效力
- 毋庸扣押 / 無庸扣押
- 毋庸執行扣押 / 無庸執行扣押
- 非屬執行命令扣押範圍

句界定義：
- 由『上一個句號』到『下一個句號』（含右邊句號）。
- 句號集合預設為：『。』『．』『｡』，可透過 --delims 覆寫。
- 若左/右句號不存在，則從文首/到文末。

用法：
  python extract_scope_sentence_batch.py --input-dir ./cases --output out.jsonl --verbose
  python extract_scope_sentence_batch.py --input single.txt --output out.json
  python extract_scope_sentence_batch.py --demo --verbose

備註：
- 預設輸出『句子本身』與『命中關鍵詞』、索引位置。
- 若同一句內命中多個關鍵詞，會合併成一筆句子，matches 列出所有關鍵詞。
"""
import re, json, argparse, sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

# ------------------ 可調參數 ------------------
# 關鍵詞（正則）。包含『毋/無』的變體。
KEYWORD_REGEX = re.compile(
    r"(扣押範圍不含|本命令之效力|(?:毋|無)庸執行扣押|(?:毋|無)庸扣押|非屬執行命令扣押範圍)"
)

# 預設句號字元
DEFAULT_DELIMS = "。．｡"

# ------------------ 工具函式 ------------------

def read_text_file(path: Path, encoding_hint: str = "utf-8") -> str:
    """讀取文字檔；嘗試多種編碼。"""
    encodings = [encoding_hint, "utf-8", "cp950", "big5"] if encoding_hint else ["utf-8", "cp950", "big5"]
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                return f.read()
        except Exception as e:
            last_err = e
            continue
    raise last_err or IOError(f"Unable to read {path}")


def normalize_text(s: str) -> str:
    """輕量正規化：全/半形標點、空白壓縮（保留換行）。"""
    repl = {
        "﹒": "．",
        "．": "．",  # 全形句點保留
        "　": " ",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    # 不移除換行（有些檔案以換行排版）
    return s


def find_sentence_bounds(text: str, match_span: Tuple[int, int], delims: str) -> Tuple[int, int]:
    """根據句號集合，回傳(句子start, 句子end_inclusive)。
    - start 是『上一個句號』的下一個位置（若無則 0）。
    - end 是『下一個句號』的位置（若無則 len(text)-1）。
    """
    start_idx, end_idx = match_span
    # 找左邊最近的句號
    left_positions = [text.rfind(d, 0, start_idx) for d in delims]
    left = max([p for p in left_positions if p != -1], default=-1)
    # 找右邊最近的句號
    right_candidates = [text.find(d, end_idx) for d in delims]
    right_candidates = [p for p in right_candidates if p != -1]
    right = min(right_candidates) if right_candidates else -1

    sent_start = left + 1 if left != -1 else 0
    sent_end = right if right != -1 else len(text) - 1
    return sent_start, sent_end


def extract_scope_sentences(text: str, delims: str = DEFAULT_DELIMS, verbose: bool = False) -> List[Dict[str, Any]]:
    text = normalize_text(text)
    results: List[Dict[str, Any]] = []

    # 先找到所有關鍵詞命中位置
    matches = list(KEYWORD_REGEX.finditer(text))
    if verbose:
        print(f"[info] keyword hits: {len(matches)}", file=sys.stderr)

    # 將屬於同一句的多個命中合併
    sentence_index_map: Dict[Tuple[int, int], Dict[str, Any]] = {}

    for m in matches:
        sent_start, sent_end = find_sentence_bounds(text, m.span(), delims)
        key = (sent_start, sent_end)
        segment = text[sent_start:sent_end + 1]  # 含右邊句號
        kw = m.group(0)
        if key not in sentence_index_map:
            sentence_index_map[key] = {
                "sentence": segment.strip(),
                "start": sent_start,
                "end": sent_end,
                "matches": [kw],
                "match_spans": [list(m.span())],
            }
        else:
            sentence_index_map[key]["matches"].append(kw)
            sentence_index_map[key]["match_spans"].append(list(m.span()))

        if verbose:
            left_ctx = max(0, m.start() - 10)
            right_ctx = min(len(text), m.end() + 10)
            ctx = text[left_ctx:right_ctx].replace("\n", "\\n")
            print(f"  - hit '{kw}' at {m.start()}..{m.end()} | ctx=...{ctx}...", file=sys.stderr)

    # 依文內位置排序輸出
    for key in sorted(sentence_index_map.keys()):
        results.append(sentence_index_map[key])

    return results


# ------------------ CLI ------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", type=str, help="單一 txt 檔案")
    ap.add_argument("--input-dir", "-d", type=str, help="資料夾路徑（掃描多個 .txt）")
    ap.add_argument("--pattern", "-p", type=str, default="*.txt", help="glob 樣式，預設 *.txt；可用 **/*.txt 遞迴")
    ap.add_argument("--delims", type=str, default=DEFAULT_DELIMS, help="句號集合，例如 '。．.｡' ")
    ap.add_argument("--output", "-o", type=str, help="輸出路徑（.jsonl 或 .json）若省略則印到 stdout")
    ap.add_argument("--encoding", default="utf-8", help="讀檔編碼提示，預設 utf-8，可試 big5/cp950")
    ap.add_argument("--demo", action="store_true", help="跑內建示例")
    ap.add_argument("--verbose", action="store_true", help="印出調試資訊到 stderr")
    args = ap.parse_args()

    records: List[Dict[str, Any]] = []

    if args.demo:
        demo = (
            "本命令之效力及相關事項如下.
"  # 注意：這裡刻意放入半形點號 . ，預設不視為句號
            "茲因情事變更，非屬執行命令扣押範圍。故本案毋庸執行扣押。
"
            "另：如有異議，請於 10 日內陳報。"
        )
            "本命令之效力及相關事項如下。\n"
            "茲因情事變更，非屬執行命令扣押範圍。故本案毋庸執行扣押。\n"
            "另：如有異議，請於 10 日內陳報。"
        )
        res = extract_scope_sentences(demo, delims=args.delims, verbose=args.verbose)
        records.append({"source": "DEMO", "sentences": res})
    else:
        paths: List[Path] = []
        if args.input:
            paths = [Path(args.input)]
        elif args.input_dir:
            root = Path(args.input_dir)
            # 允許 ** 遞迴
            if "**" in args.pattern:
                paths = sorted(root.glob(args.pattern))
            else:
                # 使用 rglob 以支援遞迴/非遞迴皆可
                paths = sorted(root.rglob(args.pattern))
        else:
            print("請提供 --input 或 --input-dir", file=sys.stderr)
            sys.exit(2)

        if not paths:
            print("找不到任何 .txt 檔案", file=sys.stderr)
            sys.exit(1)

        for p in paths:
            try:
                text = read_text_file(p, encoding_hint=args.encoding)
                res = extract_scope_sentences(text, delims=args.delims, verbose=args.verbose)
                records.append({"source": str(p), "sentences": res})
            except Exception as e:
                records.append({"source": str(p), "error": str(e), "sentences": []})
                if args.verbose:
                    print(f"[error] {p}: {e}", file=sys.stderr)

    # ---------- 輸出 ----------
    if not args.output:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.suffix.lower() == ".jsonl":
        with open(out, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"已輸出 {len(records)} 筆到 {out} (JSONL)")
    else:
        with open(out, "w", encoding="utf-8") as f:
            f.write(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        print(f"已輸出 {len(records)} 筆到 {out} (JSON)")

if __name__ == "__main__":
    main()
