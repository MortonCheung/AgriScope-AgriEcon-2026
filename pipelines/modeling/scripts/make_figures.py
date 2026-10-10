# -*- coding: utf-8 -*-
"""Phase: 自动图表（比赛中直接可用）。

  python3 decision_engine/scripts/make_figures.py

输出：decision_engine/evaluation/figures/*.png
"""
from __future__ import annotations
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402

# 中文字体
for f in ["PingFang SC", "Heiti TC", "Arial Unicode MS", "Songti SC", "STHeiti"]:
    try:
        matplotlib.font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [f]
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 130


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"[fig] {path.name}")


def main():
    fig_dir = ensure_dir(de_path("evaluation", "figures"))
    preds = pd.read_parquet(de_path("evaluation", "backtests", "predictions.parquet"))
    preds["date"] = pd.to_datetime(preds["date"])
    sel = pd.read_csv(de_path("evaluation", "metrics", "model_selection.csv"))
    tgt = "target_mean_price_next_30d"
    prim = preds[preds["target"] == tgt].copy()

    # 1) Actual vs Prediction（最终模型，土豆为例）
    chosen = sel[sel["crop"] == "土豆"].iloc[0]
    sub = prim[(prim["crop"] == "土豆") & (prim["model"] == chosen["model"]) &
               (prim["route"] == chosen["route"])].sort_values("date")
    if len(sub):
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(sub["date"], sub["actual"], label="实际（未来30天均价）", lw=1.6)
        ax.plot(sub["date"], sub["prediction"], label=f"预测（{chosen['model']}）", lw=1.2, alpha=0.85)
        ax.set_title(f"土豆：未来30天均价 实际 vs 预测（回测期）")
        ax.set_ylabel("元/kg"); ax.legend()
        _save(fig, fig_dir / "price_actual_vs_prediction_tudou.png")

    # 2) Baseline vs Final Model（逐作物 WAPE）
    piv = prim[prim["route"].isin(["baseline"]) | (prim["model"] == chosen["model"])]
    comp = (prim.groupby(["crop", "model", "route"]).apply(
        lambda g: np.abs(g["actual"] - g["prediction"]).sum() / np.abs(g["actual"]).sum() * 100)
        .rename("WAPE").reset_index())
    best = sel.set_index("crop")["model"].to_dict()
    base_best = (comp[comp["route"] == "baseline"].sort_values("WAPE")
                 .groupby("crop").first()["WAPE"].to_dict())
    final_map = {}
    for crop, m in best.items():
        row = comp[(comp["crop"] == crop) & (comp["model"] == m)]
        if len(row):
            final_map[crop] = row["WAPE"].min()
    crops = sorted(set(base_best) & set(final_map))
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(len(crops))
    ax.bar(x - 0.2, [base_best[c] for c in crops], width=0.4, label="最佳基线")
    ax.bar(x + 0.2, [final_map[c] for c in crops], width=0.4, label="最终模型")
    ax.set_xticks(x); ax.set_xticklabels(crops)
    ax.set_ylabel("WAPE %"); ax.set_title("逐作物：最佳基线 vs 最终模型（跨 fold 汇总）")
    ax.legend()
    _save(fig, fig_dir / "baseline_vs_final_by_crop.png")

    # 3) Error by fold
    fig, ax = plt.subplots(figsize=(9, 4))
    for crop in ["土豆", "西红柿", "黄瓜"]:
        m = sel[sel["crop"] == crop].iloc[0]
        s = prim[(prim["crop"] == crop) & (prim["model"] == m["model"])]
        g = s.groupby("fold").apply(lambda x: np.abs(x["actual"] - x["prediction"]).mean())
        ax.plot(g.index, g.values, marker="o", label=crop)
    ax.set_ylabel("MAE (元/kg)"); ax.set_title("逐 fold 误差（代表作物）")
    ax.legend()
    _save(fig, fig_dir / "error_by_fold.png")

    # 4) Interval coverage
    ivp = de_path("evaluation", "backtests", "interval_predictions.parquet")
    if ivp.exists():
        iv = pd.read_parquet(ivp)
        fig, ax = plt.subplots(figsize=(9, 4))
        cov = iv.groupby("method").apply(
            lambda g: ((g["actual"] >= g["lo"]) & (g["actual"] <= g["hi"])).mean())
        ax.barh(cov.index, cov.values * 100)
        ax.axvline(80, color="red", ls="--", label="nominal 80%")
        ax.set_xlabel("empirical coverage %"); ax.set_title("区间方法：经验覆盖率（P10-P90）")
        ax.legend()
        _save(fig, fig_dir / "interval_coverage.png")

        # 5) 区间示例（土豆示例方法）
        m0 = iv["method"].iloc[0]
        sample = iv[(iv["method"] == cov.idxmax()) & (iv["crop"] == "土豆")].sort_values("date")
        if len(sample):
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.fill_between(sample["date"], sample["lo"], sample["hi"], alpha=0.25, label="P10-P90")
            ax.plot(sample["date"], sample["actual"], color="black", lw=1.3, label="实际")
            ax.plot(sample["date"], sample["mid"], color="tab:red", lw=1, label="P50")
            ax.set_title(f"土豆：{cov.idxmax()} 区间与实际（回测）")
            ax.set_ylabel("元/kg"); ax.legend()
            _save(fig, fig_dir / "interval_example_tudou.png")

    # 6) HRI timeline
    hri = pd.read_parquet(de_path("data", "features", "hri_v1.parquet"))
    hri["date"] = pd.to_datetime(hri["date"])
    fig, ax = plt.subplots(figsize=(9, 4))
    for crop in ["土豆", "西红柿", "黄瓜"]:
        s = hri[hri["crop"] == crop]
        ax.plot(s["date"], s["hri_conceptual"], lw=1, label=crop, alpha=0.85)
    ax.set_title("HRI（conceptual 权重）时间线"); ax.set_ylabel("0-100"); ax.legend()
    _save(fig, fig_dir / "hri_timeline.png")

    # 7) 高/低 HRI 之后收益
    val = pd.read_csv(de_path("evaluation", "metrics", "hri_validation.csv"))
    v = val[val["window_days"].notna() & val["high_mean_fwd_return"].notna()]
    if len(v):
        fig, ax = plt.subplots(figsize=(8, 4))
        x = np.arange(len(v))
        ax.bar(x - 0.2, v["high_mean_fwd_return"] * 100, width=0.4, label="HRI Top5%")
        ax.bar(x + 0.2, v["low_mean_fwd_return"] * 100, width=0.4, label="HRI Bottom50%")
        ax.set_xticks(x); ax.set_xticklabels([f"{int(w)}d" for w in v["window_days"]])
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_ylabel("未来收益 %"); ax.set_title("高 vs 低 HRI 之后的实际价格变化")
        ax.legend()
        _save(fig, fig_dir / "hri_forward_returns.png")

    # 8) Climate exposure 分布 + 季节
    ce = pd.read_parquet(de_path("data", "features", "climate_daily_shenyang.parquet"))
    ce["date"] = pd.to_datetime(ce["date"])
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(ce["climate_exposure"].dropna(), bins=40)
    ax.set_title("沈阳：气候暴露指数分布（日频）"); ax.set_xlabel("0-100")
    _save(fig, fig_dir / "climate_exposure_distribution.png")

    fig, ax = plt.subplots(figsize=(9, 4))
    m = ce.groupby(ce["date"].dt.month)["climate_exposure"].mean()
    ax.plot(m.index, m.values, marker="o")
    ax.set_xticks(range(1, 13))
    ax.set_title("沈阳：气候暴露的季节性（月均）"); ax.set_ylabel("暴露指数")
    _save(fig, fig_dir / "climate_seasonal.png")

    # 9) Replay：预测 vs 实际
    rp = de_path("evaluation", "backtests", "replay_results.csv")
    if rp.exists():
        r = pd.read_csv(rp)
        r["replay_date"] = pd.to_datetime(r["replay_date"])
        r = r[r["realized_price"].notna()]
        fig, ax = plt.subplots(figsize=(9, 4))
        for crop in ["土豆", "西红柿"]:
            s = r[r["crop"] == crop].sort_values("replay_date")
            ax.plot(s["replay_date"], s["p50"], label=f"{crop} P50", lw=1.2)
            ax.plot(s["replay_date"], s["realized_price"], label=f"{crop} 实际", lw=1, ls="--")
        ax.set_title("历史回放：P50 预测 vs 实际 90 天窗口均价")
        ax.set_ylabel("元/kg"); ax.legend()
        _save(fig, fig_dir / "replay_p50_vs_realized.png")

        fig, ax = plt.subplots(figsize=(9, 4))
        cov = r.groupby(r["replay_date"].dt.year)["interval_hit"].mean() * 100
        ax.bar(cov.index.astype(str), cov.values)
        ax.axhline(80, color="red", ls="--")
        ax.set_ylabel("区间命中率 %"); ax.set_title("历史回放：P10-P90 命中率（按年）")
        _save(fig, fig_dir / "replay_coverage_by_year.png")

    # 10) 收益情景（示例 plan）
    try:
        from decision_engine.engine.engine import DecisionEngine
        eng = DecisionEngine()
        plan = {"city": "沈阳", "crop": "西红柿", "plant_date": "2026-04-10",
                "harvest_date": "2026-07-10", "area_mu": 80, "cost_per_mu": 5200,
                "expected_yield_per_mu": 4500, "risk_preference": "balanced"}
        r = eng.evaluate_plan(plan)
        if r.get("status") == "ok":
            p = r["profit"]
            fig, ax = plt.subplots(figsize=(6, 4))
            vals = [p["pessimistic"]["profit"], p["baseline"]["profit"], p["optimistic"]["profit"]]
            ax.bar(["悲观(P10)", "基准(P50)", "乐观(P90)"], vals,
                   color=["#c0504d", "#4f81bd", "#9bbb59"])
            ax.axhline(0, color="gray", lw=0.8)
            ax.set_title(f"收益情景（{plan['crop']} {plan['harvest_date']} 上市）")
            ax.set_ylabel("净收益（元）")
            _save(fig, fig_dir / "profit_scenarios_example.png")
    except Exception as e:
        print("[fig] profit example skipped:", e)

    print("[fig] all done")


if __name__ == "__main__":
    main()