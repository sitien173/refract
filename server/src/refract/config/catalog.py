"""Live configuration: the global catalog, per-project catalogs, and config health.

Parsed files are cached by file identity and parsed again only on change. Every method that reads or
reloads shares one lock with the runtime, so admission and a reload never interleave.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from collections.abc import Callable
from pathlib import Path

from refract.config.inspection import bound_error, sanitize_config_error, utc_now
from refract.config.load import load_config, load_project_config, resolve_target_environment
from refract.config.models import DaemonConfig
from refract.models import ConfigHealth, ProjectView

_FileIdentity = tuple[int, int, int]
_ProjectEntry = tuple[_FileIdentity | None, DaemonConfig, DaemonConfig, str, str | None]


def file_digest(path: Path) -> str | None:
    """Hash the file so a same-size rewrite within one file-time tick still changes the cache key."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def file_identity(path: Path) -> _FileIdentity | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size, info.st_ino)


def seed_config_health(config: DaemonConfig) -> ConfigHealth:
    loaded_at = config.config_loaded_at or utc_now()
    return ConfigHealth(
        attempted_at=loaded_at,
        successful_at=loaded_at,
        source_path=config.config_path.as_posix() if config.config_path else "",
        modification_time=config.config_modification_time,
        revision=config.config_revision,
        valid=True,
        last_known_good_revision=config.config_revision,
    )


class Catalog:
    """`current` is the last good global config; `on_reload` receives each newly loaded one."""

    def __init__(
        self, config: DaemonConfig, lock: threading.RLock, on_reload: Callable[[DaemonConfig], None]
    ) -> None:
        self.config = config
        self.current = config
        self.lock = lock
        self.health = seed_config_health(config)
        self._on_reload = on_reload
        self._stat: _FileIdentity | None = None
        # A per-catalog secret makes revision contexts opaque and prevents
        # session keys from becoming fingerprints of secret-bearing config hashes.
        self._revision_secret = secrets.token_bytes(32)
        self.project_cache: dict[Path, _ProjectEntry] = {}

    def reload_locked(self) -> DaemonConfig:
        """Reload the global config when its file changed; the caller holds the lock."""
        if self.config.config_path is None:
            return self.current
        stat = file_identity(self.config.config_path)
        if stat is not None and stat == self._stat:
            return self.current
        try:
            catalog = load_config(self.config.config_path)
        except ValueError as exc:
            self._stat = None
            self.health = self.health.model_copy(
                update={
                    "attempted_at": getattr(exc, "attempted_at", utc_now()),
                    "source_path": Path(getattr(exc, "path", self.config.config_path)).as_posix(),
                    "modification_time": getattr(exc, "modification_time", ""),
                    "revision": getattr(exc, "revision", ""),
                    "valid": False,
                    "latest_error": bound_error(sanitize_config_error(exc)),
                }
            )
            raise
        previous = self.health
        self.current = catalog
        self._stat = stat
        # Planning and execution must read the same settings after any reload.
        self._on_reload(catalog)
        self.health = ConfigHealth(
            attempted_at=catalog.config_loaded_at or utc_now(),
            successful_at=catalog.config_loaded_at or utc_now(),
            source_path=catalog.config_path.as_posix() if catalog.config_path else "",
            modification_time=catalog.config_modification_time,
            revision=catalog.config_revision,
            valid=True,
            latest_error="",
            last_known_good_revision=catalog.config_revision or previous.last_known_good_revision,
        )
        return self.current

    def publish(self) -> None:
        """Reload from the committed file, so disk and memory agree after a global mutation."""
        with self.lock:
            self._stat = None
            self.reload_locked()

    def project_snapshot(self, root: Path, base: DaemonConfig) -> tuple[DaemonConfig, str]:
        config_path = root / ".refract" / "config.toml"
        for _ in range(3):
            before = file_identity(config_path)
            before_digest = file_digest(config_path)
            cached = self.project_cache.get(root)
            if cached is not None and cached[0] == before and cached[4] == before_digest and cached[1] is base:
                return cached[2], cached[3]
            catalog = load_project_config(root, base)
            after = file_identity(config_path)
            if before != after or before_digest != file_digest(config_path):
                continue
            # Bind sessions to environment configuration, not unrelated target
            # capacity. Environment values stay inside this keyed opaque digest.
            environment_config = {
                "targets": [
                    {"id": target.id, "env": target.env}
                    for target in sorted(catalog.targets, key=lambda item: item.id)
                ],
            }
            payload = json.dumps([environment_config, after], sort_keys=True, separators=(",", ":")).encode("utf-8")
            revision = hmac.new(self._revision_secret, payload, "sha256").hexdigest()
            self.project_cache[root] = (after, base, catalog, revision, before_digest)
            return catalog, revision
        raise ValueError("Project configuration changed during loading")

    def project_catalog(self, root: Path, base: DaemonConfig) -> DaemonConfig:
        return self.project_snapshot(root, base)[0]

    def for_root(self, root: Path) -> DaemonConfig:
        """The project's catalog on top of a freshly reloaded global one."""
        with self.lock:
            return self.project_catalog(root, self.reload_locked())

    def for_root_cached(self, root: Path) -> DaemonConfig:
        """The project's catalog without attempting a global reload."""
        return self.project_catalog(root, self.current)

    def resolve_target_environment(self, project: ProjectView, target_id: str) -> tuple[dict[str, str], str]:
        """Resolve a marked target against the current project catalog off-loop."""
        with self.lock:
            catalog, revision = self.project_snapshot(Path(project.root), self.reload_locked())
            target = next((item for item in catalog.targets if item.id == target_id), None)
            if target is None:
                raise ValueError("Unknown target")
            return resolve_target_environment(catalog, target), revision
