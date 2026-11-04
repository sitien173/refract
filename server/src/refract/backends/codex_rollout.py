"""Exact-session Codex rollout collector: bounded reads of one verified rollout file for telemetry."""

from __future__ import annotations

import json
import os
import re
import stat as stat_module
from pathlib import Path
from typing import Any

from refract.logging_setup import get_logger
from refract.telemetry import TokenCounters

log = get_logger("codex")


class _CodexRolloutCollector:
    """Bounded exact-session Codex rollout collector."""

    MAX_DISCOVERY_ENTRIES = 50
    MAX_DISCOVERY_RETRIES = 3
    MAX_DISCOVERY_DEPTH = 3

    def __init__(
        self,
        *,
        cwd: Path,
        session_id: str = "",
        counters: TokenCounters,
        emitter: Any = None,
    ) -> None:
        self.cwd = cwd
        self.session_id = session_id.strip()
        self.counters = counters
        self.emitter = emitter
        self.session_file: Path | None = None
        self.file_verified = False
        self.file_dev: int | None = None
        self.file_ino: int | None = None
        self.header_verified = False
        self.has_verified_context = False
        self.pending_context: tuple[int, int | None] | None = None
        self.budget_exhausted = False
        self.offset = 0
        self.partial_buffer = ""
        self.model_name: str | None = None
        self.is_compacted = False
        self.max_bytes_per_poll = 65536
        self.max_total_bytes = 1048576
        self.total_bytes_read = 0
        self.missing_discovery_retries = 0

    def set_session_id(self, session_id: str) -> None:
        sid = session_id.strip()
        if sid and sid != self.session_id:
            if self.session_id:
                self._emit_invalidation()
            self.session_id = sid
            self._reset_file_state()
            self.total_bytes_read = 0
            self.missing_discovery_retries = 0
            self.is_compacted = False

    def _reset_file_state(self) -> None:
        self.session_file = None
        self.file_verified = False
        self.file_dev = None
        self.file_ino = None
        self.header_verified = False
        self.has_verified_context = False
        self.pending_context = None
        self.budget_exhausted = False
        self.offset = 0
        self.partial_buffer = ""

    def _emit_invalidation(self, is_compaction: bool = False) -> None:
        self.pending_context = None
        self.has_verified_context = False
        self.counters.clear_context()
        if is_compaction:
            self.is_compacted = True
        if self.emitter is not None:
            self.emitter({"kind": "telemetry.updated", "data": self.counters.as_dict()})

    def _find_exact_file(self) -> Path | None:
        if not self.session_id or not _SESSION_ID_RE.fullmatch(self.session_id):
            return None
        if self.missing_discovery_retries >= self.MAX_DISCOVERY_RETRIES:
            return None

        sessions_dir = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
        if not sessions_dir.is_dir() or sessions_dir.is_symlink():
            self.missing_discovery_retries += 1
            return None

        try:
            resolved_sessions_dir = sessions_dir.resolve()
        except OSError:
            self.missing_discovery_retries += 1
            return None

        entries_inspected = 0
        dirs_to_visit = [(sessions_dir, 0)]
        found_file: Path | None = None

        while dirs_to_visit and entries_inspected < self.MAX_DISCOVERY_ENTRIES:
            current_dir, depth = dirs_to_visit.pop(0)
            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        entries_inspected += 1
                        if entries_inspected >= self.MAX_DISCOVERY_ENTRIES:
                            break

                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if depth < self.MAX_DISCOVERY_DEPTH:
                                    dirs_to_visit.append((Path(entry.path), depth + 1))
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                        except OSError:
                            continue

                        name = entry.name
                        if not (name.endswith(".jsonl") and self.session_id in name):
                            continue

                        file_path = Path(entry.path)
                        try:
                            if file_path.is_symlink():
                                continue
                            resolved_file = file_path.resolve()
                            if not resolved_file.is_relative_to(resolved_sessions_dir):
                                continue

                            stat = file_path.stat()
                            if stat.st_size < 10:
                                continue

                            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
                            fd = os.open(file_path, flags)
                            try:
                                opened = os.fstat(fd)
                                if not stat_module.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (stat.st_dev, stat.st_ino):
                                    continue
                                with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as f:
                                    fd = -1
                                    first_line = f.readline(4096)
                            finally:
                                if fd >= 0:
                                    os.close(fd)
                            if not first_line:
                                continue

                            parsed = json.loads(first_line)
                            if not isinstance(parsed, dict) or parsed.get("type") != "session_meta":
                                continue

                            payload = parsed.get("payload")
                            if not isinstance(payload, dict):
                                continue

                            payload_id = str(payload.get("id") or "").strip()
                            payload_cwd = payload.get("cwd")
                            if payload_id == self.session_id and _same_path(payload_cwd, self.cwd):
                                self.file_dev = opened.st_dev
                                self.file_ino = opened.st_ino
                                found_file = file_path
                                break
                        except (OSError, json.JSONDecodeError):
                            continue
            except OSError:
                continue

            if found_file is not None:
                break

        if found_file is None:
            self.missing_discovery_retries += 1
            return None

        return found_file

    def poll(self) -> None:
        try:
            self._poll_internal()
        except Exception:
            log.warning("codex: rollout poll error", exc_info=True)

    def _poll_internal(self) -> None:
        if not self.session_id:
            return
        if self.session_file is None:
            self.session_file = self._find_exact_file()
            if self.session_file is None:
                return
            try:
                st = self.session_file.stat()
                if self.file_dev is None or self.file_ino is None:
                    self.file_dev = st.st_dev
                    self.file_ino = st.st_ino
                self.file_verified = True
            except OSError:
                self._reset_file_state()
                return

        if not self.file_verified:
            return

        try:
            stat = self.session_file.stat()
        except OSError:
            self._emit_invalidation()
            self._reset_file_state()
            return

        if self.file_dev is not None and self.file_ino is not None:
            if (stat.st_dev, stat.st_ino) != (self.file_dev, self.file_ino):
                self._emit_invalidation()
                self._reset_file_state()
                return

        if stat.st_size < self.offset:
            self._emit_invalidation()
            self.header_verified = False
            self.offset = 0
            self.partial_buffer = ""
        elif stat.st_size > self.offset and self.has_verified_context:
            self._emit_invalidation()

        if stat.st_size == self.offset and not self.partial_buffer:
            return

        if self.total_bytes_read >= self.max_total_bytes:
            if not self.budget_exhausted:
                self._emit_invalidation()
                self.budget_exhausted = True
            return

        read_size = min(self.max_bytes_per_poll, self.max_total_bytes - self.total_bytes_read)
        if read_size <= 0:
            return

        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            fd = os.open(self.session_file, flags)
            try:
                opened = os.fstat(fd)
                if not stat_module.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (self.file_dev, self.file_ino):
                    self._emit_invalidation()
                    self._reset_file_state()
                    return
                with os.fdopen(fd, "rb") as f:
                    fd = -1
                    if not self.header_verified:
                        first_line = f.readline(4096)
                        try:
                            header = json.loads(first_line)
                            header_payload = header.get("payload") if isinstance(header, dict) else None
                            self.header_verified = (
                                isinstance(header, dict)
                                and header.get("type") == "session_meta"
                                and isinstance(header_payload, dict)
                                and str(header_payload.get("id") or "").strip() == self.session_id
                                and _same_path(header_payload.get("cwd"), self.cwd)
                            )
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            self.header_verified = False
                        if not self.header_verified:
                            self._emit_invalidation()
                            self._reset_file_state()
                            return
                    f.seek(self.offset)
                    chunk = f.read(read_size)
            finally:
                if fd >= 0:
                    os.close(fd)
        except OSError:
            self._emit_invalidation()
            self._reset_file_state()
            return

        if not chunk:
            return

        self.offset += len(chunk)
        self.total_bytes_read += len(chunk)

        text = self.partial_buffer + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self.partial_buffer = lines.pop()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if not isinstance(record, dict):
                continue
            self._process_record(record)

        if self.offset >= stat.st_size and not self.partial_buffer and self.pending_context is not None:
            used, window = self.pending_context
            self.counters.record_context(used=used, window=window)
            self.has_verified_context = True
            if self.emitter is not None:
                self.emitter({"kind": "telemetry.updated", "data": self.counters.as_dict()})
            self.pending_context = None

        if self.total_bytes_read >= self.max_total_bytes and stat.st_size > self.offset and not self.budget_exhausted:
            self._emit_invalidation()
            self.budget_exhausted = True

    def _process_record(self, record: dict[str, Any]) -> None:
        rec_type = record.get("type", "")
        payload = record.get("payload")

        if rec_type == "session_meta":
            if isinstance(payload, dict):
                sid = str(payload.get("id") or "").strip()
                scwd = payload.get("cwd")
                if sid != self.session_id or not _same_path(scwd, self.cwd):
                    self.file_verified = False
            return

        if not self.file_verified:
            return

        if rec_type == "event_msg" and isinstance(payload, dict):
            p_type = payload.get("type", "")
            if p_type == "token_count":
                info = payload.get("info")
                if not isinstance(info, dict):
                    return
                usage = info.get("last_token_usage")
                window = _as_int(info.get("model_context_window"))
                if not isinstance(usage, dict):
                    return
                input_tokens = _as_int(usage.get("input_tokens"))
                output_tokens = _as_int(usage.get("output_tokens"))
                reasoning_tokens = _as_int(usage.get("reasoning_output_tokens"))
                if input_tokens is None or output_tokens is None or reasoning_tokens is None:
                    return
                used = input_tokens + output_tokens - reasoning_tokens
                if used < 0:
                    return
                self.pending_context = (used, window)
            elif p_type == "context_compacted":
                self._emit_invalidation(is_compaction=True)
            elif p_type in ("session_configured", "model_reroute"):
                model = payload.get("model") or payload.get("to_model")
                if model:
                    model_str = str(model)
                    if self.model_name and self.model_name != model_str:
                        self._emit_invalidation(is_compaction=False)
                    self.model_name = model_str
        elif rec_type == "context_compacted":
            self._emit_invalidation(is_compaction=True)


def _as_int(val: Any) -> int | None:
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        return None
    return val


_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _same_path(left: Any, right: Path) -> bool:
    if not isinstance(left, str) or not left.strip():
        return False
    try:
        return Path(left).resolve() == right.resolve()
    except (OSError, ValueError, TypeError):
        try:
            return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
                os.path.abspath(os.fspath(right))
            )
        except Exception:
            return False
