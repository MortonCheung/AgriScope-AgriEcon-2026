"""22_district_studies.py — A07 区县农业结构 / A08 区县面板（v2 重新计算）。

预注册对应：plan/analysis_plan.yaml 的 A07 / A08。
A08 主结局 = 单产（log）；次要 = 总产量；每模型仅 1-2 个核心暴露；
小样本推断：district-cluster SE + leave-one-district-out + leave-one-year-out + wild cluster bootstrap；
多重检验：family = crop × exposure，BH-FDR，同时报告 raw p 与 q。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v2
from _v2 import (ALPHA, DATA, DISTRICTS, append_claims, bh_fdr, cluster_ols, get_logger,
                 metrics_dump, save_fig, save_table, setup_plt, wild_cluster_bootstrap)

LOG = get_logger("22_district_studies")
CORE_CROPS = ["粮食", "谷物", "稻谷", "玉米", "豆类", "大豆", "蔬菜及食用菌", "瓜果", "甜瓜"]
EXPOSURES = ["growing_season_temp_mean", "growing_season_precip", "max_1d_precip",
             "heavy_rain_days", "vpd_mean", "et0_sum"]
YEAR_FE = True


def load():
    d = pd.read_parquet(DATA / "v2_district_yearly.parquet")
    d = d[(~d["is_supplement"]) & (d["year"].between(2018, 2024))].copy()
    return d


def A07(d, log):
    log.info("A07 区县农业结构（2018-2024，描述性）")
    # 区县 × 作物 覆盖与水平
    rows = []
    for crop in CORE_CROPS:
        g = d[d["crop"] == crop]
        for dist, gd in g.groupby("district"):
            rows.append({"crop": crop, "district": dist,
                         "years": int(gd["sown_area"].notna().sum()),
                         "sown_area_median_ha": gd["sown_area"].median(),
                         "production_median_t": gd["production"].median(),
                         "yield_median_kg_ha": gd["yield_value"].median()})
    cov = pd.DataFrame(rows)
    save_table(cov, "A07_district_crop_structure.csv")

    # 区县合计（仅主粮，排除层级嵌套：只用「粮食」总量，不与 谷物/稻谷/玉米 相加）
    tot = (d[d["crop"] == "粮食"].groupby("district")
           .agg(area_median=("sown_area", "median"),
                prod_median=("production", "median"),
                yield_median=("yield_value", "median"),
                years=("year", "nunique")).reset_index())
    save_table(tot, "A07_district_grain.csv")

    # 年际变化（2018 → 2024，仅两端可观测年份）
    chg = []
    for crop in CORE_CROPS:
        for dist, gd in d[d["crop"] == crop].groupby("district"):
            a = gd[gd["year"] == 2018]["sown_area"]
            b = gd[gd["year"] == 2024]["sown_area"]
            pa = gd[gd["year"] == 2018]["production"]
            pb = gd[gd["year"] == 2024]["production"]
            if len(a) and len(b) and a.iloc[0] and b.iloc[0]:
                chg.append({"crop": crop, "district": dist,
                            "area_2018": a.iloc[0], "area_2024": b.iloc[0],
                            "area_chg_pct": (b.iloc[0] / a.iloc[0] - 1) * 100,
                            "prod_2018": pa.iloc[0] if len(pa) else np.nan,
                            "prod_2024": pb.iloc[0] if len(pb) else np.nan,
                            "prod_chg_pct": (pb.iloc[0] / pa.iloc[0] - 1) * 100 if len(pa) and len(pb) and pa.iloc[0] else np.nan})
    C = pd.DataFrame(chg)
    save_table(C, "A07_change_2018_2024.csv")

    plt = setup_plt()
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    for ax, (crop, col, unit) in zip(axes, [("粮食", "sown_area_median_ha", "公顷"),
                                            ("粮食", "production_median_t", "吨"),
                                            ("粮食", "yield_median_kg_ha", "公斤/公顷")]):
        s = cov[(cov.crop == crop)].set_index("district")[col].reindex(DISTRICTS)
        ax.bar(s.index, s.values, color=_v2.C_MAIN)
        ax.set_title(f"粮食：{col.replace('_median','')}")
        ax.set_ylabel(unit)
        ax.tick_params(axis="x", rotation=60, labelsize=8)
    fig.suptitle("图 A07-1 沈阳 8 个农业区县粮食生产结构（2018-2024 中位数）")
    save_fig(fig, "A07_district_structure.png")
    log.info("  结构：%d 个 区县×作物 组合；粮食面积中位 %.0f–%.0f 公顷",
             len(cov), tot["area_median"].min(), tot["area_median"].max())
    return cov, tot, C


def _fe_design(g, expo):
    """year FE + district FE + 暴露（每模型仅 1 个核心暴露）。返回 X, 列名, groups。"""
    df = g.dropna(subset=["log_yield", expo, "district", "year"]).copy()
    if len(df) < 20:
        return None
    D = pd.get_dummies(df["district"], prefix="d", drop_first=True).astype(float)
    Y = pd.get_dummies(df["year"], prefix="y", drop_first=True).astype(float)
    X = pd.concat([df[[expo]].astype(float), D, Y], axis=1)
    return df, X, df["district"].to_numpy()


def A08(d, log):
    log.info("A08 区县面板（主结局=log 单产；district+year FE；每模型 1 个暴露）")
    rows, wcb_rows = [], []
    for crop in CORE_CROPS:
        g = d[d["crop"] == crop].copy()
        g = g[np.isfinite(pd.to_numeric(g["yield_value"], errors="coerce"))]
        g["log_yield"] = np.log(g["yield_value"])
        for expo in EXPOSURES:
            if expo not in g.columns:
                continue
            r = _fe_design(g, expo)
            if r is None:
                continue
            df, X, grp = r
            res = cluster_ols(df["log_yield"].to_numpy(float), X.to_numpy(float), grp)
            # 暴露是 X 的第 0 列
            rows.append({"crop": crop, "outcome": "log_yield", "exposure": expo,
                         "beta": float(res["coef"][0]), "se_cluster": float(res["se"][0]),
                         "t": float(res["t"][0]), "p_raw": float(res["p"][0]),
                         "n": res["n"], "n_clusters": res["n_clusters"], "r2": res["r2"],
                         "ci_low": float(res["coef"][0]) - 1.96 * float(res["se"][0]),
                         "ci_high": float(res["coef"][0]) + 1.96 * float(res["se"][0])})
            # wild cluster bootstrap（仅对核心 3 个暴露，控制运行时间）
            if expo in ("growing_season_temp_mean", "growing_season_precip", "max_1d_precip",
                        "heavy_rain_days"):
                w = wild_cluster_bootstrap(df["log_yield"].to_numpy(float),
                                           X.to_numpy(float), grp, j=0, n_boot=299)
                wcb_rows.append({"crop": crop, "exposure": expo, "t_stat": w["t_stat"],
                                 "p_wild_boot": w["p_boot"], "n_clusters": w["n_clusters"]})
    R = pd.DataFrame(rows)
    R["q_fdr"] = np.nan
    for e, gg in R.groupby("exposure"):                     # family = crop × exposure（按暴露分家族）
        R.loc[gg.index, "q_fdr"] = bh_fdr(gg["p_raw"].to_numpy())
    save_table(R, "A08_panel_results.csv")
    W = pd.DataFrame(wcb_rows)
    if len(W):
        save_table(W, "A08_wild_bootstrap.csv")

    # 稳健性：leave-one-district-out / leave-one-year-out（对通过 FDR 的项）
    robust = []
    sig = R[R["q_fdr"] < ALPHA]
    for _, sr in sig.iterrows():
        crop, expo = sr["crop"], sr["exposure"]
        g = d[d["crop"] == crop].copy()
        g["log_yield"] = np.log(pd.to_numeric(g["yield_value"], errors="coerce"))
        for mode in ("lodo", "loyo"):
            vals = []
            keys = DISTRICTS if mode == "lodo" else sorted(g["year"].unique())
            for k in keys:
                gg = g[g["district"] != k] if mode == "lodo" else g[g["year"] != k]
                r = _fe_design(gg, expo)
                if r is None:
                    continue
                df2, X2, grp2 = r
                try:
                    rr = cluster_ols(df2["log_yield"].to_numpy(float), X2.to_numpy(float), grp2)
                    vals.append(float(rr["coef"][0]))
                except Exception:  # noqa: BLE001
                    continue
            if vals:
                robust.append({"crop": crop, "exposure": expo, "mode": mode,
                               "beta_full": sr["beta"], "beta_min": float(np.min(vals)),
                               "beta_max": float(np.max(vals)),
                               "same_sign": bool(np.all(np.sign(vals) == np.sign(sr["beta"]))),
                               "n_loo": len(vals)})
    RB = pd.DataFrame(robust)
    if len(RB):
        save_table(RB, "A08_robustness_loo.csv")

    n_sig = int((R["q_fdr"] < ALPHA).sum())
    log.info("  A08：%d 项检验（%d 作物 × %d 暴露）；FDR 后显著 %d", len(R),
             R["crop"].nunique(), R["exposure"].nunique(), n_sig)
    if n_sig:
        log.info("  %s", R[R.q_fdr < ALPHA].round(4).to_string(index=False))
    return R, W, RB


def main() -> None:
    log = get_logger("22_district_studies")
    log.info("=" * 70)
    d = load()
    log.info("区县主样本：%d 行；%d 区县；%s", len(d), d["district"].nunique(),
             sorted(d["year"].unique()))
    cov, tot, C = A07(d, log)
    R, W, RB = A08(d, log)

    claims = []
    g24 = tot.set_index("district")["area_median"]
    claims.append(dict(claim_id="C-A07-STRUCT", study_id="A07",
                       claim_text=f"沈阳 8 个农业区县 2018-2024 粮食播种面积中位数介于 "
                                  f"{g24.min():.0f}（{g24.idxmin()}）与 {g24.max():.0f}（{g24.idxmax()}）公顷之间",
                       claim_type="descriptive", evidence_id="EV-A07-STRUCT",
                       source_ids="SRC-SY-YB", table_id="A07_district_grain.csv",
                       figure_id="A07_district_structure.png", estimate=f"{g24.min():.0f}–{g24.max():.0f}",
                       sample_size=int(len(d)), method_id="district_structure", status="descriptive_only"))
    n_sig = int((R["q_fdr"] < ALPHA).sum())
    claims.append(dict(claim_id="C-A08-PANEL", study_id="A08",
                       claim_text=f"区县面板（log 单产 ~ 生长季气象 + district FE + year FE）共 {len(R)} 项"
                                  f"（crop × exposure），district-cluster SE 下 BH-FDR 后显著 {n_sig} 项",
                       claim_type="association", evidence_id="EV-A08-PANEL",
                       source_ids="SRC-SY-YB;SRC-OM-ERA5", table_id="A08_panel_results.csv",
                       estimate=f"{n_sig}/{len(R)}", p_raw=float(R["p_raw"].min()),
                       p_adjusted=float(R["q_fdr"].min()), sample_size=int(R["n"].sum()),
                       method_id="panel_fe_cluster_district",
                       status="not_supported" if n_sig == 0 else "partly_supported"))
    if len(W):
        claims.append(dict(claim_id="C-A08-WCB", study_id="A08",
                           claim_text=f"wild cluster bootstrap（Rademacher，299 次）对 {len(W)} 项核心检验给出 "
                                      f"p 中位数 {float(W['p_wild_boot'].median()):.3f}；"
                                      f"结论：8 个聚类下常规 cluster SE 的精确性有限，须并列报告",
                           claim_type="methods", evidence_id="EV-A08-WCB",
                           source_ids="SRC-SY-YB;SRC-OM-ERA5", table_id="A08_wild_bootstrap.csv",
                           estimate=f"median p={float(W['p_wild_boot'].median()):.3f}",
                           p_adjusted=float(W["p_wild_boot"].median()), sample_size=int(len(W)),
                           method_id="wild_cluster_bootstrap",
                           status="descriptive_only"))
    append_claims(claims)
    metrics_dump("A08_summary.json", {"n_tests": int(len(R)), "n_fdr_sig": n_sig,
                                      "exposures": EXPOSURES, "crops": CORE_CROPS,
                                      "n_clusters": int(R["n_clusters"].max()),
                                      "note": "8 clusters：不得假装足够精确；wild bootstrap 已并列报告"})
    log.info("已登记 %d 条 claim", len(claims))
    log.info("完成")


if __name__ == "__main__":
    main()
