from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from io import StringIO
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from api_contract.contract_store import (
    ContractStore,
    ContractStoreError,
    GitContractStore,
    GitLabApiContractStore,
    build_contract_store,
)
from api_contract.cli import main as cli_main
from api_contract.generator import generate_client
from api_contract.indexer import load_global_index, load_manifest, load_operation_docs
from api_contract.models import OperationSearchDoc
from api_contract.provider import (
    ProviderDeleteControllerOptions,
    ProviderSyncOptions,
    delete_controller_contract_from_store,
    sync_provider_to_store,
)
from api_contract import provider as provider_module
from api_contract.search import _resolve_ambiguous, search_operation


class MemoryContractStore(ContractStore):
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, relative_path: str) -> str | None:
        return self.files.get(relative_path)

    def write_batch(self, upserts: dict[str, str], deletes: list[str], commit_message: str | None = None) -> None:
        del commit_message
        self.files.update(upserts)
        for relative_path in deletes:
            self.files.pop(relative_path, None)

    def list_files(self, prefix: str) -> list[str]:
        return sorted(path for path in self.files if path.startswith(prefix))


class MockHttpResponse:
    def __init__(self, body: str = "", headers: dict[str, str] | None = None, status: int = 200) -> None:
        self._body = body.encode("utf-8")
        self.headers = headers or {}
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "MockHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def make_http_error(url: str, status: int, message: str = "HTTP error") -> HTTPError:
    return HTTPError(url, status, message, hdrs=None, fp=None)


