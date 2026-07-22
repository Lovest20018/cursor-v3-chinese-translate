# -*- coding: utf-8 -*-
"""词典解析、校验与运行时载荷构建。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .constants import RUNTIME_PROTECTED_EXACT_TEXTS


class DictionaryError(ValueError):
    """词典格式或内容错误。"""


@dataclass(frozen=True)
class DictionaryEntry:
    source: str
    translation: str
    line_number: int
    group: Optional[str] = None


@dataclass(frozen=True)
class DictionaryPayload:
    entries: Dict[str, str]
    normalized_entries: Dict[str, str]
    groups: Dict[str, List[str]]
    conflicts: Tuple[str, ...]
    duplicates: Tuple[str, ...]


def normalize_dictionary_key(text: str) -> str:
    """NFC + 折叠空白 + trim，大小写与标点敏感。"""
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    normalized = re.sub(r"\s+", " ", normalized, flags=re.UNICODE).strip()
    return normalized


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        inner = value[1:-1]
        # 支持常见转义
        try:
            return json.loads(quote + inner + quote)
        except Exception:
            return (
                inner.replace(r"\"", '"')
                .replace(r"\'", "'")
                .replace(r"\\", "\\")
            )
    return value


def parse_translation_entry(line: str, line_number: int) -> Tuple[str, str]:
    """解析单行 `source => translation`，支持引号内包含 => 或不规范嵌套引号。"""
    raw = line.strip()
    if not raw:
        raise DictionaryError(f"第 {line_number} 行为空")

    def find_separator_outside_quotes(text: str) -> int:
        in_quotes = False
        escape_next = False
        i = 0
        while i < len(text) - 1:
            char = text[i]
            if escape_next:
                escape_next = False
                i += 1
                continue
            if char == "\\":
                escape_next = True
                i += 1
                continue
            if char == '"':
                in_quotes = not in_quotes
                i += 1
                continue
            if not in_quotes and text[i : i + 2] == "=>":
                return i
            i += 1
        return -1

    separator_index = find_separator_outside_quotes(raw)
    if separator_index == -1:
        raise DictionaryError(f"第 {line_number} 行缺少 => 分隔符")

    source = _strip_quotes(raw[:separator_index].strip())
    translation = _strip_quotes(raw[separator_index + 2 :].strip())
    if not source or not translation:
        raise DictionaryError(f"第 {line_number} 行键或值为空")
    return source, translation


def parse_dictionary_text(text: str) -> DictionaryPayload:
    """解析完整词典文本，检测重复与冲突。"""
    entries: Dict[str, str] = {}
    normalized_map: Dict[str, str] = {}
    groups: Dict[str, List[str]] = {}
    conflicts: List[str] = []
    duplicates: List[str] = []
    current_group: Optional[str] = None
    seen_normalized: Dict[str, str] = {}

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("//"):
            # 分组注释：# [Group Name] 或 # Group Name
            group_match = re.match(r'^(?:#|//)\s*\[([^\]]+)\]\s*$', stripped)
            if group_match:
                current_group = group_match.group(1).strip()
                groups.setdefault(current_group, [])
            else:
                group_match = re.match(
                    r'^(?:#|//)\s*Group:\s*(.+)$', stripped, re.IGNORECASE
                )
                if group_match:
                    current_group = group_match.group(1).strip()
                    groups.setdefault(current_group, [])
            continue

        source, translation = parse_translation_entry(stripped, line_number)
        normalized = normalize_dictionary_key(source)
        if not normalized:
            raise DictionaryError(f"第 {line_number} 行归一化后键为空")

        if source in entries:
            if entries[source] == translation:
                duplicates.append(f"第 {line_number} 行重复键: {source!r}")
            else:
                conflicts.append(
                    f"第 {line_number} 行冲突键 {source!r}: "
                    f"{entries[source]!r} vs {translation!r}"
                )
            continue

        if normalized in seen_normalized and seen_normalized[normalized] != source:
            conflicts.append(
                f"第 {line_number} 行归一化后与 {seen_normalized[normalized]!r} "
                f"冲突: {source!r}"
            )
            continue

        if normalized in normalized_map and normalized_map[normalized] != translation:
            conflicts.append(
                f"第 {line_number} 行归一化键冲突 {normalized!r}: "
                f"{normalized_map[normalized]!r} vs {translation!r}"
            )
            continue

        entries[source] = translation
        normalized_map[normalized] = translation
        seen_normalized[normalized] = source
        if current_group:
            groups.setdefault(current_group, []).append(source)

    if conflicts or duplicates:
        details = "\n".join(conflicts + duplicates)
        raise DictionaryError(f"词典校验失败:\n{details}")

    return DictionaryPayload(
        entries=entries,
        normalized_entries=normalized_map,
        groups=groups,
        conflicts=tuple(conflicts),
        duplicates=tuple(duplicates),
    )


def load_dictionary_file(path: str) -> DictionaryPayload:
    with open(path, "r", encoding="utf-8") as handle:
        return parse_dictionary_text(handle.read())


def validate_dictionary_file(path: str) -> DictionaryPayload:
    return load_dictionary_file(path)


def build_runtime_dictionary(payload: DictionaryPayload) -> Dict[str, str]:
    """运行时字典：保留精确键。"""
    return dict(payload.entries)


def protected_exact_texts() -> Sequence[str]:
    return RUNTIME_PROTECTED_EXACT_TEXTS
