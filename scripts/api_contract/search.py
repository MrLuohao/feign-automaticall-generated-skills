from __future__ import annotations

import re
import sys
from pathlib import Path

from .contract_store import ContractStore
from .models import OperationSearchDoc
from .text_normalizer import normalize_query_terms


def search_operation(store: ContractStore, query: str, consumer_repo: Path | None = None) -> tuple[str, str]:
    terms = normalize_query_terms(query)
    preferred_service = _detect_consumer_service(consumer_repo)
    global_index = store.load_global_index()
    services = _route_services(global_index, terms, preferred_service)[:3]
    if not services:
        raise RuntimeError(f"TERMINAL_NO_OPERATION_FOUND: No operation found for query: {query}")
    candidates: list[tuple[float, OperationSearchDoc]] = []
    for service_name in services:
        candidates.extend(_search_service(store, service_name, terms))
    if not candidates:
        raise RuntimeError(f"TERMINAL_NO_OPERATION_FOUND: No operation found for query: {query}")
    candidates.sort(key=lambda item: (-item[0], item[1].operation_id))
    top = candidates[:5]
    if len(top) == 1:
        return top[0][1].operation_id, top[0][1].controller
    if top[0][0] >= top[1][0] + 3:
        return top[0][1].operation_id, top[0][1].controller
    return _resolve_ambiguous(top)


def _route_services(global_index, terms: list[str], preferred_service: str | None) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for item in global_index.services:
        if preferred_service and item.identity.service == preferred_service:
            ranked.append((10_000, item.identity.service))
            continue
        score = 0
        haystacks = [
            item.identity.service.lower(),
            item.identity.domain.lower(),
            item.owner.name.lower(),
            *[value.lower() for value in item.capability.capability_terms],
        ]
        for term in terms:
            if any(term in haystack for haystack in haystacks):
                score += 1
        if score > 0:
            ranked.append((score, item.identity.service))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[1] for item in ranked]


def _search_service(store: ContractStore, service: str, terms: list[str]) -> list[tuple[float, OperationSearchDoc]]:
    docs = {item.operation_id: item for item in store.load_operation_docs(service)}
    candidate_ids: set[str] = set()
    for term in terms:
        bucket = store.load_inverted_bucket(service, _bucket_file(term))
        if not bucket:
            continue
        for key, operation_ids in bucket.items():
            if term == key or term in key:
                candidate_ids.update(operation_ids)
    if not candidate_ids:
        candidate_ids = set(docs.keys())
    scored: list[tuple[float, OperationSearchDoc]] = []
    for operation_id in candidate_ids:
        doc = docs.get(operation_id)
        if doc is None:
            continue
        score = _score_doc(doc, terms)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: (-item[0], item[1].operation_id))
    return scored[:50]


def _score_doc(doc: OperationSearchDoc, terms: list[str]) -> float:
    haystacks = {
        "summary": [doc.summary],
        "description": [doc.description],
        "aliases": doc.aliases,
        "tags": doc.tags,
        "path": [doc.full_path],
        "method": [doc.method_name],
        "types": [doc.body_type or "", doc.response_data_type],
        "params": doc.key_params,
    }
    score = 0.0
    score += _count_hits(terms, haystacks["summary"]) * 5
    score += _count_hits(terms, haystacks["aliases"]) * 4
    score += _count_hits(terms, haystacks["description"]) * 3
    score += _count_hits(terms, haystacks["tags"]) * 2
    score += _count_hits(terms, haystacks["path"]) * 2
    score += _count_hits(terms, haystacks["method"]) * 1.5
    score += _count_hits(terms, haystacks["types"]) * 1.5
    score += _count_hits(terms, haystacks["params"]) * 1
    return score


def _count_hits(terms: list[str], haystacks: list[str]) -> int:
    normalized = [value.lower() for value in haystacks if value]
    return sum(1 for term in terms if any(term in entry for entry in normalized))


def _resolve_ambiguous(candidates: list[tuple[float, OperationSearchDoc]]) -> tuple[str, str]:
    if _can_prompt():
        print("Multiple operations found. 请输入候选编号，或输入 q 取消：", file=sys.stderr)
        for index, (_, item) in enumerate(candidates, start=1):
            print(f"{index}. [{item.service}] {item.operation_id}", file=sys.stderr)
            print(f"   {item.http_method} {item.full_path}", file=sys.stderr)
            print(f"   {item.summary} | controller={item.controller}", file=sys.stderr)
        selected = input().strip()
        if selected.lower() == "q":
            raise RuntimeError("Search cancelled.")
        if selected.isdigit():
            candidate_index = int(selected)
            if 1 <= candidate_index <= len(candidates):
                chosen = candidates[candidate_index - 1][1]
                return chosen.operation_id, chosen.controller
        raise RuntimeError("Invalid candidate selection.")
    details = "\n".join(
        f"- [{item.service}] {item.operation_id}\n  {item.http_method} {item.full_path}\n  {item.summary} | controller={item.controller}"
        for _, item in candidates
    )
    raise RuntimeError(f"Multiple operations found. 请补充更具体的条件，或在交互模式下按编号确认：\n{details}")


def _detect_consumer_service(consumer_repo: Path | None) -> str | None:
    if consumer_repo is None:
        return None
    bootstrap_candidates = [
        consumer_repo / "src/main/resources/bootstrap.properties",
        consumer_repo / "src/main/resources/bootstrap.yml",
        consumer_repo / "src/main/resources/bootstrap.yaml",
    ]
    for file_path in bootstrap_candidates:
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8")
        match = re.search(r"spring\.application\.name\s*[:=]\s*([A-Za-z0-9_.-]+)", text)
        if match:
            return match.group(1).strip()
    return None


def _bucket_file(term: str) -> str:
    from .indexer import bucket_name

    return bucket_name(term)


def _can_prompt() -> bool:
    if sys.stdin is None or sys.stdin.closed:
        return False
    return sys.stdin.isatty()
