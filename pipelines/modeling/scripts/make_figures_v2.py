# -*- coding: utf-8 -*-
"""Phase 11 / §62: v2 图表（9 类）。

  python3 decision_engine/scripts/make_figures_v2.py
输出：decision_engine/evaluation/figures/v2_*.png
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402

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
    print(f"[fig2] {path.name}")


def main():
    fig_dir = ensure_dir(de_path("evaluation", "figures"))
    opt = de_path("evaluation", "optimization")
    rec = de_path("evaluation", "recommendation")
    port = de_path("evaluation", "portfolio")

    # 1) Pareto 风险-收益前沿
    p = opt / "pareto_examples.csv"
    if p.exists():
        d = pd.read_csv(p)
        fig, ax = plt.subplots(figsize=(8, 5))
        risk = d["market_risk"]
        sc = ax.scatter(d["profit_pessimistic"] / 1e4, d["profit_baseline"] / 1e4,
                        c=risk, cmap="RdYlGn_r", s=45, edgecolor="k", linewidth=0.3)
        front = d.sort_values("profit_baseline", ascending=False)
        ax.plot(front["profit_pessimistic"] / 1e4, front["profit_baseline"] / 1e4,
                color="tab:blue", lw=1, alpha=0.6, label="Pareto 前沿（示意连线）")
        plt.colorbar(sc, label="市场风险（越低越好）")
        ax.set_xlabel("下行情景利润（万元）"); ax.set_ylabel("基准情景利润（万元）")
        ax.set_title("Pareto 风险-收益前沿（颜色=市场风险）")
        ax.legend()
        _save(fig, fig_dir / "v2_pareto_frontier.png")

    # 2) Top 方案对比
    rp = de_path("outputs", "v2_recommendation.json")
    top = None
    for cand in [rp, de_path("evaluation", "recommendation", "recommendation_cases.json")]:
        if cand.exists() and cand.name.startswith("v2"):
            top = json.loads(cand.read_text())
            break
    if top and top.get("top_plans"):
        t = pd.DataFrame(top["top_plans"]).head(5)
        fig, ax = plt.subplots(figsize=(9, 4))
        x = np.arange(len(t))
        ax.bar(x - 0.2, t["profit_baseline"] / 1e4, width=0.4, label="基准利润")
        ax.bar(x + 0.2, (t.get("profit_pessimistic", t["profit_baseline"]) / 1e4), width=0.4, label="下行利润")
        ax.set_xticks(x); ax.set_xticklabels([f"{c}\n{h}" for c, h in zip(t["crop"], t["harvest_date"])], fontsize=8)
        ax.set_ylabel("万元"); ax.set_title("Top 方案对比（基准 vs 下行）"); ax.legend()
        _save(fig, fig_dir / "v2_top_plan_comparison.png")
        # 3) Profit vs Risk
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.scatter(t["HRI"], t["profit_baseline"] / 1e4, s=60, label="Top5 方案")
        for _, r in t.iterrows():
            ax.annotate(str(r["crop"]), (r["HRI"], r["profit_baseline"] / 1e4), fontsize=8)
        ax.set_xlabel("HRI（跟风风险）"); ax.set_ylabel("基准利润（万元）")
        ax.set_title("利润 vs 跟风风险"); ax.legend()
        _save(fig, fig_dir / "v2_profit_vs_risk.png")

    # 4) HRI Exposure by Policy
    h = rec / "herding_suppression.csv"
    if h.exists():
        d = pd.read_csv(h)
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.bar(d["policy"], d["mean_HRI"], color=["#4f81bd" if "balanced" in p else "#c0504d" for p in d["policy"]])
        ax.set_ylabel("平均 HRI"); ax.set_title("各决策政策的 HRI 暴露（越低越不追高）")
        ax.tick_params(axis="x", rotation=15)
        _save(fig, fig_dir / "v2_hri_by_policy.png")

    # 5) 推荐历史表现
    bt = rec / "recommender_backtest.parquet"
    if bt.exists():
        d = pd.read_parquet(bt)
        d = d[d["rank"] == "top1"]
        fig, ax = plt.subplots(figsize=(9, 4))
        for pol, g in d.groupby("policy"):
            g = g.sort_values("cutoff")
            ax.plot(pd.to_datetime(g["cutoff"]), g["realized_profit_mean"] / 1e4, marker="o", ms=3, label=pol)
        ax.set_ylabel("实现利润（万元）"); ax.set_title("历史推荐表现（按政策，Top1）")
        ax.legend(fontsize=8); ax.tick_params(axis="x", rotation=30)
        _save(fig, fig_dir / "v2_recommendation_history.png")

    # 6) 压力测试热力图
    st = opt / "stress_test_results.csv"
    if st.exists():
        d = pd.read_csv(st)
        d = d[d["risk_preference"] == "balanced"]
        piv = d.pivot_table(index=["crop"], columns="shock", values="profit_delta_pct", aggfunc="mean")
        if len(piv):
            fig, ax = plt.subplots(figsize=(10, max(3, 0.6 * len(piv))))
            im = ax.imshow(piv.values, cmap="RdYlGn", aspect="auto", vmin=-30, vmax=30)
            ax.set_xticks(range(len(piv.columns))); ax.set_xticklabels(piv.columns, rotation=45, ha="right", fontsize=8)
            ax.set_yticks(range(len(piv.index))); ax.set_yticklabels(piv.index)
            for i in range(piv.shape[0]):
                for j in range(piv.shape[1]):
                    v = piv.values[i, j]
                    if np.isfinite(v):
                        ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7)
            plt.colorbar(im, label="利润变化 %")
            ax.set_title("压力测试热力图（利润变化 %，balanced）")
            _save(fig, fig_dir / "v2_stress_heatmap.png")

    # 7) 价格 × 亩产 利润矩阵
    v2 = de_path("outputs", "v2_recommendation.json")
    if v2.exists():
        d = json.loads(v2.read_text())
        m = (d.get("area_optimization") or {}).get("sensitivity_matrix")
        if m:
            fig, ax = plt.subplots(figsize=(7, 5))
            im = ax.imshow(np.array(m["profit_matrix"]) / 1e4, cmap="RdYlGn", aspect="auto")
            ax.set_xticks(range(len(m["price_axis"]))); ax.set_xticklabels([f"{v:.1f}" for v in m["price_axis"]], fontsize=7)
            ax.set_yticks(range(len(m["yield_axis"]))); ax.set_yticklabels([f"{v:.0f}" for v in m["yield_axis"]], fontsize=7)
            ax.set_xlabel("价格（元/kg）"); ax.set_ylabel("亩产（kg/亩）")
            ax.set_title(f"价格×亩产 利润矩阵（万元）；亏损区域占比={m['loss_region_ratio']:.1%}")
            plt.colorbar(im, label="利润（万元）")
            _save(fig, fig_dir / "v2_price_yield_matrix.png")

    # 8) 组合配置
    pb = port / "portfolio_backtest.csv"
    if pb.exists():
        d = pd.read_csv(pb)
        last = d.sort_values("cutoff").iloc[-1]
        alloc = [x.split(":") for x in str(last["allocation"]).split(";") if x]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar([a[0] for a in alloc], [float(a[1]) for a in alloc], color="#4f81bd")
        ax.set_ylabel("面积（亩）")
        ax.set_title(f"组合配置（{last['cutoff']}，HHI={last['hhi']:.2f}）")
        _save(fig, fig_dir / "v2_portfolio_allocation.png")

    # 9) 推荐稳定性
    rs = rec / "ranking_stability.csv"
    if rs.exists():
        d = pd.read_csv(rs)
        if len(d):
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.bar(d["policy"], d["crop_retention_rate"], color="#9bbb59")
            ax.set_ylabel("相邻 cutoff 推荐作物保持率")
            ax.set_title("推荐稳定性（Top1 作物保持率，越高越稳定）")
            ax.tick_params(axis="x", rotation=15)
            _save(fig, fig_dir / "v2_recommendation_stability.png")

    print("[fig2] done")


if __name__ == "__main__":
    main()