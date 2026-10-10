"""run_research.py — 六城研究统一入口。

用法（在 AgriScope/ 下）：
    python3 -m pipelines.research.run_research --module A01 --cities five
    python3 -m pipelines.research.run_research --module A01 --cities chaoyang
    python3 -m pipelines.research.run_research --module A01 --cities all

cities: all(六城,含沈阳) | five(五城,不含沈阳) | 逗号分隔城市代码
"""
from __future__ import annotations

import argparse
import importlib
import sys
import traceback

from .lib import paths

MODULES = {
    "A01": "a01_market_time",
    "A02": "a02_weather_market",
    "A03": "a03_lag_accumulation",
    "A04": "a04_extreme_events",
    "A05": "a05_crop_heterogeneity",
    "A06": "a06_predictability",
    "A07": "a07_production_structure",
    "A08": "a08_robustness",
    "A09": "a09_city_special",
    "CROSS": "cross_city",
}


def _resolve_cities(spec: str):
    if spec == "all":
        return paths.CITIES_ALL
    if spec == "five":
        return paths.CITIES_FIVE
    return [c.strip() for c in spec.split(",") if c.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True, choices=list(MODULES.keys()))
    ap.add_argument("--cities", default="five")
    args = ap.parse_args(argv)

    cities = _resolve_cities(args.cities)
    mod = importlib.import_module(f".modules.{MODULES[args.module]}", package="pipelines.research")
    print(f"[run_research] module={args.module} cities={cities}")
    if args.module == "CROSS":
        r = mod.run()
        print(f"  OK   CROSS: {r}")
        return {"cross_city": r}
    results = {}
    for c in cities:
        try:
            results[c] = mod.run(c)
            print(f"  OK   {c}: {results[c]}")
        except Exception as e:  # noqa: BLE001
            results[c] = {"error": str(e)}
            print(f"  FAIL {c}: {e}")
            traceback.print_exc()
    return results


if __name__ == "__main__":
    main(sys.argv[1:])