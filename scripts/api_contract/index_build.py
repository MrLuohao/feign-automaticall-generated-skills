from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .artifact_publisher import ArtifactPublisher
from .context_enricher import BasicContextEnricher, ContextEnricher
from .models import ControllerSpecModel, OperationSearchDoc, ServiceModel


SCHEMA_VERSION = "v1"


def build_index_release(
    store,
    output_dir: Path,
    *,
    enricher: ContextEnricher | None = None,
    publisher: ArtifactPublisher | None = None,
) -> dict[str, object]:
    enricher = enricher or BasicContextEnricher()
    output_dir.mkdir(parents=True, exist_ok=True)
    shards_dir = output_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    delta_dir = output_dir / "delta"
    delta_dir.mkdir(parents=True, exist_ok=True)
    services = store.iter_all_services()
    specs_by_service: dict[str, list[ControllerSpecModel]] = {}
    for service_name, _, spec in store.iter_all_specs():
        specs_by_service.setdefault(service_name, []).append(spec)

    built_at = _timestamp()
    service_entries: list[dict[str, object]] = []
    router_rows: list[dict[str, object]] = []
    for service in services:
        docs = _build_operation_docs(service, specs_by_service.get(service.service, []))
        service_dir = shards_dir / service.service
        service_dir.mkdir(parents=True, exist_ok=True)
        shard_sqlite_path = service_dir / "operations.sqlite"
        shard_artifact_path = service_dir / "operations.sqlite.gz"
        _write_service_shard_sqlite(shard_sqlite_path, service, docs, enricher)
        shard_sha = _compress_artifact(shard_sqlite_path, shard_artifact_path)
        service_manifest = {
            "service": service.service,
            "shardVersion": built_at,
            "operationCount": len(docs),
            "controllerCount": len(specs_by_service.get(service.service, [])),
            "builtAt": built_at,
            "artifactFile": "operations.sqlite.gz",
            "artifactSha256": shard_sha,
        }
        (service_dir / "manifest.json").write_text(
            json.dumps(service_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        service_enrichment = enricher.enrich_service(service, docs)
        keywords = service_enrichment.keywords
        context_summary = service_enrichment.context_summary
        service_entries.append(
            {
                "service": service.service,
                "domain": service.domain,
                "shardVersion": built_at,
                "artifact": f"shards/{service.service}/operations.sqlite.gz",
                "manifest": f"shards/{service.service}/manifest.json",
                "artifactSha256": shard_sha,
                "updatedAt": built_at,
                "keywords": keywords,
            }
        )
        router_rows.append(
            {
                "service": service.service,
                "domain": service.domain,
                "owner_name": service.owner.name,
                "context_summary": context_summary,
                "keywords": keywords,
                "shard_version": built_at,
                "updated_at": built_at,
            }
        )

    router_sqlite_path = output_dir / "router.sqlite"
    _write_router_sqlite(router_sqlite_path, router_rows)
    router_artifact_path = output_dir / "router.sqlite.gz"
    router_sha = _compress_artifact(router_sqlite_path, router_artifact_path)
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "indexVersion": built_at,
        "builtAt": built_at,
        "routerVersion": built_at,
        "routerArtifact": {
            "file": "router.sqlite.gz",
            "sha256": router_sha,
        },
        "services": service_entries,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (delta_dir / f"{built_at}.json").write_text(
        json.dumps(
            {
                "indexVersion": built_at,
                "services": [
                    {
                        "service": item["service"],
                        "shardVersion": item["shardVersion"],
                        "artifact": item["artifact"],
                    }
                    for item in service_entries
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if publisher is not None:
        publisher.publish_release(output_dir)
    return manifest


def _write_router_sqlite(path: Path, rows: list[dict[str, object]]) -> None:
    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.executescript(
            """
            DROP TABLE IF EXISTS services;
            DROP TABLE IF EXISTS services_fts;
            CREATE TABLE services (
                service TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                owner_name TEXT NOT NULL,
                context_summary TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                shard_version TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE services_fts USING fts5(
                service,
                domain,
                owner_name,
                context_summary,
                keywords_text
            );
            """
        )
        for row in rows:
            keywords_json = json.dumps(row["keywords"], ensure_ascii=False)
            keywords_text = " ".join(row["keywords"])
            cursor.execute(
                """
                INSERT INTO services (
                    service, domain, owner_name, context_summary, keywords_json, shard_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["service"],
                    row["domain"],
                    row["owner_name"],
                    row["context_summary"],
                    keywords_json,
                    row["shard_version"],
                    row["updated_at"],
                ),
            )
            cursor.execute(
                """
                INSERT INTO services_fts (
                    service, domain, owner_name, context_summary, keywords_text
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["service"],
                    row["domain"],
                    row["owner_name"],
                    row["context_summary"],
                    keywords_text,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _write_service_shard_sqlite(
    path: Path,
    service: ServiceModel,
    docs: list[OperationSearchDoc],
    enricher: ContextEnricher,
) -> None:
    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.executescript(
            """
            DROP TABLE IF EXISTS operations;
            DROP TABLE IF EXISTS operations_fts;
            CREATE TABLE operations (
                operation_id TEXT PRIMARY KEY,
                service TEXT NOT NULL,
                controller TEXT NOT NULL,
                method_name TEXT NOT NULL,
                http_method TEXT NOT NULL,
                full_path TEXT NOT NULL,
                summary TEXT NOT NULL,
                description TEXT NOT NULL,
                body_type TEXT,
                response_data_type TEXT NOT NULL,
                key_params_json TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                context_summary TEXT NOT NULL,
                spec_path TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE operations_fts USING fts5(
                operation_id,
                controller,
                method_name,
                http_method,
                full_path,
                summary,
                description,
                body_type,
                response_data_type,
                key_params_text,
                aliases_text,
                tags_text,
                context_summary
            );
            """
        )
        for doc in docs:
            enrichment = enricher.enrich_operation(service, doc)
            context_summary = enrichment.context_summary
            aliases = list(dict.fromkeys([*doc.aliases, *enrichment.keywords]))
            tags = list(dict.fromkeys([*doc.tags, *enrichment.keywords]))
            cursor.execute(
                """
                INSERT INTO operations (
                    operation_id, service, controller, method_name, http_method, full_path,
                    summary, description, body_type, response_data_type, key_params_json,
                    aliases_json, tags_json, context_summary, spec_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.operation_id,
                    doc.service,
                    doc.controller,
                    doc.method_name,
                    doc.http_method,
                    doc.full_path,
                    doc.summary,
                    doc.description,
                    doc.body_type,
                    doc.response_data_type,
                    json.dumps(doc.key_params, ensure_ascii=False),
                    json.dumps(aliases, ensure_ascii=False),
                    json.dumps(tags, ensure_ascii=False),
                    context_summary,
                    doc.spec_path,
                ),
            )
            cursor.execute(
                """
                INSERT INTO operations_fts (
                    operation_id, controller, method_name, http_method, full_path,
                    summary, description, body_type, response_data_type, key_params_text,
                    aliases_text, tags_text, context_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.operation_id,
                    doc.controller,
                    doc.method_name,
                    doc.http_method,
                    doc.full_path,
                    doc.summary,
                    doc.description,
                    doc.body_type or "",
                    doc.response_data_type,
                    " ".join(doc.key_params),
                    " ".join(aliases),
                    " ".join(tags),
                    context_summary,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _build_operation_docs(service: ServiceModel, specs: list[ControllerSpecModel]) -> list[OperationSearchDoc]:
    docs: list[OperationSearchDoc] = []
    for spec in sorted(specs, key=lambda item: item.controller.name):
        spec_path = (
            f"services/{service.service}/controllers/{spec.controller.name}/{spec.controller.name}.spec.yaml"
        )
        for method in spec.methods:
            docs.append(
                OperationSearchDoc(
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
            )
    docs.sort(key=lambda item: item.operation_id)
    return docs


def _collect_key_params(method) -> list[str]:
    names = [item.name for item in [*method.request.path_params, *method.request.query_params, *method.request.headers, *method.request.parts]]
    if method.request.body.type:
        names.append(method.request.body.type)
    return names[:8]


def _full_path(service: ServiceModel, controller_base_path: str, method_path: str) -> str:
    parts = [service.path_rules.path_prefix, controller_base_path, method_path]
    normalized = [item.strip("/") for item in parts if item and item.strip("/")]
    return "/" + "/".join(normalized)

def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def _compress_artifact(source_path: Path, target_path: Path) -> str:
    with source_path.open("rb") as source:
        content = source.read()
    with gzip.open(target_path, "wb") as target:
        target.write(content)
    source_path.unlink()
    return hashlib.sha256(target_path.read_bytes()).hexdigest()
