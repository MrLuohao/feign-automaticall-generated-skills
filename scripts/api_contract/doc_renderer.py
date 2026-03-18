from __future__ import annotations

from pathlib import Path

from .models import ControllerSpecModel, ServiceModel, TypeSchemaModel


def render_doc(service: ServiceModel, spec: ControllerSpecModel) -> str:
    path_prefix = service.path_rules.path_prefix.strip()
    lines = [
        f"# {spec.controller.name} 接口文档",
        "",
        "## Controller 概览",
        "",
        "| 项目 | 说明 |",
        "|------|------|",
        f"| service | `{spec.service}` |",
        f"| domain | `{spec.domain}` |",
        f"| basePath | `{spec.controller.base_path}` |",
    ]
    if path_prefix:
        lines.append(f"| pathPrefix | `{path_prefix}` |")
    lines.extend(["", "## 方法摘要", "", "| operationId | 摘要 | 方法 | 路径 |", "|------|------|------|------|"])
    for method in spec.methods:
        lines.append(
            f"| `{method.identity.operation_id}` | {method.semantic.summary} | `{method.protocol.http_method}` | `{_full_path(service, spec, method.protocol.path)}` |"
        )
    for index, method in enumerate(spec.methods, start=1):
        lines.extend(
            [
                "",
                f"## {index}. {method.semantic.summary}",
                "",
                "### 基本信息",
                "",
                "| 项目 | 说明 |",
                "|------|------|",
                f"| operationId | `{method.identity.operation_id}` |",
                f"| method | `{method.protocol.http_method}` |",
                f"| path | `{_full_path(service, spec, method.protocol.path)}` |",
                f"| description | {method.semantic.description or '无'} |",
                "",
                "### 请求",
                "",
            ]
        )
        lines.extend(_render_request(method))
        lines.extend(
            [
                "",
                "### 响应",
                "",
                "| 项目 | 说明 |",
                "|------|------|",
                f"| envelopeType | `{method.response.envelope_type}` |",
                f"| dataType | `{method.response.data_type}` |",
                f"| description | {method.response.description or '无'} |",
                "",
                "### DTO 摘要",
                "",
            ]
        )
        lines.extend(_render_schemas(method.schemas.request_types, "Request Types"))
        lines.extend(_render_response_schemas(method))
        lines.extend(
            [
                "",
                "### 错误信息",
                "",
                "| 错误码 | 含义 | 触发条件 |",
                "|------|------|------|",
            ]
        )
        if not method.errors:
            lines.append("| 无 | 无 | 无 |")
        else:
            for error in method.errors:
                lines.append(f"| `{error.code}` | {error.meaning} | {error.when} |")
        lines.extend(
            [
                "",
                "### 源码定位",
                "",
                "| 项目 | 说明 |",
                "|------|------|",
                f"| className | `{method.source.class_name}` |",
                f"| methodName | `{method.source.method_name}` |",
                f"| signature | `{method.source.signature}` |",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def write_doc(service: ServiceModel, spec: ControllerSpecModel, output: Path) -> None:
    output.write_text(render_doc(service, spec), encoding="utf-8")


def _render_request(method) -> list[str]:
    lines: list[str] = []
    rendered_any = False
    for label, items in (
        ("headers", method.request.headers),
        ("pathParams", method.request.path_params),
        ("queryParams", method.request.query_params),
        ("parts", method.request.parts),
    ):
        if not items:
            continue
        rendered_any = True
        lines.append(f"#### {label}")
        lines.append("")
        lines.append("| 字段名 | 类型 | 必填 | 说明 |")
        lines.append("|------|------|------|------|")
        for item in items:
            required = "是" if item.required else "否"
            lines.append(f"| {item.name} | `{item.type}` | {required} | {item.description or '无'} |")
        lines.append("")
    if method.request.body.type:
        rendered_any = True
        lines.extend(
            [
                "#### body",
                "",
                "| 字段名 | 类型 | 必填 | 说明 |",
                "|------|------|------|------|",
                f"| requestBody | `{method.request.body.type}` | {'是' if method.request.body.required else '否'} | {method.request.body.description or '无'} |",
            ]
        )
    if not rendered_any:
        return ["- 无请求参数"]
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _render_schemas(items: list[TypeSchemaModel], label: str) -> list[str]:
    if not items:
        return [f"#### {label}", "", "- 无"]
    lines = [f"#### {label}", ""]
    for item in items:
        lines.append(f"#### {item.name}")
        lines.append("")
        if not item.fields:
            lines.append("- 无字段")
            continue
        lines.append("| 字段名 | 类型 | 必填 | 说明 | 约束 |")
        lines.append("|------|------|------|------|------|")
        for field in item.fields:
            required = "是" if field.required else "否"
            constraints = ", ".join(field.constraints) if field.constraints else "-"
            lines.append(
                f"| {field.name} | `{field.type}` | {required} | {field.description or '无'} | {constraints} |"
            )
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _render_response_schemas(method) -> list[str]:
    if method.schemas.response_types:
        return _render_schemas(method.schemas.response_types, "Response Types")
    data_type = method.response.data_type or ""
    if data_type:
        return ["#### Response Types", "", f"- 标量类型：`{data_type}`"]
    return ["#### Response Types", "", "- 无"]


def _full_path(service: ServiceModel, spec: ControllerSpecModel, method_path: str) -> str:
    parts = [service.path_rules.path_prefix, spec.controller.base_path, method_path]
    normalized = [item.strip("/") for item in parts if item and item.strip("/")]
    return "/" + "/".join(normalized)
