from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .artifact_publisher import ContractStoreArtifactPublisher, LocalDirectoryPublisher
from .cache_manager import LocalCacheManager
from .contract_store import build_contract_store
from .context_enricher import BasicContextEnricher
from .doc_renderer import write_doc
from .generator import generate_client
from .index_build import build_index_release
from .provider import (
    ProviderDeleteControllerOptions,
    ProviderSyncError,
    ProviderSyncOptions,
    delete_controller_contract_from_store,
    rebuild_index,
    sync_provider_to_store,
)
from .search import search_operation
from .service_io import load_service
from .spec_io import load_spec


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        store = build_contract_store() if args.command not in {"doc", None} and _needs_source_store(args) else None
        if args.command == "provider" and args.provider_command == "sync":
            print("正在同步接口契约...")
            result = sync_provider_to_store(
                ProviderSyncOptions(
                    provider_repo=Path(args.provider_repo),
                    controller_fqcn=args.controller,
                    contracts_root=Path("."),
                    service_owner=args.service_owner,
                    domain=args.domain,
                ),
                store,
            )
            if result.status == "ignored":
                print("已按规则跳过")
            else:
                print("同步成功")
            return 0
        if args.command == "provider" and args.provider_command == "delete-controller":
            print("正在删除 Controller 契约...")
            delete_controller_contract_from_store(
                ProviderDeleteControllerOptions(
                    provider_repo=Path(args.provider_repo),
                    controller_fqcn=args.controller,
                    contracts_root=Path("."),
                ),
                store,
            )
            print("删除成功")
            return 0
        if args.command == "doc" and args.doc_command == "render":
            service = load_service(Path(args.service))
            spec = load_spec(Path(args.spec))
            write_doc(service, spec, Path(args.output))
            return 0
        if args.command == "contracts" and args.contracts_command == "rebuild-index":
            print("正在重建索引...")
            rebuild_index(store)
            print("重建成功")
            return 0
        if args.command == "contracts" and args.contracts_command == "index" and args.index_command == "build":
            print("正在构建索引产物...")
            publisher = _build_artifact_publisher(args.publish_dir)
            enricher = _build_index_enricher()
            build_index_release(
                store,
                Path(args.output_dir),
                enricher=enricher,
                publisher=publisher,
            )
            print("构建成功")
            return 0
        if args.command == "contracts" and args.contracts_command == "cache" and args.cache_command == "sync":
            print("正在同步本地缓存...")
            manager = _build_cache_manager(args.cache_dir, args.index_base_url)
            status = manager.sync()
            print("同步成功")
            print(f"{status.manifest_version}\t{status.updated_services}")
            return 0
        if args.command == "contracts" and args.contracts_command == "cache" and args.cache_command == "status":
            manager = _build_cache_manager(args.cache_dir, args.index_base_url)
            print(manager.status())
            return 0
        if args.command == "consumer" and args.consumer_command == "search":
            print("正在检索接口...")
            cache_manager = _build_cache_manager(args.cache_dir, args.index_base_url)
            operation_id, controller_name = search_operation(
                store,
                args.query,
                consumer_repo=Path(args.consumer_repo) if args.consumer_repo else None,
                cache_dir=_cache_dir(args.cache_dir),
                index_base_url=(args.index_base_url or os.getenv("API_CONTRACT_INDEX_BASE_URL", "").strip() or None),
                cache_manager=cache_manager,
            )
            print("检索成功")
            print(f"{operation_id}\t{controller_name}")
            return 0
        if args.command == "consumer" and args.consumer_command == "generate":
            print("正在生成调用代码...")
            cache_manager = _build_cache_manager(args.cache_dir, args.index_base_url)
            output = generate_client(
                store,
                args.operation_id,
                args.query,
                args.target,
                Path(args.output_root) if args.output_root else None,
                consumer_repo=Path(args.consumer_repo),
                cache_dir=_cache_dir(args.cache_dir),
                index_base_url=(args.index_base_url or os.getenv("API_CONTRACT_INDEX_BASE_URL", "").strip() or None),
                cache_manager=cache_manager,
            )
            print("生成成功")
            print(str(output))
            return 0
    except ProviderSyncError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(str(exc), file=sys.stderr)
        return 1
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="api-contract")
    subparsers = parser.add_subparsers(dest="command")

    provider = subparsers.add_parser("provider")
    provider_sub = provider.add_subparsers(dest="provider_command")
    provider_sync = provider_sub.add_parser("sync")
    provider_sync.add_argument("--provider-repo", required=True)
    provider_sync.add_argument("--controller", required=True)
    provider_sync.add_argument("--service-owner")
    provider_sync.add_argument("--domain", required=True)
    provider_delete = provider_sub.add_parser("delete-controller")
    provider_delete.add_argument("--provider-repo", required=True)
    provider_delete.add_argument("--controller", required=True)

    doc = subparsers.add_parser("doc")
    doc_sub = doc.add_subparsers(dest="doc_command")
    doc_render = doc_sub.add_parser("render")
    doc_render.add_argument("--service", required=True)
    doc_render.add_argument("--spec", required=True)
    doc_render.add_argument("--output", required=True)

    contracts = subparsers.add_parser("contracts")
    contracts_sub = contracts.add_subparsers(dest="contracts_command")
    contracts_sub.add_parser("rebuild-index")
    contracts_index = contracts_sub.add_parser("index")
    contracts_index_sub = contracts_index.add_subparsers(dest="index_command")
    contracts_index_build = contracts_index_sub.add_parser("build")
    contracts_index_build.add_argument("--output-dir", required=True)
    contracts_index_build.add_argument("--publish-dir")
    contracts_cache = contracts_sub.add_parser("cache")
    contracts_cache_sub = contracts_cache.add_subparsers(dest="cache_command")
    cache_sync = contracts_cache_sub.add_parser("sync")
    cache_sync.add_argument("--cache-dir")
    cache_sync.add_argument("--index-base-url")
    cache_status = contracts_cache_sub.add_parser("status")
    cache_status.add_argument("--cache-dir")
    cache_status.add_argument("--index-base-url")

    consumer = subparsers.add_parser("consumer")
    consumer_sub = consumer.add_subparsers(dest="consumer_command")
    consumer_search = consumer_sub.add_parser("search")
    consumer_search.add_argument("--query", required=True)
    consumer_search.add_argument("--consumer-repo")
    consumer_search.add_argument("--cache-dir")
    consumer_search.add_argument("--index-base-url")

    consumer_generate = consumer_sub.add_parser("generate")
    consumer_generate.add_argument("--operation-id")
    consumer_generate.add_argument("--query")
    consumer_generate.add_argument("--target")
    consumer_generate.add_argument("--output-root")
    consumer_generate.add_argument("--consumer-repo", required=True)
    consumer_generate.add_argument("--cache-dir")
    consumer_generate.add_argument("--index-base-url")

    return parser


