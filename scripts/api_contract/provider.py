from __future__ import annotations

import re
import select
import sys
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .contract_store import ContractStore
from .doc_renderer import render_doc
from .indexer import (
    build_global_index,
    build_service_shard,
    dump_global_index,
    dump_inverted_bucket,
    dump_manifest,
    dump_operation_docs,
)
from .models import (
    ControllerMeta,
    ControllerSource,
    ControllerSpecModel,
    FieldSchemaModel,
    MethodErrorModel,
    MethodIdentity,
    MethodModel,
    MethodProtocol,
    MethodSchemas,
    MethodSearch,
    MethodSemantic,
    MethodSourceModel,
    ParamModel,
    RequestBodyModel,
    RequestModel,
    ResponseModel,
    ServiceIdentity,
    ServiceModel,
    ServiceOwner,
    ServicePathRules,
    ServiceSource,
    ServiceTarget,
    TypeSchemaModel,
)


REQUIRED_FIELD_ANNOTATIONS = {"@NotNull", "@NotBlank", "@NotEmpty"}
IGNORE_CONTRACT_ANNOTATION = "ApiContractIgnore"
SOURCE_JAR_BASE_URLS = (
    "http://bkrepo.dstcar.cn/maven/vc0da8/java-sdk/",
    "https://maven.aliyun.com/repository/public/",
)
GENERIC_WRAPPER_TYPES = {
    "List",
    "Set",
    "Collection",
    "Map",
    "Tree",
    "Response",
    "PageDTO",
    "Page",
    "IPage",
    "ExportResult",
    "Optional",
}
RESPONSE_SCHEMA_WRAPPER_TYPES = {"PageDTO", "Page", "IPage", "Tree"}
_TYPE_SOURCE_CACHE: dict[str, str | None] = {}
_TYPE_BINARY_JAR_CACHE: dict[str, tuple[Path, str] | None] = {}
COMMON_FIELD_DESCRIPTION_MAP = {
    "page": "当前页码",
    "pageSize": "每页条数",
    "totalPage": "总页数",
    "totalCount": "总记录数",
    "list": "列表数据",
    "id": "标识ID",
    "index": "枚举值",
    "desc": "描述",
    "email": "邮箱",
    "phone": "手机号",
    "orgCode": "组织编码",
    "orgName": "组织名称",
    "orgFullName": "组织全称",
    "fullCode": "完整编码",
    "fullName": "完整名称",
    "personCode": "人员编码",
    "manager": "是否负责人",
    "creatorId": "创建人ID",
    "creatorName": "创建人名称",
    "createTime": "创建时间",
    "modifierId": "更新人ID",
    "modifierName": "更新人名称",
    "modifyTime": "更新时间",
}
LOW_VALUE_SEARCH_TERMS = {"处理", "对象"}
COMMENT_METADATA_PREFIXES = (
    "yapi",
    "author",
    "date",
    "time",
    "since",
    "link",
    "url",
    "see",
)


class ProviderSyncError(RuntimeError):
    pass


@dataclass
class ProviderSyncOptions:
    provider_repo: Path
    controller_fqcn: str
    contracts_root: Path
    service_owner: str | None
    domain: str


@dataclass
class ProviderDeleteControllerOptions:
    provider_repo: Path
    controller_fqcn: str
    contracts_root: Path


@dataclass
class ProviderSyncResult:
    status: str
    service_file: str
    spec_file: str
    doc_file: str


def sync_provider_to_store(options: ProviderSyncOptions, store: ContractStore) -> ProviderSyncResult:
    service_name = _read_service_name(options.provider_repo)
    controller_file = _find_java_file(options.provider_repo, options.controller_fqcn)
    controller_name = controller_file.stem
    existing_service = store.load_service(service_name)
    controller_source = controller_file.read_text(encoding="utf-8")
    if _class_is_contract_ignored(controller_source):
        return _sync_ignored_controller(service_name, controller_name, store, existing_service)
    reserved_operation_ids = _collect_reserved_operation_ids(store, service_name, controller_name)
    owner = _resolve_service_owner(existing_service, options.service_owner)
    service_model = _build_service_model(
        service_name=service_name,
        domain=options.domain,
        provider_repo=options.provider_repo,
        owner=owner,
        existing=existing_service,
    )
    existing_spec = store.load_spec(service_name, controller_name)
    spec_model = _build_controller_spec(
        provider_repo=options.provider_repo,
        controller_file=controller_file,
        controller_source=controller_source,
        service_name=service_name,
        domain=options.domain,
        existing_spec=existing_spec,
        reserved_operation_ids=reserved_operation_ids,
    )
    if spec_model is None:
        return _sync_ignored_controller(service_name, controller_name, store, service_model)
    doc_text = render_doc(service_model, spec_model)
    upserts, deletes = _build_sync_payload(store, service_model, spec_model, doc_text)
    store.write_batch(
        upserts,
        deletes,
        commit_message=f"Sync {service_name}/{controller_name} API contracts",
    )
    return ProviderSyncResult(
        status="synced",
        service_file=store.get_service_file(service_name),
        spec_file=store.get_controller_spec_file(service_name, controller_name),
        doc_file=store.get_controller_doc_file(service_name, controller_name),
    )


def delete_controller_contract_from_store(options: ProviderDeleteControllerOptions, store: ContractStore) -> tuple[str, str]:
    service_name = _read_service_name(options.provider_repo)
    controller_name = Path(*options.controller_fqcn.split(".")).stem
    service_model = store.load_service(service_name)
    if service_model is None:
        raise ProviderSyncError(f"Service metadata not found for {service_name}")
    spec_path = store.get_controller_spec_file(service_name, controller_name)
    doc_path = store.get_controller_doc_file(service_name, controller_name)
    if store.read_text(spec_path) is None and store.read_text(doc_path) is None:
        raise ProviderSyncError(f"Controller contract files not found for {controller_name} under service {service_name}.")
    all_specs = _group_specs(store.iter_all_specs())
    remaining_specs = [spec for name, spec in all_specs.get(service_name, []) if name != controller_name]
    upserts, extra_deletes = _build_service_index_payload(store, service_model, remaining_specs)
    deletes = [spec_path, doc_path, *extra_deletes]
    store.write_batch(
        upserts,
        deletes,
        commit_message=f"Delete {service_name}/{controller_name} API contracts",
    )
    return spec_path, doc_path


def rebuild_index(store: ContractStore) -> str:
    services = store.iter_all_services()
    specs_by_service = _group_specs(store.iter_all_specs())
    upserts: dict[str, str] = {}
    deletes: list[str] = []
    shards = {}
    for service_model in services:
        specs = [spec for _, spec in specs_by_service.get(service_model.service, [])]
        shard_upserts, shard_deletes, artifacts = _render_service_shard_files(store, service_model, specs)
        upserts.update(shard_upserts)
        deletes.extend(shard_deletes)
        shards[service_model.service] = artifacts
    upserts[store.get_global_index_file()] = dump_global_index(build_global_index(services, shards))
    store.write_batch(upserts, deletes, commit_message="Rebuild API contracts index")
    return store.get_global_index_file()


