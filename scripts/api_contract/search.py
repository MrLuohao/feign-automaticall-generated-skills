from __future__ import annotations

import re
import sys
from pathlib import Path

from .cache_manager import LocalCacheManager
from .contract_store import ContractStore
from .local_index import route_services, search_service_operations
from .models import OperationSearchDoc
from .text_normalizer import normalize_query_terms


def search_operation(
    store: ContractStore,
    query: str,
    consumer_repo: Path | None = None,
    *,
    cache_dir: Path | None = None,
    index_base_url: str | None = None,
    cache_manager: LocalCacheManager | None = None,
) -> tuple[str, str]:
    if cache_dir is None:
        raise RuntimeError("Missing local cache directory for search.")
    if cache_manager is not None:
        cache_manager.ensure_ready()
    elif index_base_url:
        LocalCacheManager(cache_dir=cache_dir, index_base_url=index_base_url).ensure_ready()
    preferred_service = _detect_consumer_service(consumer_repo)
    services = route_services(cache_dir, query, preferred_service)[:3]
    if not services:
        raise RuntimeError(f"TERMINAL_NO_OPERATION_FOUND: No operation found for query: {query}")
    candidates: list[tuple[float, OperationSearchDoc]] = []
    for routed in services:
        candidates.extend(search_service_operations(cache_dir, routed.service, query))
    if not candidates:
        raise RuntimeError(f"TERMINAL_NO_OPERATION_FOUND: No operation found for query: {query}")
    candidates.sort(key=lambda item: (-item[0], item[1].operation_id))
    top = candidates[:5]
    if len(top) == 1:
        return top[0][1].operation_id, top[0][1].controller
    if top[0][0] >= top[1][0] + 3:
        return top[0][1].operation_id, top[0][1].controller
    return _resolve_ambiguous(top)


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


def _can_prompt() -> bool:
    if sys.stdin is None or sys.stdin.closed:
        return False
    return sys.stdin.isatty()
