# -*- coding: utf-8 -*-
"""Phase 17：Long-Horizon Production Method Selection + Registry。

Gate（§8.1，逐 crop × horizon；阈值由 **development 段（fold1=2024）分布**推出，不手写常数）：
  1. 比 baseline 稳定增益：mean_WAPE < best baseline 的 mean_WAPE，且无折爆点；
  2. 无 bias 爆炸：|mean_bias| / price ≤ dev 段 p95 相对偏差；
  3. worst-case 可接受：最大折 WAPE ≤ dev 段 p95 折间比；
  4. 可复现：确定性方法（固定 seed，无 LLM）→ 是；LLM/Hybrid 未通过真实回测 → 否。

不满足 → `SCENARIO_ONLY`。150/180 一律 `EXPLORATORY_SCENARIO_ONLY`（样本不支持上线）。
range_type：只有区间覆盖落在名义带宽内才可称 `prediction_interval`，否则 `scenario_range`。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.models.backtest import FOLDS, fold_mask

from .common import (load_frozen_dataset, write_csv_artifact, write_report,
                     dataset_fingerprint, now_iso, LH_ARTIFACTS, LONG_HORIZONS)
from .targets import add_long_horizon_targets, target_availability
from .target_definition import primary_target_col
from .baselines import rowwise_baselines, ROWWISE_BASELINES, TRAINED_BASELINES
from .run_baselines import EXPLORATORY, NON_OVERLAP

COVERAGE_BAND = (0.70, 0.90)          # 名义 80% 区间可接受的实测覆盖带宽
LLM_METHODS_PREFIX = ("llm_", "hybrid_")

_RB_CACHE: Dict[int, pd.DataFrame] = {}          # horizon -> rowwise baseline 全表（复用）


def _load(name: str) -> pd.DataFrame:
    p = LH_ARTIFACTS / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def dev_thresholds(mets: pd.DataFrame, preds: pd.DataFrame) -> Dict[str, float]:
    """由 fold1（development 段）推出的 bias 与 worst-case 阈值。"""
    dev = preds[preds["fold"] == FOLDS[0]["name"]]
    if not len(dev):
        return {"bias_frac_p95": 0.05, "worst_ratio_p95": 3.0, "n_dev": 0}
    # 相对偏差：|mean(pred - actual)| / mean(actual)（逐 crop×horizon×method）
    g = dev.groupby(["crop", "horizon", "method"])
    act = g["actual"].mean().rename("act")
    err = g.apply(lambda d: float((d["prediction"] - d["actual"]).mean())).rename("err")
    j = pd.concat([act, err], axis=1).dropna()
    frac = (j["err"].abs() / j["act"].abs()).replace([np.inf, -np.inf], np.nan).dropna()
    # 折间比：worst_WAPE / mean_WAPE（按 method×crop×horizon）
    g = mets.groupby(["method", "crop", "horizon"])["WAPE"]
    ratio = (g.max() / g.mean()).replace([np.inf, -np.inf], np.nan).dropna()
    return {"bias_frac_p95": float(np.percentile(frac, 95)) if len(frac) else 0.05,
            "worst_ratio_p95": float(np.percentile(ratio, 95)) if len(ratio) else 3.0,
            "n_dev": int(len(dev))}


def _method_preds(preds: pd.DataFrame, method: str, crop: str, horizon: int) -> pd.DataFrame:
    sub = preds[(preds["method"] == method) & (preds["crop"] == crop)
                & (preds["horizon"] == horizon)]
    return sub[["date", "fold", "actual", "prediction"]].copy()


def _scenario_range(p: pd.DataFrame) -> Dict[str, float]:
    """由 **development 折（fold1=2024）** 该方法自身的残差比分布推出场景区间 [q10, q90]。

    注：本工程的 OOT 只对测试窗产出预测，因此 development 段取 fold1 的测试窗（2024），
    OOT 段取 fold2(2025)+fold3(2026) —— 时间上严格在后，无泄漏。
    """
    dev = p[p["fold"] == FOLDS[0]["name"]]
    dev = dev[dev["prediction"].notna() & (dev["prediction"] > 0)]
    if len(dev) < 30:
        return {}
    ratio = (dev["actual"].values / dev["prediction"].values)
    # 区间必须包含点值（比值带跨过 1.0），与 Long-Horizon Job 同一口径
    return {"q10": float(min(np.percentile(ratio, 10), 1.0)),
            "q90": float(max(np.percentile(ratio, 90), 1.0)),
            "n_dev": int(len(dev))}


def build_registry(dataset: pd.DataFrame | None = None) -> Dict[str, object]:
    ds = dataset if dataset is not None else load_frozen_dataset()
    summ = _load("long_horizon_summary.csv")
    # 只登记 Long-Horizon 口径（30–180）；7/14 由既有的 Final Model Registry 负责
    summ = summ[summ["horizon"].isin(LONG_HORIZONS)]
    mets = _load("LONG_HORIZON_METRICS.csv")
    preds = (pd.read_parquet(LH_ARTIFACTS / "long_horizon_predictions.parquet")
             if (LH_ARTIFACTS / "long_horizon_predictions.parquet").exists() else pd.DataFrame())
    if not len(summ) or not len(mets) or not len(preds):
        raise RuntimeError("缺少 long_horizon_summary / LONG_HORIZON_METRICS / predictions.parquet")
    thr = dev_thresholds(mets, preds)
    ds_t = add_long_horizon_targets(ds, horizons=sorted(summ["horizon"].unique().tolist()))
    av = target_availability(ds_t)
    act_mean = preds.groupby(["method", "crop", "horizon"])["actual"].mean()

    rows: List[Dict] = []
    for (crop, h), sub in summ.groupby(["crop", "horizon"]):
        h = int(h)
        base = sub[sub["method"] == "b_last_value"]
        base_wape = float(base.iloc[0]["mean_WAPE"]) if len(base) else np.nan
        cand = sub[~sub["method"].str.startswith("b_drift")].sort_values("score")
        best = cand.iloc[0]
        method = str(best["method"])

        # 稳定性 / bias / worst-case
        fold_max = float(best["worst_WAPE"]); fold_mean = float(best["mean_WAPE"])
        worst_ratio = fold_max / fold_mean if fold_mean > 0 else np.inf
        am = act_mean.get((method, crop, h), np.nan)
        bias_frac = (abs(float(best["mean_bias"])) / abs(float(am))
                     if np.isfinite(am) and am else 1.0)
        n_nonoverlap = NON_OVERLAP.get(h, 0)

        # 区间（场景区间，dev 学得） + OOT 覆盖 —— 与方法一致
        mp = _method_preds(preds, method, crop, h)
        rng = _scenario_range(mp)
        coverage = _range_coverage(mp, rng) if rng else None
        range_type = ("prediction_interval"
                      if coverage is not None and COVERAGE_BAND[0] <= coverage <= COVERAGE_BAND[1]
                      else "scenario_range")

        is_llm = method.startswith(LLM_METHODS_PREFIX)
        exploratory = h in EXPLORATORY
        gains = bool(np.isfinite(base_wape) and fold_mean < base_wape)
        stable = bool(np.isfinite(worst_ratio) and worst_ratio <= thr["worst_ratio_p95"])
        bias_ok = bool(bias_frac <= thr["bias_frac_p95"])
        reproducible = not is_llm

        if exploratory:
            status, reason = "EXPLORATORY_SCENARIO_ONLY", f"OOT 非重叠样本仅 {n_nonoverlap}（探索级）"
        elif is_llm:
            status, reason = "SCENARIO_ONLY", "LLM/Hybrid 未通过真实 OOT 回测（本轮无真实 LLM 结果）"
        elif gains and stable and bias_ok and reproducible:
            status, reason = "PRODUCTION_POINT", f"超越 last_value({base_wape:.1f}%→{fold_mean:.1f}%) 且稳定"
        else:
            fails = []
            if not gains:
                fails.append("未超越 baseline")
            if not stable:
                fails.append(f"折间不稳({worst_ratio:.2f}>{thr['worst_ratio_p95']:.2f})")
            if not bias_ok:
                fails.append(f"bias偏大({bias_frac:.3f}>{thr['bias_frac_p95']:.3f})")
            status, reason = "SCENARIO_ONLY", "；".join(fails) or "未达 Gate"

        conf = ("high" if (stable and n_nonoverlap >= 20 and h <= 90)
                else "medium" if n_nonoverlap >= 13 else "low")

        rows.append({
            "crop": crop, "horizon": h, "method": method,
            "metric": f"mean_WAPE={fold_mean:.3f};std={float(best['std_WAPE']):.3f};worst={fold_max:.3f}",
            "confidence": conf, "range_type": range_type,
            "production_status": status, "reason": reason,
            "baseline_last_value_WAPE": round(float(base_wape), 3) if np.isfinite(base_wape) else None,
            "range_coverage_oot": round(float(coverage), 3) if coverage is not None else None,
            "n_nonoverlap": n_nonoverlap,
        })

    reg = pd.DataFrame(rows).sort_values(["horizon", "crop"])
    write_csv_artifact(reg, "LONG_HORIZON_REGISTRY.csv")
    _write_method_map(reg, thr, av)
    return {"rows": len(reg), "registry": reg, "thresholds": thr}


def _range_coverage(p: pd.DataFrame, rng: Dict[str, float]) -> float | None:
    """OOT 覆盖：用 dev 学得的 [q10,q90] 乘该方法 OOT 预测构造区间，测实测覆盖率。"""
    if not rng:
        return None
    oot = p[p["fold"].isin({f["name"] for f in FOLDS[1:]})]
    oot = oot[oot["prediction"].notna() & (oot["prediction"] > 0)]
    if not len(oot):
        return None
    lo = oot["prediction"] * rng["q10"]
    hi = oot["prediction"] * rng["q90"]
    return float(((oot["actual"] >= lo) & (oot["actual"] <= hi)).mean())


def _write_method_map(reg: pd.DataFrame, thr: Dict[str, float], av: pd.DataFrame) -> None:
    def tbl(d: pd.DataFrame) -> str:
        cols = list(d.columns)
        head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
        body = ""
        for _, r in d.iterrows():
            body += "| " + " | ".join(
                (f"{v:.3f}" if isinstance(v, float) else str(v)) for v in r[cols]) + " |\n"
        return head + body

    counts = reg.groupby("production_status").size().reset_index(name="n")
    md = f"""# Long-Horizon Registry / Method Map（Phase 17）

