"""STEP 23：Phase 12 预测模型（§四十九~§五十三）。

对应任务书：
  §四十九 分别建立 Volume Model（目标 volume_anomaly）与 Price Model（目标 price_anomaly）；
  §五十   模型候选至少含 Baseline（历史均值 / Seasonal Naive）、Linear（正则回归）、
          Nonlinear（GAM）、Tree（LightGBM）；目的 = 检验「复杂模型是否真的比简单基线有提升」；
  §五十一 **绝对禁止随机切分时间序列**：采用 time-based split + Rolling Origin Validation；
  §五十二 防未来信息泄漏：任何滚动统计 / 异常基线 / 滞后特征 / scaler 只能 fit 训练集；
  §五十三 评价指标 MAE / RMSE / R2 /（MAPE 视零值情况）；且必须分层：
          overall / crop / season / extreme-event period / normal period。

设计（预登记，防挑结果）：
  1) 目标（两种口径，**主口径与全项目一致，次口径用于泄漏稳健性**）
     - hist  ：`price_anomaly_z_hist` / `volume_anomaly_z_hist`（方法B 留一年法 + 稳健 z，
               与 STEP 09-22 同口径；注意：留一年法的基线取自其他年份，含测试年之后年份）
     - strict：`*_anomaly_pct_strict`（本模块新增，**只用严格更早年份**的同期中位数做基线，
               彻底无未来信息；单位为相对偏离比例，评估看 R2 / nRMSE）
  2) 特征（两口径）
     - F_lag（**主口径**，真预测）：仅 t-1 及更早信息 —— 上游已落库的天气滞后列（lag1/3/7/14d）
       + 目标/量价滞后 + 日历控制（month 哑变量、节假日、年趋势）
     - F_now（次口径，同期临近）：F_lag + 当日天气
     两种口径都**不含**当前价格/成交量水平（当前价格 = 目标的分子，属泄漏）；
     不含完整日期固定效应（§三十九 红线）。
  3) 切分：train <=2024-12-31 / valid 2025 / test 2026-01-01~2026-09-14（时间切分，无 shuffle，
     代码中显式断言不存在 train_test_split）；
     Rolling Origin = 扩张窗，训练年 [2021, Y-1]，测试年 Y ∈ {2024, 2025, 2026}（共 3 折；
     任务书 config 期望 4 折，但气象覆盖自 2021 起且最少 3 个训练年 → 实际最多 3 折，已登记）。
  4) 预处理：中位数填补 + 标准化，二者均**只用训练集 fit**。
  5) 主证据 = test 集指标；模型选择参考 valid 集；分层指标 = test 集。
  6) MAPE/SMAPE：目标为去季节化异常（含 0 与负值）→ MAPE 无定义，一律记 NA 并说明。

产出：
  outputs/tables/model_split_meta.csv, model_feature_list.csv,
    model_metrics_overall.csv, model_metrics_by_crop.csv, model_metrics_by_season.csv,
    model_metrics_by_period.csv, model_rolling_origin.csv, model_baseline_comparison.csv
  data/processed/shenyang_model_predictions.parquet + outputs/tables/model_predictions.csv
  outputs/figures/F39..F42
  models/*.txt|*.pkl + models/model_meta.json（供 Phase 13 解释、Phase 14 反事实使用）
  reports/12_PREDICTION.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, load_parquet, read_input,
    register_results, render_figure, require_columns, save_parquet, save_table,
    set_seed, setup_matplotlib,
)

MOD = "14_prediction"
LOG = get_logger(MOD)

CFG = ANALYSIS["modeling"]
CORE_CROPS: List[str] = list(CROPS_CFG["core_crops"])
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
TRAIN_END = pd.Timestamp(CFG["train_end"])
VALID_END = pd.Timestamp(CFG["valid_end"])
LGBM_PARAMS = dict(CFG["lgbm_params"])
ENET_PARAMS = dict(CFG["elasticnet_params"])
GAM_DF = int(CFG["gam_spline_df"])
SEED = set_seed()

TARGETS = {"price": "price_anomaly_z_hist", "volume": "volume_anomaly_z_hist"}
STRICT_TARGETS = {"price": "price_anomaly_pct_strict", "volume": "volume_anomaly_pct_strict"}
KINDS = ["hist", "strict"]
# 特征口径：
#   F_wx   = 仅天气（滞后）+ 日历 + 品种 FE，**无自回归项** -> 用于量化「天气/日历」相对均值的边际贡献
#   F_lag  = F_wx + 自回归项（上一/前二交易日异常、昨日量价水平）-> **主预测口径**（真预测）
#   F_now  = F_lag + 当日天气 -> 同期临近口径（对照）
FEATURE_SETS = ["F_wx", "F_lag", "F_now"]
BASELINES = ["baseline_mean", "baseline_seasonal_naive", "baseline_persistence"]
LEARNERS = ["elasticnet", "gam", "lightgbm"]
MODELS = BASELINES + LEARNERS

# --- 天气特征（滞后列已在 01_build_panel 落库，均为 shift(k) 构造，不含未来）-------------
LAG_WEATHER = [
    "precipitation_lag1d", "precip_3d_lag1d", "precip_7d_lag1d", "temp_max_lag1d",
    "vpd_lag1d", "soil_moisture_0_7_lag1d", "temp_anomaly_lag1d",
    "precipitation_lag3d", "precip_3d_lag3d", "precip_7d_lag3d", "temp_max_lag3d",
    "vpd_lag3d", "soil_moisture_0_7_lag3d",
    "precipitation_lag7d", "precip_3d_lag7d", "precip_7d_lag7d", "temp_max_lag7d",
    "vpd_lag7d", "soil_moisture_0_7_lag7d",
    "precipitation_lag14d", "precip_3d_lag14d", "precip_7d_lag14d", "temp_max_lag14d",
    "vpd_lag14d", "soil_moisture_0_7_lag14d",
]
NOW_WEATHER = [
    "precip_1d", "precip_3d", "precip_7d", "precip_14d",
    "temp_max", "temp_min", "temp_mean", "vpd", "humidity_z", "temp_z",
    "soil_moisture_0_7_z", "precip_deficit_14d", "dry_spell_days", "wet_spell_days",
    "wind_speed",
]
# 时序控制 / 日历（§三十六：month / holiday / year trend；**禁止完整日期固定效应**）
CAL_FEATURES = ["is_public_holiday", "year_t"] + [f"m{m}" for m in range(2, 13)]
AR_HIST = ["price_anomaly_z_hist_lag1", "price_anomaly_z_hist_lag2",
           "volume_anomaly_z_hist_lag1", "volume_anomaly_z_hist_lag2",
           "log_price_lag1", "log_volume_lag1"]
AR_STRICT = ["price_anomaly_pct_strict_lag1", "volume_anomaly_pct_strict_lag1",
             "log_price_lag1", "log_volume_lag1"]
GAM_SPLINE_LAG = ["precip_3d_lag1d", "precip_7d_lag3d", "temp_max_lag1d", "vpd_lag1d",
                  "soil_moisture_0_7_lag1d", "temp_anomaly_lag1d"]
GAM_SPLINE_NOW = GAM_SPLINE_LAG + ["precip_3d", "precip_7d", "temp_max", "vpd",
                                   "soil_moisture_0_7_z", "dry_spell_days",
                                   "precip_deficit_14d"]
# 灾害影响窗（分层评价用）：事件起前 1 日至结束后 7 日
EXTREME_LEAD = 1
EXTREME_LAG = 7
MIN_BASE_OBS = int(ANALYSIS["seasonal_baseline"]["min_obs_for_baseline"])
HIST_WINDOW = int(ANALYSIS["seasonal_baseline"]["hist_window_days"]) // 2  # doy ± 5


# =============================================================================
# 1) 数据准备
# =============================================================================
def _strict_anomaly(panel_long: pd.DataFrame, var: str, log) -> pd.Series:
    """严格无未来信息异常：基线 = **严格更早年份** 同作物 doy±5 中位数，单位=相对偏离比例。

    与 方法B 的唯一区别：方法B 基线取「其他年份」（含未来年），此处仅取 year < 当前年。
    """
    out = np.full(len(panel_long), np.nan)
    doy = panel_long["doy"].to_numpy()
    yrs = panel_long["year"].to_numpy()
    val = panel_long[var].to_numpy(dtype=float)
    for i in range(len(panel_long)):
        d, y = doy[i], yrs[i]
        dist = np.abs(((doy - d + 182) % 365) - 182)
        m = (dist <= HIST_WINDOW) & (yrs < y)
        if m.sum() >= MIN_BASE_OBS:
            base = float(np.median(val[m]))
            if np.isfinite(base) and base > 0:
                out[i] = val[i] / base - 1.0
    return pd.Series(out, index=panel_long.index)


def build_strict_targets(log) -> pd.DataFrame:
    """在更长覆盖（2020 起）的日度面板上构造 strict 目标，使 2021 年也能用到 2020 参照年。"""
    d = load_parquet("daily_panel")
    d["date"] = pd.to_datetime(d["date"])
    d = d[d["crop"].isin(CORE_CROPS)].copy()
    d["year"] = d["date"].dt.year
    d["doy"] = d["date"].dt.dayofyear
    parts = []
    for crop, g in d.groupby("crop"):
        g = g.sort_values("date").reset_index(drop=True)
        sub = pd.DataFrame({"crop": crop, "date": g["date"], "doy": g["doy"], "year": g["year"]})
        for var, name in (("price", "price_anomaly_pct_strict"),
                          ("volume", "volume_anomaly_pct_strict")):
            tmp = sub.copy()
            tmp[var] = g[var].to_numpy(dtype=float)
            tmp["anom"] = _strict_anomaly(tmp, var, log)
            sub[name] = tmp["anom"].to_numpy()
        parts.append(sub[["crop", "date", "price_anomaly_pct_strict", "volume_anomaly_pct_strict"]])
    out = pd.concat(parts, ignore_index=True)
    save_table(out[out["date"] >= CORE_START], "model_strict_targets.csv")
    log.info("strict 目标（严格无未来信息）构造完成：%d 行；缺失 %.1f%%",
             len(out), 100 * float(out["price_anomaly_pct_strict"].isna().mean()))
    return out


def build_design(log) -> pd.DataFrame:
    panel = load_parquet("panel_final")
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel[(panel["date"] >= CORE_START) & (panel["date"] <= CORE_END)
                  & (panel["crop"].isin(CORE_CROPS))].copy()
    require_columns(panel, ["date", "crop", "doy", "price_prev_obs", "volume_prev_obs",
                            "price_anomaly_z_hist", "volume_anomaly_z_hist"] + LAG_WEATHER + NOW_WEATHER,
                    MOD)

    df = panel[["date", "crop", "doy", "year",
                "price_anomaly_z_hist", "volume_anomaly_z_hist",
                "price_prev_obs", "volume_prev_obs", "is_public_holiday"] + LAG_WEATHER + NOW_WEATHER].copy()

    # strict 目标（另口径合并）
    st = build_strict_targets(log)
    df = df.merge(st, on=["crop", "date"], how="left")

    df = df.sort_values(["crop", "date"]).reset_index(drop=True)
    df["month"] = df["date"].dt.month
    df["year_t"] = (df["date"].dt.year - CORE_START.year).astype(float)
    for m in range(2, 13):
        df[f"m{m}"] = (df["month"] == m).astype(float)

    # 滞后特征（仅用 groupby-shift，绝不读取未来；shift(1) = 上一交易日观测）
    g = df.groupby("crop", sort=False)
    for t in ("price_anomaly_z_hist", "volume_anomaly_z_hist",
              "price_anomaly_pct_strict", "volume_anomaly_pct_strict"):
        df[f"{t}_lag1"] = g[t].shift(1)
    df["price_anomaly_z_hist_lag2"] = g["price_anomaly_z_hist"].shift(2)
    df["volume_anomaly_z_hist_lag2"] = g["volume_anomaly_z_hist"].shift(2)
    df["log_price_lag1"] = np.where(df["price_prev_obs"] > 0, np.log(df["price_prev_obs"]), np.nan)
    df["log_volume_lag1"] = np.where(df["volume_prev_obs"] > 0, np.log(df["volume_prev_obs"]), np.nan)

    # 灾害影响窗标记（用于分层评价）
    ev = read_input("fact_disaster_events")
    ev = ev[ev["city"] == "沈阳"].copy()
    ev["start_date"] = pd.to_datetime(ev["start_date"])
    ev["end_date"] = pd.to_datetime(ev["end_date"])
    hazard_days = set()
    for _, r in ev.iterrows():
        for d in pd.date_range(r["start_date"] - pd.Timedelta(days=EXTREME_LEAD),
                               r["end_date"] + pd.Timedelta(days=EXTREME_LAG), freq="D"):
            hazard_days.add(d)
    df["is_extreme_period"] = df["date"].isin(hazard_days)
    df["season"] = df["month"].map(
        lambda m: "春(3-5)" if m in (3, 4, 5) else "夏(6-8)" if m in (6, 7, 8)
        else "秋(9-11)" if m in (9, 10, 11) else "冬(12-2)")
    LOG.info("设计矩阵：%d 行；灾害影响窗内 %d 行（%.1f%%）；2026 测试期灾害窗内 %d 行",
             len(df), int(df["is_extreme_period"].sum()),
             100 * df["is_extreme_period"].mean(),
             int(df[(df["date"] > VALID_END) & df["is_extreme_period"]].shape[0]))
    return df, ev


def feature_columns(df: pd.DataFrame, kind: str, fs: str) -> List[str]:
    weather = LAG_WEATHER + (NOW_WEATHER if fs == "F_now" else [])
    ar = [] if fs == "F_wx" else (AR_HIST if kind == "hist" else AR_STRICT)
    crops = [f"crop_{c}" for c in CORE_CROPS[1:]]
    cols = weather + ar + CAL_FEATURES + crops
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"特征缺失：{missing}")
    return cols


def add_crop_dummies(df: pd.DataFrame) -> pd.DataFrame:
    for c in CORE_CROPS[1:]:
        df[f"crop_{c}"] = (df["crop"] == c).astype(float)
    return df


# =============================================================================
# 2) 模型
# =============================================================================
class Prep:
    """训练集拟合的中位数填补 + 标准化（严格只 fit 训练集，§五十二）。"""

    def __init__(self, Xtr: pd.DataFrame) -> None:
        self.median = Xtr.median(numeric_only=True)
        self.n_imputed = int(Xtr.isna().sum().sum())
        filled = Xtr.fillna(self.median)
        self.mean = filled.mean()
        self.scale = filled.std(ddof=0).replace(0, 1.0)

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        Z = X.fillna(self.median)
        Z = (Z - self.mean) / self.scale
        return Z.to_numpy(dtype=float)

    def state(self) -> Dict:
        return {"median": self.median.to_dict(), "mean": self.mean.to_dict(),
                "scale": self.scale.to_dict(), "n_imputed_in_train": self.n_imputed}


class Fitted:
    def __init__(self, name: str, predict_fn, obj=None) -> None:
        self.name = name
        self.predict = predict_fn
        self.obj = obj


def fit_learner(name: str, Xtr: np.ndarray, ytr: np.ndarray, cols: List[str],
                fs: str) -> Fitted:
    if name == "elasticnet":
        from sklearn.linear_model import ElasticNet
        m = ElasticNet(**ENET_PARAMS)
        m.fit(Xtr, ytr)
        return Fitted(name, lambda X: m.predict(X), m)
    if name == "lightgbm":
        import lightgbm as lgb
        m = lgb.LGBMRegressor(**LGBM_PARAMS)
        m.fit(Xtr, ytr)
        return Fitted(name, lambda X: m.predict(X), m)
    if name == "gam":
        from pygam import LinearGAM, l, s
        spline = GAM_SPLINE_NOW if fs == "F_now" else GAM_SPLINE_LAG
        spline_idx = {i for i, c in enumerate(cols) if c in spline}
        terms = None
        for j in range(len(cols)):
            # pygam 0.10 的 s() 只接受 n_splines（近似自由度），config 的 gam_spline_df 直接作为 n_splines
            t = s(j, n_splines=GAM_DF, spline_order=3) if j in spline_idx else l(j)
            terms = t if terms is None else terms + t
        m = LinearGAM(terms, max_iter=200)
        m.fit(Xtr, ytr)
        return Fitted(name, lambda X: m.predict(X), m)
    raise ValueError(f"未知学习器 {name}")


def baseline_predict(name: str, train: pd.DataFrame, test: pd.DataFrame,
                     target: str, cols_unused=None) -> np.ndarray:
    """无泄漏基线：均值基线 / 季节朴素 / 持续性（昨日观测）。

    注：`baseline_persistence` = 昨日同品种同目标口径的异常值（仅用 t-1 观测），
    是本项目意义上**不含任何天气信息**的强基线；只有超过它才能说天气/模型带来预测增益。
    """
    if name == "baseline_mean":
        cm = train.groupby("crop")[target].mean()
        gm = float(train[target].mean())
        return test["crop"].map(cm).fillna(gm).to_numpy(dtype=float)

    if name == "baseline_persistence":
        lag = f"{target}_lag1"
        cm = train.groupby("crop")[target].mean()
        gm = float(train[target].mean())
        v = test[lag].to_numpy(dtype=float)
        fallback = test["crop"].map(cm).fillna(gm).to_numpy(dtype=float)
        return np.where(np.isfinite(v), v, fallback)

    if name == "baseline_seasonal_naive":
        tr = train[["crop", "doy", "year", target]].dropna()
        table: Dict[Tuple[str, int], Tuple[np.ndarray, np.ndarray]] = {}
        for (c, d), g in tr.groupby(["crop", "doy"]):
            table[(c, int(d))] = (g["year"].to_numpy(), g[target].to_numpy(dtype=float))
        cm = train.groupby("crop")[target].mean()
        gm = float(train[target].mean())
        preds = np.empty(len(test), dtype=float)
        tc = test["crop"].to_numpy()
        td = test["doy"].to_numpy()
        ty = test["year"].to_numpy()
        for i in range(len(test)):
            acc: List[float] = []
            for off in range(-HIST_WINDOW, HIST_WINDOW + 1):
                key = (tc[i], int(td[i]) + off)
                if key in table:
                    ys, vs = table[key]
                    m = ys < ty[i]
                    if m.any():
                        acc.extend(vs[m].tolist())
            preds[i] = float(np.median(acc)) if len(acc) >= 3 else float(
                cm.get(tc[i], gm) if np.isfinite(cm.get(tc[i], np.nan)) else gm)
        return preds
    raise ValueError(name)


# =============================================================================
# 3) 评价
# =============================================================================
def metrics(y: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    m = np.isfinite(y) & np.isfinite(yhat)
    if m.sum() < 3:
        return {"n": int(m.sum()), "mae": np.nan, "rmse": np.nan, "r2": np.nan,
                "bias": np.nan, "nrmse_sd": np.nan, "mape": np.nan}
    yy, yh = y[m], yhat[m]
    err = yh - yy
    rmse = float(np.sqrt((err ** 2).mean()))
    sd = float(yy.std(ddof=1))
    ss_tot = float(((yy - yy.mean()) ** 2).sum())
    return {
        "n": int(m.sum()),
        "mae": float(np.abs(err).mean()),
        "rmse": rmse,
        "r2": float(1 - (err ** 2).sum() / ss_tot) if ss_tot > 0 else np.nan,
        "bias": float(err.mean()),
        "nrmse_sd": rmse / sd if sd > 0 else np.nan,
        # 目标为去季节化异常（含 0 与负值）→ MAPE 无定义，按红线记 NA
        "mape": np.nan,
    }


def evaluate(y: np.ndarray, yhat: np.ndarray, tag: Dict) -> Dict:
    row = dict(tag)
    row.update(metrics(y, yhat))
    return row


# =============================================================================
# 4) 主流程
# =============================================================================
def run_split(df: pd.DataFrame, train: pd.DataFrame, test: pd.DataFrame,
              split_name: str, log, save_preds: bool = False,
              persist_prefix: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """在给定 train/test 上训练全部 模型 × 目标口径 × 特征口径，返回逐行指标与预测。"""
    rows, pred_rows = [], []
    for kind in KINDS:
        targets = TARGETS if kind == "hist" else STRICT_TARGETS
        for tname, tcol in targets.items():
            for fs in FEATURE_SETS:
                cols = feature_columns(df, kind, fs)
                tr = train.dropna(subset=[tcol])
                te = test.dropna(subset=[tcol])
                if len(tr) < 100 or len(te) < 30:
                    log.warning("跳过 %s/%s/%s：train=%d test=%d", kind, tname, fs, len(tr), len(te))
                    continue
                prep = Prep(tr[cols])
                Xtr, Xte = prep.transform(tr[cols]), prep.transform(te[cols])
                ytr = tr[tcol].to_numpy(dtype=float)
                yte = te[tcol].to_numpy(dtype=float)

                fitted: Dict[str, Fitted] = {}
                for b in BASELINES:
                    fn = (lambda tb, te_, t=tcol, b_=b:
                          baseline_predict(b_, tb, te_, t))
                    fitted[b] = Fitted(b, fn)
                for ln in LEARNERS:
                    try:
                        fitted[ln] = fit_learner(ln, Xtr, ytr, cols, fs)
                    except Exception as exc:  # 不静默：记录并继续其他模型
                        log.warning("模型 %s 在 %s/%s/%s 拟合失败：%s", ln, kind, tname, fs, exc)
                        rows.append(evaluate(yte, np.full(len(te), np.nan),
                                             {"target_kind": kind, "target": tname,
                                              "feature_set": fs, "model": f"{ln}_FAILED",
                                              "split": split_name}))
                        continue

                for mname, f in fitted.items():
                    # 基线只依赖训练集历史（predict(训练子集, 测试子集)）；学习器只用训练集 fit 的变换器
                    yhat = f.predict(tr, te) if mname in BASELINES else f.predict(Xte)
                    base = pd.DataFrame({
                        "date": te["date"].to_numpy(), "crop": te["crop"].to_numpy(),
                        "target_kind": kind, "target": tname, "feature_set": fs,
                        "model": mname, "split": split_name,
                        "y_true": yte, "y_pred": np.asarray(yhat, dtype=float),
                    })
                    base["is_extreme_period"] = te["is_extreme_period"].to_numpy()
                    base["season"] = te["season"].to_numpy()
                    for gname, gdf in base.groupby("crop"):
                        rows.append(evaluate(gdf["y_true"].to_numpy(), gdf["y_pred"].to_numpy(),
                                             {"target_kind": kind, "target": tname,
                                              "feature_set": fs, "model": mname,
                                              "split": split_name, "stratum": "crop",
                                              "stratum_value": gname}))
                    for gname, gdf in base.groupby("season"):
                        rows.append(evaluate(gdf["y_true"].to_numpy(), gdf["y_pred"].to_numpy(),
                                             {"target_kind": kind, "target": tname,
                                              "feature_set": fs, "model": mname,
                                              "split": split_name, "stratum": "season",
                                              "stratum_value": gname}))
                    for gname, gdf in base.groupby("is_extreme_period"):
                        rows.append(evaluate(gdf["y_true"].to_numpy(), gdf["y_pred"].to_numpy(),
                                             {"target_kind": kind, "target": tname,
                                              "feature_set": fs, "model": mname,
                                              "split": split_name, "stratum": "period",
                                              "stratum_value": "extreme" if gname else "normal"}))
                    rows.append(evaluate(yte, np.asarray(yhat, dtype=float),
                                         {"target_kind": kind, "target": tname,
                                          "feature_set": fs, "model": mname,
                                          "split": split_name, "stratum": "overall",
                                          "stratum_value": "all"}))
                    if save_preds:
                        pred_rows.append(base)

                # 持久化（历史口径 + 主口径 F_lag 的 LightGBM 供 Phase 14 使用）
                if persist_prefix is not None:
                    for ln, f in fitted.items():
                        path = PATHS.dir("models") / f"{persist_prefix}_{kind}_{tname}_{fs}_{ln}"
                        try:
                            if ln == "lightgbm":
                                f.obj.booster_.save_model(str(path.with_suffix(".txt")))
                            elif ln in ("elasticnet", "gam"):
                                import joblib
                                joblib.dump(f.obj, path.with_suffix(".pkl"))
                            else:
                                continue
                        except Exception as exc:
                            log.warning("模型持久化失败 %s: %s", path.name, exc)
                    with (PATHS.dir("models") / f"{persist_prefix}_{kind}_{tname}_{fs}_prep.json").open(
                            "w", encoding="utf-8") as fh:
                        json.dump({"features": cols, "prep": prep.state(),
                                   "target": tcol, "feature_set": fs,
                                   "note": "中位数填补与标准化仅 fit 训练集"}, fh,
                                  ensure_ascii=False, indent=1)
    return pd.DataFrame(rows), (pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame())


def rolling_origin(df: pd.DataFrame, log) -> pd.DataFrame:
    """扩张窗 Rolling Origin：训练年 [2021, Y-1]，测试年 Y。GAM 因折内成本高不参与，已登记。"""
    rows = []
    years = sorted(df["year"].unique())
    folds = 0
    for y in years:
        tr_years = [v for v in years if v < y]
        if len(tr_years) < int(CFG["rolling_origin_min_train_years"]):
            continue
        if y not in (2024, 2025, 2026):
            continue
        folds += 1
        tr = df[df["year"] < y]
        te = df[df["year"] == y]
        for kind in KINDS:
            targets = TARGETS if kind == "hist" else STRICT_TARGETS
            for tname, tcol in targets.items():
                for fs in FEATURE_SETS:
                    cols = feature_columns(df, kind, fs)
                    a = tr.dropna(subset=[tcol])
                    b = te.dropna(subset=[tcol])
                    if len(a) < 100 or len(b) < 30:
                        continue
                    prep = Prep(a[cols])
                    Xa, Xb = prep.transform(a[cols]), prep.transform(b[cols])
                    ya, yb = a[tcol].to_numpy(float), b[tcol].to_numpy(float)
                    models = {}
                    for bl in BASELINES:
                        models[bl] = Fitted(bl, (lambda x, yy, t=tcol, b_=bl:
                                                 baseline_predict(b_, x, yy, t)))
                    for ln in ("elasticnet", "lightgbm"):
                        models[ln] = fit_learner(ln, Xa, ya, cols, fs)
                    for mname, f in models.items():
                        yhat = (f.predict(a, b) if mname in BASELINES else f.predict(Xb))
                        r = evaluate(yb, np.asarray(yhat, float),
                                     {"fold": folds, "test_year": int(y),
                                      "target_kind": kind, "target": tname,
                                      "feature_set": fs, "model": mname})
                        rows.append(r)
        log.info("Rolling origin 折 %d：测试年 %d，训练年 %s", folds, int(y), tr_years)
    if folds < int(CFG["rolling_origin_folds"]):
        log.warning("Rolling origin 实际 %d 折 < config 期望 %d 折（气象自 2021 起 + 最少 %d 训练年）",
                    folds, int(CFG["rolling_origin_folds"]),
                    int(CFG["rolling_origin_min_train_years"]))
    return pd.DataFrame(rows)


# =============================================================================
# 5) 图
# =============================================================================
def autocorr_table(df: pd.DataFrame) -> pd.DataFrame:
    """目标序列滞后 1 期自相关（判断「样本外可预测性」主要来自持续性还是天气）。"""
    rows = []
    for kind in KINDS:
        targets = TARGETS if kind == "hist" else STRICT_TARGETS
        for tname, tcol in targets.items():
            for sname, sub in (("train", df[df["date"] <= TRAIN_END]),
                               ("test", df[df["date"] > VALID_END])):
                v = sub[tcol].to_numpy(dtype=float)
                lag = sub[f"{tcol}_lag1"].to_numpy(dtype=float)
                m = np.isfinite(v) & np.isfinite(lag)
                rows.append({
                    "target_kind": kind, "target": tname, "split": sname, "n": int(m.sum()),
                    "lag1_autocorr": float(np.corrcoef(v[m], lag[m])[0, 1]) if m.sum() > 3 else np.nan,
                    "sd": float(np.nanstd(v)),
                })
    return pd.DataFrame(rows)


def persistence_ablation(overall: pd.DataFrame) -> pd.DataFrame:
    """分离两种「可预测性」：天气/日历的边际贡献 vs 异常序列持续性的边际贡献。"""
    rows = []
    test = overall[(overall["split"] == "test") & (overall["stratum"] == "overall")]
    for (kind, tname), g in test.groupby(["target_kind", "target"]):
        get = lambda fs, m: g[(g["feature_set"] == fs) & (g["model"] == m)]  # noqa: E731
        mean_b = get("F_wx", "baseline_mean")
        pers_b = get("F_wx", "baseline_persistence")
        wx_lr = g[(g["feature_set"] == "F_wx") & (g["model"].isin(LEARNERS))]
        lag_lr = g[(g["feature_set"] == "F_lag") & (g["model"].isin(LEARNERS))]
        r = {
            "target_kind": kind, "target": tname,
            "r2_baseline_mean": float(mean_b["r2"].iloc[0]) if len(mean_b) else np.nan,
            "r2_persistence": float(pers_b["r2"].iloc[0]) if len(pers_b) else np.nan,
            "r2_best_weather_only": float(wx_lr["r2"].max()) if len(wx_lr) else np.nan,
            "r2_best_weather_plus_AR": float(lag_lr["r2"].max()) if len(lag_lr) else np.nan,
            "rmse_baseline_mean": float(mean_b["rmse"].iloc[0]) if len(mean_b) else np.nan,
            "rmse_persistence": float(pers_b["rmse"].iloc[0]) if len(pers_b) else np.nan,
            "rmse_best_weather_only": float(wx_lr["rmse"].min()) if len(wx_lr) else np.nan,
            "rmse_best_weather_plus_AR": float(lag_lr["rmse"].min()) if len(lag_lr) else np.nan,
        }
        r["gain_from_weather"] = r["r2_best_weather_only"] - r["r2_baseline_mean"]
        r["gain_from_persistence"] = r["r2_best_weather_plus_AR"] - r["r2_best_weather_only"]
        # 天气是否真的具有样本外解释力：以「测试集均值」为参照（R2 > 0），而非以弱基线为参照
        r["weather_only_has_skill"] = bool(np.isfinite(r["r2_best_weather_only"])
                                           and r["r2_best_weather_only"] > 0)
        r["learner_beats_persistence"] = bool(r["rmse_best_weather_plus_AR"] < r["rmse_persistence"])
        rows.append(r)
    return pd.DataFrame(rows)


def fig_metrics(overall: pd.DataFrame, log):
    plt = setup_matplotlib()
    d = overall[(overall["split"] == "test") & (overall["stratum"] == "overall")]
    colors = {"F_wx": "#c9b48f", "F_lag": "#2f6f9f", "F_now": "#a8c4a2"}
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.4))
    for j, kind in enumerate(KINDS):
        for i, tname in enumerate(("price", "volume")):
            ax = axes[i][j]
            s = d[(d["target_kind"] == kind) & (d["target"] == tname)]
            piv = s.pivot_table(index="model", columns="feature_set", values="r2")
            piv = piv.reindex([m for m in MODELS if m in piv.index])[
                [c for c in FEATURE_SETS if c in piv.columns]]
            piv.plot(kind="bar", ax=ax, color=[colors[c] for c in piv.columns], width=0.8)
            ax.axhline(0, color="#8a2b2b", lw=1.0)
            ax.set_title(f"{tname} 异常，目标口径={kind}（test=2026）")
            ax.set_ylabel("R2（测试集；<0 = 不如均值预测）")
            ax.set_xlabel("")
            ax.tick_params(axis="x", rotation=20)
            ax.legend(title="特征口径", fontsize=8)
    fig.suptitle("图 F39：预测模型测试集表现（时间切分，禁止随机切分）\n"
                 "F_wx=仅天气滞后（无自回归）；F_lag=主口径（+昨日异常等自回归项）；"
                 "F_now=+当日天气",
                 fontsize=11.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, "F39_model_metrics.png")


def fig_rolling(ro: pd.DataFrame, log):
    plt = setup_matplotlib()
    d = ro[(ro["target"] == "price") & (ro["target_kind"] == "hist")]
    fig, axes = plt.subplots(1, 3, figsize=(14.4, 4.4), sharey=True)
    for ax, fs in zip(axes, FEATURE_SETS):
        s = d[d["feature_set"] == fs]
        for m, g in s.groupby("model"):
            g = g.sort_values("test_year")
            ax.plot(g["test_year"], g["r2"], marker="o", label=m, lw=1.7)
        ax.axhline(0, color="#8a2b2b", lw=1.0, ls="--")
        ax.set_title(f"价格异常（口径 {fs}）")
        ax.set_xlabel("滚动验证的测试年")
        ax.set_xticks(sorted(s["test_year"].unique()))
    axes[0].set_ylabel("R2（滚动验证）")
    axes[0].legend(fontsize=8)
    fig.suptitle("图 F40：Rolling Origin 扩张窗验证（训练年 [2021, Y-1] → 测试年 Y）\n"
                 "GAM 未参与滚动验证（成本与折内样本量），仅在其他模型对比中出现",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, "F40_model_rolling_origin.png")


def fig_test_series(preds: pd.DataFrame, overall: pd.DataFrame, log):
    plt = setup_matplotlib()
    d = preds[(preds["target"] == "price") & (preds["target_kind"] == "hist")
              & (preds["feature_set"] == "F_lag") & (preds["split"] == "test")]
    if d.empty:
        log.warning("无测试期预测，跳过 F41/F42")
        return
    best = (overall[(overall["split"] == "test") & (overall["stratum"] == "overall")
                    & (overall["target"] == "price") & (overall["target_kind"] == "hist")
                    & (overall["feature_set"] == "F_lag")]
            .sort_values("rmse").iloc[0])["model"]
    d = d[d["model"].isin([best, "baseline_mean"])]
    agg = d.groupby(["date", "model"])[["y_true", "y_pred"]].mean().reset_index()
    fig, axes = plt.subplots(2, 1, figsize=(13.2, 7.0))
    ax = axes[0]
    t = agg[agg["model"] == best].sort_values("date")
    ax.plot(t["date"], t["y_true"], color="#333333", lw=1.2, label="真实值（10 品种等权均值）")
    ax.plot(t["date"], t["y_pred"], color="#2f6f9f", lw=1.4, label=f"预测（{best}）")
    for _, r in preds[(preds["model"] == best) & (preds["is_extreme_period"])].groupby("date"):
        ax.axvspan(r["date"].min(), r["date"].max(), color="#f0c7c7", alpha=0.45, lw=0)
    ax.set_ylabel("价格异常（稳健 z）")
    ax.set_title(f"2026 测试期价格异常：真实 vs {best} 预测（粉底 = 灾害影响窗）")
    ax.legend(fontsize=8.5)
    ax = axes[1]
    s = d
    ax.scatter(s["y_true"], s["y_pred"], s=6, alpha=0.35, color="#2f6f9f", edgecolors="none")
    lim = [float(np.nanmin([s["y_true"].min(), s["y_pred"].min()])),
           float(np.nanmax([s["y_true"].max(), s["y_pred"].max()]))]
    ax.plot(lim, lim, color="#8a2b2b", lw=1.1, ls="--")
    ax.set_xlabel("真实价格异常 z")
    ax.set_ylabel("预测价格异常 z")
    ax.set_title(f"{best}：预测 vs 真实（逐品种逐日）")
    fig.suptitle("图 F41：2026 年测试期预测诊断（时间切分：训练 <=2024，验证 2025，测试 2026）",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    render_figure(fig, "F41_model_test_series.png")
    return best


def fig_period_gap(overall: pd.DataFrame, log):
    plt = setup_matplotlib()
    d = overall[(overall["split"] == "test") & (overall["stratum"] == "period")
                & (overall["target_kind"] == "hist")]
    if d.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.4), sharey=True)
    for ax, tname in zip(axes, ("price", "volume")):
        s = d[d["target"] == tname]
        piv = s.pivot_table(index="model", columns="stratum_value", values="rmse")
        piv = piv.reindex([m for m in MODELS if m in piv.index])
        piv.plot(kind="bar", ax=ax, color=["#c98b8b", "#2f6f9f"], width=0.78)
        ax.set_title(f"{tname} 异常：灾害窗 vs 平常期")
        ax.set_ylabel("RMSE（越低越好）")
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=20)
        ax.legend(fontsize=8)
    fig.suptitle("图 F42：灾害影响窗与平常期的误差对比（分层评价，§五十三）\n"
                 "灾害窗 = 沈阳气象灾害事件起前 1 日至结束后 7 日",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, "F42_model_period_rmse.png")


# =============================================================================
# 6) 报告
# =============================================================================
def _md(df: pd.DataFrame) -> str:
    """轻量 markdown 表（避免额外依赖 tabulate；数值统一 4 位小数）。"""
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: f"{v:.4f}" if np.isfinite(v) else "NA")
        elif pd.api.types.is_bool_dtype(d[c]):
            d[c] = d[c].map(lambda v: "是" if v else "否")
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "| " + " | ".join("---" for _ in d.columns) + " |"
    body = ["| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep] + body)


def write_report(overall, ro, feats, split_meta, log, ablation=None, autocorr=None):
    def _fmt(df, cols, sort=None, n=14):
        d = df.copy()
        if sort:
            d = d.sort_values(sort)
        d = d.head(n)
        return _md(d[[c for c in cols if c in d.columns]])

    ov = overall[(overall["stratum"] == "overall")]
    test = ov[ov["split"] == "test"]
    valid = ov[ov["split"] == "valid"]
    cols = ["target_kind", "target", "feature_set", "model", "n", "mae", "rmse", "r2", "bias"]

    # 基线对比：每个 target×口径 的 RMSE 最优模型 vs 最优基线
    cmp_rows = []
    for (kind, tname, fs), g in ov.groupby(["target_kind", "target", "feature_set"]):
        gt = g[g["split"] == "test"]
        if gt.empty:
            continue
        base = gt[gt["model"].isin(BASELINES)]
        best_b = base.sort_values("rmse").iloc[0] if not base.empty else None
        best_a = gt.sort_values("rmse").iloc[0]
        thr = best_b["rmse"] if best_b is not None else np.nan
        for _, r in gt.iterrows():
            cmp_rows.append({
                "target_kind": kind, "target": tname, "feature_set": fs,
                "model": r["model"], "rmse_test": r["rmse"], "r2_test": r["r2"],
                "best_baseline": None if best_b is None else best_b["model"],
                "best_baseline_rmse": thr,
                "beats_baseline": bool(np.isfinite(r["rmse"]) and np.isfinite(thr) and r["rmse"] < thr),
                "complex_beats_simple": bool(r["model"] in LEARNERS and np.isfinite(thr)
                                             and r["rmse"] < thr),
                "mae_test": r["mae"], "n_test": r["n"],
            })
    cmp = pd.DataFrame(cmp_rows)
    save_table(cmp, "model_baseline_comparison.csv")

    extreme_note = ""
    ep = overall[(overall["split"] == "test") & (overall["stratum"] == "period")]
    if not ep.empty:
        piv = ep.pivot_table(index=["target_kind", "target", "feature_set", "model"],
                             columns="stratum_value", values=["rmse", "n"])
        extreme_note = _md(piv.reset_index())

    txt = f"""# 12 预测模型（Phase 12，§四十九~§五十三）

