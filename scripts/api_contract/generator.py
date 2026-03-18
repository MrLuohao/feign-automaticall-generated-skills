from __future__ import annotations

from pathlib import Path

from .contract_store import ContractStore
from .java_feign_generator import generate_java_feign


def generate_client(
    store: ContractStore,
    operation_id: str,
    target: str | None,
    output_root: Path | None,
    consumer_repo: Path | None = None,
) -> Path:
    if target and target != "java-feign":
        raise RuntimeError("Only java-feign generation is supported.")
    if consumer_repo is None:
        raise RuntimeError("Missing --consumer-repo for Java/OpenFeign generation.")
    global_index = store.load_global_index()
    for service_entry in global_index.services:
        docs = store.load_operation_docs(service_entry.identity.service)
        for doc in docs:
            if doc.operation_id != operation_id:
                continue
            service = store.load_service(doc.service)
            spec = store.load_spec(doc.service, doc.controller)
            if service is None or spec is None:
                raise RuntimeError(f"Missing contracts for {operation_id}")
            method = next((item for item in spec.methods if item.operation_id == operation_id), None)
            if method is None:
                raise RuntimeError(f"Missing method {operation_id} in spec")
            return generate_java_feign(service, spec, method, consumer_repo)
    raise RuntimeError(f"Unknown operationId: {operation_id}")