def _build_sync_payload(
    store: ContractStore,
    service_model: ServiceModel,
    spec_model: ControllerSpecModel,
    doc_text: str,
) -> tuple[dict[str, str], list[str]]:
    service_name = service_model.service
    controller_name = spec_model.controller.name
    upserts = {
        store.get_service_file(service_name): render_service_text(service_model),
        store.get_controller_spec_file(service_name, controller_name): render_spec_text(spec_model),
        store.get_controller_doc_file(service_name, controller_name): doc_text,
    }
    specs_by_service = _group_specs(store.iter_all_specs())
    service_specs = {name: spec for name, spec in specs_by_service.get(service_name, [])}
    service_specs[controller_name] = spec_model
    shard_upserts, shard_deletes, shard = _render_service_shard_files(
        store,
        service_model,
        [service_specs[name] for name in sorted(service_specs)],
    )
    upserts.update(shard_upserts)
    services = {item.service: item for item in store.iter_all_services()}
    services[service_name] = service_model
    all_shards = _load_existing_shards(store, set(services), {service_name: shard})
    upserts[store.get_global_index_file()] = dump_global_index(
        build_global_index([services[name] for name in sorted(services)], all_shards)
    )
    return upserts, shard_deletes


def _build_service_index_payload(
    store: ContractStore,
    service_model: ServiceModel,
    specs: list[ControllerSpecModel],
) -> tuple[dict[str, str], list[str]]:
    upserts, deletes, shard = _render_service_shard_files(store, service_model, specs)
    services = {item.service: item for item in store.iter_all_services()}
    services[service_model.service] = service_model
    all_shards = _load_existing_shards(store, set(services), {service_model.service: shard})
    upserts[store.get_global_index_file()] = dump_global_index(
        build_global_index([services[name] for name in sorted(services)], all_shards)
    )
    return upserts, deletes


def _render_service_shard_files(
    store: ContractStore,
    service_model: ServiceModel,
    specs: list[ControllerSpecModel],
) -> tuple[dict[str, str], list[str], object]:
    artifacts = build_service_shard(service_model, specs)
    upserts = {
        store.get_service_manifest_file(service_model.service): dump_manifest(artifacts.manifest),
        store.get_service_operations_file(service_model.service): dump_operation_docs(artifacts.operation_docs),
    }
    deletes: list[str] = []
    existing_bucket_files = store.list_files(store.get_service_inverted_dir(service_model.service))
    new_bucket_files = {
        store.get_service_inverted_bucket_file(service_model.service, bucket)
        for bucket in artifacts.inverted_buckets
    }
    for bucket_file in existing_bucket_files:
        if bucket_file not in new_bucket_files:
            deletes.append(bucket_file)
    for bucket, content in artifacts.inverted_buckets.items():
        upserts[store.get_service_inverted_bucket_file(service_model.service, bucket)] = dump_inverted_bucket(content)
    return upserts, deletes, artifacts


def _load_existing_shards(store: ContractStore, services: set[str], overrides: dict[str, object]) -> dict[str, object]:
    results = dict(overrides)
    for service in services:
        if service in results:
            continue
        manifest = store.load_service_manifest(service)
        docs = store.load_operation_docs(service)
        if manifest is None:
            continue
        results[service] = type(
            "ShardStub",
            (),
            {"manifest": manifest, "operation_docs": docs, "inverted_buckets": {}},
        )()
    return results


def _group_specs(items: list[tuple[str, str, ControllerSpecModel]]) -> dict[str, list[tuple[str, ControllerSpecModel]]]:
    results: dict[str, list[tuple[str, ControllerSpecModel]]] = defaultdict(list)
    for service, controller, spec in items:
        results[service].append((controller, spec))
    return results


def render_service_text(service_model: ServiceModel) -> str:
    from .service_io import render_service

    return render_service(service_model)


def render_spec_text(spec_model: ControllerSpecModel) -> str:
    from .spec_io import render_spec

    return render_spec(spec_model)


def _build_service_model(service_name: str, domain: str, provider_repo: Path, owner: str, existing: ServiceModel | None) -> ServiceModel:
    return ServiceModel(
        identity=ServiceIdentity(domain=domain, service=service_name),
        owner=ServiceOwner(name=owner),
        source=ServiceSource(repo=_display_repo(provider_repo)),
        target=ServiceTarget(
            type=existing.target.type if existing else "service-name",
            value=existing.target.value if existing else service_name,
            context_id_prefix=existing.target.context_id_prefix if existing else "",
        ),
        path_rules=ServicePathRules(
            path_prefix=existing.path_rules.path_prefix if existing else "",
            base_path_style=existing.path_rules.base_path_style if existing else "controller-base-plus-method-path",
            exceptions=list(existing.path_rules.exceptions) if existing else [],
        ),
    )


def _resolve_service_owner(existing: ServiceModel | None, explicit_owner: str | None) -> str:
    if explicit_owner:
        return explicit_owner
    if existing is not None and existing.owner.name:
        return existing.owner.name
    if _can_prompt():
        owner = input("请输入当前 service owner: ").strip()
        if owner:
            return owner
    raise ProviderSyncError("缺少 service owner。首次接入服务时请提供 --service-owner，或在交互模式输入 owner。")


def _build_controller_spec(
    provider_repo: Path,
    controller_file: Path,
    controller_source: str,
    service_name: str,
    domain: str,
    existing_spec: ControllerSpecModel | None,
    reserved_operation_ids: set[str],
) -> ControllerSpecModel | None:
    controller_name = controller_file.stem
    base_path = _extract_controller_base_path(controller_source)
    existing_methods = {item.source.method_name: item for item in (existing_spec.methods if existing_spec else [])}
    parsed_methods = _parse_methods(controller_source)
    if not parsed_methods:
        raise ProviderSyncError(f"No supported controller methods found in {controller_file}")
    methods: list[MethodModel] = []
    used_operation_ids: set[str] = set(reserved_operation_ids)
    for parsed in parsed_methods:
        if parsed["ignored"]:
            continue
        existing_method = existing_methods.get(parsed["name"])
        request_types = _collect_type_schemas(provider_repo, parsed["body"]) if parsed["body"] else []
        for part in parsed["parts"]:
            if not _is_scalar_type(part["type"]):
                request_types.extend(_collect_type_schemas(provider_repo, part["type"]))
        for query_object in parsed["query_objects"]:
            if not _is_scalar_type(query_object["type"]):
                request_types.extend(_collect_type_schemas(provider_repo, query_object["type"]))
        request_types = _dedupe_types(request_types)
        response_envelope = parsed["response_envelope"]
        response_type = _normalize_response_type(parsed["response"])
        response_types = _collect_type_schemas(provider_repo, response_type)
        summary = _extract_summary(parsed["comment"], parsed["name"], parsed["http_method"], parsed["path"], parsed["body"], response_type)
        description = _description_for(parsed["comment"], summary, parsed["name"], parsed["http_method"], parsed["path"], parsed["body"], response_type)
        operation_id = _resolve_operation_id(
            domain=domain,
            controller_name=controller_name,
            method_name=parsed["name"],
            existing_method=existing_method,
            used_operation_ids=used_operation_ids,
        )
        methods.append(
            MethodModel(
                identity=MethodIdentity(operation_id=operation_id),
                semantic=MethodSemantic(summary=summary, description=description),
                search=MethodSearch(
                    intent_aliases=_intent_aliases_for(summary, parsed["name"], parsed["path"], parsed["body"], response_type, parsed["headers"], parsed["path_params"], parsed["query_params"], parsed["parts"]),
                    tags=_tags_for(parsed["name"], parsed["path"], parsed["body"], response_type),
                ),
                protocol=MethodProtocol(http_method=parsed["http_method"], path=parsed["path"]),
                request=RequestModel(
                    headers=_to_params(parsed["headers"]),
                    path_params=_to_params(parsed["path_params"]),
                    query_params=_to_params(parsed["query_params"]),
                    query_objects=_to_params(parsed["query_objects"]),
                    parts=_to_params(parsed["parts"]),
                    body=RequestBodyModel(
                        type=parsed["body"],
                        required=bool(parsed.get("body_required", False)),
                        description=_request_description(
                            parsed["name"],
                            parsed["body"],
                            bool(parsed.get("body_required", False)),
                        )
                        if parsed["body"]
                        else None,
                    ),
                ),
                response=ResponseModel(
                    envelope_type=existing_method.response.envelope_type if existing_method else response_envelope,
                    data_type=response_type,
                    description=_response_description(
                        parsed["comment"],
                        summary,
                        parsed["name"],
                        parsed["http_method"],
                        parsed["path"],
                        response_type,
                        str(parsed.get("response_kind", "")),
                    ),
                ),
                schemas=MethodSchemas(request_types=request_types, response_types=response_types),
                errors=_extract_method_errors(provider_repo, controller_source, parsed["body_text"])
                or (list(existing_method.errors) if existing_method else []),
                source=MethodSourceModel(
                    class_name=controller_name,
                    method_name=parsed["name"],
                    signature=_signature_for(parsed["name"], parsed["signature_params"]),
                ),
            )
        )
    if not methods:
        return None
    return ControllerSpecModel(
        domain=domain,
        service=service_name,
        controller=ControllerMeta(
            name=controller_name,
            base_path=base_path,
            source=ControllerSource(repo=_display_repo(provider_repo), file=str(controller_file.relative_to(provider_repo))),
        ),
        methods=methods,
    )


