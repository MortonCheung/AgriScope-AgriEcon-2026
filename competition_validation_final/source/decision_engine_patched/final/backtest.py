# -*- coding: utf-8 -*-
"""F12-F14: Final 推荐策略 + 历史回测 + Balanced 根因诊断与修复。

设计原则（诚实性优先）：
  - 沈阳 10 蔬菜的「成本/亩产」在 model_ready 中只有零散 RESEARCH_REFERENCE/proxy，
    不足以支撑真实利润点估计（§11/§26）→ 主指标改用**真实价格结果**：
        realized_return = 未来 h 天窗口均价 / 建仓时点价 - 1（无成本/亩产假设）
        realized_downside = 未来 h 天窗口最低价 / 建仓时点价 - 1
  - 预测值来自 Final Price Model 的严格 OOT 预测（selected model per crop）；
  - HRI / Market Risk 来自 Final 单层价格派生指标（as_of 时点可得）；
  - 策略：Balanced(原) / Balanced(修) / Profit-only / Risk-only / Chase-price / Seasonal / Random / Most-Robust；
  - 指标：平均/中位收益、downside、worst、max drawdown、high-HRI 选中率、win rate、regret、稳定性。

======================================================================
experiments 分支修复记录（P0，详见 experiments/code/FIXES.md）
  [P0-3] `_seasonal_pick` 原实现算了同月历史均价 `best` 却未取 `best.idxmax()`，
         改为「同月历史已成熟相对收益均值最高」的可核验季节基线。
  [P0-4] `strategy_scores` 原以**跨作物绝对价格水平**排序（s_profit=forecast、
         s_chase=anchor_price），跨品种不可比。改为以 `predicted_return
         = forecast/anchor_price - 1` 为收益分量；绝对价格水平单列为
         `Highest_price_level` 并明确其语义限制；`Profit_only` 更名为
         `Highest_forecast_return`（禁止再称“真实利润最优”）。
  [P0-5a] 原 `run_backtest(cutoff_step_days=7)` 定义了 `step` 却从未使用，
         实际遍历全部交易日 → 相邻切点未来 30 天窗口高度重叠，665+ 切点被
         当成独立实验。新增 `_select_cutoffs` 真正按步长抽稀（并支持非重叠 30 天）。
  [P0-5b] `Random` 原用 Python 内建 `hash(str(t))`（受 PYTHONHASHSEED 影响，
         跨进程不可复现）且每切点只抽 1 次。改为确定性 `_cutoff_seed` 单次抽取
         + `Random_expectation`（均匀随机选择的解析期望＝池内均值）。
======================================================================
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from decision_engine.final.fcommon import (SNAPSHOT_DIR, FINAL_EVAL_DIR, REPORTS_DIR,
                                           ensure_dir, write_json, now_stamp)
from decision_engine.final.risk import daily_prices, weekly_prices, hri_components, combine, market_risk

H = 30
P90_HRI_THR_KEY = "hri_pool_p90"

# [P0-A] 前瞻标签可获知的额外滞后（数据发布/整理滞后，保守取 1 天）
LABEL_AVAIL_EXTRA_LAG_DAYS = 1

# [P0-5b FIX] 固定盐：仅用于由切点日期派生确定性随机种子
_RANDOM_SALT = 20261010


def _cutoff_seed(t) -> int:
    """确定性种子：由切点日期 ordinal 与固定盐派生。

    [P0-5b FIX] 不依赖 Python 内建 `hash()`（受 PYTHONHASHSEED 影响，跨进程不可复现）。
    """
    return int((_RANDOM_SALT * 1000003 + pd.Timestamp(t).toordinal()) % (2 ** 31 - 1))


def _select_cutoffs(dates, step_days: int = 7) -> List:
    """[P0-5a FIX] 按自然日步长对切点抽稀。

    原实现定义了 `step = pd.Timedelta(days=cutoff_step_days)` 但从未使用，
    实际遍历 panel 中全部日期，导致相邻切点的未来 30 天窗口几乎完全重叠，
    使「n 个切点」被误当作 n 个独立实验。此处真正按步长抽稀：
    默认 7 天（与历史口径可比）；设为 H=30 时相邻切点的未来窗口不再重叠。
    """
    ds = sorted(pd.Timestamp(x) for x in dates)
    if not step_days or step_days <= 1:
        return ds
    step = pd.Timedelta(days=int(step_days))
    out, last = [], None
    for d in ds:
        if last is None or (d - last) >= step:
            out.append(d)
            last = d
    return out


# ---------------------------------------------------------------- 候选池构建
def build_panel() -> pd.DataFrame:
    """每 (date, crop) 一行：预测 / 现价 / 实际 / HRI / market risk。"""
    preds = pd.read_parquet(FINAL_EVAL_DIR / "price_predictions.parquet")
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    sel30 = sel[(sel["city"] == "沈阳") & (sel["horizon"] == H)]
    keys = set(zip(sel30["crop"], sel30["model"], sel30["route"]))
    p = preds[(preds["city"] == "沈阳") & (preds["target"] == f"target_mean_price_next_{H}d")].copy()
    p = p[[(c, m, r) in keys for c, m, r in zip(p["crop"], p["model"], p["route"])]]
    p = p.rename(columns={"prediction": "forecast", "actual": "realized_mean"})
    p["date"] = pd.to_datetime(p["date"])
    p = p[["date", "crop", "forecast", "realized_mean", "anchor_price", "fold"]]

    # HRI（周）—— 附带 run_up_4w 供「追涨」基线使用
    w = weekly_prices("沈阳"); w["wk"] = w["iso_year"] * 100 + w["iso_week"]
    hri_cols = ["crop", "iso_year", "iso_week", "HRI", "hri_pct"]
    hc = hri_components(w)
    if "run_up_4w" in hc.columns:
        hri_cols = hri_cols + ["run_up_4w"]
    hri = combine(hc)[hri_cols]
    hri["wk"] = hri["iso_year"] * 100 + hri["iso_week"]
    p["iso_year"] = p["date"].dt.isocalendar().year.astype(int)
    p["iso_week"] = p["date"].dt.isocalendar().week.astype(int)
    p["wk"] = p["iso_year"] * 100 + p["iso_week"]
    p = p.merge(hri[["crop", "wk", "HRI", "hri_pct"] +
                    (["run_up_4w"] if "run_up_4w" in hri.columns else [])],
                on=["crop", "wk"], how="left")

    # market risk（日）
    mr = market_risk(daily_prices("沈阳"))[["date", "crop", "market_risk"]]
    p = p.merge(mr, on=["date", "crop"], how="left")

    # 区间 P10/P90（seasonal_window_quantile 或最优）
    try:
        iv = pd.read_parquet(FINAL_EVAL_DIR / "predictions_with_intervals.parquet")
        iv["date"] = pd.to_datetime(iv["date"])
        iv = iv.rename(columns={"p10": "fc_low", "p90": "fc_high"})[["date", "crop", "fc_low", "fc_high"]]
        p = p.merge(iv, on=["date", "crop"], how="left")
    except Exception:
        p["fc_low"] = np.nan; p["fc_high"] = np.nan

    p["realized_return"] = p["realized_mean"] / p["anchor_price"] - 1
    # 未来窗口最低价（downside 真实结果）
    ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet",
                         columns=["date", "crop", "target_min_price_next_30d"])
    ds["date"] = pd.to_datetime(ds["date"])
    p = p.merge(ds, on=["date", "crop"], how="left")
    p["realized_worst"] = p["target_min_price_next_30d"] / p["anchor_price"] - 1
    return p.dropna(subset=["forecast", "realized_return", "anchor_price"]).reset_index(drop=True)


# ---------------------------------------------------------------- 策略
def _pool_pct(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").rank(pct=True, na_option="bottom").fillna(0.5)


def strategy_scores(g: pd.DataFrame) -> pd.DataFrame:
    """同一 (date) 候选池内的策略得分。

    [P0-4 FIX] 收益分量一律基于**预测相对收益** predicted_return = forecast/anchor - 1；
    另单列 s_price_level（绝对价格水平最高）并明确其不可跨品种解释。
    """
    d = g.copy()
    d["predicted_return"] = d["forecast"] / d["anchor_price"] - 1
    d["predicted_low_return"] = d["fc_low"].fillna(d["forecast"]) / d["anchor_price"] - 1
    d["hri_n"] = _pool_pct(d["HRI"])                 # 池内百分位
    d["mr_n"] = (pd.to_numeric(d["market_risk"], errors="coerce") / 100).fillna(0.5)
    d["fc_n"] = _pool_pct(d["forecast"])             # 绝对价格水平（仅用于复现旧口径）
    d["low_n"] = _pool_pct(d["fc_low"].fillna(d["forecast"]))
    d["ret_n"] = _pool_pct(d["predicted_return"])    # 预测相对收益百分位
    d["lret_n"] = _pool_pct(d["predicted_low_return"])
    d["cur_n"] = _pool_pct(d["anchor_price"])
    # 原 Balanced（复现旧权重语义：收益 0.35 / 下行 0.20 / 置信 0.10 / 市场 0.15 / 跟风 0.12 / 气候 0.08；无气候→剔除）
    d["s_balanced_old"] = 0.35 * d["fc_n"] + 0.20 * d["low_n"] - 0.15 * d["mr_n"] - 0.12 * d["hri_n"]
    # 修复版 Balanced v1（第一步修复：HRI 用池内百分位 + 提高跟风惩罚；收益分量仍为绝对价格水平）
    d["s_balanced_fix_v1"] = 0.30 * d["fc_n"] + 0.20 * d["low_n"] - 0.20 * d["mr_n"] - 0.30 * d["hri_n"]
    # [P0-4 FIX] Balanced v2：收益分量改为预测相对收益
    d["s_balanced_fix_v2"] = 0.30 * d["ret_n"] + 0.20 * d["lret_n"] - 0.20 * d["mr_n"] - 0.30 * d["hri_n"]
    # 收益最大化（预测相对收益最高）——替代原名为 Profit_only 的绝对价格排序
    d["s_profit"] = d["predicted_return"]
    # 绝对价格水平最高（明确命名；不可解释为利润/机会最优）
    d["s_price_level"] = d["anchor_price"]
    # 追涨：过去 4 周相对涨幅最高（run_up_4w）；缺失则退化为 predicted_return
    if "run_up_4w" in d.columns:
        d["s_chase"] = pd.to_numeric(d["run_up_4w"], errors="coerce").fillna(d["predicted_return"])
    else:
        d["s_chase"] = d["predicted_return"]
    d["s_lowrisk"] = -(d["mr_n"] + d["hri_n"])
    d["s_robust"] = d["predicted_low_return"] - 0.5 * d["hri_n"] * d["predicted_return"]
    return d


STRATS = {
    "Balanced_old": "s_balanced_old",
    "Balanced_fix_v1": "s_balanced_fix_v1",
    "Balanced_fix_v2": "s_balanced_fix_v2",
    "Highest_forecast_return": "s_profit",
    "Highest_price_level": "s_price_level",
    "Chase_price_momentum": "s_chase",
    "Low_risk": "s_lowrisk",
    "Most_Robust": "s_robust",
}


def _seasonal_hist(h: int = H, extra_lag_days: int = LABEL_AVAIL_EXTRA_LAG_DAYS) -> pd.DataFrame:
    """历史「已成熟」相对收益 + 标签可获知日期。

    [P0-A FIX] 原实现仅用 `hist["date"] < t` 判断历史性，并在意 `rel_ret` 是否非缺失。
    但 `rel_ret` 由 (d, d+h] 的价格窗口计算，**其可获知日期是 d+h（+发布滞后）**，
    并非 d。因此在 t 处，只能使用 d + h (+lag) <= t 的历史样本；
    否则等价于用决策日之后才会出现的标签来打分（未来标签泄漏）。

    本函数显式给出 `label_avail_date = date + h 天 (+ extra_lag_days)`，
    由 `_seasonal_pick` 按 `label_avail_date <= t` 过滤。
    """
    ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet",
                         columns=["date", "crop", "month", "price_per_kg",
                                  f"target_mean_price_next_{h}d"])
    ds["date"] = pd.to_datetime(ds["date"])
    tgt = f"target_mean_price_next_{h}d"
    ds["rel_ret"] = ds[tgt] / ds["price_per_kg"] - 1
    ds["label_avail_date"] = ds["date"] + pd.Timedelta(days=int(h) + int(extra_lag_days))
    return ds[["date", "crop", "month", "rel_ret", "label_avail_date"]]


def _seasonal_pick(g: pd.DataFrame, hist: pd.DataFrame) -> int:
    """同月历史「已成熟且已在决策日可获知」相对收益均值最高的作物。

    定义（可核验）：
      1. 同月（month 相同）；
      2. **标签可获知日期 <= 决策日 t**（`label_avail_date <= t`）——[P0-A FIX]；
      3. `rel_ret` 非缺失（前瞻窗口完整）；
      4. 按作物求 `rel_ret` 均值，取最高者。

    历史沿革：
      - 更早版本先算同月历史均价却未取 `idxmax`，退化为「按作物名排序第一个」（P0-3）；
      - 上一版本改为按 `date < t` 筛选（P0-3 修复），但仍存在 P0-A 的未来标签泄漏：
        历史日期早于 t 并不代表该历史日期之后 h 天的价格结果在 t 已可观察。
    """
    t = pd.Timestamp(g["date"].iloc[0])
    hh = hist[(hist["month"] == t.month) &
              (hist["label_avail_date"] <= t) &
              (hist["rel_ret"].notna())]
    if not len(hh):
        return g["predicted_return"].idxmax() if "predicted_return" in g.columns else g["forecast"].idxmax()
    best = hh.groupby("crop")["rel_ret"].mean()
    sel = best.reindex(list(g["crop"].values)).dropna()
    if not len(sel):
        return g["forecast"].idxmax()
    winner = sel.idxmax()
    return g.index[g["crop"] == winner][0]


def run_backtest(cutoff_step_days: int = 7, tag: str = "step7") -> Dict[str, object]:
    """历史回测。cutoff_step_days 现在**真正生效**（[P0-5a]）。"""
    panel = build_panel()
    hist = _seasonal_hist()
    dates = _select_cutoffs(sorted(panel["date"].unique()), cutoff_step_days)
    rows = []
    for t in dates:
        g = panel[panel["date"] == t]
        if len(g) < 4:
            continue
        sc = strategy_scores(g)
        thr = g["HRI"].quantile(0.90)
        for name, col in STRATS.items():
            idx = sc[col].idxmax()
            sel = g.loc[[idx]]
            rows.append(_rec(t, name, sel, g, thr))
        # Seasonal 与 Random（同一切点、同池）
        sidx = _seasonal_pick(g, hist)
        rows.append(_rec(t, "Seasonal", g.loc[[sidx]], g, thr))
        # [P0-5b FIX] 确定性单次抽取
        rng = np.random.RandomState(_cutoff_seed(t))
        ridx = g.index[rng.permutation(len(g))[0]]
        rows.append(_rec(t, "Random_seeded", g.loc[[ridx]], g, thr))
        # [P0-5b FIX] 均匀随机选择的解析期望（池内均值）——显著性检验应以此为准
        rows.append(_expectation_rec(t, g))
    bt = pd.DataFrame(rows)
    if not len(bt):
        return {"status": "no_results"}
    best = bt.groupby("date")["realized_return"].max().rename("best")
    bt = bt.merge(best, on="date", how="left")
    bt["regret"] = bt["best"] - bt["realized_return"]
    bt["cutoff_step_days"] = cutoff_step_days
    bt.to_parquet(FINAL_EVAL_DIR / f"strategy_backtest_{tag}.parquet", index=False)

    summ = (bt.groupby("strategy")
            .agg(n=("realized_return", "size"),
                 mean_market_return=("realized_return", "mean"),
                 median_market_return=("realized_return", "median"),
                 downside=("realized_return", lambda s: float(s[s < 0].mean()) if (s < 0).any() else 0.0),
                 worst_market_return=("realized_return", "min"),
                 p05=("realized_return", lambda s: float(s.quantile(0.05))),
                 p_down=("realized_return", lambda s: float((s < 0).mean())),
                 mean_worst_path=("realized_worst", "mean"),
                 high_hri_rate=("high_hri", "mean"),
                 mean_HRI=("HRI", "mean"),
                 mean_market_risk=("market_risk", "mean"),
                 win_rate=("win", "mean"),
                 mean_regret=("regret", "mean"),
                 stability=("realized_return", "std"))
            .reset_index())
    summ["risk_adj"] = summ["mean_market_return"] / summ["downside"].abs().replace(0, np.nan)
    summ["metric_semantics"] = "market_return = 未来30天窗口均价/建仓价-1（市场机会，非农户利润）"
    summ["cutoff_step_days"] = cutoff_step_days
    summ = summ.sort_values("mean_market_return", ascending=False)
    summ.to_csv(REPORTS_DIR / "tables" / f"strategy_benchmark_{tag}.csv", index=False, encoding="utf-8-sig")
    if tag == "step7":   # 兼容既有下游文件名
        summ.to_csv(REPORTS_DIR / "tables" / "strategy_benchmark.csv", index=False, encoding="utf-8-sig")
    return {"status": "ok", "n_cutoffs": int(bt["date"].nunique()),
            "cutoff_step_days": cutoff_step_days, "summary": summ}


def _rec(t, name, sel, pool, thr) -> Dict:
    r = sel.iloc[0]
    return {
        "date": str(pd.Timestamp(t).date()), "strategy": name, "crop": r["crop"],
        "forecast": float(r["forecast"]), "anchor": float(r["anchor_price"]),
        "predicted_return": float(r["forecast"] / r["anchor_price"] - 1),
        "realized_return": float(r["realized_return"]),
        "realized_worst": float(r["realized_worst"]) if "realized_worst" in r else np.nan,
        "HRI": float(r["HRI"]) if pd.notna(r["HRI"]) else np.nan,
        "high_hri": float(bool(pd.notna(r["HRI"]) and r["HRI"] >= thr)),   # 单次实现记为 0/1
        "market_risk": float(r["market_risk"]) if pd.notna(r["market_risk"]) else np.nan,
        "win": bool(r["realized_return"] > 0),
        "stat_type": "realized",   # 单次策略选择的实际实现
    }


def _expectation_rec(t, g) -> Dict:
    """均匀随机选择的**解析期望**（=池内均匀平均），不依赖任何随机数。

    [P0-B FIX] 原实现把「池内高 HRI 占比」用 `>= 0.10` 转成布尔值，
    因阈值本身取自池内 90 分位（占比恒约 10%），导致随机策略的高 HRI 命中率**恒为 100%**。
    现改为记录**占比本身**（连续值），并在汇总时区分「期望」与「随机实现分布」。

    同时明确：本行给出的是**期望结果**（stat_type='expected'），
    其 realized_return 为池内均值（数学期望），而 median/worst/p05/p_down 等
    **不是某一次随机实现的风险分布**，仅作为池的横截面统计；随机实现的风险分布
    由多种子蒙特卡洛抽样另行评估（见 analysis/audit_final.py 与 final_strategy_comparison.py）。
    """
    rr = pd.to_numeric(g["realized_return"], errors="coerce")
    rw = pd.to_numeric(g["realized_worst"], errors="coerce")
    hr = pd.to_numeric(g["HRI"], errors="coerce")
    mrn = pd.to_numeric(g["market_risk"], errors="coerce")
    thr = hr.quantile(0.90)
    mean_ret = float(rr.mean())
    return {
        "date": str(pd.Timestamp(t).date()), "strategy": "Random_expectation", "crop": "__POOL__",
        "forecast": float(pd.to_numeric(g["forecast"], errors="coerce").mean()),
        "anchor": float(pd.to_numeric(g["anchor_price"], errors="coerce").mean()),
        "predicted_return": float(np.nanmean(pd.to_numeric(g["forecast"], errors="coerce") /
                                             pd.to_numeric(g["anchor_price"], errors="coerce") - 1)),
        "realized_return": mean_ret,
        "realized_worst": float(rw.mean()),
        "HRI": float(hr.mean()),
        # [P0-B FIX] 高 HRI 命中率 = 池内高 HRI 作物占比（随机选择的命中概率），不再布尔化
        "high_hri": float((hr >= thr).mean()),
        "market_risk": float(mrn.mean()),
        "win": bool(mean_ret > 0),
        "stat_type": "expected",   # ['expected' = 解析期望; 'realized' = 单次选择实现]
    }


# ---------------------------------------------------------------- Balanced 根因诊断
def diagnosis(panel: pd.DataFrame) -> Dict[str, object]:
    rows = []
    for t, g in panel.groupby("date"):
        if len(g) < 6 or g["HRI"].notna().sum() < 4:
            continue
        sc = strategy_scores(g)
        rows.append({
            "date": str(pd.Timestamp(t).date()),
            "corr_HRI_forecast": stats.spearmanr(g["HRI"], g["forecast"], nan_policy="omit")[0],
            "corr_HRI_anchor": stats.spearmanr(g["HRI"], g["anchor_price"], nan_policy="omit")[0],
            "corr_HRI_realized": stats.spearmanr(g["HRI"], g["realized_return"], nan_policy="omit")[0],
            "pick_old_highhri": bool(g.loc[sc["s_balanced_old"].idxmax(), "HRI"] >= g["HRI"].quantile(0.9)),
            "pick_fix_highhri": bool(g.loc[sc["s_balanced_fix_v2"].idxmax(), "HRI"] >= g["HRI"].quantile(0.9)),
            "pick_profit_highhri": bool(g.loc[sc["s_profit"].idxmax(), "HRI"] >= g["HRI"].quantile(0.9)),
        })
    d = pd.DataFrame(rows)
    out = {
        "n_cutoffs": int(len(d)),
        "mean_corr_HRI_forecast": float(d["corr_HRI_forecast"].mean()),
        "mean_corr_HRI_anchor": float(d["corr_HRI_anchor"].mean()),
        "mean_corr_HRI_realized": float(d["corr_HRI_realized"].mean()),
        "high_hri_rate_old": float(d["pick_old_highhri"].mean()),
        "high_hri_rate_fix": float(d["pick_fix_highhri"].mean()),
        "high_hri_rate_profit": float(d["pick_profit_highhri"].mean()),
    }
    d.to_csv(REPORTS_DIR / "tables" / "balanced_diagnosis_by_cutoff.csv", index=False, encoding="utf-8-sig")
    # 判定 A/B/C
    valid_hri = out["mean_corr_HRI_realized"] < -0.05
    corr_fc = out["mean_corr_HRI_forecast"]
    if valid_hri and abs(corr_fc) > 0.15:
        case = "C (HRI 有效，但与预测收益/价格水平高相关 → 旧 score 未有效惩罚)"
    elif valid_hri:
        case = "A (HRI 有效，推荐层未正确惩罚)"
    else:
        case = "B (HRI 验证失败)"
    out["diagnosis_case"] = case
    write_json(out, REPORTS_DIR / "tables" / "balanced_diagnosis.json")
    return out


if __name__ == "__main__":
    p = build_panel()
    print("panel rows:", len(p), "dates:", p["date"].nunique())
    print("diagnosis:", diagnosis(p))
    print(run_backtest())
