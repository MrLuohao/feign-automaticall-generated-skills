from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import date

from .models import (
    ControllerSpecModel,
    GlobalIndexModel,
    GlobalServiceCapability,
    GlobalServiceEntry,
    GlobalServiceIdentity,
    GlobalServiceOwner,
    GlobalServiceShard,
    OperationSearchDoc,
    ServiceModel,
    ServiceShardArtifacts,
    ServiceShardManifest,
)
from .text_normalizer import build_text_terms


BUCKET_COUNT = 32


def build_service_shard(service: ServiceModel, specs: list[ControllerSpecModel]) -> ServiceShardArtifacts:
    operation_docs: list[OperationSearchDoc] = []
    inverted_buckets: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for spec in sorted(specs, key=lambda item: item.controller.name):
        spec_path = (
            f"services/{service.service}/controllers/{spec.controller.name}/{spec.controller.name}.spec.yaml"
        )
        for method in spec.methods:
            doc = OperationSearchDoc(
                operation_id=method.identity.operation_id,
                service=service.service,
                controller=spec.controller.name,
                method_name=method.source.method_name,
                http_method=method.protocol.http_method,
                full_path=_full_path(service, spec.controller.base_path, method.protocol.path),
                summary=method.semantic.summary,
                description=method.semantic.description,
                aliases=list(method.search.intent_aliases),
                tags=list(method.search.tags),
                body_type=method.request.body.type,
                response_data_type=method.response.data_type,
                key_params=_collect_key_params(method),
                spec_path=spec_path,
            )
            operation_docs.append(doc)
            for term in _doc_terms(doc):
                bucket = bucket_name(term)
                inverted_buckets[bucket][term].append(doc.operation_id)

    manifest = ServiceShardManifest(
        service=service.service,
        version=1,
        updated_at=str(date.today()),
        controller_count=len(specs),
        operation_count=len(operation_docs),
        operations_file="operations.jsonl",
        inverted_dir="inverted",
    )
    return ServiceShardArtifacts(
        manifest=manifest,
        operation_docs=sorted(operation_docs, key=lambda item: item.operation_id),
        inverted_buckets={bucket: dict(terms) for bucket, terms in sorted(inverted_buckets.items())},
    )


def build_global_index(services: list[ServiceModel], shards: dict[str, ServiceShardArtifacts]) -> GlobalIndexModel:
    entries: list[GlobalServiceEntry] = []
    for service in sorted(services, key=lambda item: item.service):
        shard = shards.get(service.service)
        capability_terms = _capability_terms(shard.operation_docs) if shard else []
        entries.append(
            GlobalServiceEntry(
                identity=GlobalServiceIdentity(service=service.service, domain=service.domain),
                owner=GlobalServiceOwner(name=service.owner.name),
                shard=GlobalServiceShard(shard_path=f"indexes/services/{service.service}/"),
                capability=GlobalServiceCapability(capability_terms=capability_terms),
            )
        )
    return GlobalIndexModel(services=entries)