def _resolve_operation_id(
    domain: str,
    controller_name: str,
    method_name: str,
    existing_method: MethodModel | None,
    used_operation_ids: set[str],
) -> str:
    generated = f"{domain}.innerapi.aiAgent.{method_name}"
    controller_qualified = f"{domain}.innerapi.aiAgent.{_controller_operation_segment(controller_name)}.{method_name}"
    candidates = [existing_method.operation_id] if existing_method else []
    candidates.append(generated)
    candidates.append(controller_qualified)
    for candidate in candidates:
        if candidate not in used_operation_ids:
            used_operation_ids.add(candidate)
            return candidate
    suffix = 2
    while True:
        candidate = f"{generated}{suffix}"
        if candidate not in used_operation_ids:
            used_operation_ids.add(candidate)
            return candidate
        suffix += 1


def _collect_reserved_operation_ids(store: ContractStore, service_name: str, current_controller: str) -> set[str]:
    reserved: set[str] = set()
    for service, controller, spec in store.iter_all_specs():
        if service != service_name or controller == current_controller:
            continue
        reserved.update(method.identity.operation_id for method in spec.methods)
    return reserved


def _controller_operation_segment(controller_name: str) -> str:
    base = controller_name[:-10] if controller_name.endswith("Controller") else controller_name
    if not base:
        return "controller"
    return base[0].lower() + base[1:]


def _to_params(items: list[dict]) -> list[ParamModel]:
    return [ParamModel(name=str(i["name"]), type=str(i["type"]), required=bool(i["required"]), description=str(i.get("description", ""))) for i in items]


def _dedupe_types(items: list[TypeSchemaModel]) -> list[TypeSchemaModel]:
    results: list[TypeSchemaModel] = []
    seen: set[str] = set()
    for item in items:
        if item.name in seen:
            continue
        seen.add(item.name)
        results.append(item)
    return results


def _read_service_name(provider_repo: Path) -> str:
    bootstrap = provider_repo / "src" / "main" / "resources" / "bootstrap.properties"
    if bootstrap.exists():
        for line in bootstrap.read_text(encoding="utf-8").splitlines():
            if line.startswith("spring.application.name="):
                return line.split("=", 1)[1].strip()
    raise ProviderSyncError("Unable to determine service name from bootstrap.properties")


def _find_java_file(root: Path, fqcn: str) -> Path:
    relative = Path(*fqcn.split(".")).with_suffix(".java")
    direct = root / "src" / "main" / "java" / relative
    if direct.exists():
        return direct
    matches = list(root.rglob(relative.name))
    if not matches:
        raise ProviderSyncError(f"Missing java source for {fqcn}")
    return matches[0]


def _parse_type_schema(provider_repo: Path, type_name: str) -> tuple[TypeSchemaModel, str | None]:
    local_source = _find_local_type_source(provider_repo, type_name)
    if local_source is not None:
        source_path, source_type_name = local_source
        return _parse_type_schema_from_source(source_type_name, source_path.read_text(encoding="utf-8"))
    external_source = _load_type_source_from_sources_jar(type_name)
    if external_source is not None:
        return _parse_type_schema_from_source(type_name, external_source)
    raise ProviderSyncError(f"缺少类型源码: {type_name}")


def _collect_type_schemas(
    provider_repo: Path,
    type_name: str | None,
    seen: set[str] | None = None,
) -> list[TypeSchemaModel]:
    if not type_name or _is_scalar_type(type_name) or _is_type_variable(type_name):
        return []
    normalized = type_name.replace(" ", "")
    seen = set() if seen is None else set(seen)
    if normalized in seen:
        return []
    seen.add(normalized)
    if "<" in normalized and ">" in normalized:
        raw_type = _raw_generic_type(normalized)
        result: list[TypeSchemaModel] = []
        if raw_type in RESPONSE_SCHEMA_WRAPPER_TYPES:
            try:
                result.extend(_collect_type_schemas(provider_repo, raw_type, seen))
            except ProviderSyncError:
                pass
        elif raw_type not in GENERIC_WRAPPER_TYPES:
            try:
                result.extend(_collect_type_schemas(provider_repo, raw_type, seen))
            except ProviderSyncError:
                pass
        for arg in _generic_arguments(normalized):
            result.extend(_collect_type_schemas(provider_repo, arg, seen))
        return _dedupe_types(result)
    schema, parent = _parse_type_schema(provider_repo, type_name)
    result = []
    if parent and not _is_scalar_type(parent):
        try:
            result.extend(_collect_type_schemas(provider_repo, parent, seen))
        except ProviderSyncError:
            # External base classes such as company shared PageQuery should enrich the schema
            # when source is available, but should not block the whole controller sync if not.
            pass
    result.append(schema)
    for field in schema.fields:
        field_type = field.type
        if not field_type or _is_scalar_type(field_type) or _is_type_variable(field_type):
            continue
        try:
            result.extend(_collect_type_schemas(provider_repo, field_type, seen))
        except ProviderSyncError:
            continue
    return result


