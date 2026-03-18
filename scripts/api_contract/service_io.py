from __future__ import annotations

from pathlib import Path

import yaml

from .models import (
    ServiceIdentity,
    ServiceModel,
    ServiceOwner,
    ServicePathRules,
    ServiceSource,
    ServiceTarget,
)


def load_service(path: Path) -> ServiceModel:
    return load_service_text(path.read_text(encoding="utf-8"))


def load_service_text(text: str) -> ServiceModel:
    data = yaml.safe_load(text) or {}
    identity = data.get("identity", {})
    owner = data.get("owner", {})
    source = data.get("source", {})
    target = data.get("target", {})
    path_rules = data.get("pathRules", {})
    return ServiceModel(
        identity=ServiceIdentity(
            domain=str(identity.get("domain", "")),
            service=str(identity.get("service", "")),
        ),
        owner=ServiceOwner(name=str(owner.get("name", ""))),
        source=ServiceSource(repo=str(source.get("repo", ""))),
        target=ServiceTarget(
            type=str(target.get("type", "")),
            value=str(target.get("value", "")),
            context_id_prefix=str(target.get("contextIdPrefix", "")),
        ),
        path_rules=ServicePathRules(
            path_prefix=str(path_rules.get("pathPrefix", "")),
            base_path_style=str(path_rules.get("basePathStyle", "controller-base-plus-method-path")),
            exceptions=[str(item) for item in (path_rules.get("exceptions") or [])],
        ),
    )


def dump_service(model: ServiceModel, path: Path) -> None:
    path.write_text(render_service(model), encoding="utf-8")


def render_service(model: ServiceModel) -> str:
    data = {
        "identity": {
            "domain": model.identity.domain,
            "service": model.identity.service,
        },
        "owner": {
            "name": model.owner.name,
        },
        "source": {
            "repo": model.source.repo,
        },
        "target": {
            "type": model.target.type,
            "value": model.target.value,
            "contextIdPrefix": model.target.context_id_prefix,
        },
        "pathRules": {
            "pathPrefix": model.path_rules.path_prefix,
            "basePathStyle": model.path_rules.base_path_style,
            "exceptions": list(model.path_rules.exceptions),
        },
    }
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