class GitHubSourceWorkflowTest(unittest.TestCase):
    def test_provider_sync_builds_global_and_shard_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/FoundationAdminController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RequestParam;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/foundation")
                public class FoundationAdminController {

                    /**
                     * 获取个人用户信息
                     */
                    @GetMapping("/detail")
                    public Response<String> detail(@RequestParam("userId") Long userId) {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.FoundationAdminController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="user",
                ),
                store,
            )

            self.assertIn("services/demo-service/SERVICE.yaml", store.files)
            self.assertIn(
                "services/demo-service/controllers/FoundationAdminController/FoundationAdminController.spec.yaml",
                store.files,
            )
            self.assertIn("indexes/global.index.json", store.files)
            self.assertIn("indexes/services/demo-service/manifest.json", store.files)
            self.assertIn("indexes/services/demo-service/operations.jsonl", store.files)
            doc_text = store.files[
                "services/demo-service/controllers/FoundationAdminController/FoundationAdminController.doc.md"
            ]
            self.assertIn("| 项目 | 说明 |", doc_text)
            self.assertIn("| 字段名 | 类型 | 必填 | 说明 |", doc_text)

    def test_provider_sync_allows_controller_without_class_request_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/PingController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                public class PingController {

                    @GetMapping("/ping")
                    public Response<String> ping() {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.PingController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="infra",
                ),
                store,
            )

            spec_text = store.files[
                "services/demo-service/controllers/PingController/PingController.spec.yaml"
            ]
            self.assertIn("basePath: ''", spec_text)
            self.assertIn("path: /ping", spec_text)

    def test_provider_sync_allows_bare_method_mapping_without_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/TrackController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.validation.annotation.Validated;
                import org.springframework.web.bind.annotation.PostMapping;
                import org.springframework.web.bind.annotation.RequestBody;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/api/v1/track")
                public class TrackController {

                    @PostMapping
                    public Response<Boolean> collect(@RequestBody @Validated TrackRequest request) {
                        return null;
                    }
                }
                """,
            )
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/TrackRequest.java",
                """
                package com.example.controller;

                public class TrackRequest {
                    private String eventId;
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.TrackController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="track",
                ),
                store,
            )

            spec_text = store.files[
                "services/demo-service/controllers/TrackController/TrackController.spec.yaml"
            ]
            self.assertIn("basePath: /api/v1/track", spec_text)
            self.assertIn("path: ''", spec_text)
            self.assertIn("httpMethod: POST", spec_text)

    def test_provider_sync_same_service_multiple_controllers_rebuilds_full_shard_and_avoids_operation_id_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/FoundationAdminController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.PostMapping;
                import org.springframework.web.bind.annotation.RequestBody;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/foundation/admin")
                public class FoundationAdminController {

                    @RequestMapping("/getAdminInformation")
                    public Response<String> getAdminInformation(@RequestBody QueryAdminParam param) {
                        return null;
                    }

                    @RequestMapping("/modifyAdminInformation")
                    public Response<Object> modifyAdminInformation(@RequestBody ModifyAdminParam param) {
                        return null;
                    }

                    @RequestMapping("/modifyJobNumber")
                    public Response<Object> modifyJobNumber(@RequestBody ModifyAdminParam param) {
                        return null;
                    }

                    @PostMapping("/logAdminChangeInfo")
                    public Response<Object> logMessage(@RequestBody AdminLogParam param) {
                        return null;
                    }
                }
                """,
            )
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/FoundationEnterpriseController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.PostMapping;
                import org.springframework.web.bind.annotation.RequestBody;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/foundation/enterprise")
                public class FoundationEnterpriseController {

                    @RequestMapping("/getEnterpriseInformation")
                    public Response<String> getEnterpriseInformation(@RequestBody QueryEnterpriseParam param) {
                        return null;
                    }

                    @RequestMapping("/modifyEnterpriseInformation")
                    public Response<Object> modifyEnterpriseInformation(@RequestBody ModifyEnterpriseParam param) {
                        return null;
                    }

                    @PostMapping("/logEnterpriseChangeInfo")
                    public Response<Object> logMessage(@RequestBody EnterpriseLogParam param) {
                        return null;
                    }
                }
                """,
            )
            for type_name in [
                "QueryAdminParam",
                "ModifyAdminParam",
                "AdminLogParam",
                "QueryEnterpriseParam",
                "ModifyEnterpriseParam",
                "EnterpriseLogParam",
            ]:
                self._write_java(
                    provider_repo / f"src/main/java/com/example/controller/{type_name}.java",
                    f"""
                    package com.example.controller;

                    public class {type_name} {{
                        private String id;
                    }}
                    """,
                )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.FoundationAdminController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="user-center",
                ),
                store,
            )
            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.FoundationEnterpriseController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="user-center",
                ),
                store,
            )

            manifest = load_manifest(store.files["indexes/services/demo-service/manifest.json"])
            operation_docs = load_operation_docs(store.files["indexes/services/demo-service/operations.jsonl"])
            global_index = load_global_index(store.files["indexes/global.index.json"])
            self.assertEqual(2, manifest.controller_count)
            self.assertEqual(7, manifest.operation_count)
            self.assertEqual(7, len(operation_docs))

            operation_ids = {item.operation_id for item in operation_docs}
            self.assertEqual(7, len(operation_ids))
            self.assertIn("user-center.innerapi.aiAgent.logMessage", operation_ids)
            self.assertIn("user-center.innerapi.aiAgent.foundationEnterprise.logMessage", operation_ids)
            capability_terms = global_index.services[0].capability.capability_terms
            self.assertGreaterEqual(len(capability_terms), 6)

    def test_provider_sync_skips_method_marked_with_api_contract_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/FilteredController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/filtered")
                public class FilteredController {

                    @GetMapping("/public")
                    public Response<String> publicMethod() {
                        return null;
                    }

                    @ApiContractIgnore
                    @GetMapping("/private")
                    public Response<String> privateMethod() {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.FilteredController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            spec_text = store.files[
                "services/demo-service/controllers/FilteredController/FilteredController.spec.yaml"
            ]
            operations = load_operation_docs(store.files["indexes/services/demo-service/operations.jsonl"])
            self.assertIn("publicMethod", spec_text)
            self.assertNotIn("privateMethod", spec_text)
            self.assertEqual(1, len(operations))
            self.assertEqual("publicMethod", operations[0].method_name)

    def test_provider_sync_preserves_full_constraint_expressions_in_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/ConstraintController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import jakarta.validation.constraints.Min;
                import jakarta.validation.constraints.NotBlank;
                import jakarta.validation.constraints.Size;
                import org.springframework.web.bind.annotation.PostMapping;
                import org.springframework.web.bind.annotation.RequestBody;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/constraint")
                public class ConstraintController {

                    @PostMapping("/submit")
                    public Response<String> submit(@RequestBody ConstraintRequest request) {
                        return null;
                    }
                }
                """,
            )
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/ConstraintRequest.java",
                """
                package com.example.controller;

                import jakarta.validation.constraints.Min;
                import jakarta.validation.constraints.NotBlank;
                import jakarta.validation.constraints.Size;

                public class ConstraintRequest {
                    /**
                     * 名称
                     */
                    @NotBlank
                    @Size(min = 1, max = 32)
                    private String name;

                    /**
                     * 数量
                     */
                    @Min(1)
                    private Integer count;
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.ConstraintController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            doc_text = store.files[
                "services/demo-service/controllers/ConstraintController/ConstraintController.doc.md"
            ]
            self.assertIn("@NotBlank", doc_text)
            self.assertIn("@Size(min = 1, max = 32)", doc_text)
            self.assertIn("@Min(1)", doc_text)

    def test_provider_sync_uses_first_meaningful_javadoc_line_as_summary_and_strips_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/SummaryController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/summary")
                public class SummaryController {

                    /**
                     * 推送权限数据（增量同步机制）
                     * DST---> Space ：地上铁增量推送权限数据至思倍云
                     * <p>
                     *     梳理增删改权限接口，调用此方法实现Api同步推送
                     * </p>
                     */
                    @GetMapping("/push")
                    public Response<String> push() {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.SummaryController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            spec_text = store.files[
                "services/demo-service/controllers/SummaryController/SummaryController.spec.yaml"
            ]
            doc_text = store.files[
                "services/demo-service/controllers/SummaryController/SummaryController.doc.md"
            ]
            self.assertIn("summary: 推送权限数据（增量同步机制）", spec_text)
            self.assertIn("推送权限数据（增量同步机制）", doc_text)
            self.assertNotIn("</p>", spec_text)
            self.assertNotIn("<p>", spec_text)

    def test_provider_sync_includes_unannotated_complex_parameter_in_request_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/PushController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/push")
                public class PushController {

                    @GetMapping
                    public Response<Boolean> push(PermissionDTO permissionDTO) {
                        return null;
                    }
                }
                """,
            )
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/PermissionDTO.java",
                """
                package com.example.controller;

                public class PermissionDTO {
                    private String id;
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.PushController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            doc_text = store.files[
                "services/demo-service/controllers/PushController/PushController.doc.md"
            ]
            self.assertIn("#### Request Types", doc_text)
            self.assertIn("#### PermissionDTO", doc_text)
            self.assertIn("- 标量类型：`Boolean`", doc_text)

    def test_provider_sync_class_level_ignore_removes_existing_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            controller_file = provider_repo / "src/main/java/com/example/controller/IgnoredController.java"
            self._write_java(
                controller_file,
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/ignored")
                public class IgnoredController {

                    @GetMapping("/visible")
                    public Response<String> visible() {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.IgnoredController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            self._write_java(
                controller_file,
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @ApiContractIgnore
                @RestController
                @RequestMapping("/ignored")
                public class IgnoredController {

                    @GetMapping("/visible")
                    public Response<String> visible() {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.IgnoredController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            self.assertNotIn(
                "services/demo-service/controllers/IgnoredController/IgnoredController.spec.yaml",
                store.files,
            )
            self.assertNotIn(
                "services/demo-service/controllers/IgnoredController/IgnoredController.doc.md",
                store.files,
            )
            manifest = load_manifest(store.files["indexes/services/demo-service/manifest.json"])
            operations = load_operation_docs(store.files["indexes/services/demo-service/operations.jsonl"])
            self.assertEqual(0, manifest.controller_count)
            self.assertEqual(0, manifest.operation_count)
            self.assertEqual([], operations)

    def test_provider_downloads_missing_sources_jar_from_binary_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m2_repo = root / "m2"
            binary_dir = m2_repo / "com/dst/demo-artifact/1.0.0"
            binary_dir.mkdir(parents=True, exist_ok=True)
            binary_jar = binary_dir / "demo-artifact-1.0.0.jar"
            with zipfile.ZipFile(binary_jar, "w") as archive:
                archive.writestr("com/dst/demo/PageQuery.class", b"stub")

            remote_root = root / "remote"
            remote_dir = remote_root / "com/dst/demo-artifact/1.0.0"
            remote_dir.mkdir(parents=True, exist_ok=True)
            remote_sources = remote_dir / "demo-artifact-1.0.0-sources.jar"
            with zipfile.ZipFile(remote_sources, "w") as archive:
                archive.writestr(
                    "com/dst/demo/PageQuery.java",
                    "package com.dst.demo; public class PageQuery { private Integer pageNum; }",
                )

            with mock.patch.object(provider_module, "_maven_repo_root", return_value=m2_repo):
                with mock.patch.object(provider_module, "SOURCE_JAR_BASE_URLS", (remote_root.as_uri() + "/",)):
                    provider_module._TYPE_SOURCE_CACHE.clear()
                    provider_module._TYPE_BINARY_JAR_CACHE.clear()
                    source = provider_module._load_type_source_from_sources_jar("PageQuery")

            self.assertIsNotNone(source)
            self.assertIn("class PageQuery", source)
            self.assertTrue((binary_dir / "demo-artifact-1.0.0-sources.jar").exists())

    def test_provider_skips_missing_external_parent_when_child_schema_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/ExternalBaseRequest.java",
                """
                package com.example.controller;

                public class ExternalBaseRequest extends MissingParent {
                    private String requestId;
                }
                """,
            )

            with mock.patch.object(provider_module, "_load_type_source_from_sources_jar", return_value=None):
                schemas = provider_module._collect_type_schemas(provider_repo, "ExternalBaseRequest")

            self.assertEqual(1, len(schemas))
            self.assertEqual("ExternalBaseRequest", schemas[0].name)

    def test_provider_collects_generic_inner_type_without_resolving_external_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/PositionRoleNew.java",
                """
                package com.example.controller;

                public class PositionRoleNew {
                    private String id;
                }
                """,
            )

            with mock.patch.object(provider_module, "_load_type_source_from_sources_jar", return_value=None):
                schemas = provider_module._collect_type_schemas(provider_repo, "PageDTO<PositionRoleNew>")

            self.assertEqual(1, len(schemas))
            self.assertEqual("PositionRoleNew", schemas[0].name)

    def test_provider_collects_nested_inner_type_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/OuterType.java",
                """
                package com.example.controller;

                public class OuterType {
                    private int page;

                    public static class InnerType {
                        /**
                         * 名称
                         */
                        private String name;
                    }
                }
                """,
            )

            schemas = provider_module._collect_type_schemas(provider_repo, "OuterType.InnerType")
            self.assertEqual(1, len(schemas))
            self.assertEqual("InnerType", schemas[0].name)
            self.assertEqual("名称", schemas[0].fields[0].description)

    def test_provider_infers_common_field_descriptions_when_comment_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/PageResult.java",
                """
                package com.example.controller;

                public class PageResult {
                    private int page;
                    private int pageSize;
                    private int totalPage;
                    private int totalCount;
                    private String creatorName;
                }
                """,
            )

            schemas = provider_module._collect_type_schemas(provider_repo, "PageResult")
            field_map = {field.name: field.description for field in schemas[0].fields}
            self.assertEqual("当前页码", field_map["page"])
            self.assertEqual("每页条数", field_map["pageSize"])
            self.assertEqual("总页数", field_map["totalPage"])
            self.assertEqual("总记录数", field_map["totalCount"])
            self.assertEqual("创建人名称", field_map["creatorName"])

    def test_provider_parses_nonstandard_comment_terminator_without_trailing_slash(self) -> None:
        schema, _ = provider_module._parse_type_schema_from_source(
            "BaseDO",
            textwrap.dedent(
                """
                public class BaseDO {
                    /**
                     * 创建人
                     **/
                    private Long creatorId;
                }
                """
            ),
        )
        self.assertEqual("创建人", schema.fields[0].description)

    def test_cli_provider_sync_reports_ignored_controller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/IgnoredController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @ApiContractIgnore
                @RestController
                @RequestMapping("/ignored")
                public class IgnoredController {

                    @GetMapping("/visible")
                    public Response<String> visible() {
                        return null;
                    }
                }
                """,
            )

            stdout = StringIO()
            with mock.patch("api_contract.cli.build_contract_store", return_value=store):
                with mock.patch("sys.stdout", stdout):
                    exit_code = cli_main(
                        [
                            "provider",
                            "sync",
                            "--provider-repo",
                            str(provider_repo),
                            "--controller",
                            "com.example.controller.IgnoredController",
                            "--domain",
                            "demo",
                            "--service-owner",
                            "tester",
                        ]
                    )
            self.assertEqual(0, exit_code)
            output = stdout.getvalue()
            self.assertIn("正在同步接口契约...", output)
            self.assertIn("已按规则跳过", output)

    def test_search_and_generate_java_feign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            consumer_repo = root / "consumer"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._init_consumer_repo(consumer_repo)
            self._write_java(
                consumer_repo / "src/main/java/com/example/infrastructure/acl/base/entity/ExistingDto.java",
                """
                package com.example.infrastructure.acl.base.entity;

                import lombok.Data;

                @Data
                public class ExistingDto {
                    private String id;
                }
                """,
            )
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/FoundationAdminController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.PostMapping;
                import org.springframework.web.bind.annotation.RequestBody;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/foundation")
                public class FoundationAdminController {

                    /**
                     * 查询用户标签
                     */
                    @PostMapping("/tags/query")
                    public Response<String> queryTags(@RequestBody QueryTagsRequest request) {
                        return null;
                    }
                }
                """,
            )
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/QueryTagsRequest.java",
                """
                package com.example.controller;

                public class QueryTagsRequest {
                    private Long userId;
                    private java.util.Map<String, Object> properties;
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.FoundationAdminController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="user",
                ),
                store,
            )

            operation_id, controller_name = search_operation(store, "标签 查询 userId", consumer_repo=consumer_repo)
            self.assertEqual("FoundationAdminController", controller_name)

            generated = generate_client(
                store,
                operation_id,
                "java-feign",
                None,
                consumer_repo=consumer_repo,
            )

            content = generated.read_text(encoding="utf-8")
            self.assertIn('@FeignClient(name = "demo-service"', content)
            self.assertIn('@PostMapping("/foundation/tags/query")', content)
            self.assertIn("interface FoundationAdminApi", content)
            dto_text = (
                consumer_repo
                / "src/main/java/com/example/infrastructure/acl/user/dto/QueryTagsRequest.java"
            ).read_text(encoding="utf-8")
            self.assertIn("import lombok.Data;", dto_text)
            self.assertIn("import java.util.Map;", dto_text)
            self.assertIn("@Data", dto_text)

    def test_provider_sync_supports_tree_wrapper_response_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/TreeController.java",
                """
                package com.example.controller;

                import cn.hutool.core.lang.tree.Tree;
                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                import java.util.List;

                @RestController
                @RequestMapping("/tree")
                public class TreeController {

                    @GetMapping("/nodes")
                    public Response<List<Tree<Integer>>> nodes() {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.TreeController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            spec_text = store.files["services/demo-service/controllers/TreeController/TreeController.spec.yaml"]
            self.assertIn("dataType: List<Tree<Integer>>", spec_text)

    def test_provider_sync_supports_plain_string_return_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/CallbackController.java",
                """
                package com.example.controller;

                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RequestParam;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/callback")
                public class CallbackController {

                    @GetMapping("/verify")
                    public String verify(@RequestParam("token") String token) {
                        return token;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.CallbackController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            spec_text = store.files["services/demo-service/controllers/CallbackController/CallbackController.spec.yaml"]
            self.assertIn("envelopeType: ''", spec_text)
            self.assertIn("dataType: String", spec_text)

    def test_provider_sync_parses_request_body_map_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/MapBodyController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.PostMapping;
                import org.springframework.web.bind.annotation.RequestBody;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                import java.util.Map;

                @RestController
                @RequestMapping("/map")
                public class MapBodyController {

                    @PostMapping("/submit")
                    public Response<String> submit(@RequestBody Map<String, Object> payload) {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.MapBodyController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="demo",
                ),
                store,
            )

            spec_text = store.files["services/demo-service/controllers/MapBodyController/MapBodyController.spec.yaml"]
            self.assertIn("type: Map<String,Object>", spec_text)

    def test_search_non_interactive_ambiguity_fails_fast(self) -> None:
        candidates = [
            (
                10.0,
                OperationSearchDoc(
                    operation_id="demo.op.one",
                    service="demo-service",
                    controller="FirstController",
                    method_name="status",
                    http_method="GET",
                    full_path="/first/status",
                    summary="查询状态",
                    description="查询状态",
                ),
            ),
            (
                10.0,
                OperationSearchDoc(
                    operation_id="demo.op.two",
                    service="demo-service",
                    controller="SecondController",
                    method_name="status",
                    http_method="GET",
                    full_path="/second/status",
                    summary="查询状态",
                    description="查询状态",
                ),
            ),
        ]

        with mock.patch("sys.stdin", StringIO("")):
            with self.assertRaises(RuntimeError) as exc:
                _resolve_ambiguous(candidates)
        self.assertIn("Multiple operations found", str(exc.exception))

    def test_delete_controller_removes_spec_and_rebuilds_global_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_repo = root / "provider"
            store = MemoryContractStore()
            self._init_provider_repo(provider_repo)
            self._write_java(
                provider_repo / "src/main/java/com/example/controller/FoundationAdminController.java",
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/foundation")
                public class FoundationAdminController {

                    @GetMapping("/ping")
                    public Response<String> ping() {
                        return null;
                    }
                }
                """,
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.FoundationAdminController",
                    contracts_root=root / "unused",
                    service_owner="tester",
                    domain="user",
                ),
                store,
            )

            delete_controller_contract_from_store(
                ProviderDeleteControllerOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.FoundationAdminController",
                    contracts_root=root / "unused",
                ),
                store,
            )

            self.assertNotIn(
                "services/demo-service/controllers/FoundationAdminController/FoundationAdminController.spec.yaml",
                store.files,
            )
            self.assertIn("indexes/global.index.json", store.files)
            self.assertIn("demo-service", store.files["indexes/global.index.json"])

    def test_build_contract_store_rejects_local_source(self) -> None:
        with mock.patch.dict("os.environ", {"API_CONTRACT_SOURCE": "local"}, clear=False):
            with self.assertRaises(ContractStoreError):
                build_contract_store()

    def test_build_contract_store_returns_git_store(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            store = build_contract_store()
        self.assertIsInstance(store, GitContractStore)

    def test_gitlab_api_contract_store_reads_text(self) -> None:
        store = GitLabApiContractStore(
            "https://gitlab.example.com/api/v4",
            "group/contracts-repo",
            "main",
            "secret-token",
        )
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=10):
            del timeout
            headers = {key.lower(): value for key, value in request.header_items()}
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = headers
            return MockHttpResponse("service: demo-service\n")

        with mock.patch("api_contract.contract_store.urllib.request.urlopen", side_effect=fake_urlopen):
            text = store.read_text("services/demo-service/SERVICE.yaml")

        self.assertEqual("service: demo-service\n", text)
        self.assertEqual("GET", captured["method"])
        self.assertEqual("secret-token", captured["headers"]["private-token"])
        self.assertIn(
            "/projects/group%2Fcontracts-repo/repository/files/services%2Fdemo-service%2FSERVICE.yaml/raw",
            captured["url"],
        )
        self.assertIn("ref=main", captured["url"])

    def test_gitlab_api_contract_store_lists_files_with_pagination(self) -> None:
        store = GitLabApiContractStore(
            "https://gitlab.example.com/api/v4",
            "group/contracts-repo",
            "main",
            "secret-token",
        )
        pages: list[str] = []

        def fake_urlopen(request, timeout=10):
            del timeout
            parsed = urlparse(request.full_url)
            query = parse_qs(parsed.query)
            page = query.get("page", ["1"])[0]
            pages.append(page)
            if page == "1":
                return MockHttpResponse(
                    json.dumps(
                        [
                            {"type": "tree", "path": "services/demo-service/controllers"},
                            {"type": "blob", "path": "services/demo-service/SERVICE.yaml"},
                        ]
                    ),
                    headers={"X-Next-Page": "2"},
                )
            if page == "2":
                return MockHttpResponse(
                    json.dumps(
                        [
                            {
                                "type": "blob",
                                "path": "services/demo-service/controllers/FoundationController/FoundationController.spec.yaml",
                            }
                        ]
                    ),
                    headers={"X-Next-Page": ""},
                )
            self.fail(f"unexpected page request: {request.full_url}")

        with mock.patch("api_contract.contract_store.urllib.request.urlopen", side_effect=fake_urlopen):
            files = store.list_files("services/demo-service")

        self.assertEqual(
            [
                "services/demo-service/SERVICE.yaml",
                "services/demo-service/controllers/FoundationController/FoundationController.spec.yaml",
            ],
            files,
        )
        self.assertEqual(["1", "2"], pages)

    def test_gitlab_api_contract_store_writes_batch_via_commit_api(self) -> None:
        store = GitLabApiContractStore(
            "https://gitlab.example.com/api/v4",
            "group/contracts-repo",
            "main",
            "secret-token",
        )
        commit_payload: dict[str, object] = {}

        def fake_urlopen(request, timeout=10):
            del timeout
            url = request.full_url
            method = request.get_method()
            if url.endswith("/repository/branches/main"):
                return MockHttpResponse(json.dumps({"name": "main"}))
            if "services%2Fdemo-service%2FSERVICE.yaml" in url and method == "HEAD":
                return MockHttpResponse("", headers={"X-Gitlab-File-Path": "services/demo-service/SERVICE.yaml"})
            if "services%2Fdemo-service%2Fnew.txt" in url and method == "HEAD":
                raise make_http_error(url, 404, "Not Found")
            if "services%2Fdemo-service%2Fold.txt" in url and method == "HEAD":
                return MockHttpResponse("", headers={"X-Gitlab-File-Path": "services/demo-service/old.txt"})
            if url.endswith("/repository/commits") and method == "POST":
                commit_payload["body"] = json.loads(request.data.decode("utf-8"))
                commit_payload["headers"] = {key.lower(): value for key, value in request.header_items()}
                return MockHttpResponse(json.dumps({"id": "abc123"}), status=201)
            self.fail(f"unexpected request: {method} {url}")

        with mock.patch("api_contract.contract_store.urllib.request.urlopen", side_effect=fake_urlopen):
            store.write_batch(
                {
                    "services/demo-service/SERVICE.yaml": "service: demo-service\n",
                    "services/demo-service/new.txt": "new\n",
                },
                ["services/demo-service/old.txt"],
                "sync contracts",
            )

        payload = commit_payload["body"]
        actions = {item["file_path"]: item["action"] for item in payload["actions"]}
        self.assertEqual("main", payload["branch"])
        self.assertEqual("sync contracts", payload["commit_message"])
        self.assertNotIn("start_branch", payload)
        self.assertEqual("update", actions["services/demo-service/SERVICE.yaml"])
        self.assertEqual("create", actions["services/demo-service/new.txt"])
        self.assertEqual("delete", actions["services/demo-service/old.txt"])
        self.assertEqual("secret-token", commit_payload["headers"]["private-token"])

    def test_gitlab_api_contract_store_uses_start_branch_when_target_branch_missing(self) -> None:
        store = GitLabApiContractStore(
            "https://gitlab.example.com/api/v4",
            "group/contracts-repo",
            "feature/contracts-api",
            "secret-token",
            start_branch="main",
        )
        commit_payload: dict[str, object] = {}

        def fake_urlopen(request, timeout=10):
            del timeout
            url = request.full_url
            method = request.get_method()
            if url.endswith("/repository/branches/feature%2Fcontracts-api"):
                raise make_http_error(url, 404, "Not Found")
            if "services%2Fdemo-service%2FSERVICE.yaml" in url and method == "HEAD":
                raise make_http_error(url, 404, "Not Found")
            if url.endswith("/repository/commits") and method == "POST":
                commit_payload["body"] = json.loads(request.data.decode("utf-8"))
                return MockHttpResponse(json.dumps({"id": "abc123"}), status=201)
            self.fail(f"unexpected request: {method} {url}")

        with mock.patch("api_contract.contract_store.urllib.request.urlopen", side_effect=fake_urlopen):
            store.write_batch(
                {"services/demo-service/SERVICE.yaml": "service: demo-service\n"},
                [],
                "bootstrap contracts branch",
            )

        payload = commit_payload["body"]
        self.assertEqual("feature/contracts-api", payload["branch"])
        self.assertEqual("main", payload["start_branch"])
        self.assertEqual("create", payload["actions"][0]["action"])

    def test_build_contract_store_returns_gitlab_api_store(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "API_CONTRACT_SOURCE": "gitlab_api",
                "API_CONTRACT_GITLAB_TOKEN": "secret-token",
            },
            clear=True,
        ):
            store = build_contract_store()
        self.assertIsInstance(store, GitLabApiContractStore)

    def test_build_contract_store_requires_gitlab_api_token(self) -> None:
        with mock.patch.dict("os.environ", {"API_CONTRACT_SOURCE": "gitlab_api"}, clear=True):
            with self.assertRaises(ContractStoreError) as exc:
                build_contract_store()
        self.assertIn("API_CONTRACT_GITLAB_TOKEN", str(exc.exception))

    def _init_provider_repo(self, provider_repo: Path) -> None:
        (provider_repo / "src/main/resources").mkdir(parents=True, exist_ok=True)
        (provider_repo / "src/main/java").mkdir(parents=True, exist_ok=True)
        (provider_repo / "src/main/resources/bootstrap.properties").write_text(
            "spring.application.name=demo-service\n",
            encoding="utf-8",
        )

    def _init_consumer_repo(self, consumer_repo: Path) -> None:
        acl_root = consumer_repo / "src/main/java/com/example/infrastructure/acl/existing"
        acl_root.mkdir(parents=True, exist_ok=True)
        (consumer_repo / "src/main/resources").mkdir(parents=True, exist_ok=True)
        (consumer_repo / "src/main/resources/bootstrap.properties").write_text(
            "spring.application.name=consumer-service\n",
            encoding="utf-8",
        )

    def _write_java(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