def _parse_type_schema_from_source(type_name: str, source: str) -> tuple[TypeSchemaModel, str | None]:
    class_name = type_name.split(".")[-1]
    class_source = _extract_class_source(source, class_name) or source
    extends_match = re.search(rf"class\s+{class_name}\s+extends\s+(?P<parent>\w+)", class_source)
    parent_type = extends_match.group("parent") if extends_match else None
    fields: list[FieldSchemaModel] = []
    record_match = re.search(rf"record\s+{re.escape(class_name)}\s*\((?P<components>[^)]*)\)", class_source)
    if record_match:
        for component in _split_params(record_match.group("components")):
            component_text = component.strip()
            if not component_text:
                continue
            component_match = re.match(r"(?P<type>[A-Za-z0-9_<>?,. ]+)\s+(?P<name>\w+)$", component_text)
            if not component_match:
                continue
            field_name = component_match.group("name")
            fields.append(
                FieldSchemaModel(
                    name=field_name,
                    type=component_match.group("type").replace(" ", ""),
                    required=False,
                    description=_infer_field_description(field_name) or "未提供说明",
                )
            )
    current_comment = ""
    constraints: list[str] = []
    in_class_body = False
    for raw_line in class_source.splitlines():
        line = raw_line.strip()
        if line.startswith("/**"):
            current_comment = ""
        elif _is_comment_terminator(line):
            continue
        elif line.startswith("*"):
            current_comment = (current_comment + line.lstrip("*").strip()).strip()
        elif re.search(r"\b(class|record)\b", line):
            in_class_body = True
            constraints = []
        elif line.startswith("@"):
            if in_class_body:
                constraints.append(line)
        elif re.match(r"private\s+[\w<>?,. ]+\s+\w+;", line):
            field_match = re.match(r"private\s+(?P<type>[\w<>?,. ]+)\s+(?P<name>\w+);", line)
            field_name = field_match.group("name")
            description = _field_description_from_sources(current_comment, constraints, field_name)
            fields.append(
                FieldSchemaModel(
                    name=field_name,
                    type=field_match.group("type").replace(" ", ""),
                    required=any(_annotation_name(item) in REQUIRED_FIELD_ANNOTATIONS for item in constraints),
                    constraints=constraints.copy(),
                    description=description,
                )
            )
            current_comment = ""
            constraints = []
        elif line and in_class_body and not line.startswith(("public", "private", "protected")):
            constraints = []
    if parent_type and not fields:
        fields.append(
            FieldSchemaModel(
                name="inheritance",
                type=parent_type,
                required=False,
                description=f"继承自 {parent_type}",
            )
        )
    return TypeSchemaModel(name=class_name, fields=fields), parent_type


def _annotation_name(annotation: str) -> str:
    return annotation.split("(", 1)[0].strip()


def _find_imported_fqcn(provider_repo: Path, type_name: str) -> str | None:
    for file_path in provider_repo.rglob("*.java"):
        text = file_path.read_text(encoding="utf-8")
        if re.search(rf"\b(?:class|record|enum)\s+{re.escape(type_name)}\b", text):
            package = re.search(r"package\s+([a-zA-Z0-9_.]+);", text)
            if package:
                return f"{package.group(1)}.{type_name}"
    return None


def _find_local_type_source(provider_repo: Path, type_name: str) -> tuple[Path, str] | None:
    outer_type = type_name.split(".", 1)[0]
    local_fqcn = _find_imported_fqcn(provider_repo, outer_type)
    if local_fqcn is None:
        return None
    source_path = _find_java_file(provider_repo, local_fqcn)
    return source_path, type_name


def _maven_repo_root() -> Path:
    return Path.home() / ".m2" / "repository"


def _load_type_source_from_sources_jar(type_name: str) -> str | None:
    if type_name in _TYPE_SOURCE_CACHE:
        return _TYPE_SOURCE_CACHE[type_name]
    repository = _maven_repo_root()
    if not repository.exists():
        return None
    outer_type = type_name.split(".", 1)[0]
    for jar_path in repository.rglob("*-sources.jar"):
        try:
            with zipfile.ZipFile(jar_path) as archive:
                matches = [name for name in archive.namelist() if name.endswith(f"/{outer_type}.java")]
                if not matches:
                    continue
                with archive.open(matches[0]) as entry:
                    source = entry.read().decode("utf-8")
                    _TYPE_SOURCE_CACHE[type_name] = source
                    return source
        except zipfile.BadZipFile:
            continue
    binary_jar = _find_binary_jar_for_type(type_name)
    if binary_jar is not None:
        jar_path, class_entry = binary_jar
        source = _load_type_source_from_binary_jar(jar_path, class_entry)
        _TYPE_SOURCE_CACHE[type_name] = source
        return source
    _TYPE_SOURCE_CACHE[type_name] = None
    return None


def _find_binary_jar_for_type(type_name: str) -> tuple[Path, str] | None:
    if type_name in _TYPE_BINARY_JAR_CACHE:
        return _TYPE_BINARY_JAR_CACHE[type_name]
    repository = _maven_repo_root()
    if not repository.exists():
        _TYPE_BINARY_JAR_CACHE[type_name] = None
        return None
    if "." in type_name:
        outer_type, inner_type = type_name.split(".", 1)
        target_suffix = f"/{outer_type}${inner_type}.class"
    else:
        target_suffix = f"/{type_name}.class"
    for jar_path in repository.rglob("*.jar"):
        if jar_path.name.endswith("-sources.jar"):
            continue
        try:
            with zipfile.ZipFile(jar_path) as archive:
                for entry_name in archive.namelist():
                    if entry_name.endswith(target_suffix):
                        result = (jar_path, entry_name)
                        _TYPE_BINARY_JAR_CACHE[type_name] = result
                        return result
        except zipfile.BadZipFile:
            continue
    _TYPE_BINARY_JAR_CACHE[type_name] = None
    return None


def _load_type_source_from_binary_jar(binary_jar: Path, class_entry: str) -> str | None:
    sources_jar = binary_jar.with_name(binary_jar.name[:-4] + "-sources.jar")
    if not sources_jar.exists():
        _download_sources_jar_for_binary_jar(binary_jar, sources_jar)
    if not sources_jar.exists():
        return None
    source_entry = class_entry[:-6].split("$", 1)[0] + ".java"
    try:
        with zipfile.ZipFile(sources_jar) as archive:
            if source_entry not in archive.namelist():
                return None
            with archive.open(source_entry) as entry:
                return entry.read().decode("utf-8")
    except zipfile.BadZipFile:
        return None


def _download_sources_jar_for_binary_jar(binary_jar: Path, sources_jar: Path) -> None:
    repository = _maven_repo_root()
    try:
        relative_path = binary_jar.relative_to(repository)
    except ValueError:
        return
    source_relative = relative_path.with_name(binary_jar.name[:-4] + "-sources.jar").as_posix()
    sources_jar.parent.mkdir(parents=True, exist_ok=True)
    for base_url in SOURCE_JAR_BASE_URLS:
        source_url = base_url.rstrip("/") + "/" + source_relative
        try:
            with urllib.request.urlopen(source_url, timeout=8) as response:
                status = getattr(response, "status", 200)
                if status not in (None, 200):
                    continue
                sources_jar.write_bytes(response.read())
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            continue


def _normalize_response_type(text: str) -> str:
    normalized = text.strip().replace(" >", ">")
    if normalized == "?":
        return "Object"
    if "<?>" in normalized:
        return normalized.replace("<?>", "<Object>")
    return normalized


def _parse_return_type(return_type: str) -> tuple[str, str, str]:
    normalized = return_type.strip()
    compact = normalized.replace(" ", "")
    if compact == "void":
        return "", "void", ""
    if compact == "Response":
        return "Response", "Object", "raw"
    if compact.startswith("Response<") and compact.endswith(">"):
        inner = compact[len("Response<") : -1]
        if inner == "?":
            return "Response", "Object", "wildcard"
        if inner == "Object":
            return "Response", "Object", "object"
        return "Response", _normalize_response_type(inner), ""
    return "", _normalize_response_type(compact), ""


