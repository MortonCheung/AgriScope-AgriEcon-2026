# -*- coding: utf-8 -*-
"""C2: 旧 v1 依赖审计（静态 + 运行时文件访问），对应 §6/§60。

静态：扫描 models/src/** 中对 v1 快照 / decision_dataset_v1 / model_selection.csv /
      city_data / retained_source / archive 的引用，区分「Final 生产路径」与「LEGACY」。
运行时：instrument pandas IO + builtins.open，运行 Final 生产入口，记录真实访问文件，
        断言 Final 生产路径不访问任何 v1 / legacy 数据。
"""
from __future__ import annotations
import builtins
import io
import json
import os
import re
from typing import Dict, List

import pandas as pd

from decision_engine.final.fcommon import (ROOT, DE, MANIFEST_DIR, ensure_dir, write_json, now_stamp)

FORBIDDEN = [
    r"snapshots[/\\]v1", r"snapshots[/\\]v2", r"decision_dataset_v1",
    r"evaluation[/\\]metrics[/\\]model_selection",   # 精确到 v1 指标路径（排除 price_model_selection.csv）
    r"city_data", r"retained_source", r"archive[/\\]", r"old_marts", r"decision_engine_supplement",
]
FORBIDDEN_RE = re.compile("|".join(FORBIDDEN), re.I)
# 只有「真实读取调用」才算依赖；纯注释/文档字符串/说明不计入
READ_CALL_RE = re.compile(r"read_csv|read_parquet|\bopen\(|de_path\(|\.read_text\(", re.I)
# Final 生产路径（不得含 v1 依赖）
PROD_SCOPE = ["final/", "run_final.py", "check_acceptance_final.py"]
SELF = "final/audit_paths.py"


def _is_comment_or_doc(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("#") or s.startswith("- ") or s.startswith('"""') or s.startswith("'''") \
        or s.startswith("-  ") or s.startswith("（") or s.startswith("- `")


def static_scan() -> pd.DataFrame:
    rows = []
    for base in [DE / "src", DE / "scripts", DE / "tests"]:
        for p in sorted(base.rglob("*.py")):
            rel = str(p.relative_to(DE))
            if rel.endswith(SELF):
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            hits = []
            for i, line in enumerate(txt.splitlines(), 1):
                if FORBIDDEN_RE.search(line):
                    kind = "code_read" if (READ_CALL_RE.search(line) and not _is_comment_or_doc(line)) else "mention"
                    hits.append({"line": i, "kind": kind, "text": line.strip()[:120]})
            if hits:
                in_prod = any(s in rel for s in PROD_SCOPE)
                n_read = sum(1 for h in hits if h["kind"] == "code_read")
                rows.append({"file": rel, "n_hits": len(hits), "n_code_reads": n_read,
                             "in_final_production_scope": in_prod,
                             "hits": json.dumps(hits[:5], ensure_ascii=False)})
    return pd.DataFrame(rows)


class _Tracer:
    def __init__(self):
        self.paths: List[str] = []
        self._orig_read_parquet = pd.read_parquet
        self._orig_read_csv = pd.read_csv
        self._orig_open = builtins.open

    def __enter__(self):
        def rp(path, *a, **k):
            self.paths.append(str(path)); return self._orig_read_parquet(path, *a, **k)
        def rc(path, *a, **k):
            self.paths.append(str(path)); return self._orig_read_csv(path, *a, **k)
        def op(file, *a, **k):
            try:
                self.paths.append(str(file))
            except Exception:
                pass
            return self._orig_open(file, *a, **k)
        pd.read_parquet = rp
        pd.read_csv = rc
        builtins.open = op
        return self

    def __exit__(self, *exc):
        pd.read_parquet = self._orig_read_parquet
        pd.read_csv = self._orig_read_csv
        builtins.open = self._orig_open
        return False


def runtime_audit() -> Dict[str, object]:
    from decision_engine.final.inference import FinalDecisionEngine
    eng = FinalDecisionEngine()  # 强制实例化（会触发全部数据装载）
    reqs = [
        {"city": "沈阳", "crop": "西红柿", "area_mu": 60, "horizon_days": 30},
        {"city": "沈阳", "crop": "黄瓜", "area_mu": 60, "horizon_days": 90,
         "actual_cost_per_mu": 20000, "actual_yield_per_mu": 4000},
        {"city": "朝阳", "crop": "土豆", "area_mu": 40, "horizon_days": 14},
        {"city": "大连", "crop": "西红柿", "horizon_days": 30},
    ]
    with _Tracer() as t:
        for r in reqs:
            eng.evaluate(r)
    # 覆盖 Final 优化路径（Pareto / 窗口 / 面积 / 组合 / 压力 / regret）
    from decision_engine.final import optimize as OPT
    with _Tracer() as t2:
        cuts = OPT.rep_cutoffs()
        if cuts:
            c = OPT.build_candidates(cuts[len(cuts) // 2])
            if len(c):
                OPT.run_pareto(c)
                OPT.run_window_area(c)
                OPT.run_portfolio(c, risk_preference="balanced")
                OPT.run_stress_regret(c)
                OPT.robustness_extensions(c)
        t.paths.extend(t2.paths)
    accessed = sorted(set(t.paths))
    forbidden = [p for p in accessed if FORBIDDEN_RE.search(p)]
    out = {
        "n_files_accessed": len(accessed),
        "forbidden_accessed": forbidden,
        "final_production_v1_dependency": len(forbidden),
        "pass": len(forbidden) == 0,
        "sample_accessed": accessed[:15],
        "ts": now_stamp(),
    }
    return out


def run() -> Dict[str, object]:
    ensure_dir(MANIFEST_DIR)
    st = static_scan()
    st.to_csv(MANIFEST_DIR / "static_dependency_scan.csv", index=False, encoding="utf-8-sig")
    prod = st[(st["in_final_production_scope"]) & (st["n_code_reads"] > 0)] if len(st) else st
    rt = runtime_audit()
    out = {
        "static_files_with_v1_refs_total": int(len(st)),
        "static_legacy_files_with_v1_code_reads": int((st["n_code_reads"] > 0).sum()) if len(st) else 0,
        "static_final_production_files_with_v1_code_reads": int(len(prod)) if len(prod) else 0,
        "static_final_production_offenders": prod["file"].tolist() if len(prod) else [],
        "static_final_production_hits": prod["hits"].tolist() if len(prod) else [],
        "runtime": rt,
        "final_production_v1_dependency": (int(len(prod)) if len(prod) else 0) + int(rt["final_production_v1_dependency"]),
        "pass": (len(prod) == 0) and rt["pass"],
    }
    write_json(out, MANIFEST_DIR / "dependency_audit.json")
    return out


if __name__ == "__main__":
    r = run()
    print(json.dumps(r, ensure_ascii=False, indent=1)[:2500])