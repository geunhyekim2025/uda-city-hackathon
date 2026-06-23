#!/usr/bin/env python
"""Static check: detect YAML keys that current supy silently ignores (#23).

supy's pydantic models drop unknown keys without erroring, so a config full
of legacy field names validates and runs while the intended values silently
fall back to supy defaults. This script walks the raw YAML against the
validated model dump and reports every key that did not survive the round
trip — i.e. every value the model is NOT actually using.

Exit codes: 0 = no drift, 1 = drift found, 2 = usage/load error.

Run:
    .venv/bin/python scripts/check_schema_drift.py [config.yml ...]

With no arguments it checks `uda-city.yml` plus every `config-ss/*.yml`.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.simplefilter("ignore")

import yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def iter_ignored(raw, loaded, path=""):
    """Yield dotted paths of keys present in raw YAML but absent from the
    validated-model dump (case-insensitive key match)."""
    if isinstance(raw, dict):
        if not isinstance(loaded, dict):
            # whole branch ignored / replaced by a scalar default
            yield path or "<root>"
            return
        loaded_by_lower = {k.lower(): k for k in loaded}
        for k, v in raw.items():
            sub = f"{path}.{k}" if path else str(k)
            lk = str(k).lower()
            if lk not in loaded_by_lower:
                yield sub
            else:
                yield from iter_ignored(v, loaded[loaded_by_lower[lk]], sub)
    elif isinstance(raw, list) and isinstance(loaded, list):
        for i, item in enumerate(raw):
            if i < len(loaded):
                yield from iter_ignored(item, loaded[i], f"{path}[{i}]")


def site_label(raw_cfg, dotted: str) -> str:
    """Replace a leading sites[i] with the site name for readability."""
    if dotted.startswith("sites["):
        idx = int(dotted.split("[", 1)[1].split("]", 1)[0])
        name = raw_cfg["sites"][idx].get("name", idx)
        return dotted.replace(f"sites[{idx}]", f"sites[{name}]", 1)
    return dotted


def check(config_path: Path) -> int:
    import warnings as _w

    from supy.data_model.core import SUEWSConfig

    raw = yaml.safe_load(config_path.read_text())
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        cfg = SUEWSConfig.model_validate(raw)
    deprecations = sorted({
        str(c.message) for c in caught
        if "deprecated" in str(c.message).lower()
    })
    dumped = cfg.model_dump()
    ignored = sorted(set(iter_ignored(raw, dumped)))
    if deprecations:
        print(f"DRIFT: {config_path.name} — {len(deprecations)} deprecated "
              f"field spellings still in use:")
        for msg in deprecations:
            print(f"  {msg}")
        if not ignored:
            return 1
    if not ignored:
        print(f"OK: {config_path.name} — no ignored keys")
        return 0
    # collapse identical per-site paths so the report stays readable
    seen: dict[str, list[str]] = {}
    for dotted in ignored:
        generic = dotted
        if dotted.startswith("sites["):
            generic = "sites[*]" + dotted.split("]", 1)[1]
        seen.setdefault(generic, []).append(site_label(raw, dotted))
    print(f"DRIFT: {config_path.name} — {len(ignored)} ignored keys "
          f"({len(seen)} unique paths):")
    for generic, instances in sorted(seen.items()):
        print(f"  {generic}  (x{len(instances)})")
    return 1


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [
        REPO_ROOT / "uda-city.yml",
        *sorted((REPO_ROOT / "config-ss").glob("*.yml")),
    ]
    status = 0
    for t in targets:
        if not t.is_file():
            print(f"missing: {t}", file=sys.stderr)
            return 2
        status |= check(t)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
