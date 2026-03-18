from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .contract_store import build_contract_store
from .doc_renderer import write_doc
from .generator import generate_client
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
        store = build_contract_store() if args.command != "doc" else None
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
        if args.command == "consumer" and args.consumer_command == "search":
            print("正在检索接口...")
            operation_id, controller_name = search_operation(
                store,
                args.query,
                consumer_repo=Path(args.consumer_repo) if args.consumer_repo else None,
            )
            print("检索成功")
            print(f"{operation_id}\t{controller_name}")
            return 0
        if args.command == "consumer" and args.consumer_command == "generate":
            print("正在生成调用代码...")
            output = generate_client(
                store,
                args.operation_id,
                args.target,
                Path(args.output_root) if args.output_root else None,
                consumer_repo=Path(args.consumer_repo),
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

    consumer = subparsers.add_parser("consumer")
    consumer_sub = consumer.add_subparsers(dest="consumer_command")
    consumer_search = consumer_sub.add_parser("search")
    consumer_search.add_argument("--query", required=True)
    consumer_search.add_argument("--consumer-repo")

    consumer_generate = consumer_sub.add_parser("generate")
    consumer_generate.add_argument("--operation-id", required=True)
    consumer_generate.add_argument("--target")
    consumer_generate.add_argument("--output-root")
    consumer_generate.add_argument("--consumer-repo", required=True)

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
