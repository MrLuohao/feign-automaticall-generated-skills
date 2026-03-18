from __future__ import annotations

import select
import sys
from pathlib import Path

import yaml

from .models import (
    ConsumerDtoRule,
    ConsumerLocalRuleModel,
    ConsumerNamingRule,
    ConsumerPlacementRule,
    ResolvedConsumerContext,
)


RULE_FILE = "api-contract-consumer.yaml"


class ConsumerRuleError(RuntimeError):
    pass


def resolve_consumer_context(consumer_repo: Path, domain: str) -> ResolvedConsumerContext:
    local_rule = _load_local_rule(consumer_repo)
    if local_rule is not None:
        return ResolvedConsumerContext(
            consumer_repo=consumer_repo,
            placement=local_rule.placement,
            naming=local_rule.naming,
            dto=local_rule.dto,
        )
    placement = _infer_java_placement(consumer_repo, domain)
    return ResolvedConsumerContext(
        consumer_repo=consumer_repo,
        placement=placement,
        naming=ConsumerNamingRule(),
        dto=ConsumerDtoRule(use_lombok_data=_infer_use_lombok_data(placement)),
    )


def _load_local_rule(consumer_repo: Path) -> ConsumerLocalRuleModel | None:
    path = consumer_repo / RULE_FILE
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    placement = data.get("placement", {})
    naming = data.get("naming", {})
    dto = data.get("dto", {})
    return ConsumerLocalRuleModel(
        placement=ConsumerPlacementRule(
            client_dir=consumer_repo / placement["clientDir"],
            dto_dir=consumer_repo / placement["dtoDir"],
            support_dir=consumer_repo / placement["supportDir"],
            client_package=placement["clientPackage"],
            dto_package=placement["dtoPackage"],
            support_package=placement["supportPackage"],
        ),
        naming=ConsumerNamingRule(
            client_suffix=naming.get("clientSuffix", "Api"),
            support_class_name=naming.get("supportClassName", "ApiContractSupport"),
        ),
        dto=ConsumerDtoRule(
            use_lombok_data=bool(dto.get("useLombokData", False)),
        ),
    )


def _infer_java_placement(consumer_repo: Path, domain: str) -> ConsumerPlacementRule:
    source_root = consumer_repo / "src/main/java"
    if not source_root.exists():
        raise ConsumerRuleError(f"Missing Java source root: {source_root}")
    candidates = sorted(path for path in source_root.rglob("acl") if path.is_dir() and "infrastructure" in path.parts)
    if not candidates:
        raise ConsumerRuleError(
            f"Unable to infer ACL root from {consumer_repo}. Add {RULE_FILE} at repo root."
        )
    if len(candidates) > 1:
        acl_root = _choose_candidate(candidates)
    else:
        acl_root = candidates[0]
    domain_root = acl_root / domain
    package_root = ".".join(acl_root.relative_to(source_root).parts)
    return ConsumerPlacementRule(
        client_dir=domain_root / "client",
        dto_dir=domain_root / "dto",
        support_dir=domain_root / "support",
        client_package=f"{package_root}.{domain}.client",
        dto_package=f"{package_root}.{domain}.dto",
        support_package=f"{package_root}.{domain}.support",
    )


def _choose_candidate(candidates: list[Path]) -> Path:
    if _can_prompt():
        print("检测到多个 ACL 根目录，请输入编号确认：", file=sys.stderr)
        for index, candidate in enumerate(candidates, start=1):
            print(f"{index}. {candidate}", file=sys.stderr)
        selected = input().strip()
        if selected.isdigit():
            candidate_index = int(selected)
            if 1 <= candidate_index <= len(candidates):
                return candidates[candidate_index - 1]
        raise ConsumerRuleError("Invalid consumer ACL root selection.")
    raise ConsumerRuleError(
        "Multiple ACL roots found. Add api-contract-consumer.yaml at repo root or rerun in interactive mode."
    )


def _infer_use_lombok_data(placement: ConsumerPlacementRule) -> bool:
    search_roots = [
        placement.dto_dir.parent,
        placement.client_dir.parent,
        placement.client_dir.parents[1] if len(placement.client_dir.parents) > 1 else placement.client_dir.parent,
    ]
    seen: set[Path] = set()
    for root in search_roots:
        if root in seen or not root.exists():
            continue
        seen.add(root)
        for java_file in root.rglob("*.java"):
            try:
                text = java_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if "import lombok.Data;" in text or "@Data" in text:
                return True
    return False


def _can_prompt() -> bool:
    if sys.stdin is None or sys.stdin.closed:
        return False
    if sys.stdin.isatty():
        return True
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    return bool(ready)
