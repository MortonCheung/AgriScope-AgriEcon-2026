"""STEP 12：全历史极端天气 Event Study（Phase 5，§二十九~§三十二）。

对应任务书：
  §二十九 使用派生极端天气事件，但必须先核对定义；官方灾害事件（event_source=official）
          与算法派生事件（event_source=derived_weather）**严格分开，不得混用**——
          本模块量化只用 derived_weather；official 仅在 STEP 13 案例中作定性佐证；
  §三十   统一事件窗口 T-14 ~ T+21（T0 = 事件/簇开始日），响应=量价异常相对
          **事件前正常状态**的变化（本模块：稳健 z 减去各自事件前窗均值）；
  §三十一 事件重叠处理：相隔 ≤3 天的事件合并为**复合事件簇**（compound cluster），
          原始事件保留；统计单元=簇（同一簇内多事件不重复计数）；
  §三十二 Event Study 的目的不是讲单个事件，而是「过去所有暴雨发生后市场平均如何响应」：
          输出 Average Event Response（T-7..T+14 重点展示，全窗 T-14..T+21 计算）
          + Bootstrap 置信区间。

本模块新增的预登记规则（防事后挑结果，写入报告）：
  1) 统计单元 = 复合簇（gap≤3 天合并；簇内多事件算 1 个单元）；
  2) **清洁性规则**：某簇的完整窗口 [T0-14, T0+21] 内若出现**其他簇**的事件日，
     该簇记 `contaminated`，主分析剔除（其事件前基线或事件后响应被相邻事件污染），
     保留在敏感性清单中；
  3) 2026-07 暴雨簇（is_2026_case）不进入「历史平均」（它是 STEP 13 的案例研究对象），
     敏感性中给出含/不含的平均曲线对照；
  4) 事件相对化：z_rel = z_hist − mean(z_hist, T-14..T-1)，事件前窗观测 < min_pre_obs(=5)
     的 (簇×品种) 剔除；
  5) 平均曲线的 CI = **簇级 Bootstrap**（B=1000，重抽簇、整簇替换）；
  6) 事后窗统计量 mean(T+1..T+14) 的零分布 = **安慰剂事件**（500 个伪 T0，
     采样自与任何真实事件窗不重叠的日期），双侧经验 p。

产出：
  outputs/tables/event_cluster_meta.csv        簇元数据（T0、类型、清洁性、剔除原因）
  outputs/tables/event_study_curves.csv        平均响应曲线（组×响应×offset，含 CI）
  outputs/tables/event_study_percrop.csv       逐品种平均响应（雨事件，含 CI）
  outputs/tables/event_study_summary.csv       事后窗汇总 + 安慰剂 p
  outputs/tables/event_study_placebo.csv       安慰剂分布记录
  outputs/figures/F23..F25
  reports/06_EVENT_STUDY.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, EVENTS_CFG, PATHS, StepTimer, get_logger,
    load_parquet, register_results, render_figure, save_table, set_seed,
    setup_matplotlib,
)

LOG = get_logger("07_event_study")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
ES = ANALYSIS["event_study"]
PRE_W = int(ES["window_pre"])
POST_W = int(ES["window_post"])
MIN_PRE = int(ES["min_pre_obs"])
N_BOOT = int(ES["n_boot"])
N_PLACEBO = int(ES["placebo_draws"])
CURVE_LO, CURVE_HI = [int(x) for x in ES["response_curve_window"]]
BASE_SEED = int(ANALYSIS["project"]["random_seed"])
VARS = [("price", "价格"), ("volume", "成交量")]
RESP_COL = {v: f"{v}_anomaly_z_hist" for v, _ in VARS}
RAIN_TYPES = {"rainstorm", "heavy_rain"}


# -----------------------------------------------------------------------------
# 事件簇构建
# -----------------------------------------------------------------------------
def load_clusters() -> pd.DataFrame:
    """从 STEP 02 产物读取派生事件并按 compound_cluster 聚簇。"""
    fl = pd.read_csv(PATHS.table("event_overlap_flags.csv"),
                     parse_dates=["event_start", "event_end"])
    d = fl[fl["event_source"] == "derived_weather"].copy()
    rows = []
    for cid, g in d.groupby("compound_cluster"):
        types = sorted(g["event_type"].unique())
        rows.append({
            "cluster": int(cid),
            "t0": g["event_start"].min(),
            "t_end": g["event_end"].max(),
            "n_events": int(len(g)),
            "event_ids": "|".join(g["event_id"]),
            "types": "|".join(types),
            "group": "rain" if set(types) & RAIN_TYPES else "heat",
            "is_2026_case": bool(g["is_2026_case"].any()),
        })
    cl = pd.DataFrame(rows).sort_values("t0").reset_index(drop=True)
    # 清洁性：完整窗口 [t0-14, t0+21] 内出现其他簇的事件日 → contaminated
    clean = []
    for _, r in cl.iterrows():
        lo, hi = r["t0"] - pd.Timedelta(days=PRE_W), r["t0"] + pd.Timedelta(days=POST_W)
        others = cl[cl["cluster"] != r["cluster"]]
        hit = others[(others["t0"] <= hi) & (others["t_end"] >= lo)]
        clean.append(hit.empty)
    cl["clean"] = clean
    cl["in_primary"] = cl["clean"] & ~cl["is_2026_case"]
    cl["exclude_reason"] = np.where(
        cl["is_2026_case"], "2026-07 案例（STEP 13 单独研究）",
        np.where(~cl["clean"], "窗口与其他簇重叠（污染）", ""))
    return cl


# -----------------------------------------------------------------------------
# 窗口响应（真实簇与安慰剂共用）
# -----------------------------------------------------------------------------
def window_response(panel: pd.DataFrame, t0: pd.Timestamp, tag: str,
                    pre_hi: int = -1) -> pd.DataFrame:
    """单个事件窗的 (品种×响应×offset) 长表：z 原值 + 事件相对化 z_rel。

    pre_hi：事件前窗的上界 offset（默认 -1；STEP 13 案例窗事件日早于 T0 时前移）。
    """
    lo = t0 - pd.Timedelta(days=PRE_W)
    hi = t0 + pd.Timedelta(days=POST_W)
    w = panel[(panel["date"] >= lo) & (panel["date"] <= hi)].copy()
    w["offset"] = (w["date"] - t0).dt.days
    rows = []
    for crop in CORE_CROPS:
        g = w[w["crop"] == crop]
        for var, _ in VARS:
            s = g.set_index("offset")[RESP_COL[var]].dropna()
            pre = s[(s.index >= -PRE_W) & (s.index <= pre_hi)]
            if len(pre) < MIN_PRE:
                continue  # 事件前观测不足，无法定义「事件前正常状态」
            base = float(pre.mean())
            for off, v in s.items():
                rows.append({"tag": tag, "crop": crop, "response": var,
                             "offset": int(off), "z": float(v), "z_rel": float(v - base)})
    return pd.DataFrame(rows)


def mean_curve(df: pd.DataFrame, keys: list, cluster_of: dict | None = None):
    """按 keys 聚合的平均响应曲线 + 簇级 Bootstrap CI。

    Bootstrap 重抽单元 = tag（簇或安慰剂编号）；cluster_of 不再需要（tag 即单元）。
    """
    boot_rng = np.random.default_rng(BASE_SEED)
    out = []
    for key, g in df.groupby(keys):
        tags = g["tag"].unique()
        # 观测曲线
        cur = g.groupby("offset")["z_rel"].agg(["mean", "count"]).reset_index()
        # 簇级 bootstrap
        parts = {t: g[g["tag"] == t] for t in tags}
        offs = np.sort(g["offset"].unique())
        boots = np.full((N_BOOT, len(offs)), np.nan)
        for b in range(N_BOOT):
            pick = boot_rng.choice(tags, size=len(tags), replace=True)
            bb = pd.concat([parts[t] for t in pick])
            m = bb.groupby("offset")["z_rel"].mean()
            boots[b] = [m.get(o, np.nan) for o in offs]
        cur["ci_low"] = np.nanpercentile(boots, 2.5, axis=0)
        cur["ci_high"] = np.nanpercentile(boots, 97.5, axis=0)
        if not isinstance(key, tuple):
            key = (key,)
        for c, v in zip(keys, key):
            cur[c] = v
        cur["n_units"] = len(tags)
        out.append(cur)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def post_statistic(df: pd.DataFrame) -> float:
    """事后窗统计量：mean(z_rel, T+1..T+14)（全品种合并）。"""
    s = df[(df["offset"] >= 1) & (df["offset"] <= CURVE_HI)]["z_rel"]
    return float(s.mean()) if len(s) else np.nan


def placebo_distribution(panel: pd.DataFrame, cl: pd.DataFrame,
                          rng: np.random.Generator) -> tuple:
    """安慰剂事件：伪 T0 采样自与任何真实簇窗口不重叠的日期。"""
    # 全部真实事件日（含案例簇）
    event_days = pd.DatetimeIndex([])
    for _, r in cl.iterrows():
        event_days = event_days.append(pd.date_range(r["t0"], r["t_end"]))
    blocked = set()
    for d in event_days:
        for k in range(-PRE_W, POST_W + 1):
            blocked.add(d + pd.Timedelta(days=k))
    dmin = panel["date"].min() + pd.Timedelta(days=PRE_W)
    dmax = panel["date"].max() - pd.Timedelta(days=POST_W)
    all_days = pd.date_range(dmin, dmax)
    eligible = np.array([d for d in all_days if d not in blocked])
    LOG.info("安慰剂可用日期 %d / %d（剔除事件 ±%d 天）", len(eligible), len(all_days), PRE_W)

    stats = []
    for i in range(N_PLACEBO):
        t0 = pd.Timestamp(rng.choice(eligible))
        wr = window_response(panel, t0, f"PL{i:04d}")
        if wr.empty:
            continue
        stats.append(post_statistic(wr))
    return np.asarray(stats, dtype=float), eligible


# -----------------------------------------------------------------------------
# 图
# -----------------------------------------------------------------------------
def fig_avg_curves(curves: pd.DataFrame, group: str, fname: str, tag: str,
                   subtitle: str) -> None:
    plt = setup_matplotlib()
    d = curves[curves["group"] == group]
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.2))
    for ax, (var, vlabel) in zip(axes, VARS):
        g = d[d["response"] == var].sort_values("offset")
        ax.axvspan(0, POST_W, color="#f2f2f2", zorder=0, label="事件后窗")
        ax.axhline(0, color="#333", lw=0.8)
        ax.fill_between(g["offset"], g["ci_low"], g["ci_high"], color="#9dc3e6",
                        alpha=0.55, label="95% 簇级 Bootstrap CI")
        ax.plot(g["offset"], g["mean"], color="#1f4e79", lw=1.8, marker="o", ms=2.5,
                label="平均事件响应")
        ax.axvline(0, color="#c0392b", ls=":", lw=1.2, label="T0 事件开始")
        ax.set_xlabel("相对事件开始的日历日偏移")
        ax.set_ylabel("事件相对化异常（稳健 z）")
        ax.set_title(f"{vlabel}异常")
        ax.legend(fontsize=8)
    n = int(d["n_units"].max()) if len(d) else 0
    fig.suptitle(f"图{tag}　{subtitle}（n={n} 个事件簇）\n"
                 "响应=去季节化稳健 z 减去各自事件前窗(T-14..T-1)均值；CI 为簇级 Bootstrap(1000)",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；事件=Open-Meteo ERA5 再分析"
                  "日值阈值识别（派生事件，与官方通报严格分开）；窗口 T-14~T+21，图示重点 T-7~T+14。")


def fig_placebo(placebo: np.ndarray, obs: dict, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.6))
    for ax, (var, vlabel) in zip(axes, VARS):
        ax.hist(placebo, bins=40, color="#9dc3e6", edgecolor="#1f4e79", lw=0.4,
                label="安慰剂分布(500)")
        ax.axvline(obs[var], color="#c0392b", lw=1.8,
                   label=f"观测值 {obs[var]:+.3f}")
        ax.set_xlabel("mean(z_rel, T+1..T+14)")
        ax.set_ylabel("频数")
        ax.set_title(f"{vlabel}异常（雨事件簇）")
        ax.legend(fontsize=8.5)
    fig.suptitle(f"图{tag}　安慰剂检验：真实雨事件的事后响应 vs 随机伪事件\n"
                 "伪 T0 采样自与任何真实事件窗不重叠的日期；两尾经验 p 见汇总表",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                  "安慰剂=无事件日期上的同一窗口统计量；经验 p=(1+#{|安慰剂|≥|观测|})/(1+500)。")


def fig_percrop_heatmap(percrop: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    d = percrop[percrop["group"] == "rain"]
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.4))
    for ax, (var, vlabel) in zip(axes, VARS):
        dv = d[d["response"] == var]
        mat = dv.pivot_table(index="crop", columns="offset", values="mean").reindex(CORE_CROPS)
        sig = dv.pivot_table(index="crop", columns="offset", values="ci_excl0").reindex(CORE_CROPS)
        mat = mat[[c for c in mat.columns if CURVE_LO <= c <= CURVE_HI]]
        sig = sig[[c for c in sig.columns if CURVE_LO <= c <= CURVE_HI]]
        vmax = float(np.nanmax(np.abs(mat.values))) or 1.0
        im = ax.imshow(mat.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        for i, crop in enumerate(mat.index):
            for j, c in enumerate(mat.columns):
                if bool(sig.loc[crop, c]):
                    ax.plot(j, i, marker="o", ms=4, mfc="none", mec="#111", mew=0.9)
        ax.set_xticks(range(len(mat.columns)))
        ax.set_xticklabels([f"T{c:+d}" if c != 0 else "T0" for c in mat.columns], fontsize=7.5)
        ax.set_yticks(range(len(mat.index)))
        ax.set_yticklabels(mat.index)
        ax.set_xlabel("相对事件开始的日历日偏移")
        ax.set_title(f"{vlabel}异常")
        fig.colorbar(im, ax=ax, label="平均事件相对化响应（稳健 z）")
    fig.suptitle(f"图{tag}　逐品种平均事件响应（雨事件簇，主分析）\n"
                 "黑圈=该格簇级 Bootstrap 95% CI 不含 0；n=簇数，热量不足 8 簇的格子解释须谨慎",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；事件=ERA5 派生（暴雨/连续强降雨簇）。"
                  "响应=事件相对化稳健 z；逐品种曲线由同一组事件簇平均得到（品种间共享天气冲击，非独立证据）。")


# -----------------------------------------------------------------------------
# 报告
# -----------------------------------------------------------------------------
def write_report(cl_meta, curves, percrop, summ, placebo_stats, n_sens) -> None:
    L: list = []
    A = L.append
    A("# 06 EVENT STUDY — 全历史极端天气的平均市场响应（STEP 12）\n")
    A(f"> 窗口 **T-14 ~ T+21**（T0=事件簇开始日）；统计单元 = **复合事件簇**"
      f"（§三十一：间隔 ≤{EVENTS_CFG['overlap_rules']['gap_days']} 天的事件合并）；"
      f"响应 = 去季节化稳健 z − 事件前窗均值（§三十：相对事件前正常状态）。\n")
    A("> 证据等级：Level B（统计关联）。事件=算法派生（ERA5 阈值识别），"
      "与官方通报严格分开（§二十九）；官方事件仅 STEP 13 作定性佐证。\n")

    A("## 1. 事件簇清单与预登记规则\n")
    A("| 簇 | T0 | 类型 | 组 | 事件数 | 清洁 | 主分析 | 剔除原因 |")
    A("|---|---|---|---|---|---|---|---|")
    for _, r in cl_meta.iterrows():
        A(f"| C{int(r['cluster'])} | {r['t0']:%Y-%m-%d} | {r['types']} | "
          f"{'雨' if r['group'] == 'rain' else '高温'} | {int(r['n_events'])} | "
          f"{'✓' if r['clean'] else '✗'} | {'✓' if r['in_primary'] else '—'} | {r['exclude_reason'] or '—'} |")
    A("")
    A("- 清洁性规则：簇完整窗口 [T0-14, T0+21] 内出现其他簇事件日 → 剔除出主分析"
      "（事件前基线或事件后响应被相邻事件污染），保留于敏感性；")
    A("- 2026-07 案例簇不进入历史平均（STEP 13 单独研究）；")
    A(f"- 主分析簇数：雨 {int(((cl_meta['group'] == 'rain') & cl_meta['in_primary']).sum())}、"
      f"高温 {int(((cl_meta['group'] == 'heat') & cl_meta['in_primary']).sum())}；"
      f"敏感性（全 13 簇含案例/污染簇）另存。\n")

    A("## 2. 方法\n")
    A("| 环节 | 实现 |")
    A("|---|---|")
    A(f"| 事件相对化 | z_rel = z(方法B 去季节化稳健 z) − mean(z, T-14..T-1)；前窗观测 <{MIN_PRE} 的品种剔除 |")
    A(f"| 平均曲线 | 簇×品种单元在每 offset 上取均值（图示重点 T{CURVE_LO:+d}..T+{CURVE_HI}） |")
    A(f"| CI | 簇级 Bootstrap，B={N_BOOT}，重抽簇整簇替换，2.5/97.5 百分位 |")
    A(f"| 零分布 | 安慰剂事件 {N_PLACEBO} 个：伪 T0 采样自与任何真实事件窗不重叠的日期 |")
    A(f"| 事后统计量 | mean(z_rel, T+1..T+{CURVE_HI})，双侧经验 p |")
    A("")

    A("## 3. 主结果：平均事件响应（雨事件簇）\n")
    A("| 响应 | 前窗均值(z_rel, T-14..T-1) | 事后 T+1..T+14 | 95% Bootstrap CI | "
      "安慰剂 p | 事后谷底(T+1..T+14, z) | CI 不含 0 的 offset 数(T-7..T+14) |")
    A("|---|---|---|---|---|---|---|")
    rain_curves = curves[curves["group"] == "rain"]
    for var, vlabel in VARS:
        s = summ[(summ["group"] == "rain") & (summ["response"] == var)].iloc[0]
        g = rain_curves[(rain_curves["response"] == var)
                        & (rain_curves["offset"] >= CURVE_LO) & (rain_curves["offset"] <= CURVE_HI)]
        n_sig = int(((g["ci_low"] > 0) | (g["ci_high"] < 0)).sum()) if len(g) else 0
        A(f"| {vlabel} | {s['pre_mean']:+.3f} | {s['post_mean']:+.3f} | "
          f"[{s['post_ci_low']:+.3f}, {s['post_ci_high']:+.3f}] | {s['placebo_p']:.3f} | "
          f"T{s['trough_offset']:+d}, {s['trough_z']:+.3f} | {n_sig}/{len(g)} |")
    A("")
    A("- 判定：事后均值 CI 含 0 且安慰剂 p>0.05 → 该响应在事件口径下记"
      "`NOT SUPPORTED BY CURRENT DATA`；")
    A("- 曲线逐 offset 的 CI 不含 0 的格子仅作探索性描述（多重比较未校正），"
      "正式结论以上一行事后窗统计为准。\n")

    A("## 4. 高温事件簇\n")
    heat_n = int(((cl_meta["group"] == "heat") & cl_meta["in_primary"]).sum())
    A(f"- 主分析清洁高温簇仅 **{heat_n}** 个（2025-06-23；2026 年 7-8 月两个高温簇被 2026-07 "
      "暴雨簇窗口污染而剔除）——样本量不足以给出可信的平均曲线与 CI；")
    A("- 高温响应仅作描述性记录（见 `event_study_curves.csv` 的 heat/all 组），"
      "不进入任何假设判定。\n")

    A("## 5. 逐品种差异（RQ5 描述性）\n")
    A("| 品种 | 成交量 T+1..T+14 | 价格 T+1..T+14 | 成交量谷底(T+1..T+14) | 价格谷底(T+1..T+14) |")
    A("|---|---|---|---|---|")
    for crop in CORE_CROPS:
        vals = []
        for var in ("volume", "price"):
            g = percrop[(percrop["group"] == "rain") & (percrop["crop"] == crop)
                        & (percrop["response"] == var)]
            post = g[(g["offset"] >= 1) & (g["offset"] <= CURVE_HI)]
            vals.append(float(post["mean"].mean()) if len(post) else np.nan)
            gp = g[(g["offset"] >= 1) & (g["offset"] <= CURVE_HI)]
            trough = gp.loc[gp["mean"].idxmin()] if len(gp) else None
            vals.append(f"T{int(trough['offset']):+d} {trough['mean']:+.2f}" if trough is not None else "—")
        A(f"| {crop} | {vals[0]:+.3f} | {vals[2]:+.3f} | {vals[1]} | {vals[3]} |")
    A("")
    A("> 10 个品种共享同一组事件（天气在市内同质），品种间差异只能作为**异质性描述**，"
      "不能当作独立证据（与 STEP 10 同一限制）。\n")

    A("## 6. 敏感性\n")
    A(f"- 含案例簇与污染簇的全 13 簇平均曲线另行保存（n_units 列区分）；"
      f"主分析结论若在敏感性下翻转，以两者不一致为限写作「不稳健」；")
    A(f"- 安慰剂均值分布：均值 {np.nanmean(placebo_stats):+.4f}、"
      f"标准差 {np.nanstd(placebo_stats):.4f}（伪事件数 {len(placebo_stats)}）。\n")

    A("## 7. 图表清单\n")
    A("| 图 | 内容 | 回答的问题 |")
    A("|---|---|---|")
    A("| 图23 `F23_event_avg_curves_rain.png` | 雨事件平均响应曲线 ± CI | 极端降雨后量价平均如何变动 |")
    A("| 图24 `F24_event_placebo.png` | 安慰剂分布 vs 观测 | 平均响应是否超出随机波动 |")
    A("| 图25 `F25_event_percrop_heatmap.png` | 逐品种响应热力图 | 哪些品种响应更强（RQ5） |")
    A("")

    A("## 8. 本节结论（Level B）\n")
    nsup = summ[(summ["group"] == "rain")]
    for _, s in nsup.iterrows():
        vlabel = dict(VARS)[s["response"]]
        ok = (s["post_ci_low"] > 0 or s["post_ci_high"] < 0) or s["placebo_p"] < 0.05
        A(f"- 雨事件 → {vlabel}：事后均值 {s['post_mean']:+.3f} "
          f"[{s['post_ci_low']:+.3f}, {s['post_ci_high']:+.3f}]，安慰剂 p={s['placebo_p']:.3f} → "
          + ("存在平均响应（仍为统计关联）" if ok else "`NOT SUPPORTED BY CURRENT DATA`"))
    A("- 该结论与 STEP 10（日度滞后）、STEP 11（非线性/临界点）共享同一功效约束"
      "（AR(1) 高、事件数少）；事件口径把「极端日」而非「连续日值」作为处理，"
      "是对前两步的重要补充，但同样不构成因果识别。\n")

    pth = PATHS.report("06_EVENT_STUDY.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("Event Study 报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("07_event_study", LOG):
        panel = load_parquet("panel_final")
        panel = panel[(panel["date"] >= CORE_START) & (panel["date"] <= CORE_END)
                      & (panel["crop"].isin(CORE_CROPS))].copy()
        cl = load_clusters()
        save_table(cl, "event_cluster_meta.csv")
        LOG.info("事件簇 %d 个：主分析 %d（雨 %d / 高温 %d），污染 %d，案例 %d",
                 len(cl), int(cl["in_primary"].sum()),
                 int(((cl["group"] == "rain") & cl["in_primary"]).sum()),
                 int(((cl["group"] == "heat") & cl["in_primary"]).sum()),
                 int((~cl["clean"] & ~cl["is_2026_case"]).sum()),
                 int(cl["is_2026_case"].sum()))

        # ---- 主分析曲线（清洁簇、不含案例）与敏感性曲线（全簇） ----------
        frames_primary, frames_sens = [], []
        for _, r in cl.iterrows():
            wr = window_response(panel, r["t0"], f"C{int(r['cluster'])}")
            if wr.empty:
                LOG.warning("簇 C%d 无有效响应（前窗观测不足）", r["cluster"])
                continue
            wr["group"] = r["group"]
            frames_sens.append(wr)
            if r["in_primary"]:
                frames_primary.append(wr)
        cur_p = pd.concat(frames_primary, ignore_index=True)
        cur_s = pd.concat(frames_sens, ignore_index=True)
        # 原始逐簇响应长表（供 STEP 13 案例对照复用，保证口径一致）
        save_table(cur_p, "event_study_primary_long.csv")

        curves_p = mean_curve(cur_p, ["group", "response"])
        curves_p["analysis"] = "primary"
        curves_s = mean_curve(cur_s.assign(group="all_sens"), ["group", "response"])
        curves_s["analysis"] = "sensitivity_all13"
        curves = pd.concat([curves_p, curves_s], ignore_index=True)
        save_table(curves, "event_study_curves.csv")

        # ---- 逐品种（雨事件，主分析） --------------------------------------
        cur_rain = cur_p[cur_p["group"] == "rain"]
        percrop = mean_curve(cur_rain, ["group", "crop", "response"])
        # T+1..T+14 逐 offset CI 不含 0 标记
        percrop["ci_excl0"] = (percrop["ci_low"] > 0) | (percrop["ci_high"] < 0)
        save_table(percrop, "event_study_percrop.csv")

        # ---- 安慰剂 ---------------------------------------------------------
        rng = np.random.default_rng(BASE_SEED + 7)
        placebo, eligible = placebo_distribution(panel, cl, rng)
        obs = {var: post_statistic(cur_p[(cur_p["group"] == "rain")
                                         & (cur_p["response"] == var)]) for var, _ in VARS}
        pvals = {}
        for var, _ in VARS:
            pv = (1 + np.nansum(np.abs(placebo) >= abs(obs[var]))) / (1 + len(placebo))
            pvals[var] = float(pv)

        # ---- 汇总 -----------------------------------------------------------
        rows = []
        for group in ("rain", "heat"):
            for var, _ in VARS:
                g = cur_p[(cur_p["group"] == group) & (cur_p["response"] == var)]
                if g.empty:
                    continue
                pre = g[(g["offset"] >= -PRE_W) & (g["offset"] <= -1)]["z_rel"]
                post = g[(g["offset"] >= 1) & (g["offset"] <= CURVE_HI)]["z_rel"]
                # 簇级 bootstrap 的 post 均值 CI
                tags = g["tag"].unique()
                parts = {t: g[g["tag"] == t] for t in tags}
                brng = np.random.default_rng(BASE_SEED + 11)
                boots = np.array([
                    pd.concat([parts[t] for t in brng.choice(tags, size=len(tags), replace=True)])
                    .pipe(lambda d: d[(d["offset"] >= 1) & (d["offset"] <= CURVE_HI)]["z_rel"].mean())
                    for _ in range(N_BOOT)])
                cur_mean = g.groupby("offset")["mean"] if "mean" in g else None
                gm = g.groupby("offset")["z_rel"].mean()
                gm_post = gm.loc[gm.index.intersection(range(1, CURVE_HI + 1))]
                trough_off = int(gm_post.idxmin()) if len(gm_post) else np.nan
                rows.append({
                    "group": group, "response": var, "n_clusters": int(len(tags)),
                    "pre_mean": float(pre.mean()), "post_mean": float(post.mean()),
                    "post_ci_low": float(np.nanpercentile(boots, 2.5)),
                    "post_ci_high": float(np.nanpercentile(boots, 97.5)),
                    "trough_offset": trough_off,
                    "trough_z": float(gm.get(trough_off, np.nan)),
                    "placebo_p": pvals[var] if group == "rain" else np.nan,
                })
        summ = pd.DataFrame(rows)
        save_table(summ, "event_study_summary.csv")
        save_table(pd.DataFrame({"placebo_post_mean": placebo}), "event_study_placebo.csv")

        # ---- 图 -------------------------------------------------------------
        fig_avg_curves(curves_p, "rain", "F23_event_avg_curves_rain.png", "23",
                       "雨事件簇的平均市场响应")
        fig_placebo(placebo, obs, "F24_event_placebo.png", "24")
        fig_percrop_heatmap(percrop, "F25_event_percrop_heatmap.png", "25")

        write_report(cl, curves, percrop, summ, placebo, len(curves_s))

        # ---- 结果登记 -------------------------------------------------------
        rows_reg = []
        for _, s in summ[summ["group"] == "rain"].iterrows():
            vlabel = dict(VARS)[s["response"]]
            ok = (s["post_ci_low"] > 0 or s["post_ci_high"] < 0) or s["placebo_p"] < 0.05
            rows_reg.append({
                "result_id": f"EVENT-AVG-rain-{s['response']}",
                "research_question": "RQ1" if s["response"] == "volume" else "RQ2",
                "crop": "全体10品种",
                "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": f"Event Study 平均响应（簇级 Bootstrap B={N_BOOT} + 安慰剂 {N_PLACEBO}）",
                "metric": "mean(z_rel, T+1..T+14)，事件相对化稳健 z",
                "estimate": round(float(s["post_mean"]), 4),
                "ci_low": round(float(s["post_ci_low"]), 4),
                "ci_high": round(float(s["post_ci_high"]), 4),
                "p_value": round(float(s["placebo_p"]), 4) if np.isfinite(s["placebo_p"]) else None,
                "robustness": f"n_clusters={int(s['n_clusters'])}；谷底 T{s['trough_offset']:+d}({s['trough_z']:+.3f})",
                "figure": "F23_event_avg_curves_rain.png",
                "table": "event_study_summary.csv",
                "evidence_level": "B",
                "notes": ("H1/H2 相关证据：支持" if ok else
                          "NOT SUPPORTED BY CURRENT DATA（CI 含 0 且安慰剂 p>0.05）"),
            })
        register_results(rows_reg)
        LOG.info("结果登记 %d 条", len(rows_reg))


if __name__ == "__main__":
    main()