def _is_scalar_type(type_name: str) -> bool:
    primitives = {
        "String",
        "Long",
        "Integer",
        "Boolean",
        "Double",
        "Float",
        "BigDecimal",
        "Object",
        "Date",
        "LocalDate",
        "LocalDateTime",
        "int",
        "long",
        "boolean",
        "double",
        "float",
        "byte[]",
        "void",
    }
    normalized = type_name.replace(" ", "")
    if normalized in primitives:
        return True
    if "<" in normalized and ">" in normalized:
        raw_type = _raw_generic_type(normalized)
        generic_args = _generic_arguments(normalized)
        return raw_type in {"List", "Set", "Collection", "Optional"} and all(_is_scalar_type(arg) for arg in generic_args)
    return False


def _raw_generic_type(type_name: str) -> str:
    return type_name.split("<", 1)[0]


def _generic_arguments(type_name: str) -> list[str]:
    start = type_name.find("<")
    end = type_name.rfind(">")
    if start == -1 or end == -1 or end <= start:
        return []
    body = type_name[start + 1 : end]
    args: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "," and depth == 0:
            value = "".join(current).strip()
            if value:
                args.append(value)
            current = []
            continue
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        current.append(char)
    value = "".join(current).strip()
    if value:
        args.append(value)
    return args


def _extract_summary(comment: str, method_name: str, http_method: str, path: str, body_type: str | None, response_type: str) -> str:
    lines = _comment_lines(comment)
    if lines:
        return lines[0]
    action = _infer_action(method_name, http_method)
    target = _infer_target_label(path, body_type, response_type)
    return _build_summary(action, target)


def _description_for(
    comment: str,
    summary: str,
    method_name: str,
    http_method: str,
    path: str,
    body_type: str | None,
    response_type: str,
) -> str:
    lines = _comment_lines(comment)
    if lines:
        return _join_comment_lines(lines[1:]) if len(lines) > 1 else summary
    action = _infer_action(method_name, http_method)
    target = _infer_target_label(path, body_type, response_type)
    return _build_description(action, target)


def _request_description(method_name: str, body_type: str | None, required: bool) -> str:
    if _is_dynamic_body_type(body_type):
        required_text = "必填" if required else "可选"
        return f"动态对象，非固定 schema（{required_text}）"
    readable = "".join(_split_identifier(method_name))
    return f"{readable or method_name} 请求体"


def _response_description(
    comment: str,
    summary: str,
    method_name: str,
    http_method: str,
    path: str,
    response_type: str,
    response_kind: str = "",
) -> str:
    if response_kind in {"raw", "wildcard"}:
        return "响应体未显式声明，按通用对象处理"
    if response_kind == "object":
        return "通用对象返回结果"
    if _comment_lines(comment):
        return _response_description_from_summary(summary)
    action = _infer_action(method_name, http_method)
    target = _infer_target_label(path, None, response_type)
    return _build_response_description(action, target)


def _intent_aliases_for(summary: str, method_name: str, path: str, body_type: str | None, response_type: str, headers: list[dict], path_params: list[dict], query_params: list[dict], parts: list[dict]) -> list[str]:
    aliases = [summary, method_name, response_type]
    if body_type:
        aliases.append(body_type)
    aliases.extend(_path_tokens(path))
    aliases.extend(item["name"] for item in [*headers, *path_params, *query_params, *parts])
    aliases.extend(_split_identifier(method_name))
    return _clean_search_values(aliases)


def _tags_for(method_name: str, path: str, body_type: str | None, response_type: str) -> list[str]:
    tags = [method_name, *list(_path_tokens(path))]
    if body_type:
        tags.append(body_type)
    if response_type:
        tags.append(response_type.replace("List<", "").replace(">", ""))
    return _clean_search_values(tags)


def _infer_action(method_name: str, http_method: str) -> str:
    lowered = method_name.lower()
    if lowered in {"query", "list", "page", "search", "find"} or "query" in lowered or lowered.endswith("list"):
        return "查询列表"
    if lowered in {"detail", "get", "info", "load"}:
        return "查询详情"
    if lowered in {"create", "add", "save"}:
        return "新增"
    if lowered in {"update", "edit", "modify"}:
        return "更新"
    if lowered in {"delete", "remove", "cancel"}:
        return "删除"
    if lowered in {"send", "push"} or lowered.startswith("send") or lowered.startswith("push"):
        return "发送"
    if "callback" in lowered or "notify" in lowered:
        return "接收"
    if lowered in {"execute", "run", "submit", "start"}:
        return "执行"
    if http_method == "GET":
        return "查询"
    if http_method == "POST":
        return "提交"
    if http_method == "PUT":
        return "更新"
    if http_method == "DELETE":
        return "删除"
    return "执行"


def _infer_target_label(path: str, body_type: str | None, response_type: str) -> str:
    path_tokens = _path_tokens(path)
    if path_tokens:
        label = "".join(_translate_token(token) for token in path_tokens[-2:])
        if label:
            return label
    for candidate in (body_type, response_type):
        label = _humanize_type_name(candidate)
        if label:
            return label
    return "对象"


def _humanize_type_name(type_name: str | None) -> str:
    if not type_name:
        return ""
    cleaned = type_name.replace("List<", "").replace(">", "")
    cleaned = re.sub(r"(DTO|VO|DO|BO|Query|Request|Response)$", "", cleaned)
    tokens = _split_identifier(cleaned)
    translated = "".join(_translate_token(token) for token in tokens)
    return translated or cleaned


def _split_identifier(value: str) -> list[str]:
    value = re.sub(r"call\s*back", "Callback", value, flags=re.IGNORECASE)
    value = re.sub(r"dynamicsql", "DynamicSql", value, flags=re.IGNORECASE)
    value = re.sub(r"tmpposition", "TmpPosition", value, flags=re.IGNORECASE)
    return re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", value)


def _path_tokens(path: str) -> list[str]:
    return [
        token
        for token in path.strip("/").split("/")
        if token and not token.startswith("{") and not _is_low_value_search_value(token)
    ]


def _translate_token(token: str) -> str:
    mapping = {
        "task": "任务",
        "record": "记录",
        "records": "记录",
        "workflow": "工作流",
        "execute": "执行",
        "detail": "详情",
        "query": "查询",
        "user": "用户",
        "admin": "管理员",
        "log": "日志",
        "notify": "通知",
        "callback": "回调",
        "send": "发送",
        "push": "推送",
        "login": "登录",
        "register": "注册",
        "sms": "短信",
        "message": "消息",
        "role": "角色",
        "current": "当前",
        "list": "列表",
        "tmp": "临时",
        "position": "岗位",
        "dynamic": "动态",
        "sql": "查询",
    }
    if re.search(r"[\u4e00-\u9fff]", token):
        return token
    return mapping.get(token.lower(), token.capitalize())


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _signature_for(method_name: str, signature_params: list[dict]) -> str:
    joined = ", ".join(f"{item['type']} {item['name']}" for item in signature_params)
    return f"{method_name}({joined})"


def _clean_comment(block: str) -> str:
    return _join_comment_lines(_comment_lines(block))


def _comment_lines(block: str) -> list[str]:
    cleaned_lines: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "/**" or _is_comment_terminator(stripped):
            continue
        stripped = stripped.lstrip("*").replace("*/", "").strip()
        stripped = re.sub(r"</?[^>]+>", "", stripped).strip()
        stripped = re.sub(r"/+$", "", stripped).strip()
        stripped = _normalize_comment_line(stripped)
        if not stripped or stripped.startswith("@") or _is_comment_metadata_line(stripped):
            continue
        cleaned_lines.append(stripped)
    return cleaned_lines


