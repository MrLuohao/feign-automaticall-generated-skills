from __future__ import annotations

from pathlib import Path

from .contract_store import ContractStore
from .java_feign_generator import generate_java_feign
from .search import search_operation


def generate_client(
    store: ContractStore,
    operation_id: str | None,
    query: str | None,
    target: str | None,
    output_root: Path | None,
    consumer_repo: Path | None = None,
    *,
    cache_dir: Path | None = None,
    index_base_url: str | None = None,
    cache_manager=None,
) -> Path:
    if target and target != "java-feign":
        raise RuntimeError("Only java-feign generation is supported.")
    if consumer_repo is None:
        raise RuntimeError("Missing --consumer-repo for Java/OpenFeign generation.")
    resolved_operation_id = operation_id
    controller_name: str | None = None
    if not resolved_operation_id:
        if not query:
            raise RuntimeError("Missing operation identifier. Provide --operation-id or --query.")
        resolved_operation_id, controller_name = search_operation(
            store,
            query,
            consumer_repo=consumer_repo,
            cache_dir=cache_dir,
            index_base_url=index_base_url,
            cache_manager=cache_manager,
        )
    for service_name, _, spec in store.iter_all_specs():
        for method in spec.methods:
            if method.operation_id != resolved_operation_id:
                continue
            service = store.load_service(service_name)
            if service is None:
                raise RuntimeError(f"Missing contracts for {resolved_operation_id}")
            if controller_name and spec.controller.name != controller_name:
                continue
            return generate_java_feign(service, spec, method, consumer_repo)
    raise RuntimeError(f"Unknown operationId: {resolved_operation_id}")
