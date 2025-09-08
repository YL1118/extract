# -*- coding: utf-8 -*-
"""
body_extractor_compat.py
------------------------
把原始 extract_body.py 的正文抽取邏輯「原封不動」抽出成可重用函式。
目標：輸出與原程式一致的結果，不做任何「更聰明」的變更。

介面：
    extract_fields_and_body(text: str) -> Dict[str, Any]
    extract_body(text: str) -> str
"""

import re
from typing import Dict, Tuple, List, Optional, Any

# ===== 1) 欄位別名與容錯正規化（與原版保持一致） =====

FIELD_ALIASES = {
    "recipient":  ["受文者", "受文機關", "受文單位"],
    "doc_no":     ["發文字號", "文號", "案號", "來文字號"],
    "date":       ["發文日期", "日期", "中華民國"],
    "priority":   ["速別"],
    "security":   ["密等"],
    "subject":    ["主旨"],
    "body":       ["說明", "內文", "正文", "本文"],
    "attachment": ["附件"],
    "cc":         ["副本", "正本", "抄送"],
    "contact":    ["承辦", "承辦人", "聯絡", "聯絡電話", "連絡電話"],
}

CANONICAL_REPLACEMENTS = [
    ("王旨", "主旨"), ("圭旨", "主旨"),
    ("說朋", "說明"), ("說眀", "說明"),
    ("：", ":"), ("﹕", ":"), ("︰", ":"), ("：", ":"),
    ("　", " "), ("﻿", ""), ("\ufeff", ""),
    ("－", "-"), ("—", "-"), ("–", "-"),
]

def normalize_text(raw: str) -> str:
    text = raw
    for a, b in CANONICAL_REPLACEMENTS:
        text = text.replace(a, b)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    cleaned = []
    for ln in lines:
        s = ln.strip()
        if re.fullmatch(r"-{3,}|_{3,}|=+|~+|\d+/\d+|第\d+頁", s):
            continue
        s = re.sub(r"^\s*\(?\d{1,3}\)?\s+", "", s)
        cleaned.append(s)
    return "\n".join(cleaned)

def build_field_regex() -> re.Pattern:
    names: List[str] = []
    for _, alias in FIELD_ALIASES.items():
        names.extend(alias)
    names = sorted(set(names), key=lambda x: -len(x))
    pattern = r"^(?P<field>(" + "|".join(map(re.escape, names)) + r"))\s*:?\s*(?P<after>.*)$"
    return re.compile(pattern, flags=re.MULTILINE)

FIELD_PATTERN = build_field_regex()

# ===== 2) 與原版一致的切段/對應 =====

def split_sections(text: str) -> Dict[str, str]:
    matches = list(FIELD_PATTERN.finditer(text))
    if not matches:
        return {}
    sections: Dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        field_name = m.group("field")
        after = m.group("after").strip()
        block = (after + "\n" + text[start:end]).strip() if after else text[start:end].strip()
        block = block.strip()
        if field_name in sections and sections[field_name]:
            sections[field_name] = (sections[field_name] + "\n" + block).strip()
        else:
            sections[field_name] = block
    return sections

def canonicalize_keys(sections: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for canon, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if a in sections and sections[a].strip():
                out[canon] = sections[a].strip()
                break
    return out

def _span_of_field(field_cn: str, text: str) -> Optional[Tuple[int, int]]:
    pat = re.compile(r"^" + re.escape(field_cn) + r"\s*:?\s*(.*)$", flags=re.MULTILINE)
    m = pat.search(text)
    if not m:
        return None
    start = m.end()
    nxt = FIELD_PATTERN.search(text, pos=start)
    end = nxt.start() if nxt else len(text)
    return (start, end)

def _middle_block(text: str) -> str:
    n = len(text)
    if n == 0:
        return ""
    return text[int(n * 0.2): int(n * 0.8)]

# ===== 3) 與原版一致的正文啟發式 =====

def heuristic_body(text: str, sections_raw: Dict[str, str], sections: Dict[str, str]) -> str:
    if "body" in sections and sections["body"].strip():
        return sections["body"].strip()

    tail_markers = FIELD_ALIASES["attachment"] + FIELD_ALIASES["cc"] + FIELD_ALIASES["contact"]

    # 注意：原版只用「主旨」這個字樣來抓 span，不嘗試其他別名
    subject_span = _span_of_field("主旨", text)
    if subject_span:
        start = subject_span[1]
        tail_positions = []
        for t in tail_markers:
            sp = _span_of_field(t, text)
            if sp and sp[0] > start:
                tail_positions.append(sp[0])
        end = min(tail_positions) if tail_positions else len(text)
        body = text[start:end].strip()
        body = re.sub(FIELD_PATTERN, "", body).strip()
        if body:
            return body

    m = re.search(r"^[（(]?(一|二|三|四|五|六|七|八|九|十)[)）]?[、.．]", text, flags=re.MULTILINE)
    if m:
        return text[m.start():].strip()

    return _middle_block(text).strip()

# ===== 4) 對外 API =====

def extract_fields_and_body(text: str) -> Dict[str, Any]:
    norm = normalize_text(text)
    sections_raw = split_sections(norm)
    sections = canonicalize_keys(sections_raw)
    body = heuristic_body(norm, sections_raw, sections)

    return {
        "subject": sections.get("subject", ""),
        "body": body,
        "attachment": sections.get("attachment", ""),
        "meta": {
            "recipient": sections.get("recipient", ""),
            "doc_no": sections.get("doc_no", ""),
            "date": sections.get("date", ""),
            "priority": sections.get("priority", ""),
            "security": sections.get("security", ""),
        }
    }

def extract_body(text: str) -> str:
    return extract_fields_and_body(text).get("body", "")
