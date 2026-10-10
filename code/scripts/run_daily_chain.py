#!/usr/bin/env python3
"""外围编排：Daily 成功快照 → 独立长期推理；长期失败不改写 Daily。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _monorepo_root() -> Path:
    """含 AgriScope/ 与 data/ 的祖先目录即研发态 monorepo 根（data 与 models 所在）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "AgriScope").is_dir() and (p / "data").is_dir():
            return p
    return ROOT


PROJECT = _monorepo_root()


def eligible(summary: dict, code: int) -> bool:
    return (code == 0 and not summary.get("dry_run") and
            summary.get("snapshot_status") in ("complete", "partial") and
            summary.get("crawl_status") != "FAILED" and bool(summary.get("snapshot_hash")))


def main(argv=None) -> int:
    env = dict(os.environ, PROJECT_ROOT=str(PROJECT),
               PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "pipelines" / "modeling"),
                                           str(ROOT / "pipelines" / "modeling" / "src")]))
    daily = subprocess.run([sys.executable, "pipelines/daily/run_daily.py", *(argv or [])],
                           cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE)
    print(daily.stdout, end="")
    summaries = [line[8:] for line in daily.stdout.splitlines() if line.startswith("SUMMARY ")]
    summary = json.loads(summaries[-1]) if summaries else {}
    result = {"daily_exit": daily.returncode, "daily_snapshot_hash": summary.get("snapshot_hash")}
    if eligible(summary, daily.returncode):
        job = subprocess.run([sys.executable, "pipelines/long_horizon/run_long_horizon_job.py"], cwd=ROOT, env=env)
        result.update({"long_horizon_exit": job.returncode,
                       "status": "CHAIN_SUCCESS" if job.returncode == 0 else "DAILY_SUCCESS_LONG_HORIZON_FAILED"})
    else:
        result.update({"long_horizon_exit": None, "status": "LONG_HORIZON_SKIPPED_DAILY_NOT_SUCCESSFUL"})
    sys.path.insert(0, str(ROOT))
    from pipelines.long_horizon.run_long_horizon_job import atomic_json
    atomic_json(PROJECT / "data/processed/long_horizon/chain_status.json", result)
    print("CHAIN " + json.dumps(result, ensure_ascii=False))
    return daily.returncode if daily.returncode else (5 if result["long_horizon_exit"] else 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
