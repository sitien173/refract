"""Atomic validated configuration writer preserving TOML comments."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import tomlkit

from openmcp.config import DaemonConfig, load_config, openmcp_home


def _values_equal(a: Any, b: Any) -> bool:

    """Compare two values for equality, handling tomlkit item types."""
    return str(a) == str(b)


def _set_value(table: Any, key: str, value: Any) -> None:
    """Set a key in a tomlkit table, preserving existing array trivia."""
    if isinstance(value, list):
        existing = table.get(key)
        if isinstance(existing, tomlkit.items.Array):
            # Rebuild element-by-element to preserve item trivia
            new_items: list[Any] = []
            for i, new_val in enumerate(value):
                if i < len(existing) and _values_equal(existing[i], new_val):
                    new_items.append(existing[i])
                elif isinstance(new_val, str):
                    new_items.append(tomlkit.string(new_val))
                elif isinstance(new_val, (int, float)):
                    new_items.append(new_val)
                elif isinstance(new_val, bool):
                    new_items.append(new_val)
                else:
                    new_items.append(tomlkit.item(new_val))
            existing.clear()
            for item in new_items:
                existing.append(item)
            return
        arr = tomlkit.array()
        for v in value:
            arr.append(v)
        table[key] = arr
    else:
        table[key] = value


def _dict_to_toml_doc(
    data: dict[str, Any],
    base_doc: tomlkit.TOMLDocument | None = None,
) -> tomlkit.TOMLDocument:
    unsupported = set(data) - {"daemon", "logging", "targets", "profiles"}
    if unsupported:
        raise ValueError(f"Unsupported config keys: {sorted(unsupported)}")

    # Validate section types before processing
    if "daemon" in data and not isinstance(data["daemon"], dict):
        raise ValueError("[daemon] must be a TOML table")
    if "logging" in data and not isinstance(data["logging"], dict):
        raise ValueError("[logging] must be a TOML table")
    if "targets" in data:
        if not isinstance(data["targets"], list):
            raise ValueError("[targets] must be a TOML array of tables")
        for i, t in enumerate(data["targets"]):
            if not isinstance(t, dict):
                raise ValueError(f"targets[{i}] must be a TOML table, got {type(t).__name__}")
    if "profiles" in data and not isinstance(data["profiles"], dict):
        raise ValueError("[profiles] must be a TOML table")
    if "profiles" in data:
        for prof_name, prof_data in data["profiles"].items():
            if not isinstance(prof_data, dict):
                raise ValueError(f"profiles.{prof_name} must be a TOML table, got {type(prof_data).__name__}")

    doc = base_doc if base_doc is not None else tomlkit.document()

    # Section: daemon
    if "daemon" in data:
        if "daemon" not in doc or not isinstance(doc.get("daemon"), dict):
            doc["daemon"] = tomlkit.table()
        d_table = doc["daemon"]
        for k, v in data["daemon"].items():
            if v is None:
                d_table.pop(k, None)
            else:
                d_table[k] = v

    # Section: logging
    if "logging" in data and isinstance(data["logging"], dict):
        if "logging" not in doc or not isinstance(doc.get("logging"), dict):
            doc["logging"] = tomlkit.table()
        l_table = doc["logging"]
        for k, v in data["logging"].items():
            if v is None:
                l_table.pop(k, None)
            else:
                l_table[k] = v

    # Section: targets (Array of Tables)
    if "targets" in data:
        existing_targets = doc.get("targets")
        existing_by_id: dict[str, Any] = {}
        if isinstance(existing_targets, tomlkit.items.AoT):
            for ex_target in existing_targets:
                if isinstance(ex_target, dict) and "id" in ex_target:
                    existing_by_id[str(ex_target["id"])] = ex_target
        a = tomlkit.aot()
        for target in data["targets"]:
            target_id = str(target.get("id", ""))
            if target_id and target_id in existing_by_id:
                t_table = existing_by_id[target_id]
            else:
                t_table = tomlkit.table()
            # Migrate legacy target keys
            t_table.pop("profile", None)
            t_table.pop("capabilities", None)
            for k, v in target.items():
                if k == "capabilities":
                    continue
                if v is None:
                    t_table.pop(k, None)
                    continue
                _set_value(t_table, k, v)
            a.append(t_table)
        doc["targets"] = a

    # Section: profiles
    if "profiles" in data and isinstance(data["profiles"], dict):
        if "profiles" not in doc or not isinstance(doc.get("profiles"), dict):
            doc["profiles"] = tomlkit.table()
        p_table = doc["profiles"]
        for prof_name, prof_data in data["profiles"].items():
            if prof_name not in p_table or not isinstance(p_table.get(prof_name), dict):
                p_table[prof_name] = tomlkit.table()
            prof_table = p_table[prof_name]
            if isinstance(prof_data, dict):
                for wf_name, wf_val in prof_data.items():
                    if wf_name == "extends":
                        if wf_val is None:
                            prof_table.pop(wf_name, None)
                        else:
                            prof_table[wf_name] = wf_val
                        continue
                    if wf_val is None:
                        prof_table.pop(wf_name, None)
                    elif isinstance(wf_val, dict):
                        existing = prof_table.get(wf_name)
                        # Preserve compact list form (e.g. implement = ["target"])
                        # only when incoming dict has no retry settings changed
                        if isinstance(existing, tomlkit.items.Array):
                            incoming_targets = wf_val.get("targets", [])
                            existing_vals = [str(v) for v in existing]
                            # The effective default is len(existing) when loaded from compact form
                            effective_max = len(existing)
                            incoming_max = wf_val.get("max_attempts", effective_max)
                            incoming_timeout = wf_val.get("timeout_s", 0)
                            if (incoming_targets == existing_vals
                                    and incoming_max == effective_max
                                    and incoming_timeout == 0):
                                continue
                            # Convert compact list to full table when retry settings change
                            prof_table[wf_name] = tomlkit.table()
                        if wf_name not in prof_table or not isinstance(prof_table.get(wf_name), dict):
                            prof_table[wf_name] = tomlkit.table()
                        wf_table = prof_table[wf_name]
                        for k, v in wf_val.items():
                            if v is None:
                                wf_table.pop(k, None)
                            else:
                                _set_value(wf_table, k, v)
                    elif isinstance(wf_val, list):
                        _set_value(prof_table, wf_name, wf_val)
                    else:
                        prof_table[wf_name] = wf_val
                for wf_name in list(prof_table.keys()):
                    if wf_name not in prof_data:
                        del prof_table[wf_name]
        for prof_name in list(p_table.keys()):
            if prof_name not in data["profiles"]:
                del p_table[prof_name]

    return doc


def write_config(
    content: str | dict[str, Any] | tomlkit.TOMLDocument,
    path: Path | None = None,
) -> DaemonConfig:
    """Validate and write daemon configuration atomically with backup."""
    target_path = path if path is not None else (openmcp_home() / "config.toml")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, str):
        try:
            tomlkit.parse(content)
        except Exception as exc:
            raise ValueError(f"Invalid TOML content: {exc}") from exc
        toml_text = content
    elif isinstance(content, dict):
        base_doc = None
        if target_path.exists():
            try:
                base_doc = tomlkit.parse(target_path.read_text(encoding="utf-8"))
            except Exception:
                base_doc = None
        try:
            doc = _dict_to_toml_doc(content, base_doc=base_doc)
            toml_text = tomlkit.dumps(doc)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Invalid config structure: {exc}") from exc
    elif isinstance(content, tomlkit.TOMLDocument):
        toml_text = tomlkit.dumps(content)
    else:
        raise ValueError(f"Invalid payload type: expected dict, str, or TOMLDocument, got {type(content).__name__}")

    tmp_path = target_path.parent / f".tmp_{uuid.uuid4().hex}.toml"
    try:
        tmp_path.write_text(toml_text, encoding="utf-8")
        load_config(tmp_path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise ValueError(f"Invalid configuration: {exc}") from exc

    if target_path.exists():
        bak_path = target_path.parent / f"{target_path.name}.bak"
        shutil.copy2(target_path, bak_path)

    if target_path.exists():
        os.chmod(tmp_path, target_path.stat().st_mode)

    os.replace(tmp_path, target_path)
    return load_config(target_path)


def write_task_guide(
    content: str | dict[str, Any],
    path: Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Validate and write task guide atomically with backup."""
    from openmcp.config import load_task_guide

    if path is not None:
        target_path = path
    elif home is not None:
        target_path = home / "task_guide.json"
    else:
        target_path = openmcp_home() / "task_guide.json"

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, str):
        try:
            json.loads(content)
        except Exception as exc:
            raise ValueError(f"Invalid JSON content: {exc}") from exc
        json_text = content
    elif isinstance(content, dict):
        json_text = json.dumps(content, indent=2)
    else:
        json_text = json.dumps(content, indent=2)

    tmp_dir = target_path.parent / f".tmp_dir_{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / "task_guide.json"

    try:
        tmp_file.write_text(json_text, encoding="utf-8")
        load_task_guide(home=tmp_dir)
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"Invalid task guide: {exc}") from exc

    try:
        if target_path.exists():
            bak_path = target_path.parent / f"{target_path.name}.bak"
            shutil.copy2(target_path, bak_path)
            os.chmod(tmp_file, target_path.stat().st_mode)

        os.replace(tmp_file, target_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return load_task_guide(home=target_path.parent)


__all__ = ["write_config", "write_task_guide"]
