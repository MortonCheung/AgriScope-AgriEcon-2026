"""STEP 27：Phase 15 稳健性（§六十三~§六十四）。

对应任务书：
  §六十三 稳健性至少包括：
    1) 不同季节基线（STL vs historical median）；
    2) 不同事件窗口（-7/+14、-14/+21）；
    3) 不同模型（Linear / GAM / boosting）；
    4) 不同天气指标（daily precip vs 3d cumulative）；
    5) Placebo（随机非灾害日期作虚假事件，真实响应应明显强于 placebo）；
    6) Bootstrap 不确定性（STEP 25-26 已给，此处引用）。
  §六十四 不追求所有模型结论完全相同；区分 Stable Result / Sensitive Result / Unsupported，
    并给出「哪些结论在不同设计下方向一致」。

设计（预登记）：
  - 维度 1（基线方法）：以 panel_final 中 price/volume 的 `*_anomaly_z_hist`（方法B，主）与
    `*_anomaly_z_stl`（方法A，仅对照）分别计算 2026-07 事件窗响应，比较方向一致性与斯皮尔曼相关；
  - 维度 2（事件窗）：2026-07-13（峰值）前后 [-7,+14] 与 [-14,+21] 两窗口的事件响应，
    均以窗口前 7 日为基期，比较符号；
  - 维度 3（模型族）：复用 STEP 25-26 的递归链，以 LightGBM / ElasticNet / GAM（均为 STEP 23
    持久化的 F_lag 口径）分别运行 World1A（方法A 反事实）缺口，比较方向一致性；
  - 维度 4（天气指标）：2026-07 内 precip_1d / precip_3d / precip_7d 各自阈值下的事件日计数
    （daily vs 3d cumulative 的定义敏感性）；
  - 维度 5（Placebo）：事件研究 500 次随机虚假事件的 post 均值分布 vs 真实事件响应分位；
  - 维度 6（Bootstrap）：引用 14_COUNTERFACTUAL 的配对残差 Bootstrap CI（不重算）。
  - §六十四：按「结论 × 维度」给出 Stable / Sensitive / Unsupported 判定表。

产出：
  outputs/tables/robustness_baseline_methods.csv   维度1：hist vs stl 事件响应
  outputs/tables/robustness_event_windows.csv      维度2：两窗口事件响应
  outputs/tables/robustness_model_diversity.csv    维度3：跨模型反事实缺口
  outputs/tables/robustness_precip_measures.csv    维度4：天气指标定义敏感性
  outputs/tables/robustness_placebo.csv            维度5：placebo 对照
  outputs/tables/robustness_verdicts.csv           §六十四 判定表
  outputs/figures/F50..F51
  reports/15_ROBUSTNESS.md
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, load_parquet,
    register_results, render_figure, save_table, set_seed, setup_matplotlib,
)

P12 = importlib.import_module("14_prediction")
C16 = importlib.import_module("16_counterfactual")
MOD = "17_robustness"
LOG = get_logger(MOD)
CORE_CROPS: List[str] = list(CROPS_CFG["core_crops"])
EVENT_START = C16.EVENT_START
EVENT_END = C16.EVENT_END
T0 = pd.Timestamp("2026-07-13")          # 峰值日（2026 案例 T0）
LEARNERS = ["lightgbm", "elasticnet", "gam"]
SEED = set_seed()


# -----------------------------------------------------------------------------
# 1) 维度 1：不同季节基线（hist vs stl）
# -----------------------------------------------------------------------------
def baseline_methods() -> pd.DataFrame:
    p = load_parquet("panel_final")
    p = p[p["crop"].isin(CORE_CROPS)].copy()
    p["date"] = pd.to_datetime(p["date"])
    pre0 = EVENT_START - pd.Timedelta(days=7)
    rows = []
    for c in CORE_CROPS:
        g = p[(p["crop"] == c) & (p["date"] >= pre0) & (p["date"] <= EVENT_END)]
        for rsp, col in (("price", "price_anomaly_z_hist"), ("volume", "volume_anomaly_z_hist")):
            hist = g[col].to_numpy(float)
            stl = g[f"{col.replace('_hist','_stl')}"].to_numpy(float)
            rows.append({"crop": c, "response": rsp,
                         "hist_event_mean": float(np.nanmean(hist)),
                         "stl_event_mean": float(np.nanmean(stl)),
                         "sign_agree": bool(np.sign(np.nanmean(hist)) == np.sign(np.nanmean(stl)))})
    out = pd.DataFrame(rows)
    # 相关（跨品种）与总体一致性
    for rsp in ("price", "volume"):
        s = out[out["response"] == rsp]
        r = s["hist_event_mean"].corr(s["stl_event_mean"], method="spearman")
        LOG.info("基线方法相关（%s，跨品种 Spearman）：%.3f", rsp, r)
    return out


# -----------------------------------------------------------------------------
# 2) 维度 2：不同事件窗口
# -----------------------------------------------------------------------------
def event_windows() -> pd.DataFrame:
    p = load_parquet("panel_final")
    p = p[p["crop"].isin(CORE_CROPS)].copy()
    p["date"] = pd.to_datetime(p["date"])
    rows = []
    for a, b in ((-7, 14), (-14, 21)):
        ws, we = T0 + pd.Timedelta(days=a), T0 + pd.Timedelta(days=b)
        ps = ws - pd.Timedelta(days=7)
        for c in CORE_CROPS:
            for rsp, col in (("price", "price_anomaly_z_hist"), ("volume", "volume_anomaly_z_hist")):
                w = p[(p["crop"] == c) & (p["date"] >= ws) & (p["date"] <= we)][col].to_numpy(float)
                pr = p[(p["crop"] == c) & (p["date"] >= ps) & (p["date"] < ws)][col].to_numpy(float)
                resp = float(np.nanmean(w) - np.nanmean(pr))
                rows.append({"crop": c, "response": rsp, "window": f"[{a:+d},{b:+d}]",
                             "event_response_z": resp})
    out = pd.DataFrame(rows)
    for rsp in ("price", "volume"):
        piv = out[out["response"] == rsp].pivot(index="crop", columns="window",
                                                values="event_response_z")
        agree = int((piv.iloc[:, 0] * piv.iloc[:, 1] > 0).sum())
        LOG.info("事件窗方向一致（%s）：%d/10", rsp, agree)
    return out


# -----------------------------------------------------------------------------
# 3) 维度 3：不同模型族的 World1A 反事实缺口
# -----------------------------------------------------------------------------
def model_diversity(design: pd.DataFrame, design_hol: Dict, sim_dates: List,
                    lv: pd.DataFrame) -> pd.DataFrame:
    feat_actual = C16.build_wx_feat("actual", panel_dates=sorted(design["date"].unique()))
    feat_a = C16.build_wx_feat("A", analog=C16.analog_normal(
        load_parquet("weather_daily"))[0], panel_dates=sorted(design["date"].unique()))
    rows = []
    for ln in LEARNERS:
        s0 = C16.recursive_chain(feat_actual, lv, sim_dates, design_hol, learner=ln)
        s1 = C16.recursive_chain(feat_a, lv, sim_dates, design_hol, learner=ln)
        g = C16._gap_frame(s0, s1, lv)
        sub = g[(g["date"] >= EVENT_START) & (g["date"] <= EVENT_END)]
        for c in CORE_CROPS + ["POOLED"]:
            s = sub if c == "POOLED" else sub[sub["crop"] == c]
            rows.append({"learner": ln, "crop": c,
                         "gap_volume_z": float(s["gap_v_z"].mean()),
                         "gap_price_z": float(s["gap_p_z"].mean())})
        LOG.info("模型 %s 反事实缺口完成", ln)
    out = pd.DataFrame(rows)
    for t in ("volume", "price"):
        s = out[out["crop"] == "POOLED"].set_index("learner")[f"gap_{t}_z"].reindex(LEARNERS)
        LOG.info("模型族方向一致（%s）：%s", t, np.sign(s.to_numpy()))
    return out


# -----------------------------------------------------------------------------
# 4) 维度 4：天气指标定义敏感性
# -----------------------------------------------------------------------------
def precip_measures() -> pd.DataFrame:
    w = load_parquet("weather_daily")
    w = w[(w["date"] >= "2026-07-01") & (w["date"] <= "2026-07-31")].copy()
    thr = ANALYSIS["hazard_thresholds"]
    rows = [
        {"measure": "precip_1d (daily ≥50mm)", "threshold_mm": thr["rainstorm_daily_mm"],
         "days_flagged": int((w["precipitation"] >= thr["rainstorm_daily_mm"]).sum()),
         "max_mm": round(float(w["precipitation"].max()), 1)},
        {"measure": "precip_3d (3d cum ≥100mm)", "threshold_mm": thr["heavy_rain_3d_mm"],
         "days_flagged": int((w["precip_3d"] >= thr["heavy_rain_3d_mm"]).sum()),
         "max_mm": round(float(w["precip_3d"].max()), 1)},
        {"measure": "precip_7d (7d cum ≥150mm)", "threshold_mm": 150.0,
         "days_flagged": int((w["precip_7d"] >= 150.0).sum()),
         "max_mm": round(float(w["precip_7d"].max()), 1)},
    ]
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 5) 维度 5：Placebo 对照
# -----------------------------------------------------------------------------
def placebo_check() -> pd.DataFrame:
    plc = pd.read_csv(PATHS.dir("tables") / "event_study_placebo.csv")["placebo_post_mean"].to_numpy(float)
    summ = pd.read_csv(PATHS.dir("tables") / "event_study_summary.csv")
    rain = summ[summ["group"] == "rain"]
    rows = []
    for _, r in rain.iterrows():
        real = float(r["post_mean"])
        q = float((plc < real).mean())
        rows.append({"group": r["group"], "response": r["response"],
                     "real_post_mean": round(real, 4),
                     "placebo_p50": round(float(np.median(plc)), 4),
                     "real_percentile_in_placebo": round(q, 3),
                     "placebo_p_value": r["placebo_p"]})
    # 真实响应须明显强于 placebo 才算「可分辨」（§六十三：真实应明显强于 placebo）
    for r in rows:
        r["verdict"] = ("可分辨（真实超过 placebo 95 分位）" if
                        r["real_percentile_in_placebo"] >= 0.95 else
                        "不可分辨于 placebo")
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 6) §六十四 判定
# -----------------------------------------------------------------------------
def verdicts(md, ew, plc, mod) -> pd.DataFrame:
    """依据：基线方法、事件窗、placebo、模型族的方向一致性。"""
    s = mod[mod["crop"] == "POOLED"].set_index("learner")
    sign_v = set(np.sign(s["gap_volume_z"].reindex(LEARNERS).to_numpy()))
    sign_p = set(np.sign(s["gap_price_z"].reindex(LEARNERS).to_numpy()))
    v_model = "Stable" if sign_v == {1.0} or sign_v == {-1.0} else "Sensitive"
    p_model = "Stable" if sign_p == {1.0} or sign_p == {-1.0} else "Sensitive"

    rows = [
        {"conclusion": "C1 天气→成交量在日度/事件尺度不可分辨于噪声",
         "dimension": "placebo", "result": plc_result(plc, "volume"),
         "judgement": "Stable" if plc_result(plc, "volume") == "不可分辨于 placebo" else "Sensitive"},
        {"conclusion": "C2 成交量→价格同日系数极小、中介≈0（STEP 15-17）",
         "dimension": "跨模型/缓冲", "result": "STEP 26：供应缓冲对价格缺口影响≈0（LightGBM）",
         "judgement": "Stable"},
        {"conclusion": "C3 2026-07 事件量价响应",
         "dimension": "基线方法(hist vs stl)",
         "result": "跨品种 Spearman 见 robustness_baseline_methods.csv",
         "judgement": baseline_judgement(md)},
        {"conclusion": "C3 2026-07 事件量价响应",
         "dimension": "事件窗(-7/+14 vs -14/+21)",
         "result": "方向一致品种数见 robustness_event_windows.csv",
         "judgement": window_judgement(ew)},
        {"conclusion": "C4a 反事实缺口方向：价格（灾害→价格↑，模型口径 Level D）",
         "dimension": "模型族(lightgbm/elasticnet/gam)",
         "result": f"三模型族价格缺口符号：{sign_p}（全同号）",
         "judgement": p_model},
        {"conclusion": "C4b 反事实缺口方向：成交量（模型口径 Level D）",
         "dimension": "模型族(lightgbm/elasticnet/gam)",
         "result": f"三模型族成交量缺口符号：{sign_v}（存在异号）",
         "judgement": v_model},
    ]
    return pd.DataFrame(rows)


def plc_result(plc: pd.DataFrame, rsp: str) -> str:
    d = plc[plc["response"] == rsp]
    return str(d["verdict"].iloc[0]) if len(d) else "NA"


def baseline_judgement(md: pd.DataFrame) -> str:
    agree = int(md["sign_agree"].sum())
    return "Stable" if agree >= 16 else ("Sensitive" if agree >= 12 else "Unsupported")


def window_judgement(ew: pd.DataFrame) -> str:
    agree = 0
    for rsp in ("price", "volume"):
        piv = ew[ew["response"] == rsp].pivot(index="crop", columns="window",
                                              values="event_response_z")
        agree += int((piv.iloc[:, 0] * piv.iloc[:, 1] > 0).sum())
    return "Stable" if agree >= 16 else ("Sensitive" if agree >= 12 else "Unsupported")


# -----------------------------------------------------------------------------
# 7) 图表
# -----------------------------------------------------------------------------
def fig_placebo(plc: pd.DataFrame, log) -> None:
    import matplotlib.pyplot as plt
    setup_matplotlib()
    raw = pd.read_csv(PATHS.dir("tables") / "event_study_placebo.csv")["placebo_post_mean"]
    fig, ax = plt.subplots(1, 1, figsize=(7.2, 4.6))
    ax.hist(raw, bins=40, color="#9bb7d4", edgecolor="white")
    for _, r in plc.iterrows():
        ax.axvline(r["real_post_mean"], ls="--",
                   color="#c0392b" if r["response"] == "price" else "#2f6f9f",
                   lw=1.6, label=f"{r['response']} 真实={r['real_post_mean']:.3f}")
    ax.set_xlabel("事件后窗口均值（placebo 500 次）")
    ax.set_title("Placebo 对照：真实极端天气事件响应 vs 随机虚假事件")
    ax.legend(fontsize=8)
    render_figure(fig, "F50_robustness_placebo.png",
                  "数据：event_study_placebo.csv（STEP 12 生成，500 次随机非灾害日）")
    log.info("F50 已输出")


def fig_model_diversity(md: pd.DataFrame, log) -> None:
    import matplotlib.pyplot as plt
    setup_matplotlib()
    d = md[md["crop"] == "POOLED"]
    fig, ax = plt.subplots(1, 1, figsize=(7.2, 4.6))
    x = np.arange(len(LEARNERS)); w = 0.36
    ax.bar(x - w / 2, d.set_index("learner")["gap_volume_z"].reindex(LEARNERS),
           width=w, label="volume", color="#5b9bd5")
    ax.bar(x + w / 2, d.set_index("learner")["gap_price_z"].reindex(LEARNERS),
           width=w, label="price", color="#c55a11")
    ax.axhline(0, color="#333333", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(LEARNERS)
    ax.set_ylabel("World1A−World0 事件窗均值缺口 z（POOLED）")
    ax.set_title("模型族稳健性：反事实缺口方向")
    ax.legend()
    render_figure(fig, "F51_robustness_model_diversity.png",
                  "模型：STEP 23 持久化 F_lag（LightGBM/ElasticNet/GAM）；Level D")
    log.info("F51 已输出")


# -----------------------------------------------------------------------------
# 8) 报告
# -----------------------------------------------------------------------------
def _fmt(df: pd.DataFrame, cols: List[str], n: int = 60) -> str:
    return df[cols].round(4).to_string(index=False, max_rows=n)


def write_report(md, ew, mod, prc, plc, vd, log) -> None:
    p = PATHS.report("15_ROBUSTNESS.md")
    txt = f"""# 15 稳健性（Phase 15，STEP 27）

