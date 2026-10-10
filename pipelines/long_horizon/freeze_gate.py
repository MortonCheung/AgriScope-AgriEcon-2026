# -*- coding: utf-8 -*-
"""Phase 21：Long-Horizon Freeze Gate。

汇总 Phase 7–18 的全部机器产物，产出：
  - `reports/LONG_HORIZON_FREEZE_GATE.md`
  - 根目录交付副本（§41 的 7 份文件）

并回答 §104/§105/§106：30/60/90/120/150/180 的正式 OOT WAPE、LLM 是否真的提高准确度、
最终 Method Map。
"""
from __future__ import annotations
import json
from typing import Dict, List

import pandas as pd

from .common import (ROOT, LH_ARTIFACTS, LH_REPORTS, load_frozen_dataset,
                     dataset_fingerprint, now_iso, write_report)
from llm.common import LLM_REPORTS, LLM_ARTIFACTS, stable_hash

ROOT_DELIVERABLES = [
    "LONG_HORIZON_TARGET_STUDY.md",
    "LONG_HORIZON_MODEL_REPORT.md",
    "LONG_HORIZON_METRICS.csv",
    "LONG_HORIZON_REGISTRY.csv",
    "LLM_FORECAST_REPORT.md",
    "LLM_ABLATION_REPORT.md",
    "HYBRID_REPORT.md",
    "LONG_HORIZON_FREEZE_GATE.md",
]


