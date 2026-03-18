from __future__ import annotations

import re


SYNONYMS = {
    "查询": ["获取", "查看", "搜索"],
    "获取": ["查询", "查看"],
    "修改": ["更新", "编辑"],
    "更新": ["修改", "编辑"],
    "用户id": ["userid", "uid", "用户编号"],
    "管理员": ["admin", "管理用户"],
    "日志": ["记录", "log"],
}


def normalize_query_terms(text: str) -> list[str]:
    return dedupe_terms(expand_terms(tokenize(text)))


def tokenize(text: str) -> list[str]:
    normalized = _normalize_text(text)
    tokens: list[str] = []
    for chunk in normalized.split():
        if re.search(r"[\u4e00-\u9fff]", chunk):
            tokens.extend(_han_ngrams(chunk))
            tokens.append(chunk)
        else:
            tokens.append(chunk)
    return [item for item in tokens if item]


def expand_terms(terms: list[str]) -> list[str]:
    expanded = list(terms)
    for term in terms:
        expanded.extend(SYNONYMS.get(term, []))
    return expanded


def dedupe_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        value = term.strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_text_terms(*values: str) -> list[str]:
    tokens: list[str] = []
    for value in values:
        tokens.extend(normalize_query_terms(value))
    return dedupe_terms(tokens)


def _normalize_text(text: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    value = value.replace("/", " ").replace("_", " ").replace("-", " ")
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def _han_ngrams(text: str) -> list[str]:
    if len(text) < 2:
        return [text]
    grams: list[str] = []
    max_len = min(3, len(text))
    for size in range(2, max_len + 1):
        for index in range(0, len(text) - size + 1):
            grams.append(text[index : index + size])
    return grams