> 数据指纹 `{dataset_fingerprint()}`；生成时间 `{now_iso()}`。
> Gate 阈值由 **development 段（fold1=2024）** 推出：bias_frac_p95={thr['bias_frac_p95']:.4f}，
> worst_ratio_p95={thr['worst_ratio_p95']:.3f}（n_dev={thr['n_dev']}）。

## 1. 状态分布

{tbl(counts)}

## 2. 完整 Registry（{len(reg)} 行 → `artifacts/LONG_HORIZON_REGISTRY.csv`）

{tbl(reg[["crop", "horizon", "method", "confidence", "range_type",
              "production_status", "baseline_last_value_WAPE", "range_coverage_oot"]])}

## 3. 口径声明

- **正式长期 target** = `full`（N 天窗口均价）。
- 长期能力一律表述为「情景化估计」；`range_type=scenario_range` 表示**未经校准**，
  **不得**称 prediction interval。
- 150/180 为探索级（`EXPLORATORY_SCENARIO_ONLY`），不得作为上线依据。
- LLM/Hybrid 未被赋「天然预测权」：本轮无真实 LLM 数值结果 → 一律 `SCENARIO_ONLY`。
"""
    write_report(md, "LONG_HORIZON_METHOD_MAP.md")


if __name__ == "__main__":
    out = build_registry()
    print("registry rows:", out["rows"])
    print(out["registry"]["production_status"].value_counts().to_string())