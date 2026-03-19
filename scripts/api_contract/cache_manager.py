from __future__ import annotations

import gzip
import json
import hashlib
from datetime import datetime, timedelta, timezone
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .contract_store import ContractStore


STATE_FILE = "state.json"
MANIFEST_FILE = "manifest.json"


@dataclass
class CacheSyncStatus:
    manifest_version: str
    updated_services: int


class LocalCacheManager:
    def __init__(
        self,
        cache_dir: Path,
        index_base_url: str | None,
        *,
        index_store: ContractStore | None = None,
        index_prefix: str = "indexes/releases",
        timeout_seconds: int = 5,
        sync_interval_minutes: int = 0,
    ):
        self.cache_dir = cache_dir
        self.index_base_url = index_base_url.rstrip("/") if index_base_url else None
        self.index_store = index_store
        self.index_prefix = index_prefix.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.sync_interval_minutes = sync_interval_minutes

    def sync(self) -> CacheSyncStatus:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._load_remote_json(MANIFEST_FILE)
        current_manifest = self._load_local_manifest()
        current_versions = {
            item["service"]: item.get("shardVersion", "")
            for item in (current_manifest or {}).get("services", [])
        }
        updated_services = 0
        router_artifact = manifest.get("routerArtifact", {})
        self._download_and_extract_gzip(
            router_artifact["file"],
            self.cache_dir / "router.sqlite",
            expected_sha256=router_artifact.get("sha256"),
        )
        shards_dir = self.cache_dir / "shards"
        shards_dir.mkdir(parents=True, exist_ok=True)
        for item in manifest.get("services", []):
            service = item["service"]
            target = shards_dir / f"{service}.sqlite"
            if current_versions.get(service) != item.get("shardVersion") or not target.exists():
                self._download_and_extract_gzip(
                    item["artifact"],
                    target,
                    expected_sha256=item.get("artifactSha256"),
                )
                updated_services += 1
        (self.cache_dir / MANIFEST_FILE).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        state = {
            "manifestVersion": manifest.get("indexVersion", ""),
            "routerVersion": manifest.get("routerVersion", ""),
            "lastManifestCheckAt": _now_iso(),
            "lastSyncAt": _now_iso(),
            "serviceVersions": {
                item["service"]: item.get("shardVersion", "")
                for item in manifest.get("services", [])
            },
        }
        (self.cache_dir / STATE_FILE).write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return CacheSyncStatus(manifest_version=manifest.get("indexVersion", ""), updated_services=updated_services)

    def ensure_ready(self) -> None:
        has_cache = (self.cache_dir / "router.sqlite").exists()
        if not has_cache:
            self.sync()
            return
        if not self._should_check_manifest():
            return
        try:
            remote_manifest = self._load_remote_json(MANIFEST_FILE)
        except Exception:
            self._touch_manifest_check()
            return
        local_state = self.status()
        remote_version = str(remote_manifest.get("indexVersion", ""))
        if local_state.get("manifestVersion") != remote_version:
            self.sync()
            return
        self._touch_manifest_check()

    def status(self) -> dict[str, object]:
        state_path = self.cache_dir / STATE_FILE
        if not state_path.exists():
            return {"ready": False}
        return json.loads(state_path.read_text(encoding="utf-8"))

    def _should_check_manifest(self) -> bool:
        if self.sync_interval_minutes <= 0:
            return True
        state = self.status()
        last_checked = state.get("lastManifestCheckAt")
        if not last_checked:
            return True
        try:
            last_checked_at = datetime.fromisoformat(str(last_checked))
        except ValueError:
            return True
        return datetime.now(timezone.utc) - last_checked_at >= timedelta(minutes=self.sync_interval_minutes)

    def _touch_manifest_check(self) -> None:
        state = self.status()
        if not state.get("ready", True) and not (self.cache_dir / STATE_FILE).exists():
            return
        state["lastManifestCheckAt"] = _now_iso()
        (self.cache_dir / STATE_FILE).write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _download(self, relative_path: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        with urllib.request.urlopen(self._resolve_url(relative_path), timeout=self.timeout_seconds) as response:
            tmp_path.write_bytes(response.read())
        tmp_path.replace(target_path)

    def _download_and_extract_gzip(self, relative_path: str, target_path: Path, *, expected_sha256: str | None) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        compressed_tmp = target_path.with_suffix(target_path.suffix + ".gz.tmp")
        remote_bytes = self._read_remote_bytes(relative_path)
        if remote_bytes is None:
            raise RuntimeError(f"Missing remote artifact: {relative_path}")
        compressed_tmp.write_bytes(remote_bytes)
        if expected_sha256:
            actual_sha256 = hashlib.sha256(compressed_tmp.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                compressed_tmp.unlink(missing_ok=True)
                raise RuntimeError(f"Checksum mismatch for {relative_path}")
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        with gzip.open(compressed_tmp, "rb") as source:
            tmp_path.write_bytes(source.read())
        compressed_tmp.unlink(missing_ok=True)
        tmp_path.replace(target_path)

    def _load_remote_json(self, relative_path: str) -> dict[str, object]:
        if self.index_store is not None:
            path = self._store_path(relative_path)
            text = self.index_store.read_text(path)
            if text is None:
                raise RuntimeError(f"Missing remote manifest: {path}")
            return json.loads(text)
        with urllib.request.urlopen(self._resolve_url(relative_path), timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _load_local_manifest(self) -> dict[str, object] | None:
        path = self.cache_dir / MANIFEST_FILE
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_url(self, relative_path: str) -> str:
        base = self.index_base_url
        if base is None:
            raise RuntimeError("Missing index base URL.")
        if "://" not in base:
            return (Path(base) / relative_path).as_uri()
        return urllib.parse.urljoin(base + "/", relative_path)

    def _read_remote_bytes(self, relative_path: str) -> bytes | None:
        if self.index_store is not None:
            return self.index_store.read_bytes(self._store_path(relative_path))
        with urllib.request.urlopen(self._resolve_url(relative_path), timeout=self.timeout_seconds) as response:
            return response.read()

    def _store_path(self, relative_path: str) -> str:
        if not self.index_prefix:
            return relative_path
        return f"{self.index_prefix}/{relative_path}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