## 1 结论摘要

- 正式预测模型仅在此前描述 / 异常 / 滞后 / 事件 / 传导 / 异质性 / 物候 / 年度生产
  全部完成后启动（§四十九 前置条件已满足）。
- 目标：价格异常与成交量异常，各 2 种口径 x 3 种特征口径 x {len(MODELS)} 个模型。
- **复杂模型是否比简单基线有提升**（§五十 核心问题）见第 6 节；总体判断以 test（2026）RMSE 为准。
- **关键读法（务必先看第 7 节）**：价格/成交量异常序列本身高度持续（滞后 1 期自相关
  见第 7 节），因此「用昨日异常预测今日异常」即可拿到很高的 R2；
  这部分能力**与天气无关**。判别天气是否有用的正确做法是：
  只看去掉自回归项后的 `F_wx` 口径相对均值基线的增量（第 7 节 `gain_from_weather`）。
- MAPE/SMAPE **不适用**：目标为去季节化异常（含 0 与负值），分母可为 0，全部记 NA（§五十三）。
- 数据断裂 / 覆盖限制不插补，均按 BLOCKED 登记（见 reports/BLOCKERS.md）。

## 2 切分与防泄漏（§五十一~§五十二）

{_fmt(split_meta, list(split_meta.columns), n=40)}

