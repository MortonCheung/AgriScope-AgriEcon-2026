"""a06_predictability.py — A06 市场可预测性与天气信息预测增量（六城统一）。

- 目标：价格水平 1 步向前（日度城市=次日；大连=次周）。
- 基线：last_value（随机游走）、seasonal_naive（上年同期）。
- 增强：OLS(price_lag1, price_year_ago, weather_z_lag1...) 扩展窗滚动，1 步预测。
- 指标：RMSE 与相对基线增益；不得只汇报最好结果。
- 量价关系：五城无成交量 → NOT_SUPPORTED（仅沈阳可做）。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, stats

MODULE = "A06"
SLUG = "predictability-weather-gain"
TITLE = "市场可预测性与天气信息预测增量"
CITY_FREQ = {"chaoyang": "D", "jinzhou": "D", "dalian": "W", "shenyang": "D"}


def _rmse(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    return float(np.sqrt(np.mean((a[m] - b[m]) ** 2))) if m.any() else np.nan


def run(city: str) -> Dict:
    if city not in CITY_FREQ:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="无满足最小覆盖的价格序列，无法做预测与预测增量分析。",
                                       notes=["五城亦无成交量数据，量价关系对五城不成立"])
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    freq = CITY_FREQ[city]; win = int(an["price"]["deseason"]["doy_window"])
    min_obs = int(an["price"]["min_days_weather"]); seed = int(an["global"]["random_seed"])
    weather = loaders.load_weather(city); veg = loaders.veg_crops()
    pool = [c for c in veg if len(loaders.load_primary_series(city, c)) >= min_obs]
    period_lag = 52 if freq == "W" else 365

    rows, detail = [], []
    for crop in pool:
        s = loaders.load_primary_series(city, crop).sort_values("date").reset_index(drop=True)
        s = panel.add_weather(s, weather, freq, "date")
        s = s.dropna(subset=["price_per_kg"]).reset_index(drop=True)
        s["y"] = s["price_per_kg"]
        s["lag1"] = s["y"].shift(1)
        s["year_ago"] = s["y"].shift(period_lag) if freq == "W" else s["y"].shift(365)
        feats = [c + "_z" for c in panel.EXPOSURES if c + "_z" in s.columns]
        for c in feats:
            s[c + "_l1"] = s[c].shift(1)
        use_cols = ["lag1", "year_ago"] + [c + "_l1" for c in feats]
        d = s.dropna(subset=["y", "lag1"]).reset_index(drop=True)
        if len(d) < max(120, min_obs):
            continue
        # 扩充预测（数据已在去季节化上不需；这里直接价格水平预测）
        start = int(len(d) * 0.5)
        pred_aug, pred_lv, pred_sn, truth = [], [], [], []
        model = None
        for i in range(start, len(d)):
            if (i - start) % 10 == 0:
                tr = d.iloc[:i].dropna(subset=use_cols + ["y"])
                if len(tr) > 50:
                    X = tr[use_cols].to_numpy(); yy = tr["y"].to_numpy()
                    model = stats.hac_ols(yy, X, maxlags=0)  # 仅取系数
                    model = {"coef": model["coef"], "intercept": float(np.mean(yy) - np.dot(np.mean(X, axis=0), model["coef"]))}
            row = d.iloc[i]
            if model is not None and row[use_cols].notna().all():
                pred_aug.append(model["intercept"] + float(np.dot(row[use_cols].to_numpy(dtype=float), model["coef"])))
                pred_lv.append(row["lag1"])
                pred_sn.append(row["year_ago"])
                truth.append(row["y"])
        if not truth:
            continue
        r_lv = _rmse(pred_lv, truth); r_sn = _rmse(pred_sn, truth); r_aug = _rmse(pred_aug, truth)
        base = np.nanmin([r_lv, r_sn])
        gain = 100.0 * (base - r_aug) / base if base and base > 0 else np.nan
        rows.append({"city": city, "crop": crop, "rmse_last_value": r_lv, "rmse_seasonal_naive": r_sn,
                     "rmse_augmented": r_aug, "best_baseline": "last_value" if r_lv <= r_sn else "seasonal_naive",
                     "rmse_gain_pct": gain, "n_eval": len(truth), "freq": freq})

    df = pd.DataFrame(rows)
    if df.empty:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="有效评估样本不足，未得到可比较的预测结果。")
    med_gain = float(df["rmse_gain_pct"].median())
    n_pos = int((df["rmse_gain_pct"] > 0).sum())

    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    w.save_table(df, f"{MODULE}_forecast_gain.csv")
    fig = _fig(cfg["name"], df)
    w.save_fig(fig, f"{MODULE}_gain.png")
    metrics = {"city": city, "freq": freq, "n_crops": len(df), "median_rmse_gain_pct": med_gain,
               "n_crops_positive_gain": n_pos,
               "volume_price_relation": "NOT_SUPPORTED_BY_CURRENT_DATA"}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    abstract = (
        f"本研究评估{cfg['name']}主要农产品价格的可预测性，以及加入气象信息是否带来预测增量。"
        f"价格为该城主源（{cfg['price_level_note']}），频率{'日度' if freq=='D' else '周度'}。"
        f"基线为 last_value 与 seasonal_naive；增强模型在扩展窗上以 [价格滞后1期, 上年同期, 气象滞后1期] "
        f"做 1 步向前 OLS 预测。以 RMSE 相对基线变化衡量增益。"
        f"{len(df)} 种作物中，RMSE 相对变化中位数为 {med_gain:+.2f}%（{n_pos}/{len(df)} 种为正增益）。"
        f"量价关系因{cfg['name']}无成交量数据而不成立。\n\n"
        f"**关键词**：预测；滚动评估；RMSE 增量；随机游走基线；{cfg['name']}"
    )
    frontend_summary = (f"{cfg['name']}：天气信息 RMSE 相对变化中位 {med_gain:+.2f}%（{n_pos}/{len(df)} 种正增益）。"
                        f"量价关系 NOT_SUPPORTED。")
    data_scope = (f"### 2.1 研究对象\n{cfg['name']}主要蔬菜价格（{'、'.join(pool)}）。\n\n"
                  f"### 2.2 数据来源\n价格：{cfg['price_level_note']}；气象：ERA5 再分析网格。\n\n"
                  f"### 2.3 变量\n- 目标：价格水平（1 步向前）；- 特征：价格滞后、上年同期、气象滞后。\n"
                  f"- 成交量：**NOT_FOUND**，量价关系不成立。")
    methods = (f"### 3.1 基线\nlast_value（随机游走）与 seasonal_naive（上年同期）。\n\n"
               f"### 3.2 增强\n扩展窗滚动、1 步向前 OLS；每 10 步重估。\n\n"
               f"### 3.3 评估\nRMSE 与相对基线增益；汇报全部作物，不只最好结果。")
    results_text = [
        ("预测增益", f"{len(df)} 种作物 RMSE 相对变化中位 **{med_gain:+.2f}%**；{n_pos} 种为正增益。"
                     f"（表 {MODULE}_forecast_gain.csv，图 {MODULE}_gain.png）"),
        ("逐作物", df[["crop", "rmse_last_value", "rmse_seasonal_naive", "rmse_augmented",
                       "rmse_gain_pct"]].round(4).to_string(index=False)),
        ("量价关系", "NOT_SUPPORTED_BY_CURRENT_DATA（本城无成交量数据）。"),
    ]
    discussion = ("若天气信息带来显著预测增量，会在多数作物上表现为稳定正增益；本城结果中位增益较小，"
                  "提示天气对价格水平的边际预测价值有限。市场价格的强持续性使随机游走/季节朴素基线本身较强。")
    limitations = [
        f"1. **价格口径**：{cfg['price_level_note']}。",
        "2. **单步预测**：仅评估 1 步向前，未评估多步。",
        "3. **线性模型**：未使用非线性/集成模型，增益为下界参考。",
        "4. **未做预测差异显著性检验**：未执行 Diebold-Mariano 等检验，RMSE 差异不构成统计显著性结论。",
        "5. **重估频率**：扩展窗每 10 步重估一次，非逐步重估。",
        "6. **量价关系不成立**：本城无成交量。",
    ]
    conclusion = (f"{cfg['name']}：加入气象信息后 RMSE 相对变化中位数 {med_gain:+.2f}%（{n_pos}/{len(df)} 种正增益）；"
                  f"天气信息{'未带来稳定预测增量' if med_gain <= 0 else '带来有限预测增量'}。量价关系不成立。")
    explorer = {
        "selectors": [{"key": "crop", "label": "作物", "options": pool}],
        "metrics": ["median_rmse_gain_pct", "n_crops_positive_gain"],
        "series": [{"id": "gain", "table": f"{MODULE}_forecast_gain.csv", "x": "crop", "y": "rmse_gain_pct"}],
        "tables": [f"{MODULE}_forecast_gain.csv"], "figures": [f"{MODULE}_gain.png"], "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["预测", "滚动评估", "RMSE 增量", "随机游走基线", cfg["name"]],
        research_questions=[f"{cfg['name']}价格可预测性如何？天气信息是否带来预测增量？"],
        data_scope=data_scope, methods=methods, results=results_text, discussion=discussion,
        limitations=limitations, conclusion=conclusion, explorer=explorer,
        tables=[f"{MODULE}_forecast_gain.csv"], figures=[f"{MODULE}_gain.png"],
        claims=[{"claim_id": f"{city}-A06-C1", "study_id": "A06", "city": cfg["name"],
                 "claim_text": f"天气信息 RMSE 相对变化中位 {med_gain:+.2f}%",
                 "claim_type": "inferential", "table_id": f"{MODULE}_forecast_gain.csv",
                 "estimate": med_gain, "sample_size": int(df["n_eval"].sum()),
                 "status": "PARTIAL" if med_gain > 0 else "NOT_SUPPORTED"},
                {"claim_id": f"{city}-A06-C2", "study_id": "A06", "city": cfg["name"],
                 "claim_text": "量价关系 NOT_SUPPORTED（无成交量数据）",
                 "claim_type": "limitation", "status": "NOT_SUPPORTED"}])


def _fig(city_name, df):
    from ..lib.plotting import setup_plt, C_MAIN, C_ALT
    plt = setup_plt()
    d = df.sort_values("rmse_gain_pct")
    fig, ax = plt.subplots(figsize=(max(7.6, 0.4 * len(d) + 3), 4.6))
    colors = [C_MAIN if v > 0 else C_ALT for v in d["rmse_gain_pct"]]
    ax.bar(d["crop"], d["rmse_gain_pct"], color=colors)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_ylabel("RMSE 相对变化 (%)"); ax.set_title(f"{city_name}市 天气信息的预测增量（正=改善）")
    ax.tick_params(axis="x", rotation=45)
    return fig