def _cache_dir(value: str | None) -> Path:
    if value:
        return Path(value)
    env_value = os.getenv("API_CONTRACT_CACHE_DIR", "").strip()
    if env_value:
        return Path(env_value)
    return _project_root() / ".cache" / "api-contract"


def _index_base_url(value: str | None) -> str:
    resolved = value or os.getenv("API_CONTRACT_INDEX_BASE_URL", "")
    if not resolved:
        raise RuntimeError("Missing index base URL. Set --index-base-url or API_CONTRACT_INDEX_BASE_URL.")
    return resolved


def _needs_source_store(args) -> bool:
    if args.command == "contracts" and getattr(args, "contracts_command", None) == "cache":
        return False
    return True


def _build_index_enricher():
    return BasicContextEnricher()


def _build_artifact_publisher(publish_dir: str | None):
    if publish_dir:
        return LocalDirectoryPublisher(Path(publish_dir))
    source = os.getenv("API_CONTRACT_INDEX_PUBLISH_SOURCE", "").strip()
    if not source:
        return None
    store = build_contract_store(prefix="API_CONTRACT_INDEX_PUBLISH_")
    prefix = os.getenv("API_CONTRACT_INDEX_PUBLISH_PREFIX", "indexes/releases").strip() or "indexes/releases"
    return ContractStoreArtifactPublisher(store, prefix=prefix)


def _build_cache_manager(cache_dir: str | None, index_base_url: str | None):
    resolved_cache_dir = _cache_dir(cache_dir)
    resolved_base_url = index_base_url or os.getenv("API_CONTRACT_INDEX_BASE_URL", "").strip() or None
    index_source = os.getenv("API_CONTRACT_INDEX_SOURCE", "").strip()
    if index_source:
        index_store = build_contract_store(prefix="API_CONTRACT_INDEX_")
        index_prefix = os.getenv("API_CONTRACT_INDEX_PREFIX", "indexes/releases").strip() or "indexes/releases"
        return LocalCacheManager(
            cache_dir=resolved_cache_dir,
            index_base_url=resolved_base_url,
            index_store=index_store,
            index_prefix=index_prefix,
        )
    if not resolved_base_url:
        raise RuntimeError("Missing index source. Set --index-base-url / API_CONTRACT_INDEX_BASE_URL or API_CONTRACT_INDEX_SOURCE.")
    return LocalCacheManager(cache_dir=resolved_cache_dir, index_base_url=resolved_base_url)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


if __name__ == "__main__":
    raise SystemExit(main())