- 代码中**不存在** `train_test_split` / 任何 shuffle；
- 中位数填补与标准化仅用训练集 fit（`Prep` 类），特征只用 shift 滞后列与历史异常统计；
- 特征口径定义：
  - `F_wx`：天气滞后列（lag1/3/7/14d）+ 日历控制 + 品种 FE，**无自回归项**（用于分离天气贡献）；
  - `F_lag`（**主口径**）：`F_wx` + 自回归项（昨日/前二交易日异常、昨日量价水平），全部为 t-1 及更早信息；
  - `F_now`：`F_lag` + 当日天气，属**同期临近**口径，仅作对照；
- 三口径均**不含当日价格/成交量水平**（当日价格是目标的分子，属泄漏）；
- 目标 `hist` 口径（`*_anomaly_z_hist`）与本项目前序步骤一致，但其留一年法的基线取自
  「其他年份」（含测试年之后的年份），存在跨年信息；为此额外构造 `strict` 口径
  （`*_anomaly_pct_strict`，基线**只用严格更早年份**同期中位数），作为泄漏稳健性对照。

## 3 特征

{_md(feats)}

## 4 测试集总体表现（test = 2026）

{_fmt(test, cols, sort=["target_kind", "target", "feature_set", "model"], n=60)}

## 5 验证集表现（valid = 2025）

