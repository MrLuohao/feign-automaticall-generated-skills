from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .models import OperationSearchDoc, ServiceModel
from .text_normalizer import build_text_terms


@dataclass
class ContextEnrichment:
    context_summary: str
    keywords: list[str] = field(default_factory=list)


class ContextEnricher:
    def enrich_service(self, service: ServiceModel, docs: list[OperationSearchDoc]) -> ContextEnrichment:
        raise NotImplementedError

    def enrich_operation(self, service: ServiceModel, doc: OperationSearchDoc) -> ContextEnrichment:
        raise NotImplementedError


class LlmEnrichmentClient(Protocol):
    def enrich(self, payload: dict[str, object]) -> dict[str, object]:
        ...


class BasicContextEnricher(ContextEnricher):
    def enrich_service(self, service: ServiceModel, docs: list[OperationSearchDoc]) -> ContextEnrichment:
        summaries = "；".join(doc.summary for doc in docs[:6])
        context_summary = f"{service.service} 属于 {service.domain} 域，主要能力包括：{summaries}".strip("；")
        keywords = build_text_terms(
            service.service,
            service.domain,
            service.owner.name,
            *[doc.summary for doc in docs],
            *[alias for doc in docs for alias in doc.aliases],
            *[tag for doc in docs for tag in doc.tags],
        )[:24]
        return ContextEnrichment(context_summary=context_summary, keywords=keywords)

    def enrich_operation(self, service: ServiceModel, doc: OperationSearchDoc) -> ContextEnrichment:
        parts = [service.service, doc.controller, doc.http_method, doc.full_path, doc.summary, doc.description]
        parts.extend(doc.aliases)
        parts.extend(doc.tags)
        parts.extend(doc.key_params)
        context_summary = " ".join(part for part in parts if part)
        keywords = build_text_terms(
            doc.operation_id,
            doc.summary,
            doc.description,
            doc.full_path,
            *doc.aliases,
            *doc.tags,
            *doc.key_params,
        )[:24]
        return ContextEnrichment(context_summary=context_summary, keywords=keywords)


class LlmContextEnricher(ContextEnricher):
    def __init__(self, client: LlmEnrichmentClient, fallback: ContextEnricher | None = None):
        self.client = client
        self.fallback = fallback or BasicContextEnricher()

    def enrich_service(self, service: ServiceModel, docs: list[OperationSearchDoc]) -> ContextEnrichment:
        payload = {
            "kind": "service",
            "service": service.service,
            "domain": service.domain,
            "owner": service.owner.name,
            "operations": [
                {
                    "operation_id": doc.operation_id,
                    "summary": doc.summary,
                    "description": doc.description,
                    "path": doc.full_path,
                }
                for doc in docs[:20]
            ],
        }
        return self._safe_enrich(payload, self.fallback.enrich_service(service, docs))

    def enrich_operation(self, service: ServiceModel, doc: OperationSearchDoc) -> ContextEnrichment:
        payload = {
            "kind": "operation",
            "service": service.service,
            "domain": service.domain,
            "controller": doc.controller,
            "operation_id": doc.operation_id,
            "summary": doc.summary,
            "description": doc.description,
            "http_method": doc.http_method,
            "full_path": doc.full_path,
            "aliases": list(doc.aliases),
            "tags": list(doc.tags),
            "key_params": list(doc.key_params),
            "body_type": doc.body_type,
            "response_data_type": doc.response_data_type,
        }
        return self._safe_enrich(payload, self.fallback.enrich_operation(service, doc))

    def _safe_enrich(self, payload: dict[str, object], fallback: ContextEnrichment) -> ContextEnrichment:
        try:
            response = self.client.enrich(payload)
        except Exception:
            return fallback
        context_summary = str(response.get("context_summary", "")).strip()
        keywords = [str(item).strip() for item in response.get("keywords", []) if str(item).strip()]
        if not context_summary:
            return fallback
        return ContextEnrichment(context_summary=context_summary, keywords=keywords)
