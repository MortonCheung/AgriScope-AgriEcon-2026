"""Explicit V2 retrain command; RC1 artifacts remain historical.

Use python -m long_horizon.run_long_horizon --retrain for authorized research.
Daily inference uses load_bundle()/predict_at(), never this entry point.
LLM experiments and Daily jobs have separate entry points.
"""
from __future__ import annotations
import argparse
import json


def run(*, retrain: bool = False) -> dict:
    if not retrain:
        raise ValueError("explicit retrain=True required; inference must load frozen artifacts")
    from .v2 import retrain as rebuild
    return rebuild()


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrain",action="store_true")
    args=parser.parse_args()
    if not args.retrain:
        parser.error("--retrain is required; Daily inference does not retrain")
    print(json.dumps(run(retrain=True),ensure_ascii=False))