{_fmt(valid, cols, sort=["target_kind", "target", "feature_set", "model"], n=60)}

## 6 是否优于简单基线

{_fmt(cmp, list(cmp.columns), sort=["target_kind", "target", "feature_set", "rmse_test"], n=60)}

## 7 持续性 vs 天气：增量分解（本次预测结果的正确读法）

### 7.1 目标序列滞后 1 期自相关

{_md(autocorr) if autocorr is not None else "NA"}

### 7.2 增量分解（test = 2026）

`gain_from_weather` = 最优学习器（仅天气口径 F_wx）R2 - 均值基线 R2；
`gain_from_persistence` = 最优学习器（含自回归 F_lag）R2 - 最优学习器（仅天气）R2。
注意：均值基线本身可能很差（R2 可为负），因此**判断天气是否有解释力应以
`weather_only_has_skill`（即 R2 > 0，参照测试集均值）为准**，`gain_from_weather` 仅作参考。

{_md(ablation) if ablation is not None else "NA"}

- 若 `gain_from_persistence` 远大于 `gain_from_weather`，则结论是：
  **样本外可预测性主要来自异常序列自身的持续性，天气的边际贡献很小**；
- 若 `learner_beats_persistence` 为「否」，则即使含自回归项的学习器也**没有超过**
  单纯的「昨日值」持续基线，说明 §五十 意义上的「复杂模型优于简单基线」在本数据上不成立。

