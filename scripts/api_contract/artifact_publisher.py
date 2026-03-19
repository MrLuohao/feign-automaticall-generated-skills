from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from .contract_store import ContractStore


class ArtifactPublisher(ABC):
    @abstractmethod
    def publish_release(self, build_dir: Path) -> None:
        raise NotImplementedError


class LocalDirectoryPublisher(ArtifactPublisher):
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir

    def publish_release(self, build_dir: Path) -> None:
        self.target_dir.mkdir(parents=True, exist_ok=True)
        for child in self.target_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for source in build_dir.iterdir():
            target = self.target_dir / source.name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)


class ContractStoreArtifactPublisher(ArtifactPublisher):
    def __init__(self, store: ContractStore, *, prefix: str = "indexes/releases"):
        self.store = store
        self.prefix = prefix.rstrip("/")

    def publish_release(self, build_dir: Path) -> None:
        upserts: dict[str, str | bytes] = {}
        for file_path in sorted(path for path in build_dir.rglob("*") if path.is_file()):
            relative_path = file_path.relative_to(build_dir).as_posix()
            target_path = f"{self.prefix}/{relative_path}" if self.prefix else relative_path
            if file_path.suffix == ".json":
                upserts[target_path] = file_path.read_text(encoding="utf-8")
            else:
                upserts[target_path] = file_path.read_bytes()
        existing_files = self.store.list_files(f"{self.prefix}/")
        deletes = [path for path in existing_files if path not in upserts]
        self.store.write_batch(upserts, deletes, commit_message="Publish API contract index artifacts")