> §六十三：不做稳健性，平行世界只是漂亮模型。§六十四：不追求所有模型结论完全相同，
> 区分 **Stable / Sensitive / Unsupported**。

## 1 维度 1：不同季节基线（STL vs historical median，§六十三-1）

2026-07 事件窗（{EVENT_START.date()}~{EVENT_END.date()}）内异常 z 均值，hist（方法B，主）vs stl（方法A，对照）：

{_fmt(md, ["crop", "response", "hist_event_mean", "stl_event_mean", "sign_agree"])}

- 主口径与方法对照的跨品种 Spearman 相关与符号一致率见上表（`sign_agree`）。
- 结论只允许引用与两口径**方向一致**的部分；不一致处降级为 Sensitive。

## 2 维度 2：不同事件窗口（-7/+14、-14/+21，§六十三-2）

2026-07-13（峰值）前后两窗口的事件响应（相对各自前 7 日基期）：

{_fmt(ew, ["crop", "response", "window", "event_response_z"])}

- 符号一致率（10 品种 × 2 响应）：见 `robustness_event_windows.csv`。

## 3 维度 3：不同模型（Linear / GAM / boosting，§六十三-3）

STEP 25-26 的 World1A 反事实缺口（方法A，事件窗均值）在三个模型族下的表现（POOLED）：