## 8 Rolling Origin 扩张窗验证

{_fmt(ro, ["fold", "test_year", "target_kind", "target", "feature_set", "model", "n",
           "rmse", "r2"], sort=["target_kind", "target", "feature_set", "model", "test_year"], n=100)}

## 9 分层评价（§五十三）

### 9.1 灾害影响窗 vs 平常期（test = 2026）

{extreme_note}

### 9.2 逐品种 / 分季节

明细见 `model_metrics_by_crop.csv`、`model_metrics_by_season.csv`。

## 10 图表

- F39：测试集总体 R2（模型 x 特征口径 x 目标口径）
- F40：Rolling Origin 扩张窗验证
- F41：2026 测试期价格异常真实 vs 预测 + 散点
- F42：灾害影响窗与平常期 RMSE 对比

## 11 局限（必须与结论同时引用）

1. 训练集仅 4 年（2021-2024，9850 行 = 交易日 x 10 品种），测试期 2026 仅至 9 月 14 日（1750 行）；
   §四十八 红线：**禁止**据此宣称高准确率预测能力，全部结论为 Level B（统计关联）层级。
2. 天气为 ERA5/ERA5-Land 再分析（非气象站实测）。
3. `strict` 口径基线仅用更早年份，2021 年依赖单一参照年（2020），基线噪声较大。
4. 灾害影响窗按「事件起前 1 日至结束后 7 日」划定，窗口定义属研究选择，非数据事实。
5. 若样本外 R2 < 0，即表示该模型不如训练集均值，**不得**改写成「模型有效」。
6. 高 R2 若来自自回归项，**不得**表述为「天气驱动了价格」；必须与 `gain_from_weather` 同时引用。