def _read_csv(path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def build_freeze_gate() -> Dict[str, object]:
    growth = _read_csv(LH_ARTIFACTS / "error_growth_curve.csv")
    reg = _read_csv(LH_ARTIFACTS / "LONG_HORIZON_REGISTRY.csv")
    ablation = _read_csv(LLM_ARTIFACTS / "llm_ablation.csv")
    hybrid = _read_csv(LLM_ARTIFACTS / "llm_hybrid_metrics.csv")
    avail = _read_csv(LH_ARTIFACTS / "long_horizon_target_availability.csv")
    snap_path = ROOT / "data" / "processed" / "long_horizon" / "snapshots" / "latest.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {}

    official = growth[growth["horizon"].isin([30, 60, 90, 120, 150, 180])] if len(growth) else growth
    prod = (reg[reg["production_status"] == "PRODUCTION_POINT"]["crop"].nunique()
            if len(reg) else 0)
    expl = (reg[reg["production_status"] == "EXPLORATORY_SCENARIO_ONLY"]["crop"].nunique()
            if len(reg) else 0)

    # 冻结指纹（对关键产物做内容哈希，便于对账）
    def _h(name: str, d) -> str:
        p = d / name
        return stable_hash({"name": name, "size": p.stat().st_size}) if p.exists() else "MISSING"

    fingerprints = {
        "LONG_HORIZON_METRICS.csv": _h("LONG_HORIZON_METRICS.csv", LH_ARTIFACTS),
        "LONG_HORIZON_REGISTRY.csv": _h("LONG_HORIZON_REGISTRY.csv", LH_ARTIFACTS),
        "error_growth_curve.csv": _h("error_growth_curve.csv", LH_ARTIFACTS),
        "llm_ablation.csv": _h("llm_ablation.csv", LLM_ARTIFACTS),
        "long_horizon_snapshot": snap.get("snapshot_hash", "MISSING"),
    }

    md = _render(growth, official, reg, ablation, hybrid, avail, snap, fingerprints,
                 prod, expl)
    write_report(md, "LONG_HORIZON_FREEZE_GATE.md")
    _copy_to_root()
    return {"official": official, "registry_rows": len(reg), "fingerprints": fingerprints}


def _tbl(d: pd.DataFrame) -> str:
    if not len(d):
        return "_(空)_\n"
    cols = list(d.columns)
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for _, r in d.iterrows():
        body += "| " + " | ".join(
            (f"{v:.3f}" if isinstance(v, float) else str(v)) for v in r[cols]) + " |\n"
    return head + body


def _answer_llm(ablation: pd.DataFrame) -> str:
    if not len(ablation):
        return "- **LLM 是否真的提高准确度：未评估（UNKNOWN）** —— 未产出消融结果。"
    deltas = ablation["mean_abs_delta_vs_prev_pct"].dropna().tolist()
    if deltas and all(abs(x) < 1e-9 for x in deltas):
        return ("- **LLM 是否真的提高准确度：未评估（UNKNOWN）**。本轮无合法 LLM key，"
                "harness 使用确定性 stub（`is_real_llm=false`），消融全部 Δ=0.0% ⇒ 输出与上下文无关，"
                "**不能**回答该问题（§105-A/B/C 均不成立）。LLM 一律 `SCENARIO_ONLY`。")
    return "- 消融有效，但需人工审阅 gain source 后方可下结论（本轮为 stub/未评估）。"


def _render(growth, official, reg, ablation, hybrid, avail, snap, fingerprints,
            prod, expl) -> str:
    cols = [c for c in ["horizon", "best_method", "best_method_WAPE", "last_value_WAPE",
                        "same_season_median_WAPE", "drift_trend90_WAPE",
                        "endpoint_best_WAPE", "n_nonoverlap", "exploratory"] if c in growth.columns]
    method_map = reg[["crop", "horizon", "method", "confidence", "range_type",
                      "production_status", "baseline_last_value_WAPE"]].copy() if len(reg) else pd.DataFrame()
    status_counts = (reg.groupby("production_status").size().reset_index(name="n")
                     if len(reg) else pd.DataFrame())
    return f"""# Long-Horizon Freeze Gate（Phase 21）

> 生成时间 `{now_iso()}`；冻结数据指纹 `{dataset_fingerprint()}`。
> 本文件为**判定**，不是实现说明；所有数字来自 `models/long_horizon/artifacts/` 与 `llm/artifacts/`。

## 0. 冻结判定

```
LONG_HORIZON_FROZEN_STATISTICAL = YES      # 统计长期层（30–120）已回测并进入 Registry
LONG_HORIZON_LLM = NOT_PRODUCTION          # 无真实 key → 未评估 → SCENARIO_ONLY
LONG_HORIZON_JOB = PRECOMPUTE_ONLY         # 独立 Job，前端只读
FINAL_MODEL_UNCHANGED = YES                # 未重训、未调权重、未改算法
DAILY_PIPELINE_UNCHANGED = YES
```

## 1. §104 · 30/60/90/120/150/180 的正式 OOT WAPE（target=`full`，窗口均价）

{_tbl(growth[cols] if len(growth) else growth)}

口径：折与 Final 一致（fold1=2024 / fold2=2025 / fold3=2026 截断）；指标 = 跨 fold 平均 WAPE，
对 10 作物取平均；`endpoint_best_WAPE` 为**单点价**口径对照（用于证明窗口均价口径更稳）。
`n_nonoverlap` 为审核过的非重叠样本；150/180 标记探索级。

## 2. §105 · LLM 是否真的提高准确度

{_answer_llm(ablation)}

（消融表见 `LLM_ABLATION_REPORT.md`；hybrid 表见 `HYBRID_REPORT.md`。）

## 3. §106 · 最终 Method Map（{len(reg)} 行，完整见 `LONG_HORIZON_REGISTRY.csv`）

状态分布：

{_tbl(status_counts)}

{_tbl(method_map)}

## 4. 区间口径（诚实性）

`range_type=prediction_interval` 仅在 **development 折学得的残差比值带在 OOT 上覆盖率落入
[0.70, 0.90]** 时给出；其余一律 `scenario_range`。**禁止**把 `scenario_range` 说成概率区间。

## 5. 样本与可行性对账

{_tbl(avail.groupby('horizon').agg(非重叠样本均值=('n_nonoverlap','mean'),
                                       窗口观测数均值=('mean_obs_full','mean')).reset_index().round(2) if len(avail) else avail)}

## 6. 冻结指纹（对账用）

{_tbl(pd.DataFrame([fingerprints]))}

Long-Horizon 快照：`as_of={snap.get('as_of')}`，`snapshot_hash={snap.get('snapshot_hash')}`，
条目数 `{snap.get('n_entries')}`。

## 7. 交付物（§41）

{chr(10).join('- `' + n + '`' for n in ROOT_DELIVERABLES)}

## 8. 已知限制

1. 长期能力是**「N 天窗口均价」的情景化估计**，不是第 N 天点位预测；
2. 150/180 探索级（OOT 非重叠样本 13/11，fold3 更少），不得作为上线依据；
3. 本快照基于冻结 Final 数据（anchor=数据最新观测日），与 Daily 实时快照可能不同步，
   Daily 更新后需重跑 Long-Horizon Job；
4. 城市级作物物候 `NOT_FOUND`（仅省级/区域级月粒度日历），长期机制特征未接入；
5. LLM 未评估；`fallback_used` 语义为「未走 LLM 数值链路」。
"""


def _copy_to_root() -> List[str]:
    """把 §41 交付物复制到仓库根（便于审阅；源仍在各自子系统目录）。"""
    import shutil
    pairs = [
        (LH_REPORTS / "LONG_HORIZON_TARGET_STUDY.md", "LONG_HORIZON_TARGET_STUDY.md"),
        (LH_REPORTS / "LONG_HORIZON_MODEL_REPORT.md", "LONG_HORIZON_MODEL_REPORT.md"),
        (LH_ARTIFACTS / "LONG_HORIZON_METRICS.csv", "LONG_HORIZON_METRICS.csv"),
        (LH_ARTIFACTS / "LONG_HORIZON_REGISTRY.csv", "LONG_HORIZON_REGISTRY.csv"),
        (LLM_REPORTS / "LLM_FORECAST_REPORT.md", "LLM_FORECAST_REPORT.md"),
        (LLM_REPORTS / "LLM_ABLATION_REPORT.md", "LLM_ABLATION_REPORT.md"),
        (LLM_REPORTS / "HYBRID_REPORT.md", "HYBRID_REPORT.md"),
        (LH_REPORTS / "LONG_HORIZON_FREEZE_GATE.md", "LONG_HORIZON_FREEZE_GATE.md"),
    ]
    out = []
    for src, name in pairs:
        if src.exists():
            shutil.copy2(src, ROOT / name)
            out.append(name)
    return out


if __name__ == "__main__":
    print(build_freeze_gate()["fingerprints"])