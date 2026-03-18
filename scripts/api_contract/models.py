from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServiceIdentity:
    domain: str
    service: str


@dataclass
class ServiceOwner:
    name: str


@dataclass
class ServiceSource:
    repo: str


@dataclass
class ServiceTarget:
    type: str
    value: str
    context_id_prefix: str = ""


@dataclass
class ServicePathRules:
    path_prefix: str = ""
    base_path_style: str = "controller-base-plus-method-path"
    exceptions: list[str] = field(default_factory=list)


@dataclass
class ServiceModel:
    identity: ServiceIdentity
    owner: ServiceOwner
    source: ServiceSource
    target: ServiceTarget
    path_rules: ServicePathRules

    @property
    def domain(self) -> str:
        return self.identity.domain

    @property
    def service(self) -> str:
        return self.identity.service


@dataclass
class ControllerSource:
    repo: str
    file: str


@dataclass
class ControllerMeta:
    name: str
    base_path: str
    source: ControllerSource


@dataclass
class MethodIdentity:
    operation_id: str


@dataclass
class MethodSemantic:
    summary: str
    description: str


@dataclass
class MethodSearch:
    intent_aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class MethodProtocol:
    http_method: str
    path: str


@dataclass
class ParamModel:
    name: str
    type: str
    required: bool
    description: str = ""


@dataclass
class RequestBodyModel:
    type: str | None
    required: bool = False
    description: str | None = None


@dataclass
class RequestModel:
    headers: list[ParamModel] = field(default_factory=list)
    path_params: list[ParamModel] = field(default_factory=list)
    query_params: list[ParamModel] = field(default_factory=list)
    query_objects: list[ParamModel] = field(default_factory=list)
    parts: list[ParamModel] = field(default_factory=list)
    body: RequestBodyModel = field(default_factory=lambda: RequestBodyModel(type=None))


@dataclass
class ResponseModel:
    envelope_type: str
    data_type: str
    description: str


@dataclass
class FieldSchemaModel:
    name: str
    type: str
    required: bool
    description: str = ""
    constraints: list[str] = field(default_factory=list)


@dataclass
class TypeSchemaModel:
    name: str
    fields: list[FieldSchemaModel] = field(default_factory=list)


@dataclass
class MethodSchemas:
    request_types: list[TypeSchemaModel] = field(default_factory=list)
    response_types: list[TypeSchemaModel] = field(default_factory=list)


@dataclass
class MethodErrorModel:
    code: str
    meaning: str
    when: str


@dataclass
class MethodSourceModel:
    class_name: str
    method_name: str
    signature: str


@dataclass
class MethodModel:
    identity: MethodIdentity
    semantic: MethodSemantic
    search: MethodSearch
    protocol: MethodProtocol
    request: RequestModel
    response: ResponseModel
    schemas: MethodSchemas
    errors: list[MethodErrorModel] = field(default_factory=list)
    source: MethodSourceModel = field(
        default_factory=lambda: MethodSourceModel(class_name="", method_name="", signature="")
    )

    @property
    def operation_id(self) -> str:
        return self.identity.operation_id


@dataclass
class ControllerSpecModel:
    domain: str
    service: str
    controller: ControllerMeta
    methods: list[MethodModel] = field(default_factory=list)


@dataclass
class GlobalServiceIdentity:
    service: str
    domain: str


@dataclass
class GlobalServiceOwner:
    name: str


@dataclass
class GlobalServiceShard:
    shard_path: str


@dataclass
class GlobalServiceCapability:
    capability_terms: list[str] = field(default_factory=list)


@dataclass
class GlobalServiceEntry:
    identity: GlobalServiceIdentity
    owner: GlobalServiceOwner
    shard: GlobalServiceShard
    capability: GlobalServiceCapability


@dataclass
class GlobalIndexModel:
    services: list[GlobalServiceEntry] = field(default_factory=list)


@dataclass
class ServiceShardManifest:
    service: str
    version: int
    updated_at: str
    controller_count: int
    operation_count: int
    operations_file: str
    inverted_dir: str


@dataclass
class OperationSearchDoc:
    operation_id: str
    service: str
    controller: str
    method_name: str
    http_method: str
    full_path: str
    summary: str
    description: str
    aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body_type: str | None = None
    response_data_type: str = ""
    key_params: list[str] = field(default_factory=list)
    spec_path: str = ""


@dataclass
class ConsumerPlacementRule:
    client_dir: Path
    dto_dir: Path
    support_dir: Path
    client_package: str
    dto_package: str
    support_package: str


@dataclass
class ConsumerNamingRule:
    client_suffix: str = "Api"
    support_class_name: str = "ApiContractSupport"


@dataclass
class ConsumerDtoRule:
    use_lombok_data: bool = False


@dataclass
class ConsumerLocalRuleModel:
    placement: ConsumerPlacementRule
    naming: ConsumerNamingRule = field(default_factory=ConsumerNamingRule)
    dto: ConsumerDtoRule = field(default_factory=ConsumerDtoRule)


@dataclass
class ResolvedConsumerContext:
    consumer_repo: Path
    placement: ConsumerPlacementRule
    naming: ConsumerNamingRule
    dto: ConsumerDtoRule


@dataclass
class ServiceShardArtifacts:
    manifest: ServiceShardManifest
    operation_docs: list[OperationSearchDoc]
    inverted_buckets: dict[str, dict[str, list[str]]]


@dataclass
class SearchResult:
    operation_id: str
    service: str
    controller: str
    confidence: float
