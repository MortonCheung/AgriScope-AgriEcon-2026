"""STEP 14：MILESTONE 1 汇总报告（§七十~§七十二）。

对应任务书：
  §七十   第一轮完成 A~H（项目结构与数据审计 / 日度面板 / 10 种蔬菜画像 /
          去季节化异常 / 0-30 天 lag / 初步非线性临界点 / 全历史 Event Study /
          2026-07 暴雨复盘）后输出 `reports/MILESTONE_1_REPORT.md`；
  §七十一 必须回答五个问题：
          Q1 数据中是否真的存在「极端天气 → 成交量异常」的稳定信号？
          Q2 成交量变化是否领先价格变化？
          Q3 这种关系有没有明显 lag？
          Q4 是否存在非线性阈值？
          Q5 2026 暴雨是否符合历史规律？
  §七十二 若没有明显结果：不人为加强模型；先检查季节性/节假日/缺失/作物异质性/
          event 定义/时间尺度/市场数据性质；若仍无 → 正式记录「未发现稳定证据」，
          这也是研究结论。

本模块新增的补充分析（为回答 Q2/Q3，STEP 10 只测了 weather→量价，未测量价相互领先滞后）：
  量价领先滞后扫描（探索性，Level B）：对每个品种，
    price_z(t) ~ volume_z(t-k) + 周末 + 节假日（HAC-14），k = -14..+14
  k>0 = 成交量领先价格 k 天；k<0 = 价格领先成交量 |k| 天；k=0 同日。
  与 STEP 10 同一套检验纪律（BH-FDR 全家族 + 系列内）。

产出：
  outputs/tables/m1_volume_price_leadlag.csv   量价领先滞后扫描（探索性）
  outputs/figures/F29_m1_leadlag_heatmap.png
  reports/MILESTONE_1_REPORT.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, bh_fdr, get_logger, load_parquet,
    register_results, render_figure, save_table, set_seed, setup_matplotlib,
)

LOG = get_logger("09_milestone1")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
HAC_LAGS = int(ANALYSIS["lag"]["hac_maxlags"])
MIN_OBS = int(ANALYSIS["lag"]["min_obs"])
MAX_LEAD = 14
CONTROLS = ["is_weekend", "is_public_holiday"]


# -----------------------------------------------------------------------------
# 补充分析：量价领先滞后（探索性）
# -----------------------------------------------------------------------------
def volume_price_leadlag(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for crop in CORE_CROPS:
        g = panel[panel["crop"] == crop].sort_values("date")
        ctrl = g[CONTROLS].to_numpy(dtype=float)
        p = g["price_anomaly_z_hist"].to_numpy(dtype=float)
        v = g["volume_anomaly_z_hist"].to_numpy(dtype=float)
        for k in range(-MAX_LEAD, MAX_LEAD + 1):
            x = pd.Series(v).shift(k).to_numpy(dtype=float)  # k>0: volume 滞后 k 期入场=领先价格
            ok = ~(np.isnan(p) | np.isnan(x) | np.isnan(ctrl).any(axis=1))
            if ok.sum() < MIN_OBS:
                continue
            X = sm.add_constant(np.column_stack([x[ok], ctrl[ok]]), has_constant="add")
            m = sm.OLS(p[ok], X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
            rows.append({
                "crop": crop, "lead_k": k, "direction": "成交量领先价格" if k > 0 else
                ("价格领先成交量" if k < 0 else "同日"),
                "effect": float(m.params[1]), "se": float(m.bse[1]),
                "t": float(m.tvalues[1]), "p_value": float(m.pvalues[1]),
                "n": int(m.nobs), "r2": float(m.rsquared),
            })
    out = pd.DataFrame(rows)
    out["fdr_p"] = bh_fdr(out["p_value"].to_numpy())
    out["fdr_p_within"] = out.groupby("crop")["p_value"].transform(
        lambda s: bh_fdr(s.to_numpy()))
    out["ci_low"] = out["effect"] - 1.96 * out["se"]
    out["ci_high"] = out["effect"] + 1.96 * out["se"]
    return out


def fig_leadlag(ll: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    mat = ll.pivot_table(index="crop", columns="lead_k", values="effect").reindex(CORE_CROPS)
    sig = ll.pivot_table(index="crop", columns="lead_k", values="fdr_p").reindex(CORE_CROPS)
    vmax = float(np.nanmax(np.abs(mat.values))) or 1.0
    fig, ax = plt.subplots(figsize=(13.0, 5.6))
    im = ax.imshow(mat.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    for i, crop in enumerate(mat.index):
        for j, k in enumerate(mat.columns):
            if np.isfinite(sig.loc[crop, k]) and sig.loc[crop, k] < 0.05:
                ax.plot(j, i, marker="o", ms=4, mfc="none", mec="#111", mew=0.9)
    ax.set_xticks(range(len(mat.columns)))
    ax.set_xticklabels([f"{k:+d}" if k != 0 else "0" for k in mat.columns], fontsize=8)
    ax.set_yticks(range(len(mat.index)))
    ax.set_yticklabels(mat.index)
    ax.set_xlabel("k（天）：k>0 = 成交量领先价格 k 天；k<0 = 价格领先成交量")
    ax.axvline(list(mat.columns).index(0), color="#333", lw=1.0, ls=":")
    fig.colorbar(im, ax=ax, label="效应：价格 z 对 1 个成交量 z 的回归系数")
    ax.set_title("黑圈 = 全家族 BH-FDR(0.05) 显著；虚线 = 同日", fontsize=10)
    fig.suptitle(f"图{tag}　量价领先滞后结构（探索性，回答 Milestone-1 Q2/Q3）\n"
                 "发现：同日负共变稳定（10/10 品种同号，西红柿/青椒过 FDR）；但显著格子在宽 lag 范围"
                 "内近乎恒定——强自相关序列共变的指纹，滞后项是同日关系的投影，不携带方向信息",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）。"
                  "单 lag 回归（每次仅一个 k），响应/暴露均为方法B 去季节化稳健 z，HAC(14)，周末/节假日控制；"
                  "k>0 = 成交量领先价格，k<0 = 价格领先成交量。")


# -----------------------------------------------------------------------------
# 报告
# -----------------------------------------------------------------------------
def _fmt(v, n=3):
    return f"{v:+.{n}f}" if np.isfinite(v) else "—"


def write_report(ll: pd.DataFrame, ctx: dict) -> None:
    L: list = []
    A = L.append
    A("# MILESTONE 1 REPORT — 沈阳极端天气 × 农产品市场：第一轮研究汇总\n")
    A(f"> 研究窗口：**{CORE_START:%Y-%m-%d} ~ {CORE_END:%Y-%m-%d}**（市场与气象共同覆盖期）；"
      f"10 种核心批发蔬菜；日度面板 {ctx['n_panel']:,} 行（品种 × 交易日）。\n")
    A("> 证据分级：A 直接观察 / B 统计关联 / C 机制证据 / D 模型反事实。"
      "本里程碑结论以 Level A/B 为主；机制（C）与反事实（D）留给第二阶段。\n")
    A("> 纪律：数据不支持时写 `NOT SUPPORTED BY CURRENT DATA`，不挑结果、不加强模型（§七十二）。\n")

    # ---- 五问速答 -----------------------------------------------------------
    A("## 0. 五个核心问题的速答（§七十一）\n")
    A("| # | 问题 | 速答 | 证据等级 |")
    A("|---|---|---|---|")
    A(f"| Q1 | 极端天气 → 成交量异常是否存在稳定信号？ | **未发现稳定证据**"
      f"（日度滞后 0 个 FDR 显著；事件口径 CI 含 0、安慰剂 p={ctx['es_vol_p']:.2f}） | B |")
    A(f"| Q2 | 成交量变化是否领先价格变化？ | **存在稳定同日负共变**（10/10 品种同号，"
      f"西红柿/青椒过 FDR），但**领先方向不可识别**（效应在 ±14 天内平坦） | B |")
    A("| Q3 | 关系是否存在明显 lag？ | **无可识别 lag**：量价滞后系数是同日关系的自相关投影；"
      "天气→量价的峰值 lag 亦未通过 FDR | B |")
    A("| Q4 | 是否存在非线性阈值？ | **NOT SUPPORTED BY CURRENT DATA**"
      f"（80 个非线性检验 FDR 后 0 显著；极端降水段样本不足以支撑断点识别） | B |")
    A("| Q5 | 2026 暴雨是否符合历史规律？ | **价格：符合**（落在历史 95% CI 内）；"
      "**成交量：边缘性负偏但不可分辨于噪声**（安慰剂 p=0.15） | B |")
    A("")

    # ---- A-H 完成度 ---------------------------------------------------------
    A("## 1. A~H 交付物完成度（§七十）\n")
    A("| 环节 | 交付物 | 状态 |")
    A("|---|---|---|")
    A("| A 项目结构与数据审计 | `reports/01_DATA_AUDIT.md`、`outputs/tables/input_inventory.csv` 等 | ✅ |")
    A("| B 日度核心面板 | `data/processed/shenyang_panel_final.parquet`（14,100 行 × 222 列） | ✅ |")
    A("| C 10 种蔬菜画像 | `reports/02_DESCRIPTIVE.md` | ✅ |")
    A("| D 去季节化异常 | `reports/03_DESEASONALIZATION.md`（方法B 主 + 方法A 对照） | ✅ |")
    A("| E 0–30 天 lag | `reports/04_LAG_ANALYSIS.md` | ✅ |")
    A("| F 初步非线性/临界点 | `reports/05_THRESHOLD.md` | ✅ |")
    A("| G 全历史 Event Study | `reports/06_EVENT_STUDY.md` | ✅ |")
    A("| H 2026-07 暴雨复盘 | `reports/07_CASE_2026.md` | ✅ |")
    A("")
    A(f"- 结果登记累计 {ctx['n_registry']} 条（`outputs/results_registry.csv`），"
      f"图 {ctx['n_figures']} 张，表 {ctx['n_tables']} 张；")
    A(f"- 数据阻断/降级 {ctx['n_blockers']} 条（`reports/BLOCKERS.md`），"
      "最重要的降级：土壤水分官方基线缺失 → 自建观测期基线（B\\* 级）。\n")

    # ---- Q1/Q3 --------------------------------------------------------------
    A("## 2. Q1 / Q3：极端天气 → 成交量异常的信号与滞后结构\n")
    A("### 2.1 日度滞后（STEP 10）\n")
    A(f"- 单 lag 全网格（方法B 稳健 z）：**FDR 校正后显著 lag 数 = {ctx['lag_n_fdr_sig']}"
      f" / {ctx['lag_n_tests']:,}**；成交量对全部 7 个 hazard 的同期相关 |r| ≤ 0.06（噪声级）；")
    A(f"- 窗聚合分布滞后模型（4 窗口联合）：联合 FDR 显著的品种×响应组合 = "
      f"{ctx['win_n_joint_sig']} 个；")
    A("- 解释：异常序列 AR(1) 高（价格 0.97 / 成交量 0.89），有效样本量约 22–79，"
      "名义 1410 个交易日的信息量远低于表面规模。\n")
    A("### 2.2 事件口径（STEP 12）\n")
    A(f"- 8 个清洁雨事件簇：成交量事后均值 {ctx['es_vol_mean']:+.3f} "
      f"[{ctx['es_vol_lo']:+.3f}, {ctx['es_vol_hi']:+.3f}]，安慰剂 p={ctx['es_vol_p']:.3f}；"
      f"价格 {ctx['es_pri_mean']:+.3f} [{ctx['es_pri_lo']:+.3f}, {ctx['es_pri_hi']:+.3f}]，"
      f"安慰剂 p={ctx['es_pri_p']:.3f}；")
    A("- 两个独立口径（连续日值 / 离散事件）都不可分辨于噪声 → Q1 答「未发现稳定证据」；"
      "Q3 的「峰值 lag」在两口径下均未通过多重检验。\n")

    # ---- Q2 补充分析 ---------------------------------------------------------
    A("## 3. Q2 / Q3：量价领先滞后（本里程碑补充的探索性分析）\n")
    A("STEP 10 只测了 weather→量与 weather→价；量价相互关系是 Q2 的直接对象，"
      "故补做扫描：`price_z(t) ~ volume_z(t-k)`，k=-14..+14（k>0=量领先价 k 天），"
      "单 lag 回归 + HAC(14) + 周末/节假日控制，逐品种。\n")
    A("### 3.1 发现一：同日负共变是稳定的\n")
    A("| 品种 | 同日系数（k=0） | 95% CI | 全家族 FDR p |")
    A("|---|---|---|---|")
    for _, r in ctx["k0"].iterrows():
        A(f"| {r['crop']} | {r['effect']:+.3f} | [{r['ci_low']:+.3f}, {r['ci_high']:+.3f}] | "
          f"{r['fdr_p']:.3f}{'*' if r['fdr_p'] < 0.05 else ''} |")
    A("")
    A(f"- **10/10 品种同日系数全部为负**（范围 {ctx['k0']['effect'].min():+.3f} ~ "
      f"{ctx['k0']['effect'].max():+.3f}）：若各品种独立，方向一致性的二项 p≈0.002；"
      "品种共享市场级冲击（非独立），故仅作描述性证据；")
    A(f"- 经全家族 BH-FDR 校正后显著：**{ctx['sig_k0']}**（见上表 \\* 行）——"
      "量价负共变（量缩价升的同向共变，与 H2 叙事同向）"
      "是该数据中**少数经得起多重检验的稳定结构**；")
    A("- 注意：这是**共变**（成交低迷日伴随价格偏高），不是传导证据——传导需要"
      "Weather→Volume→Price 的链式检验（STEP 15-17，Level C）。\n")
    A("### 3.2 发现二：「谁领先谁」不可识别\n")
    A(f"- 290 个检验中 FDR 显著 {ctx['ll_n_sig']} 个，但显著格子**不成峰**："
      f"西红柿集中在 k=-3..+3（效应 -0.26~-0.27）与 k=+13/14，青椒集中在 k=-7..+2"
      f"（-0.19~-0.22）——效应在宽 lag 范围内近乎恒定；")
    A(f"- 这是两条强自相关序列（量/价异常 AR(1)≈0.89/0.97）共变的典型指纹："
      "vol_z(t-k)≈ρ^k·vol_z(t)，滞后系数≈同日系数×ρ^k，**滞后项是同日关系的投影**，"
      "不携带方向信息；")
    A("- 若真实存在「量领先价」，效应应在特定 k 处成峰并向两侧衰减；实际剖面平坦 → "
      "**无法支持「成交量领先价格」的表述**（也无法支持反向）；")
    A("- **Q2 结论：存在稳定同日负共变；领先方向不可识别。Q3 结论：无可识别 lag**"
      "（量价之间）；天气→量价的滞后结构在 STEP 10 已证不可分辨。\n")

    # ---- Q4 -----------------------------------------------------------------
    A("## 4. Q4：非线性阈值（STEP 11）\n")
    A(f"- 4 hazard × 10 品种 × 2 响应 = 80 个「自然样条 vs 线性」Wald 检验，"
      f"全家族 FDR 后 **0 个显著**（最小 FDR p={ctx['thr_min_fdr']:.3f}）；")
    A("- 断点（kink）分析：预登记门槛（非线性 FDR）无一通过；探索性最佳候选"
      "（黄瓜·价格·3日降水）sup-Wald 块 Bootstrap p=0.172，断点未被识别；")
    A("- 硬约束：3 日累计降水 >50mm 仅 41 个交易日（2.9%）、>100mm 仅 6 天，"
      "理论上最关心的暴雨阈值段原则上不可识别（样本量约束，非方法问题）；")
    A("- **RQ3 / H5：`NOT SUPPORTED BY CURRENT DATA`**。\n")

    # ---- Q5 -----------------------------------------------------------------
    A("## 5. Q5：2026-07 暴雨是否符合历史规律（STEP 13）\n")
    A("- 天气：极端性确凿（单日 173.9mm、三日 221.1mm 均为观测期第 1；相对 1991-2020 同期 "
      "z≈21；官方口径特大暴雨、红色预警、蒲河 1957 年以来第一大洪水）——Level A；")
    A(f"- 市场响应：价格事后均值 {ctx['case_pri']:+.3f}（历史 CI "
      f"[{ctx['hist_pri_lo']:+.3f}, {ctx['hist_pri_hi']:+.3f}] 内，安慰剂 p=0.23）→ 符合历史规律；")
    A(f"- 成交量事后均值 {ctx['case_vol']:+.3f}（历史 CI [{ctx['hist_vol_lo']:+.3f}, "
      f"{ctx['hist_vol_hi']:+.3f}] 下方，安慰剂 p=0.15）→ 边缘性负偏，不可分辨于噪声；")
    A("- 品种层面：黄瓜一枝独秀（事件后 T+3..14 价格 z +3.44、成交量 z -1.52），"
      "是「暴雨→黄瓜涨价」叙事的直接来源，但单品种单事件不可外推；")
    A("- 结论：**观测期最强暴雨未引发超常市场响应**——这是市场韧性/外部供应缓冲的"
      "间接迹象（Level B），也是第二阶段机制研究的核心问题。\n")

    # ---- §七十二 检查清单 ---------------------------------------------------
    A("## 6. §七十二检查清单（阴性结果的尽责排查）\n")
    A("| 检查项 | 做法 | 结论 |")
    A("|---|---|---|")
    A("| 季节性 | 方法B（留一年法历史同期中位数）主口径 + 方法A（STL）对照，两法剖面一致 | 已控制，非季节性残余所致 |")
    A("| 节假日 | 全部回归含 is_weekend / is_public_holiday 控制 | 已控制 |")
    A("| 缺失 | 交易日缺失显式保留（不插值不重采样）；QA 见 02 报告 | 已记录，无静默填补 |")
    A("| 作物异质性 | 逐品种全网格 + 品种间差异仅作描述（共享同一冲击，非独立证据） | 已检查，无品种驱动伪影 |")
    A("| event 定义 | 派生 vs 官方严格分开；复合簇合并规则预登记；清洁性规则预登记 | 定义可靠 |")
    A("| 时间尺度 | 日度 calendar-day lag + 事件窗 T-14~T+21 + 窗聚合四窗口 | 多尺度一致阴性 |")
    A("| 市场数据性质 | 批发口径、成交量单位 unknown（仅 z 口径）、产地未知 | 属实，已按红线执行 |")
    A("")
    A("> 以上七项排查后结论不变。按 §七十二 正式记录：**「未发现稳定证据」**——"
      "在当前数据（2021-2026、日度、单一城市、批发口径）与当前功效约束下，"
      "极端天气对批发市场量价的日度/事件尺度影响不可分辨于噪声。这也是研究结论。\n")

    # ---- 局限与下一步 -------------------------------------------------------
    A("## 7. 局限与下一步\n")
    A("局限（§六十九 同源）：")
    A("- ERA5 再分析非气象站实测（网格均值还平滑了城区极值：ERA5 173.9mm vs 官方城区 234.7mm）；")
    A("- 成交量单位未知、批发产品产地未知（本地供给 vs 外调供给不可分离）；")
    A("- 市级农业灾损总量无公开权威统计（§三十四 红线已执行）；")
    A("- 单城市、名义 1410 交易日、异常序列强自相关 → n_eff≈22–79；")
    A("- 观察性研究，一切关联不构成因果。\n")
    A("下一步（第二阶段）：")
    A("- STEP 15-17 传导机制（Weather→Volume→Price 链式，Level C）；")
    A("- STEP 18-22 作物异质性、冲击指纹、市场韧性（2026 案例的「无超常响应」是关键线索）；")
    A("- STEP 23-27 预测模型、反事实与稳健性；")
    A("- STEP 28 总报告。\n")
    A("## 8. 图表清单（本里程碑新增）\n")
    A("| 图 | 内容 |")
    A("|---|---|")
    A("| 图29 `F29_m1_leadlag_heatmap.png` | 量价领先滞后热力图（Q2/Q3 探索性证据） |")
    A("")
    A("## 9. 结论\n")
    A("1. **Q1 未发现稳定证据**：极端天气→成交量异常在日度与事件两个口径下均不可分辨于噪声；")
    A("2. **Q2 存在稳定同日负共变、领先方向不可识别**：10/10 品种量价同日系数为负，"
      "西红柿(-0.27)/青椒(-0.21) 经 FDR 显著；但滞后剖面平坦（自相关投影），"
      "「成交量领先价格」不成立；")
    A("3. **Q3 无可识别 lag**：量价之间无峰值结构；天气→量价的峰值 lag 亦未通过多重检验；")
    A("4. **Q4 NOT SUPPORTED**：无线性阈值证据，极端段样本量原则上不可识别；")
    A("5. **Q5 价格符合历史规律、成交量边缘性负偏不可分辨**：观测期最强暴雨未引发超常市场响应；"
      "「黄瓜大涨」为真实观测（Level A）但属单品种单事件，不可外推；")
    A("6. 第一轮的净发现：**该数据的唯一稳定结构是量价负共变**（统计关联，Level B）；"
      "天气端信号在当前功效约束下不可分辨——按 §七十二 正式记录「未发现稳定证据」"
      "（针对天气→量价链条），其可能的经济解释（外部供应缓冲、库存调节、批发环节韧性）"
      "转入第二阶段机制检验。\n")

    pth = PATHS.report("MILESTONE_1_REPORT.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("Milestone 1 报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("09_milestone1", LOG):
        panel = load_parquet("panel_final")
        panel = panel[(panel["date"] >= CORE_START) & (panel["date"] <= CORE_END)
                      & (panel["crop"].isin(CORE_CROPS))].copy()

        # 补充分析：量价领先滞后
        ll = volume_price_leadlag(panel)
        save_table(ll, "m1_volume_price_leadlag.csv")
        fig_leadlag(ll, "F29_m1_leadlag_heatmap.png", "29")
        LOG.info("量价领先滞后：%d 个检验，FDR 显著 %d 个", len(ll),
                 int((ll["fdr_p"] < 0.05).sum()))

        # 汇总上下文
        def _csv(name):
            return pd.read_csv(PATHS.table(name))

        lag = _csv("lag_profile_single.csv")
        win = _csv("lag_window_model.csv")
        es = _csv("event_study_summary.csv")
        thr = _csv("threshold_gam_scan.csv")
        case = _csv("case2026_vs_history.csv")
        es_v = es[(es["group"] == "rain") & (es["response"] == "volume")].iloc[0]
        es_p = es[(es["group"] == "rain") & (es["response"] == "price")].iloc[0]
        c_v = case[case["response"] == "volume"].iloc[0]
        c_p = case[case["response"] == "price"].iloc[0]
        k0 = ll[ll["lead_k"] == 0].set_index("crop").reindex(CORE_CROPS).reset_index()
        k0_sig = k0[k0["fdr_p"] < 0.05]
        sig_k0 = "、".join(f"{r['crop']}({r['effect']:+.3f})" for _, r in k0_sig.iterrows()) or "无"
        reg_dir = PATHS.out("outputs/results_registry.csv").parent
        ctx = {
            "n_panel": 14100,
            "n_registry": len(pd.read_csv(reg_dir / "results_registry.csv")),
            "n_figures": len(list((reg_dir.parent / "outputs/figures").glob("*.png"))),
            "n_tables": len(list((reg_dir.parent / "outputs/tables").glob("*.csv"))),
            "n_blockers": 5,
            "lag_n_fdr_sig": int((lag["fdr_p"] < 0.05).sum()),
            "lag_n_tests": len(lag),
            "win_n_joint_sig": int((win["fdr_p_joint"] < 0.05).sum()),
            "es_vol_mean": es_v["post_mean"], "es_vol_lo": es_v["post_ci_low"],
            "es_vol_hi": es_v["post_ci_high"], "es_vol_p": es_v["placebo_p"],
            "es_pri_mean": es_p["post_mean"], "es_pri_lo": es_p["post_ci_low"],
            "es_pri_hi": es_p["post_ci_high"], "es_pri_p": es_p["placebo_p"],
            "ll_n_sig": int((ll["fdr_p"] < 0.05).sum()),
            "k0": k0, "sig_k0": sig_k0,
            "thr_min_fdr": float(thr["fdr_p"].min()),
            "case_pri": c_p["case_post_mean"], "case_vol": c_v["case_post_mean"],
            "hist_pri_lo": c_p["hist_ci_low"], "hist_pri_hi": c_p["hist_ci_high"],
            "hist_vol_lo": c_v["hist_ci_low"], "hist_vol_hi": c_v["hist_ci_high"],
        }
        write_report(ll, ctx)

        # ---- 结果登记（五问结论 + 量价共变发现） -----------------------------
        rows = []
        # 量价同日负共变（本里程碑的净发现；k=0 过全家族 FDR 的品种）
        for _, r in k0_sig.iterrows():
            rows.append({
                "result_id": f"M1-CORR-{r['crop']}",
                "research_question": "RQ2", "crop": r["crop"],
                "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "同日量价回归 price_z ~ volume_z + 控制（HAC-14），全家族 BH-FDR(290)",
                "metric": "同日效应（价格 z / 1 个成交量 z）",
                "estimate": round(float(r["effect"]), 4),
                "ci_low": round(float(r["ci_low"]), 4), "ci_high": round(float(r["ci_high"]), 4),
                "p_value": round(float(r["fdr_p"]), 4),
                "robustness": f"未校正 p={r['p_value']:.4f}；10/10 品种同号（方向一致性，非独立）",
                "figure": "F29_m1_leadlag_heatmap.png",
                "table": "m1_volume_price_leadlag.csv", "evidence_level": "B",
                "notes": "共变而非传导；滞后剖面平坦（自相关投影），领先方向不可识别",
            })
        qa = [
            ("M1-Q1", "RQ1", "未发现稳定证据",
             f"日度 FDR 显著 0/{len(lag)}；事件口径 CI 含 0、安慰剂 p={es_v['placebo_p']:.3f}"),
            ("M1-Q2", "RQ2", "存在稳定同日负共变；领先方向不可识别",
             f"10/10 品种同日系数为负；FDR 显著：{sig_k0}；滞后剖面平坦"),
            ("M1-Q3", "RQ2", "无可识别 lag",
             "量价滞后系数=同日关系的自相关投影；天气→量价峰值 lag 未通过 FDR"),
            ("M1-Q4", "RQ3", "NOT SUPPORTED BY CURRENT DATA",
             f"80 个非线性检验 FDR 后 0 显著（最小 p={float(thr['fdr_p'].min()):.3f}）"),
            ("M1-Q5", "RQ4", "价格符合历史规律；成交量边缘性负偏不可分辨",
             f"价格 p=0.23 在 CI 内；成交量 p=0.15 低于 CI 下界"),
        ]
        for rid, rq, ans, note in qa:
            rows.append({
                "result_id": rid, "research_question": rq, "crop": "全体10品种",
                "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "Milestone 1 五问汇总（STEP 10-13 + 量价领先滞后补充）",
                "metric": "结论性判定", "estimate": None, "ci_low": None, "ci_high": None,
                "p_value": None, "robustness": "见 MILESTONE_1_REPORT.md 各节",
                "figure": "F29_m1_leadlag_heatmap.png" if rid == "M1-Q2" else None,
                "table": "m1_volume_price_leadlag.csv" if rid == "M1-Q2" else None,
                "evidence_level": "B", "notes": f"{ans}；{note}",
            })
        register_results(rows)
        LOG.info("Milestone 结论登记 %d 条", len(rows))


if __name__ == "__main__":
    main()
