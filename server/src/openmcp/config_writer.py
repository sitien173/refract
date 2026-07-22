"""Atomic validated configuration writer preserving TOML comments."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import tomlkit

from openmcp.config import DaemonConfig, load_config, openmcp_home


def _dict_to_toml_doc(
    data: dict[str, Any],
    base_doc: tomlkit.TOMLDocument | None = None,
) -> tomlkit.TOMLDocument:
    doc = base_doc if base_doc is not None else tomlkit.document()

    # Section: daemon
    if "daemon" in data and isinstance(data["daemon"], dict):
        if "daemon" not in doc or not isinstance(doc.get("daemon"), dict):
            doc["daemon"] = tomlkit.table()
        d_table = doc["daemon"]
        for k, v in data["daemon"].items():
            if v is None:
                d_table.pop(k, None)
            else:
                d_table[k] = v
        for k in list(d_table.keys()):
            if k not in data["daemon"]:
                del d_table[k]

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
        for k in list(l_table.keys()):
            if k not in data["logging"]:
                del l_table[k]

    # Section: targets (Array of Tables)
    if "targets" in data and isinstance(data["targets"], list):
        a = tomlkit.aot()
        for target in data["targets"]:
            if isinstance(target, dict):
                t_table = tomlkit.table()
                for k, v in target.items():
                    if v is None:
                        continue
                    if isinstance(v, list):
                        arr = tomlkit.array()
                        arr.extend(v)
                        t_table[k] = arr
                    else:
                        t_table[k] = v
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
                    if wf_val is None:
                        prof_table.pop(wf_name, None)
                    elif isinstance(wf_val, dict):
                        if wf_name not in prof_table or not isinstance(prof_table.get(wf_name), dict):
                            prof_table[wf_name] = tomlkit.table()
                        wf_table = prof_table[wf_name]
                        for k, v in wf_val.items():
                            if v is None:
                                wf_table.pop(k, None)
                            elif isinstance(v, list):
                                arr = tomlkit.array()
                                arr.extend(v)
                                wf_table[k] = arr
                            else:
                                wf_table[k] = v
                        for k in list(wf_table.keys()):
                            if k not in wf_val:
                                del wf_table[k]
                    elif isinstance(wf_val, list):
                        arr = tomlkit.array()
                        arr.extend(wf_val)
                        prof_table[wf_name] = arr
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
        doc = _dict_to_toml_doc(content, base_doc=base_doc)
        toml_text = tomlkit.dumps(doc)
    else:
        toml_text = tomlkit.dumps(content)

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

    os.replace(tmp_path, target_path)
    return load_config(target_path)


__all__ = ["write_config"]