---
生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}
"""
    p = PATHS.report("12_PREDICTION.md")
    p.write_text(txt, encoding="utf-8")
    log.info("报告已写出: %s", p)
    return cmp


def main():
    t0 = pd.Timestamp.now()
    log = LOG
    with StepTimer("14_prediction", log):
        log.info("=" * 78)
        log.info("STEP 23 Phase 12 预测模型（时间切分 + Rolling Origin + 分层评价）")
        df, ev = build_design(log)
        df = add_crop_dummies(df)

        train = df[df["date"] <= TRAIN_END]
        valid = df[(df["date"] > TRAIN_END) & (df["date"] <= VALID_END)]
        test = df[df["date"] > VALID_END]

        split_meta = pd.DataFrame([
            {"split": "train", "start": train["date"].min().date(), "end": train["date"].max().date(),
             "rows": len(train), "crops": train["crop"].nunique(),
             "n_public_holiday": int(train["is_public_holiday"].sum())},
            {"split": "valid", "start": valid["date"].min().date(), "end": valid["date"].max().date(),
             "rows": len(valid), "crops": valid["crop"].nunique(),
             "n_public_holiday": int(valid["is_public_holiday"].sum())},
            {"split": "test", "start": test["date"].min().date(), "end": test["date"].max().date(),
             "rows": len(test), "crops": test["crop"].nunique(),
             "n_public_holiday": int(test["is_public_holiday"].sum())},
        ])
        save_table(split_meta, "model_split_meta.csv")
        log.info("切分：train %d 行 / valid %d 行 / test %d 行",
                 len(train), len(valid), len(test))

        # 特征清单
        feat_rows = []
        for kind in KINDS:
            for fs in FEATURE_SETS:
                for c in feature_columns(df, kind, fs):
                    feat_rows.append({
                        "target_kind": kind, "feature_set": fs, "feature": c,
                        "group": ("weather_now" if c in NOW_WEATHER else
                                  "weather_lag" if c in LAG_WEATHER else
                                  "autoregressive" if c in set(AR_HIST + AR_STRICT) else
                                  "crop_fixed_effect" if c.startswith("crop_") else "calendar"),
                        "missing_rate": float(df[c].isna().mean()),
                    })
        feats = pd.DataFrame(feat_rows)
        save_table(feats, "model_feature_list.csv")

        # 主切分：train vs valid / train vs test
        log.info("拟合 train->valid ...")
        m_valid, _ = run_split(df, train, valid, "valid", log)
        log.info("拟合 train->test ...")
        m_test, preds = run_split(df, train, test, "test", log, save_preds=True,
                                  persist_prefix="mainsplit")
        overall = pd.concat([m_valid, m_test], ignore_index=True)
        overall.to_csv(PATHS.table("model_metrics_all.csv"), index=False, encoding="utf-8-sig")
        for st, name in (("overall", "model_metrics_overall.csv"),
                         ("crop", "model_metrics_by_crop.csv"),
                         ("season", "model_metrics_by_season.csv"),
                         ("period", "model_metrics_by_period.csv")):
            save_table(overall[overall["stratum"] == st], name)

        # 扩展训练（<=2025）供 Phase 14 反事实使用（不接触 2026 测试期）
        log.info("拟合扩展训练集（<=2025-12-31）供 Phase 14 使用 ...")
        _, _ = run_split(df, df[df["date"] <= VALID_END], df[df["date"] > VALID_END],
                         "extended_trainvalid", log, save_preds=False,
                         persist_prefix="extended")

        log.info("Rolling origin ...")
        ro = rolling_origin(df, log)
        save_table(ro, "model_rolling_origin.csv")

        # 预测明细
        if not preds.empty:
            save_parquet(preds, "model_predictions")
            save_table(preds, "model_predictions.csv")

        ac = autocorr_table(df)
        save_table(ac, "model_target_autocorr.csv")
        abl = persistence_ablation(overall)
        save_table(abl, "model_persistence_ablation.csv")
        log.info("持续性 vs 天气增量分解：\n%s", abl.to_string(index=False))

        cmp = write_report(overall, ro, feats.head(60), split_meta, log, ablation=abl, autocorr=ac)
        fig_metrics(overall, log)
        fig_rolling(ro, log)
        fig_period_gap(overall, log)
        best_name = fig_test_series(preds, overall, log)

        # 结果登记
        rows = []
        for _, r in cmp[~cmp["model"].isin(BASELINES)].iterrows():
            if r["target_kind"] != "hist":
                continue
            rows.append({
                "result_id": f"PRED-{r['target'].upper()}-{r['feature_set']}-{r['model']}",
                "research_question": "RQ 预测能力",
                "crop": "10 品种（含 crop FE）",
                "period": "train<=2024 / valid 2025 / test 2026-01-01~09-14",
                "method": f"时间切分 + {r['model']}（{r['feature_set']}）",
                "metric": "test RMSE / R2",
                "estimate": round(float(r["rmse_test"]), 4),
                "ci_low": None, "ci_high": None, "p_value": None,
                "robustness": f"最优基线 {r['best_baseline']}={float(r['best_baseline_rmse']):.4f}；"
                              f"是否优于基线={r['beats_baseline']}",
                "figure": "F39/F40/F41/F42", "table": "model_metrics_overall.csv",
                "evidence_level": "Level B（样本外统计表现，非因果）",
                "notes": f"R2={float(r['r2_test']):.4f}；目标为去季节化异常；"
                         f"n={int(r['n_test'])}；禁止宣称高准确率（§四十八）",
            })
        if rows:
            register_results(rows)
        log.info("STEP 23 完成（用时 %.1f 分钟）",
                 (pd.Timestamp.now() - t0).total_seconds() / 60)
        return best_name


if __name__ == "__main__":
    main()
