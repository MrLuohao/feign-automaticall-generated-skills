from __future__ import annotations

from pathlib import Path
import re

from .consumer_local_rules import resolve_consumer_context
from .models import ControllerSpecModel, MethodModel, ResolvedConsumerContext, ServiceModel, TypeSchemaModel


def generate_java_feign(
    service: ServiceModel,
    spec: ControllerSpecModel,
    method: MethodModel,
    consumer_repo: Path,
) -> Path:
    context = resolve_consumer_context(consumer_repo, spec.domain)
    class_name = _client_class_name(spec.controller.name, context)
    context.placement.client_dir.mkdir(parents=True, exist_ok=True)
    context.placement.dto_dir.mkdir(parents=True, exist_ok=True)
    context.placement.support_dir.mkdir(parents=True, exist_ok=True)
    _write_dto_files(method, context)
    path = context.placement.client_dir / f"{class_name}.java"
    content = _render_java_client(service, spec, method, context, class_name)
    path.write_text(content, encoding="utf-8")
    return path


def _render_java_client(
    service: ServiceModel,
    spec: ControllerSpecModel,
    method: MethodModel,
    context: ResolvedConsumerContext,
    class_name: str,
) -> str:
    imports = [
        "import com.dst.steed.common.domain.response.Response;",
        "import org.springframework.cloud.openfeign.FeignClient;",
    ]
    imports.extend(_annotation_imports(method))
    for type_name in _ordered_java_types(method):
        if type_name in _local_type_names(method):
            imports.append(f"import {context.placement.dto_package}.{type_name};")
    imports = _dedupe(imports)
    return f"""package {context.placement.client_package};

{chr(10).join(imports)}

@FeignClient(name = "{service.target.value}", contextId = "{_context_id(service, class_name)}")
public interface {class_name} {{

    /**
     * {method.semantic.summary}
     *
     * {method.semantic.description or "无"}
     */
    @{_mapping_annotation(method)}("{_full_path(service, spec, method)}")
    {_return_type(method)} {method.source.method_name}({_java_parameters(method)});
}}
"""


def _write_dto_files(method: MethodModel, context: ResolvedConsumerContext) -> None:
    for schema in [*method.schemas.request_types, *method.schemas.response_types]:
        path = context.placement.dto_dir / f"{schema.name}.java"
        imports = _dto_imports(schema, context)
        lines = [f"package {context.placement.dto_package};", ""]
        if imports:
            lines.extend(imports)
            lines.append("")
        if context.dto.use_lombok_data:
            lines.append("@Data")
        lines.append(f"public class {schema.name} {{")
        for field in schema.fields:
            if field.description:
                lines.extend(["    /**", f"     * {field.description}", "     */"])
            lines.append(f"    private {field.type} {field.name};")
            lines.append("")
        lines.append("}")
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _ordered_java_types(method: MethodModel) -> list[str]:
    names: list[str] = []
    if method.request.body.type:
        names.append(method.request.body.type)
    names.append(method.response.data_type)
    for item in [*method.request.headers, *method.request.path_params, *method.request.query_params, *method.request.parts]:
        names.append(item.type)
    return [item for item in _dedupe(names) if item and item[0].isupper()]


def _local_type_names(method: MethodModel) -> set[str]:
    return {item.name for item in [*method.schemas.request_types, *method.schemas.response_types]}


def _annotation_imports(method: MethodModel) -> list[str]:
    imports = [f"import org.springframework.web.bind.annotation.{_mapping_annotation(method)};"]
    if method.request.body.type:
        imports.append("import org.springframework.web.bind.annotation.RequestBody;")
    if method.request.path_params:
        imports.append("import org.springframework.web.bind.annotation.PathVariable;")
    if method.request.query_params:
        imports.append("import org.springframework.web.bind.annotation.RequestParam;")
    if method.request.headers:
        imports.append("import org.springframework.web.bind.annotation.RequestHeader;")
    if method.request.parts:
        imports.append("import org.springframework.web.bind.annotation.RequestPart;")
    return _dedupe(imports)


def _mapping_annotation(method: MethodModel) -> str:
    mapping = {
        "GET": "GetMapping",
        "POST": "PostMapping",
        "PUT": "PutMapping",
        "DELETE": "DeleteMapping",
    }
    return mapping.get(method.protocol.http_method.upper(), "RequestMapping")


def _java_parameters(method: MethodModel) -> str:
    params: list[str] = []
    for item in method.request.path_params:
        params.append(f'@PathVariable("{item.name}") {item.type} {item.name}')
    for item in method.request.query_params:
        required = str(item.required).lower()
        params.append(f'@RequestParam(value = "{item.name}", required = {required}) {item.type} {item.name}')
    for item in method.request.headers:
        required = str(item.required).lower()
        params.append(f'@RequestHeader(value = "{item.name}", required = {required}) {item.type} {item.name}')
    for item in method.request.parts:
        params.append(f'@RequestPart("{item.name}") {item.type} {item.name}')
    if method.request.body.type:
        params.append(f"@RequestBody {method.request.body.type} request")
    return ", ".join(params)


def _return_type(method: MethodModel) -> str:
    envelope = method.response.envelope_type
    if not envelope:
        return method.response.data_type or "void"
    if "<" in envelope:
        return envelope
    if not method.response.data_type or method.response.data_type == "void":
        return envelope
    return f"{envelope}<{method.response.data_type}>"


def _client_class_name(controller_name: str, context: ResolvedConsumerContext) -> str:
    base = controller_name[:-10] if controller_name.endswith("Controller") else controller_name
    return f"{base}{context.naming.client_suffix}"


def _context_id(service: ServiceModel, class_name: str) -> str:
    return f"{service.target.context_id_prefix}{class_name}" if service.target.context_id_prefix else class_name


def _full_path(service: ServiceModel, spec: ControllerSpecModel, method: MethodModel) -> str:
    parts = [service.path_rules.path_prefix, spec.controller.base_path, method.protocol.path]
    normalized = [item.strip("/") for item in parts if item and item.strip("/")]
    return "/" + "/".join(normalized)


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _dto_imports(schema: TypeSchemaModel, context: ResolvedConsumerContext) -> list[str]:
    imports: list[str] = []
    if context.dto.use_lombok_data:
        imports.append("import lombok.Data;")
    util_types: set[str] = set()
    for field in schema.fields:
        util_types.update(_java_util_imports_for_type(field.type))
    imports.extend(sorted(util_types))
    return imports


def _java_util_imports_for_type(type_name: str) -> set[str]:
    imports: set[str] = set()
    tokens = set(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", type_name))
    mapping = {
        "List": "import java.util.List;",
        "Map": "import java.util.Map;",
        "Set": "import java.util.Set;",
        "Date": "import java.util.Date;",
    }
    for token in tokens:
        statement = mapping.get(token)
        if statement:
            imports.add(statement)
    return imports
