from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from api_contract.artifact_publisher import ContractStoreArtifactPublisher, LocalDirectoryPublisher
from api_contract.cli import main as cli_main
from api_contract.cache_manager import LocalCacheManager
from api_contract.context_enricher import ContextEnrichment, ContextEnricher, LlmContextEnricher
from api_contract.contract_store import ContractStore, GitContractStore, LocalPathContractStore, build_contract_store
from api_contract.generator import generate_client
from api_contract.index_build import build_index_release
from api_contract.models import (
    ControllerMeta,
    ControllerSource,
    ControllerSpecModel,
    MethodIdentity,
    MethodModel,
    MethodProtocol,
    MethodSchemas,
    MethodSearch,
    MethodSemantic,
    MethodSourceModel,
    RequestBodyModel,
    RequestModel,
    ResponseModel,
    ServiceIdentity,
    ServiceModel,
    ServiceOwner,
    ServicePathRules,
    ServiceSource,
    ServiceTarget,
)
from api_contract.provider import ProviderSyncOptions, sync_provider_to_store
from api_contract.search import search_operation


class MemoryContractStore(ContractStore):
    def __init__(self) -> None:
        self.files: dict[str, str | bytes] = {}

    def read_text(self, relative_path: str) -> str | None:
        value = self.files.get(relative_path)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    def read_bytes(self, relative_path: str) -> bytes | None:
        value = self.files.get(relative_path)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        return value.encode("utf-8")

    def write_batch(
        self,
        upserts: dict[str, str | bytes],
        deletes: list[str],
        commit_message: str | None = None,
    ) -> None:
        del commit_message
        self.files.update(upserts)
        for relative_path in deletes:
            self.files.pop(relative_path, None)

    def list_files(self, prefix: str) -> list[str]:
        return sorted(path for path in self.files if path.startswith(prefix))