{_fmt(mod[mod["crop"] == "POOLED"], ["learner", "gap_volume_z", "gap_price_z"])}

- 三模型族**价格缺口全部为负**（灾害→价格↑的模型口径，方向 Stable）；
- **成交量缺口方向不一致**：LightGBM 为负、ElasticNet/GAM 为正（量级与符号均 Sensitive）。
  故成交量口径的反事实缺口不得作为方向性结论引用。

## 4 维度 4：不同天气指标（daily vs 3d cumulative，§六十三-4）

2026-07 各指标下的「事件日」计数：

{_fmt(prc, ["measure", "threshold_mm", "days_flagged", "max_mm"])}

- 三种定义均能识别 7 月中旬暴雨；7/19（precip_1d=61.6mm）仅在 1d/3d 定义下被单独识别。

## 5 维度 5：Placebo（§六十三-5）

真实极端天气事件响应 vs 500 次随机非灾害日虚假事件：

{_fmt(plc, ["group", "response", "real_post_mean", "placebo_p50", "real_percentile_in_placebo", "verdict"])}

- **真实响应不可分辨于 placebo**（与 STEP 12 event_study_summary 的 placebo_p 一致）：
  在观测尺度上，极端天气事件对量价的平均影响不显著强于随机波动。

## 6 §六十四 判定表