def _normalize_comment_line(line: str) -> str:
    normalized = re.sub(r"^\d{3,4}[\s:：._-]*", "", line).strip()
    return re.sub(r"\s+", " ", normalized)


def _is_comment_metadata_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return True
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return True
    if any(lowered.startswith(prefix) for prefix in COMMENT_METADATA_PREFIXES):
        return True
    return "http://" in lowered or "https://" in lowered


def _build_summary(action: str, target: str) -> str:
    if action == "查询列表":
        return target if target.endswith("列表") else f"查询{target}列表"
    if action == "查询详情":
        return target if target.endswith("详情") else f"查询{target}详情"
    if action == "接收":
        return f"接收{target}"
    if action == "查询":
        return f"查询{target}"
    if action == "提交":
        return f"提交{target}"
    return f"{action}{target}"


def _build_description(action: str, target: str) -> str:
    if action == "查询列表":
        return target if target.endswith("列表") else f"查询{target}列表"
    if action == "查询详情":
        return target if target.endswith("详情") else f"查询{target}详情"
    if action == "接收":
        return f"接收{target}请求"
    if action == "查询":
        return f"查询{target}信息"
    if action == "提交":
        return f"提交{target}请求"
    if action in {"发送", "推送"}:
        return f"{action}{target}"
    return f"{action}{target}"


def _build_response_description(action: str, target: str) -> str:
    if action == "查询列表":
        return target if target.endswith("列表") else f"{target}列表"
    if action == "查询详情":
        return target if target.endswith("详情") else f"{target}详情"
    if action == "接收":
        return f"{target}结果"
    if action in {"查询", "提交", "执行", "发送", "推送", "新增", "更新", "删除"}:
        return f"{target}结果"
    return f"{target}信息"


def _response_description_from_summary(summary: str) -> str:
    if not summary:
        return "结果"
    if summary.startswith("分页查询") and len(summary) > len("分页查询"):
        target = summary[len("分页查询") :].strip()
        if target:
            return f"{target}分页结果"
    if summary.startswith("查询") and len(summary) > len("查询"):
        target = summary[len("查询") :].strip()
        if target.endswith(("详情", "列表", "信息")):
            return target
    if summary.endswith(("列表", "详情", "结果", "信息")):
        return summary
    return f"{summary}结果"


def _clean_search_values(values: list[str]) -> list[str]:
    return _dedupe_strings([value for value in values if not _is_low_value_search_value(value)])


def _is_low_value_search_value(value: str) -> bool:
    normalized = str(value).strip()
    if not normalized:
        return True
    compact = re.sub(r"[\s_\-/]+", "", normalized).lower()
    if not compact or compact in LOW_VALUE_SEARCH_TERMS:
        return True
    return compact.isdigit()


def _is_comment_terminator(line: str) -> bool:
    return re.fullmatch(r"\*+/", line) is not None


def _join_comment_lines(lines: list[str]) -> str:
    result = ""
    for line in lines:
        if not result:
            result = line
            continue
        if _needs_comment_space(result[-1], line[0]):
            result += " " + line
        else:
            result += line
    return result.strip()


def _needs_comment_space(left: str, right: str) -> bool:
    return left.isascii() and right.isascii() and left.isalnum() and right.isalnum()