class LocalIndexWorkflowTest(unittest.TestCase):
    def test_build_index_release_creates_compressed_artifacts_and_delta_manifest(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "release"

            release = build_index_release(store, output_dir)

            self.assertEqual("v1", release["schemaVersion"])
            manifest_path = output_dir / "manifest.json"
            self.assertTrue(manifest_path.exists())
            router_path = output_dir / "router.sqlite.gz"
            self.assertTrue(router_path.exists())
            shard_path = output_dir / "shards" / "user-service" / "operations.sqlite.gz"
            self.assertTrue(shard_path.exists())
            delta_path = output_dir / "delta" / f"{release['indexVersion']}.json"
            self.assertTrue(delta_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("user-service", manifest["services"][0]["service"])
            self.assertEqual("router.sqlite.gz", manifest["routerArtifact"]["file"])
            self.assertTrue(manifest["services"][0]["artifactSha256"])

    def test_cache_sync_installs_router_and_changed_shards(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            build_index_release(store, release_dir)
            cache_dir = root / "cache"

            manager = LocalCacheManager(cache_dir=cache_dir, index_base_url=release_dir.as_uri())
            status = manager.sync()

            self.assertEqual(1, status.updated_services)
            self.assertTrue((cache_dir / "manifest.json").exists())
            self.assertTrue((cache_dir / "router.sqlite").exists())
            self.assertTrue((cache_dir / "shards" / "user-service.sqlite").exists())

    def test_cache_sync_supports_contract_store_index_source(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        publisher_store = MemoryContractStore()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            build_index_release(
                store,
                release_dir,
                publisher=ContractStoreArtifactPublisher(publisher_store, prefix="indexes/releases"),
            )
            cache_dir = root / "cache"

            manager = LocalCacheManager(
                cache_dir=cache_dir,
                index_base_url=None,
                index_store=publisher_store,
                index_prefix="indexes/releases",
            )
            status = manager.sync()

            self.assertEqual(1, status.updated_services)
            self.assertTrue((cache_dir / "router.sqlite").exists())
            self.assertTrue((cache_dir / "shards" / "user-service.sqlite").exists())

    def test_cache_sync_skips_unchanged_artifacts_on_second_sync(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            build_index_release(store, release_dir)
            cache_dir = root / "cache"

            manager = LocalCacheManager(cache_dir=cache_dir, index_base_url=release_dir.as_uri())
            first = manager.sync()
            second = manager.sync()

            self.assertEqual(1, first.updated_services)
            self.assertEqual(0, second.updated_services)

    def test_cache_sync_updates_changed_service_and_searches_new_operation(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            cache_dir = root / "cache"
            build_index_release(store, release_dir)
            manager = LocalCacheManager(cache_dir=cache_dir, index_base_url=release_dir.as_uri())
            manager.sync()

            _seed_contracts(store, include_create=True)
            build_index_release(store, release_dir)
            status = manager.sync()

            self.assertEqual(1, status.updated_services)
            operation_id, controller = search_operation(
                store,
                "创建用户",
                cache_dir=cache_dir,
                index_base_url=release_dir.as_uri(),
            )
            self.assertEqual("user.api.user.create", operation_id)
            self.assertEqual("UserController", controller)

    def test_search_uses_local_cache_and_returns_unique_operation(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            build_index_release(store, release_dir)
            cache_dir = root / "cache"
            LocalCacheManager(cache_dir=cache_dir, index_base_url=release_dir.as_uri()).sync()

            operation_id, controller = search_operation(
                store,
                "查询用户详情",
                consumer_repo=None,
                cache_dir=cache_dir,
                index_base_url=release_dir.as_uri(),
            )

            self.assertEqual("user.api.user.detail", operation_id)
            self.assertEqual("UserController", controller)

    def test_search_auto_syncs_when_cache_missing(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            cache_dir = root / "cache"
            build_index_release(store, release_dir)

            operation_id, controller = search_operation(
                store,
                "查询用户详情",
                cache_dir=cache_dir,
                index_base_url=release_dir.as_uri(),
            )

            self.assertEqual("user.api.user.detail", operation_id)
            self.assertEqual("UserController", controller)
            self.assertTrue((cache_dir / "router.sqlite").exists())

    def test_search_uses_existing_cache_when_manifest_check_fails(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            cache_dir = root / "cache"
            build_index_release(store, release_dir)
            LocalCacheManager(cache_dir=cache_dir, index_base_url=release_dir.as_uri()).sync()

            with mock.patch("api_contract.cache_manager.LocalCacheManager._load_remote_json", side_effect=RuntimeError("network down")) as remote_check:
                operation_id, controller = search_operation(
                    store,
                    "查询用户详情",
                    cache_dir=cache_dir,
                    index_base_url=release_dir.as_uri(),
                )

            self.assertEqual("user.api.user.detail", operation_id)
            self.assertEqual("UserController", controller)
            self.assertGreaterEqual(remote_check.call_count, 1)

    def test_search_refreshes_cache_before_query_when_remote_manifest_changes(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            cache_dir = root / "cache"
            build_index_release(store, release_dir)
            LocalCacheManager(cache_dir=cache_dir, index_base_url=release_dir.as_uri()).sync()

            _seed_contracts(store, include_create=True)
            build_index_release(store, release_dir)

            operation_id, controller = search_operation(
                store,
                "创建用户",
                cache_dir=cache_dir,
                index_base_url=release_dir.as_uri(),
            )

            self.assertEqual("user.api.user.create", operation_id)
            self.assertEqual("UserController", controller)

    def test_search_fails_when_cache_missing_and_manifest_check_fails(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"

            with mock.patch("api_contract.cache_manager.LocalCacheManager._load_remote_json", side_effect=RuntimeError("network down")):
                with self.assertRaises(RuntimeError):
                    search_operation(
                        store,
                        "查询用户详情",
                        cache_dir=cache_dir,
                        index_base_url="file:///does-not-matter",
                    )

    def test_generate_client_supports_query_via_local_index(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir = root / "release"
            build_index_release(store, release_dir)
            cache_dir = root / "cache"
            LocalCacheManager(cache_dir=cache_dir, index_base_url=release_dir.as_uri()).sync()
            consumer_repo = root / "consumer"
            os.makedirs(consumer_repo / "src/main/resources", exist_ok=True)
            os.makedirs(consumer_repo / "src/main/java/com/example/infrastructure/acl", exist_ok=True)
            (consumer_repo / "src/main/resources/bootstrap.properties").write_text(
                "spring.application.name=consumer-app",
                encoding="utf-8",
            )

            output = generate_client(
                store,
                operation_id=None,
                query="查询用户详情",
                target="java-feign",
                output_root=None,
                consumer_repo=consumer_repo,
                cache_dir=cache_dir,
                index_base_url=release_dir.as_uri(),
            )

            self.assertTrue(output.exists())
            self.assertIn("UserApi", output.read_text(encoding="utf-8"))

    def test_build_index_release_persists_contextual_summary_for_operations(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "release"
            release = build_index_release(store, output_dir)
            cache_dir = Path(tmp) / "cache"
            LocalCacheManager(cache_dir=cache_dir, index_base_url=output_dir.as_uri()).sync()

            connection = sqlite3.connect(cache_dir / "shards" / "user-service.sqlite")
            try:
                row = connection.execute(
                    "SELECT context_summary FROM operations WHERE operation_id = ?",
                    ("user.api.user.detail",),
                ).fetchone()
            finally:
                connection.close()

            self.assertIsNotNone(row)
            self.assertIn("查询用户详情", row[0])
            self.assertTrue((output_dir / "delta" / f"{release['indexVersion']}.json").exists())

    def test_build_index_release_uses_custom_enricher_context_for_search(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "release"
            cache_dir = Path(tmp) / "cache"
            build_index_release(store, output_dir, enricher=FakeContextEnricher())
            LocalCacheManager(cache_dir=cache_dir, index_base_url=output_dir.as_uri()).sync()

            operation_id, controller = search_operation(
                store,
                "用户档案",
                cache_dir=cache_dir,
                index_base_url=output_dir.as_uri(),
            )

            self.assertEqual("user.api.user.detail", operation_id)
            self.assertEqual("UserController", controller)

    def test_build_index_release_can_publish_release_to_target_directory(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_dir = root / "build"
            publish_dir = root / "published"

            build_index_release(
                store,
                build_dir,
                publisher=LocalDirectoryPublisher(publish_dir),
            )

            self.assertTrue((publish_dir / "manifest.json").exists())
            self.assertTrue((publish_dir / "router.sqlite.gz").exists())
            self.assertTrue((publish_dir / "shards" / "user-service" / "operations.sqlite.gz").exists())

    def test_llm_context_enricher_uses_client_response(self) -> None:
        enricher = LlmContextEnricher(client=FakeLlmClient())
        service_enrichment = enricher.enrich_service(
            ServiceModel(
                identity=ServiceIdentity(domain="user", service="user-service"),
                owner=ServiceOwner(name="owner"),
                source=ServiceSource(repo="repo"),
                target=ServiceTarget(type="service-name", value="user-service"),
                path_rules=ServicePathRules(path_prefix="/api"),
            ),
            [
                _build_doc(
                    operation_id="user.api.user.detail",
                    summary="查询用户详情",
                    description="按用户ID查询详情",
                    method_name="detail",
                    http_method="GET",
                    path="/api/user/detail",
                )
            ],
        )
        operation_enrichment = enricher.enrich_operation(
            ServiceModel(
                identity=ServiceIdentity(domain="user", service="user-service"),
                owner=ServiceOwner(name="owner"),
                source=ServiceSource(repo="repo"),
                target=ServiceTarget(type="service-name", value="user-service"),
                path_rules=ServicePathRules(path_prefix="/api"),
            ),
            _build_doc(
                operation_id="user.api.user.detail",
                summary="查询用户详情",
                description="按用户ID查询详情",
                method_name="detail",
                http_method="GET",
                path="/api/user/detail",
            ),
        )

        self.assertEqual("模型生成的服务摘要", service_enrichment.context_summary)
        self.assertIn("服务关键词", service_enrichment.keywords)
        self.assertEqual("模型生成的接口摘要", operation_enrichment.context_summary)
        self.assertIn("接口关键词", operation_enrichment.keywords)

    def test_contract_store_artifact_publisher_writes_release_tree(self) -> None:
        target_store = MemoryContractStore()
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = Path(tmp) / "build"
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "manifest.json").write_text('{"ok":true}', encoding="utf-8")
            (build_dir / "router.sqlite.gz").write_bytes(b"router-bytes")
            shard_dir = build_dir / "shards" / "user-service"
            shard_dir.mkdir(parents=True, exist_ok=True)
            (shard_dir / "operations.sqlite.gz").write_bytes(b"ops-bytes")
            delta_dir = build_dir / "delta"
            delta_dir.mkdir(parents=True, exist_ok=True)
            (delta_dir / "v1.json").write_text('{"indexVersion":"v1"}', encoding="utf-8")
            publisher = ContractStoreArtifactPublisher(target_store, prefix="indexes/releases")
            publisher.publish_release(build_dir)

        self.assertIn("indexes/releases/manifest.json", target_store.files)
        self.assertIn("indexes/releases/router.sqlite.gz", target_store.files)
        self.assertIn("indexes/releases/shards/user-service/operations.sqlite.gz", target_store.files)
        self.assertIn("indexes/releases/delta/v1.json", target_store.files)

    def test_contract_store_artifact_publisher_preserves_binary_artifacts_for_local_path_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_dir = root / "build"
            build_dir.mkdir(parents=True, exist_ok=True)
            payload = b"\x1f\x8b\x08binary-index"
            (build_dir / "router.sqlite.gz").write_bytes(payload)
            target_root = root / "publish"
            publisher = ContractStoreArtifactPublisher(LocalPathContractStore(target_root), prefix="indexes/releases")

            publisher.publish_release(build_dir)

            self.assertEqual(payload, (target_root / "indexes/releases/router.sqlite.gz").read_bytes())

    def test_cli_index_build_can_publish_via_contract_store_env(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            release_dir = root / "release"
            publish_root = root / "publish"
            _materialize_store(store, source_root)
            with mock.patch.dict(
                os.environ,
                {
                    "API_CONTRACT_SOURCE": "local_path",
                    "API_CONTRACT_LOCAL_SOURCE_PATH": str(source_root),
                    "API_CONTRACT_INDEX_PUBLISH_SOURCE": "local_path",
                    "API_CONTRACT_INDEX_PUBLISH_LOCAL_PATH": str(publish_root),
                    "API_CONTRACT_INDEX_PUBLISH_PREFIX": "indexes/releases",
                },
                clear=False,
            ):
                self.assertEqual(
                    0,
                    cli_main(["contracts", "index", "build", "--output-dir", str(release_dir)]),
                )
                self.assertTrue((publish_root / "indexes/releases/manifest.json").exists())

    def test_cli_index_build_defaults_publish_prefix_to_indexes_releases(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            release_dir = root / "release"
            publish_root = root / "publish"
            _materialize_store(store, source_root)
            with mock.patch.dict(
                os.environ,
                {
                    "API_CONTRACT_SOURCE": "local_path",
                    "API_CONTRACT_LOCAL_SOURCE_PATH": str(source_root),
                    "API_CONTRACT_INDEX_PUBLISH_SOURCE": "local_path",
                    "API_CONTRACT_INDEX_PUBLISH_LOCAL_PATH": str(publish_root),
                },
                clear=False,
            ):
                self.assertEqual(
                    0,
                    cli_main(["contracts", "index", "build", "--output-dir", str(release_dir)]),
                )
                self.assertTrue((publish_root / "indexes/releases/manifest.json").exists())

    def test_index_publish_store_defaults_branch_to_test(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "API_CONTRACT_INDEX_PUBLISH_SOURCE": "github",
            },
            clear=False,
        ):
            store = build_contract_store(prefix="API_CONTRACT_INDEX_PUBLISH_")
        self.assertIsInstance(store, GitContractStore)
        self.assertEqual("test", store.branch)

    def test_provider_sync_only_updates_true_source_files(self) -> None:
        store = MemoryContractStore()
        with tempfile.TemporaryDirectory() as tmp:
            provider_repo = Path(tmp) / "provider"
            _init_provider_repo(provider_repo)
            (provider_repo / "src/main/java/com/example/controller/UserController.java").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (provider_repo / "src/main/java/com/example/controller/UserController.java").write_text(
                """
                package com.example.controller;

                import com.dst.steed.common.domain.response.Response;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @RestController
                @RequestMapping("/user")
                public class UserController {
                    @GetMapping("/detail")
                    public Response<String> detail() {
                        return null;
                    }
                }
                """,
                encoding="utf-8",
            )

            sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=provider_repo,
                    controller_fqcn="com.example.controller.UserController",
                    contracts_root=provider_repo,
                    service_owner="owner",
                    domain="user",
                ),
                store,
            )

            self.assertIn("services/demo-service/SERVICE.yaml", store.files)
            self.assertIn(
                "services/demo-service/controllers/UserController/UserController.spec.yaml",
                store.files,
            )
            self.assertIn(
                "services/demo-service/controllers/UserController/UserController.doc.md",
                store.files,
            )
            self.assertNotIn("indexes/global.index.json", store.files)

    def test_cli_supports_index_build_and_cache_sync_commands(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            release_dir = root / "release"
            cache_dir = root / "cache"
            _materialize_store(store, source_root)
            with mock.patch.dict(
                os.environ,
                {
                    "API_CONTRACT_SOURCE": "local_path",
                    "API_CONTRACT_LOCAL_SOURCE_PATH": str(source_root),
                    "API_CONTRACT_INDEX_BASE_URL": release_dir.as_uri(),
                    "API_CONTRACT_CACHE_DIR": str(cache_dir),
                },
                clear=False,
            ):
                self.assertEqual(
                    0,
                    cli_main(["contracts", "index", "build", "--output-dir", str(release_dir)]),
                )
                self.assertEqual(0, cli_main(["contracts", "cache", "sync"]))
                self.assertTrue((cache_dir / "router.sqlite").exists())

    def test_cli_cache_sync_supports_contract_store_index_env(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            publish_root = root / "publish"
            cache_dir = root / "cache"
            _materialize_store(store, source_root)
            with mock.patch.dict(
                os.environ,
                {
                    "API_CONTRACT_SOURCE": "local_path",
                    "API_CONTRACT_LOCAL_SOURCE_PATH": str(source_root),
                    "API_CONTRACT_INDEX_PUBLISH_SOURCE": "local_path",
                    "API_CONTRACT_INDEX_PUBLISH_LOCAL_PATH": str(publish_root),
                    "API_CONTRACT_INDEX_PUBLISH_PREFIX": "indexes/releases",
                },
                clear=False,
            ):
                self.assertEqual(
                    0,
                    cli_main(["contracts", "index", "build", "--output-dir", str(root / "release")]),
                )
            with mock.patch.dict(
                os.environ,
                {
                    "API_CONTRACT_INDEX_SOURCE": "local_path",
                    "API_CONTRACT_INDEX_LOCAL_PATH": str(publish_root),
                    "API_CONTRACT_INDEX_PREFIX": "indexes/releases",
                    "API_CONTRACT_CACHE_DIR": str(cache_dir),
                },
                clear=False,
            ):
                self.assertEqual(0, cli_main(["contracts", "cache", "sync"]))
                self.assertTrue((cache_dir / "router.sqlite").exists())

    def test_cli_consumer_search_supports_contract_store_index_env(self) -> None:
        store = MemoryContractStore()
        _seed_contracts(store)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            publish_root = root / "publish"
            cache_dir = root / "cache"
            consumer_repo = root / "consumer"
            (consumer_repo / "src/main/resources").mkdir(parents=True, exist_ok=True)
            (consumer_repo / "src/main/resources/bootstrap.properties").write_text(
                "spring.application.name=consumer-app",
                encoding="utf-8",
            )
            _materialize_store(store, source_root)
            with mock.patch.dict(
                os.environ,
                {
                    "API_CONTRACT_SOURCE": "local_path",
                    "API_CONTRACT_LOCAL_SOURCE_PATH": str(source_root),
                    "API_CONTRACT_INDEX_PUBLISH_SOURCE": "local_path",
                    "API_CONTRACT_INDEX_PUBLISH_LOCAL_PATH": str(publish_root),
                    "API_CONTRACT_INDEX_PUBLISH_PREFIX": "indexes/releases",
                },
                clear=False,
            ):
                self.assertEqual(
                    0,
                    cli_main(["contracts", "index", "build", "--output-dir", str(root / "release")]),
                )
            with mock.patch.dict(
                os.environ,
                {
                    "API_CONTRACT_INDEX_SOURCE": "local_path",
                    "API_CONTRACT_INDEX_LOCAL_PATH": str(publish_root),
                    "API_CONTRACT_INDEX_PREFIX": "indexes/releases",
                    "API_CONTRACT_CACHE_DIR": str(cache_dir),
                },
                clear=False,
            ):
                self.assertEqual(
                    0,
                    cli_main(
                        [
                            "consumer",
                            "search",
                            "--query",
                            "查询用户详情",
                            "--consumer-repo",
                            str(consumer_repo),
                        ]
                    ),
                )


def _seed_contracts(store: MemoryContractStore, *, include_create: bool = False) -> None:
    service = ServiceModel(
        identity=ServiceIdentity(domain="user", service="user-service"),
        owner=ServiceOwner(name="owner"),
        source=ServiceSource(repo="git@example.com:user-service.git"),
        target=ServiceTarget(type="service-name", value="user-service"),
        path_rules=ServicePathRules(path_prefix="/api"),
    )
    methods = [
        MethodModel(
            identity=MethodIdentity(operation_id="user.api.user.detail"),
            semantic=MethodSemantic(summary="查询用户详情", description="按用户ID查询详情"),
            search=MethodSearch(intent_aliases=["获取用户详情"], tags=["用户", "详情"]),
            protocol=MethodProtocol(http_method="GET", path="/detail"),
            request=RequestModel(
                query_params=[],
                path_params=[],
                headers=[],
                query_objects=[],
                parts=[],
                body=RequestBodyModel(type=None),
            ),
            response=ResponseModel(
                envelope_type="Response",
                data_type="UserDetailResponse",
                description="用户详情",
            ),
            schemas=MethodSchemas(request_types=[], response_types=[]),
            errors=[],
            source=MethodSourceModel(
                class_name="UserController",
                method_name="detail",
                signature="Response<UserDetailResponse> detail(Long userId)",
            ),
        )
    ]
    if include_create:
        methods.append(
            MethodModel(
                identity=MethodIdentity(operation_id="user.api.user.create"),
                semantic=MethodSemantic(summary="创建用户", description="创建新用户"),
                search=MethodSearch(intent_aliases=["新增用户"], tags=["用户", "创建"]),
                protocol=MethodProtocol(http_method="POST", path="/create"),
                request=RequestModel(
                    query_params=[],
                    path_params=[],
                    headers=[],
                    query_objects=[],
                    parts=[],
                    body=RequestBodyModel(type="CreateUserRequest", required=True, description="创建用户入参"),
                ),
                response=ResponseModel(
                    envelope_type="Response",
                    data_type="CreateUserResponse",
                    description="创建结果",
                ),
                schemas=MethodSchemas(request_types=[], response_types=[]),
                errors=[],
                source=MethodSourceModel(
                    class_name="UserController",
                    method_name="create",
                    signature="Response<CreateUserResponse> create(CreateUserRequest request)",
                ),
            )
        )
    spec = ControllerSpecModel(
        domain="user",
        service="user-service",
        controller=ControllerMeta(
            name="UserController",
            base_path="/user",
            source=ControllerSource(repo="git@example.com:user-service.git", file="UserController.java"),
        ),
        methods=methods,
    )
    from api_contract.doc_renderer import render_doc
    from api_contract.service_io import render_service
    from api_contract.spec_io import render_spec

    store.write_batch(
        {
            store.get_service_file(service.service): render_service(service),
            store.get_controller_spec_file(service.service, spec.controller.name): render_spec(spec),
            store.get_controller_doc_file(service.service, spec.controller.name): render_doc(service, spec),
        },
        [],
    )


def _materialize_store(store: MemoryContractStore, root: Path) -> None:
    for relative_path, content in store.files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _init_provider_repo(provider_repo: Path) -> None:
    (provider_repo / "src/main/resources").mkdir(parents=True, exist_ok=True)
    (provider_repo / "src/main/resources/bootstrap.properties").write_text(
        "spring.application.name=demo-service",
        encoding="utf-8",
    )


class FakeContextEnricher(ContextEnricher):
    def enrich_service(self, service, docs) -> ContextEnrichment:
        del service, docs
        return ContextEnrichment(context_summary="用户服务档案", keywords=["用户档案"])

    def enrich_operation(self, service, doc) -> ContextEnrichment:
        del service, doc
        return ContextEnrichment(context_summary="用户档案查询接口", keywords=["用户档案"])


class FakeLlmClient:
    def enrich(self, payload: dict[str, object]) -> dict[str, object]:
        kind = payload["kind"]
        if kind == "service":
            return {
                "context_summary": "模型生成的服务摘要",
                "keywords": ["服务关键词"],
            }
        return {
            "context_summary": "模型生成的接口摘要",
            "keywords": ["接口关键词"],
        }


def _build_doc(
    *,
    operation_id: str,
    summary: str,
    description: str,
    method_name: str,
    http_method: str,
    path: str,
):
    from api_contract.models import OperationSearchDoc

    return OperationSearchDoc(
        operation_id=operation_id,
        service="user-service",
        controller="UserController",
        method_name=method_name,
        http_method=http_method,
        full_path=path,
        summary=summary,
        description=description,
        aliases=[],
        tags=[],
        body_type=None,
        response_data_type="UserDetailResponse",
        key_params=[],
        spec_path="services/user-service/controllers/UserController/UserController.spec.yaml",
    )