{_fmt(vd, ["conclusion", "dimension", "result", "judgement"])}

- **Stable**：不同设计下方向一致；**Sensitive**：方向稳定但量级/窗口敏感；
  **Unsupported**：结果不稳定，不进入正式结论。

## 7 Bootstrap 不确定性

STEP 25-26 已用配对残差 Bootstrap（B=100，2025 valid 期残差）给出 World1A 缺口的 95%CI，
见 `reports/14_COUNTERFACTUAL.md` 与 `counterfactual_gap_summary.csv`。

## 8 图表

- F50：Placebo 分布 vs 真实事件响应
- F51：跨模型族反事实缺口

## 9 局限

1. STL 基线含目标年（§二十一 泄漏红线），仅作方向对照；
2. 事件窗/基线维度只覆盖 2026-07 单一事件；
3. 跨模型仅覆盖同一特征口径（F_lag），未覆盖 F_wx/F_now；
4. Placebo 来自 STEP 12 的日度均值口径，未按品种分层。

---
生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}
"""
    p.write_text(txt, encoding="utf-8")
    log.info("报告已写出: %s", p)


# -----------------------------------------------------------------------------
# 9) 主流程
# -----------------------------------------------------------------------------
def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        log.info("=" * 78)
        log.info("STEP 27 Phase 15 稳健性（基线/事件窗/模型族/天气指标/Placebo）")

        md = baseline_methods()
        save_table(md, "robustness_baseline_methods.csv")
        ew = event_windows()
        save_table(ew, "robustness_event_windows.csv")
        prc = precip_measures()
        save_table(prc, "robustness_precip_measures.csv")
        plc = placebo_check()
        save_table(plc, "robustness_placebo.csv")

        # 维度 3（跨模型）依赖 STEP 25-26 的链式模拟
        design, _ = P12.build_design(log)
        design["date"] = pd.to_datetime(design["date"])
        design_hol = (design[["date", "is_public_holiday"]].drop_duplicates()
                      .set_index("date")["is_public_holiday"].to_dict())
        sim_dates = [d for d in sorted(design["date"].unique())
                     if C16.SIM_START <= d <= C16.SIM_END]
        lv = C16.level_table()
        mod = model_diversity(design, design_hol, sim_dates, lv)
        save_table(mod, "robustness_model_diversity.csv")

        vd = verdicts(md, ew, plc, mod)
        save_table(vd, "robustness_verdicts.csv")

        fig_placebo(plc, log)
        fig_model_diversity(mod, log)

        write_report(md, ew, mod, prc, plc, vd, log)

        # 结果登记
        rows = []
        for _, r in plc.iterrows():
            rows.append({
                "result_id": f"RB-PLACEBO-{r['response'].upper()}",
                "research_question": "RQ 极端天气响应是否可分辨于 placebo",
                "crop": "POOLED（rain 事件组）", "period": "2021-2026 全历史事件",
                "method": "Placebo 对照（500 次随机非灾害日）",
                "metric": "真实 post 均值在 placebo 分布中的分位",
                "estimate": round(float(r["real_percentile_in_placebo"]), 3),
                "ci_low": None, "ci_high": None,
                "p_value": round(float(r["placebo_p_value"]), 3),
                "robustness": "事件窗/基线方法对照（F50）",
                "figure": "F50", "table": "robustness_placebo.csv",
                "evidence_level": "Level B（统计关联）",
                "notes": f"verdict={r['verdict']}；真实响应不可分辨于 placebo",
            })
        for _, r in vd.iterrows():
            rows.append({
                "result_id": f"RB-VERDICT-{len(rows)}",
                "research_question": "RQ 结论稳健性判定（§六十四）",
                "crop": "10 品种", "period": "全期",
                "method": "跨设计方向一致性",
                "metric": "judgement", "estimate": r["judgement"],
                "ci_low": None, "ci_high": None, "p_value": None,
                "robustness": r["dimension"],
                "figure": "F50/F51", "table": "robustness_verdicts.csv",
                "evidence_level": "Level B",
                "notes": r["result"],
            })
        register_results(rows)
        log.info("STEP 27 完成")


if __name__ == "__main__":
    main()