def _extract_class_source(source: str, class_name: str) -> str | None:
    match = re.search(rf"\bclass\s+{re.escape(class_name)}\b[^\{{]*\{{", source)
    if not match:
        return None
    start = match.start()
    brace_start = source.find("{", match.start())
    if brace_start == -1:
        return None
    depth = 0
    for index in range(brace_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    return source[start:]


def _infer_field_description(field_name: str) -> str:
    return COMMON_FIELD_DESCRIPTION_MAP.get(field_name, "")


def _display_repo(provider_repo: Path) -> str:
    return str(provider_repo)


def _sync_ignored_controller(
    service_name: str,
    controller_name: str,
    store: ContractStore,
    service_model: ServiceModel | None,
) -> ProviderSyncResult:
    spec_path = store.get_controller_spec_file(service_name, controller_name)
    doc_path = store.get_controller_doc_file(service_name, controller_name)
    if service_model is None:
        store.write_batch({}, [spec_path, doc_path], commit_message=f"Ignore {service_name}/{controller_name} API contracts")
        return ProviderSyncResult(
            status="ignored",
            service_file=store.get_service_file(service_name),
            spec_file=spec_path,
            doc_file=doc_path,
        )
    all_specs = _group_specs(store.iter_all_specs())
    remaining_specs = [spec for name, spec in all_specs.get(service_name, []) if name != controller_name]
    upserts, extra_deletes = _build_service_index_payload(store, service_model, remaining_specs)
    store.write_batch(
        upserts,
        [spec_path, doc_path, *extra_deletes],
        commit_message=f"Ignore {service_name}/{controller_name} API contracts",
    )
    return ProviderSyncResult(
        status="ignored",
        service_file=store.get_service_file(service_name),
        spec_file=spec_path,
        doc_file=doc_path,
    )


def _class_is_contract_ignored(controller_source: str) -> bool:
    class_match = re.search(r"\bpublic\s+class\s+\w+\b", controller_source)
    if not class_match:
        return False
    prefix = controller_source[: class_match.start()]
    start = prefix.rfind("/**")
    start = max(start, prefix.rfind("\n\n"))
    annotation_block = prefix[start + 1 :] if start >= 0 else prefix
    return _contains_ignore_annotation(annotation_block)


def _contains_ignore_annotation(text: str) -> bool:
    return re.search(rf"@(?:[\w.]+\.)?{IGNORE_CONTRACT_ANNOTATION}\b", text) is not None


def _can_prompt() -> bool:
    if sys.stdin is None or sys.stdin.closed:
        return False
    if sys.stdin.isatty():
        return True
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    return bool(ready)


def _parse_methods(controller_source: str) -> list[dict[str, object]]:
    lines = controller_source.splitlines()
    methods: list[dict[str, object]] = []
    comment_lines: list[str] = []
    annotation_lines: list[str] = []
    capturing_comment = False
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if stripped.startswith("/**"):
            capturing_comment = True
            comment_lines = [raw_line]
            index += 1
            continue
        if capturing_comment:
            comment_lines.append(raw_line)
            if stripped.endswith("*/"):
                capturing_comment = False
            index += 1
            continue
        if stripped.startswith("@") and not _contains_mapping_annotation(stripped):
            annotation_lines.append(raw_line)
            index += 1
            continue
        if comment_lines and stripped and not stripped.startswith("@") and not _contains_mapping_annotation(stripped):
            comment_lines = []
            annotation_lines = []
        if _contains_mapping_annotation(stripped):
            mapping_lines = [raw_line]
            while "(" in mapping_lines[0] and ")" not in mapping_lines[-1]:
                index += 1
                mapping_lines.append(lines[index])
            mapping_text = " ".join(item.strip() for item in mapping_lines)
            annotation_text = " ".join(item.strip() for item in annotation_lines)
            http_method = _extract_http_method(mapping_text)
            path_value = _extract_mapping_path(mapping_text)
            if http_method is None or path_value is None:
                raise ProviderSyncError("Unsupported mapping format")
            signature_lines: list[str] = []
            index += 1
            while index < len(lines):
                candidate = lines[index]
                signature_lines.append(candidate)
                if "{" in candidate:
                    break
                index += 1
            signature_text = re.sub(r"\s+", " ", " ".join(item.strip() for item in signature_lines))
            signature_match = re.search(
                r"(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?P<return_type>(?!class\b|record\b|interface\b)[A-Za-z0-9_<>?,.\[\] ]+?)\s+(?P<name>\w+)\s*\(",
                signature_text,
            )
            if not signature_match:
                if re.search(r"\bclass\b", signature_text):
                    comment_lines = []
                    index += 1
                    continue
                raise ProviderSyncError("Unsupported method signature")
            body_text, index = _consume_method_block(lines, index, signature_lines)
            response_envelope, response_type, response_kind = _parse_return_type(signature_match.group("return_type"))
            params_text = _extract_method_params(signature_text, signature_match.end() - 1)
            parsed_params = _parse_signature_params(params_text)
            methods.append(
                {
                    "comment": "\n".join(comment_lines),
                    "ignored": _contains_ignore_annotation(annotation_text),
                    "path": path_value,
                    "http_method": http_method,
                    "response_envelope": response_envelope,
                    "response": response_type,
                    "response_kind": response_kind,
                    "body_text": body_text,
                    "name": signature_match.group("name"),
                    "body": parsed_params["body"]["type"] if parsed_params["body"] else None,
                    "body_required": parsed_params["body"]["required"] if parsed_params["body"] else False,
                    "headers": parsed_params["headers"],
                    "path_params": parsed_params["path_params"],
                    "query_params": parsed_params["query_params"],
                    "query_objects": parsed_params["query_objects"],
                    "parts": parsed_params["parts"],
                    "signature_params": parsed_params["signature_params"],
                }
            )
            comment_lines = []
            annotation_lines = []
        index += 1
    return methods


def _extract_mapping_path(mapping_text: str) -> str | None:
    named_match = re.search(r'(?:value|path)\s*=\s*"(?P<path>[^"]+)"', mapping_text)
    if named_match:
        return named_match.group("path")
    literal_match = re.search(r'(?:[\w.]+\.)?Mapping\s*\(\s*"(?P<path>[^"]+)"', mapping_text)
    if literal_match:
        return literal_match.group("path")
    bare_shortcut_match = re.search(r"@(?:[\w.]+\.)?(?:Post|Get|Put|Delete|Patch)Mapping\b(?!\s*\()", mapping_text)
    if bare_shortcut_match:
        return ""
    bare_request_mapping_match = re.search(r"@(?:[\w.]+\.)?RequestMapping\b(?!\s*\()", mapping_text)
    if bare_request_mapping_match:
        return ""
    return None


def _extract_http_method(mapping_text: str) -> str | None:
    shortcut_match = re.search(r"@(?:[\w.]+\.)?(?P<annotation>Post|Get|Put|Delete|Patch)Mapping\b", mapping_text)
    if shortcut_match:
        return shortcut_match.group("annotation").upper()
    request_mapping_match = re.search(r"@(?:[\w.]+\.)?RequestMapping\b", mapping_text)
    if not request_mapping_match:
        return None
    method_match = re.search(r"method\s*=\s*RequestMethod\.(?P<method>GET|POST|PUT|DELETE|PATCH)", mapping_text)
    if method_match:
        return method_match.group("method")
    return "REQUEST"


def _extract_controller_base_path(controller_source: str) -> str:
    controller_request_mapping = re.search(r"@(?:[\w.]+\.)?RequestMapping\s*\((?P<args>[^)]*)\)", controller_source, re.DOTALL)
    if not controller_request_mapping:
        return ""
    path_value = _extract_mapping_path(controller_request_mapping.group(0))
    if not path_value:
        return ""
    return path_value


def _contains_mapping_annotation(text: str) -> bool:
    return re.search(r"@(?:[\w.]+\.)?(?:Post|Get|Put|Delete|Patch)?Request?Mapping\b|@(?:[\w.]+\.)?(?:Post|Get|Put|Delete|Patch)Mapping\b", text) is not None


def _extract_method_params(signature_text: str, opening_paren_index: int) -> str:
    depth = 0
    chars: list[str] = []
    for char in signature_text[opening_paren_index + 1 :]:
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        chars.append(char)
    return "".join(chars)


def _consume_method_block(lines: list[str], start_index: int, signature_lines: list[str]) -> tuple[str, int]:
    block_lines = list(signature_lines)
    depth = sum(line.count("{") - line.count("}") for line in signature_lines)
    current_index = start_index
    while depth > 0 and current_index + 1 < len(lines):
        current_index += 1
        line = lines[current_index]
        block_lines.append(line)
        depth += line.count("{") - line.count("}")
    return "\n".join(block_lines), current_index


def _parse_signature_params(params_text: str) -> dict[str, object]:
    body = None
    headers: list[dict] = []
    path_params: list[dict] = []
    query_params: list[dict] = []
    parts: list[dict] = []
    query_objects: list[dict] = []
    signature_params: list[dict] = []
    for raw in _split_params(params_text):
        cleaned = " ".join(raw.strip().split())
        if not cleaned:
            continue
        plain_param = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", cleaned).strip()
        param_match = re.search(r"(?P<type>[A-Za-z0-9_<>?,. ]+?)\s+(?P<name>\w+)$", plain_param)
        if not param_match:
            continue
        param_type = param_match.group("type").replace(" ", "")
        param_name = param_match.group("name")
        signature_params.append({"type": param_type, "name": param_name})
        if "@RequestBody" in cleaned:
            required = "required = false" not in cleaned and "required=false" not in cleaned
            body = {"type": param_type, "name": param_name, "required": required}
        elif "@PathVariable" in cleaned:
            path_params.append({"name": param_name, "type": param_type, "required": True, "description": ""})
        elif "@RequestParam" in cleaned:
            required = (
                "required = false" not in cleaned
                and "required=false" not in cleaned
                and "defaultValue" not in cleaned
            )
            description = _build_param_description(cleaned, param_type)
            item = {"name": param_name, "type": param_type, "required": required, "description": description}
            if _is_file_type(param_type):
                if not description:
                    item["description"] = "文件上传字段"
                parts.append(item)
            else:
                query_params.append(item)
        elif "@RequestHeader" in cleaned:
            headers.append(
                {
                    "name": param_name,
                    "type": param_type,
                    "required": True,
                    "description": _build_param_description(cleaned, param_type),
                }
            )
        elif "@RequestPart" in cleaned:
            parts.append(
                {
                    "name": param_name,
                    "type": param_type,
                    "required": True,
                    "description": _build_part_description(param_type, cleaned),
                }
            )
        elif _is_infrastructure_type(param_type):
            continue
        elif not _is_scalar_type(param_type):
            query_objects.append(
                {
                    "name": param_name,
                    "type": param_type,
                    "required": False,
                    "description": "按 query object 参与请求",
                }
            )
    return {
        "body": body,
        "headers": headers,
        "path_params": path_params,
        "query_params": query_params,
        "parts": parts,
        "query_objects": query_objects,
        "signature_params": signature_params,
    }


def _split_params(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _build_param_description(raw_text: str, param_type: str) -> str:
    details: list[str] = []
    constraints = _extract_validation_constraints(raw_text)
    if constraints:
        details.append("约束: " + ", ".join(constraints))
    default_value = _extract_default_value(raw_text)
    if default_value is not None:
        details.append(f"defaultValue={default_value}")
    if _is_file_type(param_type):
        details.append("文件上传字段")
    return "; ".join(details)


def _build_part_description(param_type: str, raw_text: str) -> str:
    if _is_file_type(param_type):
        return "文件上传字段"
    return _build_param_description(raw_text, param_type)


def _extract_validation_constraints(raw_text: str) -> list[str]:
    return re.findall(
        r"@(?:NotBlank|NotNull|NotEmpty|Size|Length|Pattern|Min|Max|Valid|Validated)\b(?:\([^)]*\))?",
        raw_text,
    )


def _extract_default_value(raw_text: str) -> str | None:
    match = re.search(r'defaultValue\s*=\s*"([^"]*)"', raw_text)
    if match:
        return match.group(1)
    return None


def _is_file_type(type_name: str) -> bool:
    normalized = type_name.replace(" ", "")
    return normalized in {"MultipartFile", "MultipartFile[]", "MultipartFile..."}


def _is_dynamic_body_type(type_name: str | None) -> bool:
    if not type_name:
        return False
    normalized = type_name.replace(" ", "")
    return normalized in {"Map<String,Object>", "JSONObject", "JsonObject"}


def _is_infrastructure_type(type_name: str) -> bool:
    normalized = type_name.replace(" ", "")
    return normalized in {"HttpServletRequest", "HttpServletResponse"}


def _field_description_from_sources(comment: str, constraints: list[str], field_name: str) -> str:
    if comment:
        return comment
    annotation_description = _extract_field_annotation_description(constraints)
    if annotation_description:
        return annotation_description
    inferred = _infer_field_description(field_name)
    if inferred:
        return inferred
    return "未提供说明"


def _extract_field_annotation_description(constraints: list[str]) -> str:
    for annotation in constraints:
        schema_match = re.search(r'description\s*=\s*"([^"]+)"', annotation)
        if schema_match:
            return schema_match.group(1).strip()
        model_match = re.search(r'@ApiModelProperty\(\s*(?:value\s*=\s*)?"([^"]+)"', annotation)
        if model_match:
            return model_match.group(1).strip()
    return ""


def _is_type_variable(type_name: str) -> bool:
    normalized = type_name.replace(" ", "")
    return re.fullmatch(r"[A-Z]", normalized) is not None


_DEPENDENCY_IMPL_CACHE: dict[tuple[str, str], Path | None] = {}


def _extract_method_errors(provider_repo: Path, controller_source: str, method_block: str) -> list[MethodErrorModel]:
    errors: list[MethodErrorModel] = []
    seen: set[tuple[str, str, str]] = set()
    _collect_business_exception_errors(method_block, seen, errors, "直接抛出 BusinessException")
    _collect_response_error_returns(method_block, seen, errors)
    _collect_service_hop_errors(provider_repo, controller_source, method_block, seen, errors)
    return errors


def _collect_business_exception_errors(
    method_block: str,
    seen: set[tuple[str, str, str]],
    errors: list[MethodErrorModel],
    when: str,
) -> None:
    for meaning in re.findall(r'throw\s+new\s+BusinessException\(\s*"([^"]+)"\s*\)', method_block):
        _append_method_error(errors, seen, "BUSINESS_EXCEPTION", meaning.strip(), when)
    for code, meaning in re.findall(
        r'throw\s+new\s+BusinessException\(\s*([A-Za-z0-9_.]+)\s*(?:,\s*"([^"]+)")?\s*\)',
        method_block,
    ):
        normalized_code = code.strip()
        normalized_meaning = meaning.strip() if meaning.strip() else normalized_code
        _append_method_error(errors, seen, normalized_code, normalized_meaning, when)


def _collect_response_error_returns(
    method_block: str,
    seen: set[tuple[str, str, str]],
    errors: list[MethodErrorModel],
) -> None:
    for meaning in re.findall(r'Response\.error\(\s*"([^"]+)"\s*\)', method_block):
        _append_method_error(errors, seen, "BUSINESS_EXCEPTION", meaning.strip(), "返回 Response.error")
    for code in re.findall(r"Response\.error\(\s*([A-Za-z0-9_.]+)\s*\)", method_block):
        normalized_code = code.strip()
        _append_method_error(errors, seen, normalized_code, normalized_code, "返回 Response.error")


def _collect_service_hop_errors(
    provider_repo: Path,
    controller_source: str,
    method_block: str,
    seen: set[tuple[str, str, str]],
    errors: list[MethodErrorModel],
) -> None:
    dependency_types = _extract_dependency_types(controller_source)
    if not dependency_types:
        return
    processed_calls: set[tuple[str, str]] = set()
    for dependency_name, method_name in re.findall(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(", method_block):
        dependency_type = dependency_types.get(dependency_name)
        if not dependency_type:
            continue
        call_key = (dependency_type, method_name)
        if call_key in processed_calls:
            continue
        processed_calls.add(call_key)
        impl_file = _find_dependency_impl_file(provider_repo, dependency_type)
        if impl_file is None:
            continue
        service_source = impl_file.read_text(encoding="utf-8")
        service_method_block = _extract_named_method_block(service_source, method_name)
        if not service_method_block:
            continue
        _collect_business_exception_errors(
            service_method_block,
            seen,
            errors,
            f"调用 {dependency_type}.{method_name} 时抛出 BusinessException",
        )


def _append_method_error(
    errors: list[MethodErrorModel],
    seen: set[tuple[str, str, str]],
    code: str,
    meaning: str,
    when: str,
) -> None:
    item = (code, meaning, when)
    if item in seen:
        return
    seen.add(item)
    errors.append(MethodErrorModel(code=code, meaning=meaning, when=when))


def _extract_dependency_types(source: str) -> dict[str, str]:
    dependency_types: dict[str, str] = {}
    for type_name, name in re.findall(
        r"private\s+(?:final\s+)?([A-Za-z_][A-Za-z0-9_$.<>]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;",
        source,
    ):
        dependency_types[name] = type_name.split(".")[-1]
    return dependency_types


def _find_dependency_impl_file(provider_repo: Path, dependency_type: str) -> Path | None:
    cache_key = (str(provider_repo), dependency_type)
    if cache_key in _DEPENDENCY_IMPL_CACHE:
        return _DEPENDENCY_IMPL_CACHE[cache_key]
    impl_name = f"{dependency_type}Impl.java"
    matches = list(provider_repo.rglob(impl_name))
    if matches:
        _DEPENDENCY_IMPL_CACHE[cache_key] = matches[0]
        return matches[0]
    implements_pattern = re.compile(rf"\bimplements\b[^{{;]*\b{re.escape(dependency_type)}\b")
    for path in provider_repo.rglob("*.java"):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if implements_pattern.search(source):
            _DEPENDENCY_IMPL_CACHE[cache_key] = path
            return path
    _DEPENDENCY_IMPL_CACHE[cache_key] = None
    return None


def _extract_named_method_block(source: str, method_name: str) -> str | None:
    pattern = re.compile(rf"\b{re.escape(method_name)}\s*\(")
    for match in pattern.finditer(source):
        opening_brace = source.find("{", match.end())
        if opening_brace == -1:
            continue
        signature_slice = source[match.start() : opening_brace]
        if ";" in signature_slice:
            continue
        depth = 0
        for index in range(opening_brace, len(source)):
            char = source[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[match.start() : index + 1]
    return None
