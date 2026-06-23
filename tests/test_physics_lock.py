"""Physics lock for the canonical hackathon city.

The hackathon design fixes ONE physics route for `uda-city.yml`: NARP net
radiation + classic OHM storage heat, baked on disk, laptop-runnable. This is
a deliberate design decision (no SPARTACUS, no dynamic OHM) — see the
"No SPARTACUS" and "Don't use dynamic OHM" gotchas in README.md.

These tests turn that decision into a contract: if anyone (a participant, or
the suews-agent "improving" the config) flips the canonical config to
SPARTACUS radiation (`net_radiation = 1003`) or dynamic OHM
(`storage_heat = 5`), this gate fails. It reads the raw YAML, not the
validated model, because the contract is about what is *baked on disk*.

Scope: the canonical `uda-city.yml` ONLY. The `config-ss/*.yml` files are
internal morphology sources that legitimately retain `net_radiation = 1003`
as a SPARTACUS morphology container (see config-ss/README.md); they are not
asserted here.

    .venv/bin/python -m pytest tests/test_physics_lock.py -v
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPO_ROOT / "uda-city.yml"

# SUEWS method codes for the locked route.
NARP = 3          # net_radiation: NARP (laptop-runnable); 1003 = SPARTACUS
CLASSIC_OHM = 1   # storage_heat: classic OHM; 5 = dynamic OHM (NaN-prone here)
OHM_NO_QF = 0     # ohm_inc_qf: storage does not ingest anthropogenic QF


def _physics() -> dict:
    raw = yaml.safe_load(CANONICAL.read_text())
    return raw["model"]["physics"]


def test_net_radiation_is_narp_not_spartacus() -> None:
    assert _physics()["net_radiation"]["value"] == NARP, (
        "canonical uda-city.yml must use NARP (net_radiation = 3), not "
        "SPARTACUS (1003): SPARTACUS is deliberately not a hackathon route."
    )


def test_storage_heat_is_classic_ohm() -> None:
    assert _physics()["storage_heat"]["value"] == CLASSIC_OHM, (
        "canonical uda-city.yml must use classic OHM (storage_heat = 1); "
        "dynamic OHM (5) diverges to NaN on these tropical surfaces."
    )


def test_ohm_does_not_ingest_qf() -> None:
    assert _physics()["ohm_inc_qf"]["value"] == OHM_NO_QF, (
        "canonical uda-city.yml must keep ohm_inc_qf = 0."
    )
