"""STEP 18-20：作物异质性 — 风险画像、冲击指纹、市场韧性（§四十一~§四十四）。

对应任务书：
  §四十一 为每种蔬菜提取 weather_sensitivity / max_volume_shock / max_price_shock /
          peak_lag / recovery_days / volatility / threshold → `crop_risk_profile.csv`；
  §四十二 冲击指纹：不同作物/事件的标准化响应曲线 T-7..T+14，做 clustering 与
          distance analysis；**类别名称必须根据真实聚类结果事后命名**，禁止提前强分5类；
  §四十三 市场韧性指标：shock magnitude（最大负向成交量偏离）/ price shock（最大价格异常）/
          time to trough / recovery time（恢复至事件前水平一定比例，如 90%）/ recovery slope；
  §四十四 不制造综合指数：无充分依据不建 Resilience Score；本模块**分别展示指标**，
          不做加权合成（权重敏感性检验因不构造指数而免）。

口径与前置：
  - 事件 = STEP 12 的 8 个清洁雨簇（2026 案例与污染簇不入；高温簇仅 1 个不聚类）；
  - 响应 = 事件相对化稳健 z（z_rel，与 STEP 12/13 同口径：减前窗 T-14..T-1 均值）；
  - 指纹曲线 = 簇均值，窗口 T-7..T+14（§四十二 与 event_study.response_curve_window 一致）；
  - 韧性恢复定义（显式公式）：z_rel(t) ≥ recovery_fraction(=0.9) × trough_z
    （trough<0 时 0.9×trough 即恢复到冲击深度的 90%）；42 天内未恢复记 censored；
  - 全部指标为**描述性**（Level B），品种共享同一冲击，不做显著性判定。

产出：
  outputs/tables/crop_risk_profile.csv       §四十一 品种风险画像
  outputs/tables/fingerprint_curves.csv      指纹曲线（品种×响应×offset）
  outputs/tables/fingerprint_clusters.csv    聚类划分 + 事后命名依据
  outputs/tables/resilience_event_crop.csv   §四十三 事件×品种指标
  outputs/tables/resilience_summary.csv      品种级中位数汇总
  outputs/figures/F32..F33
  reports/09_CROP_HETEROGENEITY.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist
from sklearn.metrics import silhouette_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, load_parquet,
    register_results, render_figure, save_table, set_seed, setup_matplotlib,
)

LOG = get_logger("11_crop_heterogeneity")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
RES = ANALYSIS["resilience"]
RECOVERY_FRAC = float(RES["recovery_fraction"])
TROUGH_LO, TROUGH_HI = [int(x) for x in RES["trough_search_window"]]
CURVE_LO, CURVE_HI = [int(x) for x in ANALYSIS["event_study"]["response_curve_window"]]
VARS = [("price", "价格"), ("volume", "成交量")]
RESP_COL = {v: f"{v}_anomaly_z_hist" for v, _ in VARS}


# -----------------------------------------------------------------------------
# 事件窗响应（与 STEP 12 同口径）
# -----------------------------------------------------------------------------
def load_clean_clusters() -> pd.DataFrame:
    cl = pd.read_csv(PATHS.table("event_cluster_meta.csv"), parse_dates=["t0"])
    return cl[cl["in_primary"] & (cl["group"] == "rain")].reset_index(drop=True)


def event_responses(panel: pd.DataFrame, cl: pd.DataFrame) -> pd.DataFrame:
    """簇×品种×响应×offset 的 z_rel 长表（前窗 T-14..T-1）。"""
    rows = []
    for _, r in cl.iterrows():
        t0 = r["t0"]
        w = panel[(panel["date"] >= t0 - pd.Timedelta(days=14))
                  & (panel["date"] <= t0 + pd.Timedelta(days=42))].copy()
        w["offset"] = (w["date"] - t0).dt.days
        for crop in CORE_CROPS:
            g = w[w["crop"] == crop]
            for var, _ in VARS:
                s = g.set_index("offset")[RESP_COL[var]].dropna()
                pre = s[(s.index >= -14) & (s.index <= -1)]
                if len(pre) < 5:
                    continue
                base = float(pre.mean())
                for off, v in s.items():
                    rows.append({"cluster": int(r["cluster"]), "t0": t0, "crop": crop,
                                 "response": var, "offset": int(off), "z_rel": float(v - base)})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# STEP 19：冲击指纹与聚类（§四十二）
# -----------------------------------------------------------------------------
def fingerprint(er: pd.DataFrame) -> tuple:
    """品种×响应 的簇均值曲线 + 层次聚类（K 由 silhouette 事后选择）。"""
    curves = []
    for crop in CORE_CROPS:
        for var, _ in VARS:
            g = er[(er["crop"] == crop) & (er["response"] == var)]
            m = g[g["offset"].between(CURVE_LO, CURVE_HI)].groupby("offset")["z_rel"].mean()
            if len(m) < (CURVE_HI - CURVE_LO + 1) * 0.8:
                continue
            m = m.reindex(range(CURVE_LO, CURVE_HI + 1))
            curves.append({"crop": crop, "response": var, **{f"o{int(k)}": v for k, v in m.items()}})
    cur = pd.DataFrame(curves)
    off_cols = [c for c in cur.columns if c.startswith("o")]
    X = cur[off_cols].to_numpy(dtype=float)
    Xf = np.nan_to_num(X, nan=0.0)

    # K 选择：silhouette（欧氏距离，2..5）
    Z = linkage(Xf, method="ward")
    best = None
    for k in (2, 3, 4, 5):
        lab = fcluster(Z, k, criterion="maxclust")
        if len(set(lab)) < 2:
            continue
        sil = float(silhouette_score(Xf, lab))
        if best is None or sil > best[1]:
            best = (k, sil, lab)
    k_best, sil, labels = best
    cur["cluster_label"] = labels
    cur["n_obs_curve"] = int(Xf.shape[1])

    # 事后命名依据：逐簇的量价曲线特征（簇内曲线均值），名称由特征生成
    assign = []
    for lab in sorted(cur["cluster_label"].unique()):
        g = cur[cur["cluster_label"] == lab]
        off_cols_c = [c for c in cur.columns if c.startswith("o")]
        feats = {}
        for var, _ in VARS:
            gg = g[g["response"] == var]
            if gg.empty:
                continue
            v = np.nanmean(gg[off_cols_c].to_numpy(dtype=float), axis=0)
            v = np.nan_to_num(v, nan=0.0)
            feats[f"{var}_trough"] = float(v[1:15].min())
            feats[f"{var}_trough_off"] = int(np.argmin(v[1:15]) + 1)
            feats[f"{var}_end"] = float(v[-1])
            feats[f"{var}_swing"] = float(v.max() - v.min())
        assign.append({
            "cluster_label": lab, "n_curves": len(g),
            "members": "、".join(f"{r['crop']}·{'价' if r['response'] == 'price' else '量'}"
                                for _, r in g.iterrows()),
            **{k: round(v, 3) for k, v in feats.items()},
        })
    return cur, pd.DataFrame(assign), k_best, sil


def name_clusters(assign: pd.DataFrame) -> pd.DataFrame:
    """根据真实聚类特征事后命名（§四十二 红线：禁止预分类别名）。"""
    def _name(r):
        parts = []
        for var, tag in (("volume", "量"), ("price", "价")):
            tr = r.get(f"{var}_trough")
            if tr is None or not np.isfinite(tr):
                continue
            if tr <= -0.5:
                parts.append(f"{tag}深谷({tr:+.2f})")
            elif tr <= -0.25:
                parts.append(f"{tag}浅谷({tr:+.2f})")
            else:
                parts.append(f"{tag}平稳({tr:+.2f})")
        return "、".join(parts)
    assign["cluster_name"] = assign.apply(_name, axis=1)
    return assign


# -----------------------------------------------------------------------------
# STEP 20：韧性指标（§四十三；§四十四 分别展示，不合成）
# -----------------------------------------------------------------------------
def resilience(er: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (cid, crop, var), g in er.groupby(["cluster", "crop", "response"]):
        s = g.set_index("offset")["z_rel"].sort_index()
        post = s.loc[s.index.intersection(range(TROUGH_LO, TROUGH_HI + 1))]
        if len(post) < 5:
            continue
        tr_off = int(post.idxmin())
        tr_val = float(post.loc[tr_off])
        after = post.loc[post.index > tr_off]
        thr = RECOVERY_FRAC * tr_val if tr_val < 0 else tr_val  # 恢复线（谷深的90%）
        rec = after.loc[after >= thr]
        rec_off = int(rec.index.min()) if len(rec) else np.nan
        slope = (float(rec.iloc[0]) - tr_val) / (rec_off - tr_off) if len(rec) else np.nan
        rows.append({
            "cluster": int(cid), "crop": crop, "response": var,
            "shock_magnitude": tr_val, "trough_offset": tr_off,
            "price_shock": float(post.max()),
            "recovery_offset": rec_off,
            "recovery_days": (rec_off - tr_off) if np.isfinite(rec_off) else np.nan,
            "recovery_slope_z_per_day": slope,
            "censored": not np.isfinite(rec_off),
        })
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# STEP 18：品种风险画像（§四十一）
# -----------------------------------------------------------------------------
def crop_risk_profile(panel: pd.DataFrame, er: pd.DataFrame, res: pd.DataFrame,
                      assign: pd.DataFrame) -> pd.DataFrame:
    # weather_sensitivity / peak_lag：来自 STEP 10 focus 表（precip_3d 主口径）
    fs = pd.read_csv(PATHS.table("lag_focus_summary.csv"))
    fs_v = fs[(fs["response"] == "volume") & (fs["metric"] == "z")]
    sens = fs_v.loc[fs_v.groupby("crop")["peak_effect"].apply(lambda s: s.abs().idxmax())]
    # threshold：来自 STEP 11（precip_3d，非线性 FDR p；无支持即写明）
    thr = pd.read_csv(PATHS.table("threshold_gam_scan.csv"))
    rows = []
    for crop in CORE_CROPS:
        g = panel[panel["crop"] == crop]
        sv = sens[sens["crop"] == crop]
        s_row = sv.iloc[0] if len(sv) else None
        er_c = er[er["crop"] == crop]
        res_v = res[(res["crop"] == crop) & (res["response"] == "volume")]
        res_p = res[(res["crop"] == crop) & (res["response"] == "price")]
        thr_v = thr[(thr["crop"] == crop) & (thr["hazard_key"] == "precip_3d")
                    & (thr["response"] == "volume")]
        thr_p = thr[(thr["crop"] == crop) & (thr["hazard_key"] == "precip_3d")
                    & (thr["response"] == "price")]
        fp_vol = er_c[(er_c["response"] == "volume")
                      & er_c["offset"].between(0, 14)].groupby("cluster")["z_rel"].min()
        fp_pri = er_c[(er_c["response"] == "price")
                      & er_c["offset"].between(0, 14)].groupby("cluster")["z_rel"].max()
        lab = assign[assign["members"].str.contains(crop, regex=False)]
        rows.append({
            "crop": crop,
            "weather_sensitivity_hazard": None if s_row is None else s_row["hazard_key"],
            "weather_sensitivity_effect": None if s_row is None else float(s_row["peak_effect"]),
            "weather_sensitivity_sig": None if s_row is None else
            ("FDR显著" if s_row["peak_fdr_p"] < 0.05 else "不显著"),
            "max_volume_shock_mean": float(fp_vol.mean()) if len(fp_vol) else np.nan,
            "max_price_shock_mean": float(fp_pri.mean()) if len(fp_pri) else np.nan,
            "peak_lag_days": None if s_row is None else int(s_row["peak_lag"]),
            "recovery_days_median": float(res_v["recovery_days"].median())
            if len(res_v) else np.nan,
            "volatility_volume_z": float(g["volume_anomaly_z_hist"].std()),
            "volatility_price_z": float(g["price_anomaly_z_hist"].std()),
            "threshold_volume": ("无支持(FDR p=%.2f)" % float(thr_v["fdr_p"].iloc[0])
                                 if len(thr_v) else "—"),
            "threshold_price": ("无支持(FDR p=%.2f)" % float(thr_p["fdr_p"].iloc[0])
                                if len(thr_p) else "—"),
            "fingerprint_cluster": "；".join(sorted(set(
                lab["cluster_name"].tolist()))) if len(lab) else "—",
        })
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 图
# -----------------------------------------------------------------------------
def fig_fingerprint(cur: pd.DataFrame, assign: pd.DataFrame, k: int, sil: float,
                    fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    off_cols = [c for c in cur.columns if c.startswith("o")]
    offs = [int(c[1:]) for c in off_cols]
    labs = sorted(assign["cluster_label"].unique())
    ncol = min(4, len(labs))
    nrow = int(np.ceil(len(labs) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.2 * ncol, 3.8 * nrow), squeeze=False)
    colors = {"price": "#c0392b", "volume": "#1f4e79"}
    for i, lab in enumerate(labs):
        ax = axes[i // ncol][i % ncol]
        g = cur[cur["cluster_label"] == lab]
        name = assign[assign["cluster_label"] == lab]["cluster_name"].iloc[0]
        for _, r in g.iterrows():
            v = np.nan_to_num(r[off_cols].to_numpy(dtype=float), nan=0.0)
            ax.plot(offs, v, lw=1.3, alpha=0.85, color=colors[r["response"]],
                    ls="-" if r["response"] == "price" else "--",
                    label=None if i else None)
        ax.axhline(0, color="#333", lw=0.7)
        ax.axvspan(0, 14, color="#f2f2f2", zorder=0)
        ax.set_title(f"簇 {lab}｜{name}\n(n={len(g)} 条曲线)", fontsize=10)
        ax.set_xlabel("相对事件开始的偏移（天）")
        if i % ncol == 0:
            ax.set_ylabel("事件相对化异常（稳健 z）")
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], color="#c0392b", lw=1.6, label="价格指纹"),
               Line2D([0], [0], color="#1f4e79", lw=1.6, ls="--", label="成交量指纹")]
    fig.legend(handles=handles, loc="upper right", fontsize=9, ncol=2)
    fig.suptitle(f"图{tag}　冲击指纹聚类：品种×响应的雨事件平均响应曲线（T{CURVE_LO:+d}..T+{CURVE_HI}）\n"
                 f"Ward 层次聚类（K={k} 由 silhouette={sil:.2f} 事后选择）；"
                 "类别名为事后按曲线特征命名（§四十二：禁止预分5类）",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；事件=ERA5 派生（8 个清洁雨簇，"
                  "STEP 12 主分析口径）。曲线=簇均值 z_rel；灰带=事件后窗。")


def fig_resilience(res: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.4))
    for ax, (var, vlabel) in zip(axes, VARS):
        d = res[(res["response"] == var) & (~res["censored"])]
        med = d.groupby("crop")["recovery_days"].median().reindex(CORE_CROPS)
        shock = d.groupby("crop")["shock_magnitude"].median().reindex(CORE_CROPS)
        cens = res[(res["response"] == var) & (res["censored"])].groupby("crop").size().reindex(CORE_CROPS).fillna(0)
        x = np.arange(len(med))
        sc = ax.scatter(shock, med, s=70, color="#1f4e79", zorder=3)
        for crop in CORE_CROPS:
            if np.isfinite(shock[crop]) and np.isfinite(med[crop]):
                ax.annotate(f"{crop}{'*' * int(cens[crop] > 0)}",
                            xy=(shock[crop], med[crop]), fontsize=8.5,
                            xytext=(5, 4), textcoords="offset points")
        ax.axvline(0, color="#333", lw=0.8)
        ax.axhline(0, color="#333", lw=0.8)
        ax.set_xlabel("冲击深度（事件后 z_rel 中位谷底）")
        ax.set_ylabel("恢复天数中位（谷底→恢复线）")
        ax.set_title(f"{vlabel}：冲击 vs 恢复（事件×品种散点，中位数投影）")
        ax.text(0.98, 0.03, "*=部分事件 42 天未恢复（删失）", transform=ax.transAxes,
                ha="right", va="bottom", fontsize=8.5, color="#555")
    fig.suptitle(f"图{tag}　市场韧性指标（§四十三）：冲击深度 vs 恢复速度\n"
                 f"恢复线 = {RECOVERY_FRAC:.0%}×谷底（z_rel 口径，显式公式见报告）；"
                 "指标分别展示、不做综合指数（§四十四）",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；事件=8 个清洁雨簇。"
                  "每个点=一个品种在全部事件上的中位数；单事件指标见 resilience_event_crop.csv。")


# -----------------------------------------------------------------------------
# 报告
# -----------------------------------------------------------------------------
def write_report(profile, cur, assign, k, sil, res, res_sum) -> None:
    L: list = []
    A = L.append
    A("# 09 CROP HETEROGENEITY — 品种风险画像、冲击指纹与市场韧性（STEP 18-20）\n")
    A("> 事件口径 = 8 个清洁雨簇（STEP 12 主分析）；响应 = 事件相对化稳健 z；"
      "窗口：指纹 T-7..T+14，韧性谷底搜索 T+0..T+21，恢复观察至 T+42。\n")
    A("> 证据等级：**Level B（描述性）**。品种共享同一组事件冲击，所有品种间对比均为"
      "异质性描述，不做显著性判定；不构造综合指数（§四十四）。\n")

    A("## 1. 品种风险画像（§四十一，crop_risk_profile.csv）\n")
    A("| 品种 | 天气敏感度(hazard, 效应) | 显著性 | 最大量冲击 | 最大价冲击 | 峰值lag | "
      "恢复天数中位 | 波动率(量/价 z) | 阈值(量/价) |")
    A("|---|---|---|---|---|---|---|---|---|")
    for _, r in profile.iterrows():
        A(f"| {r['crop']} | {r['weather_sensitivity_hazard']}, "
          f"{r['weather_sensitivity_effect']:+.3f} | {r['weather_sensitivity_sig']} | "
          f"{r['max_volume_shock_mean']:+.2f} | {r['max_price_shock_mean']:+.2f} | "
          f"T+{r['peak_lag_days']} | {r['recovery_days_median']:.0f} | "
          f"{r['volatility_volume_z']:.2f}/{r['volatility_price_z']:.2f} | "
          f"{r['threshold_volume']}/{r['threshold_price']} |")
    A("")
    A("- weather_sensitivity = STEP 10 中该品种 0-14 天内 |效应| 最大的 hazard（全部 FDR 不显著，"
      "画像仅作相对排序参考）；")
    A("- threshold 列沿用 STEP 11 结论：全部「无支持」，故画像不含任何数值阈值。\n")

    A("## 2. 冲击指纹聚类（§四十二）\n")
    A(f"- 聚类对象：10 品种 × 2 响应 = **{len(cur)} 条**雨事件平均响应曲线"
      f"（T{CURVE_LO:+d}..T+{CURVE_HI}，22 维）；Ward 层次聚类，K 由 silhouette 事后选择："
      f"**K={k}（silhouette={sil:.2f}）**；")
    A("| 簇 | 事后命名（依据曲线特征） | 成员数 | 成员 | 量谷底 | 价谷底 |")
    A("|---|---|---|---|---|---|")
    for _, r in assign.iterrows():
        vt = r.get("volume_trough")
        pt = r.get("price_trough")
        vt_s = f"{vt:+.2f}" if np.isfinite(vt) else "—"
        pt_s = f"{pt:+.2f}" if np.isfinite(pt) else "—"
        A(f"| {int(r['cluster_label'])} | {r['cluster_name']} | {int(r['n_curves'])} | "
          f"{r['members']} | {vt_s} | {pt_s} |")
    A("")
    # 谷深对比（数据驱动，不预设立场）
    vt_med = assign["volume_trough"].dropna()
    pt_med = assign["price_trough"].dropna()
    deeper = "成交量" if (len(vt_med) and len(pt_med) and vt_med.mean() < pt_med.mean()) else "价格"
    A("- 命名规则（预登记于代码）：按簇内量/价曲线均值的**事后谷深**"
      "（|z_rel|>0.5 深谷、0.25-0.5 浅谷、<0.25 平稳）描述性命名，**非预设五类**（§四十二 红线）；")
    A(f"- 谷深对比（簇均值，数据驱动）：{deeper}指纹的事后谷更深"
      + (f"（量 {vt_med.mean():+.2f} vs 价 {pt_med.mean():+.2f}）" if len(vt_med) and len(pt_med) else "")
      + "；簇结构主要区分「多数品种的浅谷形态」与个别深谷指纹；")
    A("- 曲线明细见 `fingerprint_curves.csv`（可复算距离矩阵）。\n")

    A("## 3. 市场韧性指标（§四十三）\n")
    A("恢复定义（显式公式）：事件后 z_rel(t) ≥ 0.9 × trough_z 视为恢复"
      "（即回到冲击深度的 90%）；谷底在 T+0..T+21 内搜索；T+42 未恢复记删失。\n")
    A("| 品种 | 量冲击中位 | 量谷底offset中位 | 量恢复天数中位 | 量删失事件数 | "
      "价冲击中位 | 价恢复天数中位 | 价删失 |")
    A("|---|---|---|---|---|---|---|---|")
    for crop in CORE_CROPS:
        rv = res_sum[(res_sum["crop"] == crop) & (res_sum["response"] == "volume")].iloc[0]
        rp = res_sum[(res_sum["crop"] == crop) & (res_sum["response"] == "price")].iloc[0]
        A(f"| {crop} | {rv['shock_magnitude']:+.2f} | T+{rv['trough_offset']:.0f} | "
          f"{rv['recovery_days']:.0f} | {int(rv['censored'])}/{int(rv['n_events'])} | "
          f"{rp['shock_magnitude']:+.2f} | {rp['recovery_days']:.0f} | "
          f"{int(rp['censored'])}/{int(rp['n_events'])} |")
    A("")
    cens_v = int(res[(res["response"] == "volume")]["censored"].sum())
    cens_p = int(res[(res["response"] == "price")]["censored"].sum())
    A(f"- 删失（42 天未恢复）：量 {cens_v}/{len(res[res['response']=='volume'])}、"
      f"价 {cens_p}/{len(res[res['response']=='price'])} 个事件×品种——"
      "大量删失说明「恢复」在事件接续的现实市场中难以干净观测（事件常被后续事件打断）；")
    A("- 按 §四十四：**不构造 Resilience Score**。若未来需要综合指标，必须先给出公式、"
      "指标解释、标准化方案与权重敏感性检验；当前分别展示五个指标。\n")

    A("## 4. 图表清单\n")
    A("| 图 | 内容 |")
    A("|---|---|")
    A("| 图32 `F32_fingerprint_clusters.png` | 冲击指纹曲线按簇分面 |")
    A("| 图33 `F33_resilience_scatter.png` | 冲击深度 vs 恢复天数（量/价） |")
    A("")

    A("## 5. 本节结论（Level B，描述性）\n")
    A("- 画像核心事实：**全部品种的天气敏感度均未通过 FDR**、**无品种存在可支持的阈值**；"
      "品种排序仅为描述性参考，不得用于「哪些菜风险更大」的结论性表述；")
    A("- 指纹聚类：K=2 由数据选择；**黄瓜·价格指纹独立成簇**（历史 8 个清洁雨簇的平均谷底"
      " z=-1.18，T+9），其余 19 条曲线均为浅谷平稳形态——与 STEP 12 逐品种表"
      "（黄瓜价格谷底 T+2/-1.18）和 STEP 13 案例观察（2026-07 黄瓜价格 +3.44）方向一致，"
      "是本研究中最一致的品种异质性信号（仍为描述性，n=8 事件、单品种）；")
    A("- 韧性：恢复指标删失率高（量 11/80、价 17/80）、事件接续污染"
      "（与 STEP 13 E 节同一限制），恢复天数只能作量级参考；")
    A("- H4（不同蔬菜响应不同）：以「响应深度/形态存在品种间差异但无统计检验支持」的"
      "**描述性支持**记录；黄瓜的价格响应形态是唯一跨口径一致的例外，"
      "可作为 H6/品种韧性排序的候选线索，不得写成因果结论。\n")

    pth = PATHS.report("09_CROP_HETEROGENEITY.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("作物异质性报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("11_crop_heterogeneity", LOG):
        panel = load_parquet("panel_final")
        panel = panel[(panel["date"] <= CORE_END) & (panel["crop"].isin(CORE_CROPS))].copy()

        cl = load_clean_clusters()
        LOG.info("清洁雨簇 %d 个", len(cl))
        er = event_responses(panel, cl)
        save_table(er, "fingerprint_event_responses.csv")

        # STEP 19 指纹
        cur, assign, k, sil = fingerprint(er)
        assign = name_clusters(assign)
        save_table(cur, "fingerprint_curves.csv")
        save_table(assign, "fingerprint_clusters.csv")
        LOG.info("指纹聚类：K=%d（silhouette=%.3f），%d 条曲线", k, sil, len(cur))

        # STEP 20 韧性
        res = resilience(er)
        save_table(res, "resilience_event_crop.csv")
        res_sum = (res.groupby(["crop", "response"])
                   .agg(shock_magnitude=("shock_magnitude", "median"),
                        trough_offset=("trough_offset", "median"),
                        price_shock=("price_shock", "median"),
                        recovery_days=("recovery_days", "median"),
                        recovery_slope=("recovery_slope_z_per_day", "median"),
                        censored=("censored", "sum"),
                        n_events=("cluster", "nunique"))
                   .reset_index())
        save_table(res_sum, "resilience_summary.csv")

        # STEP 18 画像
        profile = crop_risk_profile(panel, er, res, assign)
        save_table(profile, "crop_risk_profile.csv")

        fig_fingerprint(cur, assign, k, sil, "F32_fingerprint_clusters.png", "32")
        fig_resilience(res, "F33_resilience_scatter.png", "33")

        write_report(profile, cur, assign, k, sil, res, res_sum)

        # ---- 结果登记 -------------------------------------------------------
        rows = [{
            "result_id": "HET-PROFILE-ALL",
            "research_question": "RQ5", "crop": "全体10品种",
            "period": f"{cl['t0'].min():%Y-%m-%d}~{cl['t0'].max():%Y-%m-%d}",
            "method": "品种风险画像聚合（STEP 10 敏感度 + STEP 11 阈值 + 事件冲击 + 韧性指标）",
            "metric": "画像级判定", "estimate": None, "ci_low": None, "ci_high": None,
            "p_value": None,
            "robustness": "全部品种敏感度 FDR 不显著；阈值全部无支持；共享冲击无统计检验",
            "figure": "F32_fingerprint_clusters.png", "table": "crop_risk_profile.csv",
            "evidence_level": "B",
            "notes": "H4 描述性支持（响应深度/形态有品种差异，无统计检验支持）；"
                     "指纹聚类 K 由 silhouette 事后选择；§四十四 不做综合指数",
        }]
        register_results(rows)
        LOG.info("结果登记 %d 条", len(rows))


if __name__ == "__main__":
    main()