def dump_global_index(index: GlobalIndexModel) -> str:
    data = {
        "services": [
            {
                "identity": asdict(item.identity),
                "owner": {"name": item.owner.name},
                "shard": {"shardPath": item.shard.shard_path},
                "capability": {"capabilityTerms": list(item.capability.capability_terms)},
            }
            for item in index.services
        ]
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def load_global_index(text: str) -> GlobalIndexModel:
    data = json.loads(text)
    return GlobalIndexModel(
        services=[
            GlobalServiceEntry(
                identity=GlobalServiceIdentity(
                    service=item["identity"]["service"],
                    domain=item["identity"]["domain"],
                ),
                owner=GlobalServiceOwner(name=item["owner"]["name"]),
                shard=GlobalServiceShard(shard_path=item["shard"]["shardPath"]),
                capability=GlobalServiceCapability(
                    capability_terms=list(item.get("capability", {}).get("capabilityTerms", []))
                ),
            )
            for item in data.get("services", [])
        ]
    )


def dump_manifest(manifest: ServiceShardManifest) -> str:
    return json.dumps(
        {
            "service": manifest.service,
            "version": manifest.version,
            "updatedAt": manifest.updated_at,
            "controllerCount": manifest.controller_count,
            "operationCount": manifest.operation_count,
            "operationsFile": manifest.operations_file,
            "invertedDir": manifest.inverted_dir,
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def load_manifest(text: str) -> ServiceShardManifest:
    data = json.loads(text)
    return ServiceShardManifest(
        service=data["service"],
        version=int(data["version"]),
        updated_at=data["updatedAt"],
        controller_count=int(data["controllerCount"]),
        operation_count=int(data["operationCount"]),
        operations_file=data["operationsFile"],
        inverted_dir=data["invertedDir"],
    )


def dump_operation_docs(items: list[OperationSearchDoc]) -> str:
    return "".join(json.dumps(_dump_operation_doc(item), ensure_ascii=False) + "\n" for item in items)


def load_operation_docs(text: str) -> list[OperationSearchDoc]:
    result: list[OperationSearchDoc] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        data = json.loads(stripped)
        result.append(
            OperationSearchDoc(
                operation_id=data["operationId"],
                service=data["service"],
                controller=data["controller"],
                method_name=data["methodName"],
                http_method=data["httpMethod"],
                full_path=data["fullPath"],
                summary=data["summary"],
                description=data["description"],
                aliases=list(data.get("aliases", [])),
                tags=list(data.get("tags", [])),
                body_type=data.get("bodyType"),
                response_data_type=data.get("responseDataType", ""),
                key_params=list(data.get("keyParams", [])),
                spec_path=data["specPath"],
            )
        )
    return result


def dump_inverted_bucket(bucket: dict[str, list[str]]) -> str:
    return json.dumps(bucket, ensure_ascii=False, indent=2) + "\n"


def load_inverted_bucket(text: str) -> dict[str, list[str]]:
    return {key: list(value) for key, value in json.loads(text).items()}


def bucket_name(term: str) -> str:
    return f"{int(hashlib.sha1(term.encode('utf-8')).hexdigest(), 16) % BUCKET_COUNT:02d}.json"


def _collect_key_params(method) -> list[str]:
    names = [item.name for item in [*method.request.path_params, *method.request.query_params, *method.request.headers, *method.request.parts]]
    if method.request.body.type:
        names.append(method.request.body.type)
    return names[:8]


def _doc_terms(doc: OperationSearchDoc) -> list[str]:
    return build_text_terms(
        doc.operation_id,
        doc.controller,
        doc.method_name,
        doc.full_path,
        doc.summary,
        doc.description,
        *doc.aliases,
        *doc.tags,
        *(doc.key_params or []),
        doc.body_type or "",
        doc.response_data_type,
    )


def _capability_terms(docs: list[OperationSearchDoc]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    term_groups = [build_text_terms(doc.summary, *doc.aliases, *doc.tags) for doc in docs]
    positions = [0 for _ in term_groups]
    while len(result) < 12:
        progressed = False
        for idx, terms in enumerate(term_groups):
            while positions[idx] < len(terms) and terms[positions[idx]] in seen:
                positions[idx] += 1
            if positions[idx] >= len(terms):
                continue
            term = terms[positions[idx]]
            positions[idx] += 1
            seen.add(term)
            result.append(term)
            progressed = True
            if len(result) >= 12:
                break
        if not progressed:
            break
    return result


def _full_path(service: ServiceModel, controller_base_path: str, method_path: str) -> str:
    parts = [service.path_rules.path_prefix, controller_base_path, method_path]
    normalized = [item.strip("/") for item in parts if item and item.strip("/")]
    return "/" + "/".join(normalized)


def _dump_operation_doc(item: OperationSearchDoc) -> dict:
    return {
        "operationId": item.operation_id,
        "service": item.service,
        "controller": item.controller,
        "methodName": item.method_name,
        "httpMethod": item.http_method,
        "fullPath": item.full_path,
        "summary": item.summary,
        "description": item.description,
        "aliases": list(item.aliases),
        "tags": list(item.tags),
        "bodyType": item.body_type,
        "responseDataType": item.response_data_type,
        "keyParams": list(item.key_params),
        "specPath": item.spec_path,
    }
