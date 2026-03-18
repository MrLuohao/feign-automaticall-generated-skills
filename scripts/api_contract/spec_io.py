from __future__ import annotations

from pathlib import Path

import yaml

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
    TypeSchemaModel,
)


def load_spec(path: Path) -> ControllerSpecModel:
    return load_spec_text(path.read_text(encoding="utf-8"))


def load_spec_text(text: str) -> ControllerSpecModel:
    data = yaml.safe_load(text) or {}
    controller_data = data.get("controller", {})
    controller_source = controller_data.get("source", {})
    methods = [_load_method(item) for item in (data.get("methods") or [])]
    return ControllerSpecModel(
        domain=str(data.get("domain", "")),
        service=str(data.get("service", "")),
        controller=ControllerMeta(
            name=str(controller_data.get("name", "")),
            base_path=str(controller_data.get("basePath", "")),
            source=ControllerSource(
                repo=str(controller_source.get("repo", "")),
                file=str(controller_source.get("file", "")),
            ),
        ),
        methods=methods,
    )


def dump_spec(spec: ControllerSpecModel, path: Path) -> None:
    path.write_text(render_spec(spec), encoding="utf-8")


def render_spec(spec: ControllerSpecModel) -> str:
    data = {
        "domain": spec.domain,
        "service": spec.service,
        "controller": {
            "name": spec.controller.name,
            "basePath": spec.controller.base_path,
            "source": {
                "repo": spec.controller.source.repo,
                "file": spec.controller.source.file,
            },
        },
        "methods": [_dump_method(item) for item in spec.methods],
    }
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _load_method(item: dict) -> MethodModel:
    identity = item.get("identity", {})
    semantic = item.get("semantic", {})
    search = item.get("search", {})
    protocol = item.get("protocol", {})
    request = item.get("request", {})
    body = request.get("body", {}) or {}
    response = item.get("response", {})
    schemas = item.get("schemas", {})
    source = item.get("source", {})
    return MethodModel(
        identity=MethodIdentity(operation_id=str(identity.get("operationId", ""))),
        semantic=MethodSemantic(
            summary=str(semantic.get("summary", "")),
            description=str(semantic.get("description", "")),
        ),
        search=MethodSearch(
            intent_aliases=[str(value) for value in (search.get("intentAliases") or [])],
            tags=[str(value) for value in (search.get("tags") or [])],
        ),
        protocol=MethodProtocol(
            http_method=str(protocol.get("httpMethod", "")),
            path=str(protocol.get("path", "")),
        ),
        request=RequestModel(
            headers=_load_params(request.get("headers")),
            path_params=_load_params(request.get("pathParams")),
            query_params=_load_params(request.get("queryParams")),
            query_objects=_load_params(request.get("queryObjects")),
            parts=_load_params(request.get("parts")),
            body=RequestBodyModel(
                type=body.get("type"),
                required=bool(body.get("required", False)),
                description=body.get("description"),
            ),
        ),
        response=ResponseModel(
            envelope_type=str(response.get("envelopeType", "")),
            data_type=str(response.get("dataType", "")),
            description=str(response.get("description", "")),
        ),
        schemas=MethodSchemas(
            request_types=_load_types(schemas.get("requestTypes")),
            response_types=_load_types(schemas.get("responseTypes")),
        ),
        errors=[
            MethodErrorModel(
                code=str(error.get("code", "")),
                meaning=str(error.get("meaning", "")),
                when=str(error.get("when", "")),
            )
            for error in (item.get("errors") or [])
        ],
        source=MethodSourceModel(
            class_name=str(source.get("className", "")),
            method_name=str(source.get("methodName", "")),
            signature=str(source.get("signature", "")),
        ),
    )


def _load_params(items: list[dict] | None) -> list[ParamModel]:
    return [
        ParamModel(
            name=str(item.get("name", "")),
            type=str(item.get("type", "")),
            required=bool(item.get("required", False)),
            description=str(item.get("description", "")),
        )
        for item in (items or [])
    ]


def _load_types(items: list[dict] | None) -> list[TypeSchemaModel]:
    return [
        TypeSchemaModel(
            name=str(item.get("name", "")),
            fields=[
                FieldSchemaModel(
                    name=str(field.get("name", "")),
                    type=str(field.get("type", "")),
                    required=bool(field.get("required", False)),
                    description=str(field.get("description", "")),
                    constraints=[str(value) for value in (field.get("constraints") or [])],
                )
                for field in (item.get("fields") or [])
            ],
        )
        for item in (items or [])
    ]


def _dump_method(method: MethodModel) -> dict:
    return {
        "identity": {
            "operationId": method.identity.operation_id,
        },
        "semantic": {
            "summary": method.semantic.summary,
            "description": method.semantic.description,
        },
        "search": {
            "intentAliases": list(method.search.intent_aliases),
            "tags": list(method.search.tags),
        },
        "protocol": {
            "httpMethod": method.protocol.http_method,
            "path": method.protocol.path,
        },
        "request": {
            "headers": _dump_params(method.request.headers),
            "pathParams": _dump_params(method.request.path_params),
            "queryParams": _dump_params(method.request.query_params),
            "queryObjects": _dump_params(method.request.query_objects),
            "parts": _dump_params(method.request.parts),
            "body": {
                "type": method.request.body.type,
                "required": method.request.body.required,
                "description": method.request.body.description,
            },
        },
        "response": {
            "envelopeType": method.response.envelope_type,
            "dataType": method.response.data_type,
            "description": method.response.description,
        },
        "schemas": {
            "requestTypes": _dump_types(method.schemas.request_types),
            "responseTypes": _dump_types(method.schemas.response_types),
        },
        "errors": [
            {
                "code": item.code,
                "meaning": item.meaning,
                "when": item.when,
            }
            for item in method.errors
        ],
        "source": {
            "className": method.source.class_name,
            "methodName": method.source.method_name,
            "signature": method.source.signature,
        },
    }


def _dump_params(items: list[ParamModel]) -> list[dict]:
    return [
        {
            "name": item.name,
            "type": item.type,
            "required": item.required,
            "description": item.description,
        }
        for item in items
    ]


def _dump_types(items: list[TypeSchemaModel]) -> list[dict]:
    return [
        {
            "name": item.name,
            "fields": [
                {
                    "name": field.name,
                    "type": field.type,
                    "required": field.required,
                    "description": field.description,
                    "constraints": list(field.constraints),
                }
                for field in item.fields
            ],
        }
        for item in items
    ]
