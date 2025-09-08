# -*- coding: utf-8 -*-
"""
body_extractor.py
-----------------
從 OCR 文字抽取臺灣制式公文欄位，並重點擷取「正文 / 內文」。

使用方式：
    from body_extractor import extract_fields_and_body

    result = extract_fields_and_body(raw_text)
    print(result["subject"])
    print(result["body"])

介面：
    extract_fields_and_body(
        text: str,
        field_aliases: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, Any]

回傳：
    {
      "subject": str,
      "body": str,
      "attachment": str,
      "meta": {
         "recipient": str, "doc_no": str, "date": str,
         "priority": str, "security": str
      }
    }
"""
from __future__ import annotations

import re
from typing import Dict, Tuple, List, Optional, Any

# -------- 1) 欄位別名與容錯正規化 --------

DEFAULT_FIELD_ALIASES: Dict[str, List[str]] = {
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

def _normalize_text(raw: str) -> str:
    text = raw
    for a, b in CANONICAL_REPLACEMENTS:
        text = text.replace(a, b)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    cleaned = []
    for ln in lines:
        s = ln.strip()
        # 橫線/頁碼/分隔等雜訊
        if re.fullmatch(r"-{3,}|_{3,}|=+|~+|\d+/\d+|第\d+頁", s):
            continue
        # 行首序號雜訊（OCR 常見）
        s = re.sub(r"^\s*\(?\d{1,3}\)?\s+", "", s)
        cleaned.append(s)
    return "\n".join(cleaned)

def _build_field_regex(field_aliases: Dict[str, List[str]]) -> re.Pattern:
    names: List[str] = []
    for _, alias in field_aliases.items():
        names.extend(alias)
    names = sorted(set(names), key=lambda x: -len(x))
    pattern = r"^(?P<field>(" + "|".join(map(re.escape, names)) + r"))\s*:?\s*(?P<after>.*)$"
    return re.compile(pattern, flags=re.MULTILINE)

# -------- 2) 基礎段落切分與對應 --------

def _split_sections(text: str, field_pattern: re.Pattern) -> Dict[str, str]:
    matches = list(field_pattern.finditer(text))
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

def _canonicalize_keys(sections_raw: Dict[str, str],
                       field_aliases: Dict[str, List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for canon, aliases in field_aliases.items():
        for a in aliases:
            if a in sections_raw and sections_raw[a].strip():
                out[canon] = sections_raw[a].strip()
                break
    return out

def _span_of_field(field_cn: str, text: str, field_pattern: re.Pattern) -> Optional[Tuple[int, int]]:
    pat = re.compile(r"^" + re.escape(field_cn) + r"\s*:?\s*(.*)$", flags=re.MULTILINE)
    m = pat.search(text)
    if not m:
        return None
    start = m.end()
    nxt = field_pattern.search(text, pos=start)
    end = nxt.start() if nxt else len(text)
    return (start, end)

def _middle_block(text: str) -> str:
    n = len(text)
    if n == 0:
        return ""
    return text[int(n * 0.2): int(n * 0.8)]

# -------- 3) 正文（body）啟發式 --------

def _heuristic_body(text: str,
                    sections_raw: Dict[str, str],
                    sections: Dict[str, str],
                    field_aliases: Dict[str, List[str]],
                    field_pattern: re.Pattern) -> str:
    # 3.1 若已抽到 body 類欄位，直接用
    if "body" in sections and sections["body"].strip():
        return sections["body"].strip()

    # 3.2 主旨之後、附件/副本/聯絡之前的內容
    tail_markers = field_aliases.get("attachment", []) + \
                   field_aliases.get("cc", []) + \
                   field_aliases.get("contact", [])

    subject_aliases = field_aliases.get("subject", ["主旨"])
    subject_span = None
    for sub in subject_aliases:
        subject_span = _span_of_field(sub, text, field_pattern)
        if subject_span:
            break

    if subject_span:
        start = subject_span[1]
        tail_positions = []
        for t in tail_markers:
            sp = _span_of_field(t, text, field_pattern)
            if sp and sp[0] > start:
                tail_positions.append(sp[0])
        end = min(tail_positions) if tail_positions else len(text)
        body = text[start:end].strip()
        body = re.sub(field_pattern, "", body).strip()
        if body:
            return body

    # 3.3 條列(一)(二)…作為正文開頭
    m = re.search(r"^[（(]?(一|二|三|四|五|六|七|八|九|十)[)）]?[、.．]", text, flags=re.MULTILINE)
    if m:
        return text[m.start():].strip()

    # 3.4 退而求其次：取中段
    return _middle_block(text).strip()

# -------- 4) 對外主函式 --------

def extract_fields_and_body(
    text: str,
    *,
    field_aliases: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    """
    從原始 OCR 文字抽取主旨/正文與常見欄位。

    Args:
        text: 原始字串（建議傳入 OCR 原文，不含檔案 I/O）
        field_aliases: 自訂欄位別名（不傳則用 DEFAULT_FIELD_ALIASES）

    Returns:
        結構化 dict（見檔頭說明）
    """
    aliases = field_aliases or DEFAULT_FIELD_ALIASES
    norm = _normalize_text(text)
    field_pattern = _build_field_regex(aliases)

    sections_raw = _split_sections(norm, field_pattern)
    sections = _canonicalize_keys(sections_raw, aliases)
    body = _heuristic_body(norm, sections_raw, sections, aliases, field_pattern)

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

__all__ = ["extract_fields_and_body", "DEFAULT_FIELD_ALIASES"]
