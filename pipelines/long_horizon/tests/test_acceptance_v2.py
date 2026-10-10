"""Artifact acceptance is deliberately read-only; production assets must exist."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from long_horizon.acceptance_v2 import run


def test_long_horizon_v2_artifact_acceptance():
    result=run()
    failures=[row["check"] for row in result["checks"] if not row["pass"]]
    assert not failures,failures
    assert result["registry_rows"]==120
