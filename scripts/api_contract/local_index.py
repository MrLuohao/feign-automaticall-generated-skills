from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import OperationSearchDoc
from .text_normalizer import normalize_query_terms


@dataclass
class RoutedService:
    service: str
    score: float


def route_services(cache_dir: Path, query: str, preferred_service: str | None = None) -> list[RoutedService]:
    terms = normalize_query_terms(query)
    connection = sqlite3.connect(cache_dir / "router.sqlite")
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT * FROM services").fetchall()
    finally:
        connection.close()
    ranked: list[RoutedService] = []
    for row in rows:
        score = 0.0
        keywords = json.loads(row["keywords_json"])
        haystacks = [
            row["service"],
            row["domain"],
            row["owner_name"],
            row["context_summary"],
            *keywords,
        ]
        if preferred_service and row["service"] == preferred_service:
            score += 10000
        for term in terms:
            if any(term in (entry or "").lower() for entry in haystacks):
                score += 1
        if score > 0:
            ranked.append(RoutedService(service=row["service"], score=score))
    ranked.sort(key=lambda item: (-item.score, item.service))
    return ranked[:8]


def search_service_operations(cache_dir: Path, service: str, query: str) -> list[tuple[float, OperationSearchDoc]]:
    terms = normalize_query_terms(query)
    shard_path = cache_dir / "shards" / f"{service}.sqlite"
    connection = sqlite3.connect(shard_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT * FROM operations").fetchall()
    finally:
        connection.close()
    scored: list[tuple[float, OperationSearchDoc]] = []
    for row in rows:
        doc = OperationSearchDoc(
            operation_id=row["operation_id"],
            service=row["service"],
            controller=row["controller"],
            method_name=row["method_name"],
            http_method=row["http_method"],
            full_path=row["full_path"],
            summary=row["summary"],
            description=row["description"],
            aliases=json.loads(row["aliases_json"]),
            tags=json.loads(row["tags_json"]),
            body_type=row["body_type"],
            response_data_type=row["response_data_type"],
            key_params=json.loads(row["key_params_json"]),
            spec_path=row["spec_path"],
        )
        context_summary = row["context_summary"]
        score = _score_doc(doc, context_summary, terms)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: (-item[0], item[1].operation_id))
    return scored[:50]


def _score_doc(doc: OperationSearchDoc, context_summary: str, terms: list[str]) -> float:
    haystacks = {
        "summary": [doc.summary],
        "description": [doc.description],
        "aliases": doc.aliases,
        "tags": doc.tags,
        "path": [doc.full_path],
        "method": [doc.method_name],
        "types": [doc.body_type or "", doc.response_data_type],
        "params": doc.key_params,
        "context": [context_summary],
    }
    score = 0.0
    score += _count_hits(terms, haystacks["summary"]) * 5
    score += _count_hits(terms, haystacks["aliases"]) * 4
    score += _count_hits(terms, haystacks["description"]) * 3
    score += _count_hits(terms, haystacks["context"]) * 3
    score += _count_hits(terms, haystacks["tags"]) * 2
    score += _count_hits(terms, haystacks["path"]) * 2
    score += _count_hits(terms, haystacks["method"]) * 1.5
    score += _count_hits(terms, haystacks["types"]) * 1.5
    score += _count_hits(terms, haystacks["params"]) * 1
    return score


def _count_hits(terms: list[str], haystacks: list[str]) -> int:
    normalized = [value.lower() for value in haystacks if value]
    return sum(1 for term in terms if any(term in entry for entry in normalized))

