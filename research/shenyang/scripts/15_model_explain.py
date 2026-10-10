"""STEP 24：Phase 13 解释模型（§五十四~§五十五）。

对应任务书：
  §五十四 使用 SHAP / PDP / ALE；**相关性较强时优先参考 ALE**；回答三个问题：
          1) 哪些天气变量最重要？
          2) 在什么区间风险开始快速变化？
          3) 不同蔬菜的响应曲线是否不同？
  §五十五 解释模型**不能替代因果**：SHAP 高不代表该变量导致了结果，
          只能表示「在预测模型中具有较高贡献」，正式报告必须区分。

设计（预登记）：
  - 解释对象 = `14_prediction.py` 训练并持久化的 LightGBM（main split：训练 <=2024-12-31），
    直接读取模型文件与预处理参数，**不重新训练**，保证与 STEP 23 指标完全对应；
  - 解释数据 = test 集（2026-01-01~2026-09-14），SHAP 采用该期全样本（10 品种）；
  - 特征口径：
    * `F_lag`（主口径，含自回归）—— 反映模型真正依赖什么；
    * `F_wx`（仅天气滞后，无自回归）—— 剥离持续性后，天气变量的相对贡献；
    * `F_now`（含当日天气）—— 天气响应曲线的「同期」版本。
  - 曲线：对 SHAP 排名前 5 的**天气**特征同时输出 PDP 与 ALE（§五十四：本数据天气类特征
    间相关性中等偏高，**结论以 ALE 为主**，PDP 仅作对照展示二者差异）；
  - 分品种响应（问题 3）：逐品种单独训练 LightGBM（F_wx、hist 口径、训练 <=2024），
    对 SHAP 排名第 1 的天气特征输出 ALE 曲线对比（探索性，品种内样本 985 行，Level B）；
  - 所有输出均标注 `causal_claim_allowed=false`。

产出：
  outputs/tables/model_shap_importance.csv      SHAP 平均绝对贡献排名
  outputs/tables/model_shap_by_crop.csv         SHAP 按品种汇总（天气特征）
  outputs/tables/model_pdp_curves.csv           PDP 曲线
  outputs/tables/model_ale_curves.csv           ALE 曲线（主）
  outputs/tables/model_ale_by_crop.csv          逐品种 ALE 曲线
  outputs/figures/F43..F45
  reports/13_MODEL_EXPLAIN.md
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, register_results,
    render_figure, save_table, set_seed, setup_matplotlib,
)

P12 = importlib.import_module("14_prediction")
MOD = "15_model_explain"
LOG = get_logger(MOD)
CORE_CROPS: List[str] = list(CROPS_CFG["core_crops"])
TRAIN_END = pd.Timestamp(ANALYSIS["modeling"]["train_end"])
VALID_END = pd.Timestamp(ANALYSIS["modeling"]["valid_end"])
SEED = set_seed()

EXPLAIN_TARGETS = ["price", "volume"]
EXPLAIN_SETS = ["F_lag", "F_wx", "F_now"]
TOP_K_WEATHER = 5
ALE_BINS = 20
N_SHAP_SAMPLE = 1750          # test 期全样本
WEATHER_ALL = set(P12.LAG_WEATHER) | set(P12.NOW_WEATHER)


# -----------------------------------------------------------------------------
# 载入模型与数据
# -----------------------------------------------------------------------------
def load_prep(target: str, fs: str, prefix: str = "mainsplit") -> Dict:
    p = PATHS.dir("models") / f"{prefix}_hist_{target}_{fs}_prep.json"
    if not p.exists():
        raise FileNotFoundError(f"缺少 STEP 23 模型元数据：{p}")
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def transform(df: pd.DataFrame, meta: Dict) -> np.ndarray:
    cols = meta["features"]
    med = pd.Series(meta["prep"]["median"])
    mu = pd.Series(meta["prep"]["mean"])
    sd = pd.Series(meta["prep"]["scale"]).replace(0, 1.0)
    X = df[cols].fillna(med)
    X = (X - mu) / sd
    return X.to_numpy(dtype=float)


def load_booster(target: str, fs: str, prefix: str = "mainsplit"):
    import lightgbm as lgb
    p = PATHS.dir("models") / f"{prefix}_hist_{target}_{fs}_lightgbm.txt"
    if not p.exists():
        raise FileNotFoundError(f"缺少 STEP 23 模型文件：{p}")
    return lgb.Booster(model_file=str(p))


# -----------------------------------------------------------------------------
# SHAP / PDP / ALE
# -----------------------------------------------------------------------------
def shap_table(booster, X: np.ndarray, cols: List[str], df: pd.DataFrame,
               target: str, fs: str) -> pd.DataFrame:
    import shap
    expl = shap.TreeExplainer(booster)
    sv = expl.shap_values(X[:N_SHAP_SAMPLE], check_additivity=False)
    sv = np.asarray(sv, dtype=float)
    if sv.ndim == 3:
        sv = sv[:, :, 0]
    imp = np.abs(sv).mean(axis=0)
    rows = []
    for j, c in enumerate(cols):
        rows.append({
            "target": target, "feature_set": fs, "feature": c,
            "is_weather": c in WEATHER_ALL,
            "mean_abs_shap": float(imp[j]),
            "share_of_total": float(imp[j] / imp.sum()) if imp.sum() > 0 else np.nan,
            "causal_claim_allowed": False,
        })
    out = pd.DataFrame(rows).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out, sv


def shap_by_crop(sv: np.ndarray, cols: List[str], df: pd.DataFrame,
                 target: str, fs: str) -> pd.DataFrame:
    rows = []
    crops = df["crop"].to_numpy()[:sv.shape[0]]
    for j, c in enumerate(cols):
        if c not in WEATHER_ALL:
            continue
        for cr in CORE_CROPS:
            m = crops == cr
            if m.sum() < 30:
                continue
            rows.append({"target": target, "feature_set": fs, "crop": cr, "feature": c,
                         "mean_abs_shap": float(np.abs(sv[m, j]).mean())})
    return pd.DataFrame(rows)


def pdp_1d(pred, X: np.ndarray, j: int, grid: np.ndarray) -> np.ndarray:
    out = np.empty(len(grid))
    for i, v in enumerate(grid):
        Xm = X.copy()
        Xm[:, j] = v
        out[i] = float(np.mean(pred(Xm)))
    return out


def ale_1d(pred, X: np.ndarray, j: int, bins: int = ALE_BINS) -> Tuple[np.ndarray, np.ndarray]:
    """标准 1 维 ALE：分位分箱 + 箱内局部差分的累积。"""
    q = np.unique(np.quantile(X[:, j], np.linspace(0, 1, bins + 1)))
    if len(q) < 3:
        return np.array([]), np.array([])
    idx = np.clip(np.digitize(X[:, j], q[1:-1], right=True), 0, len(q) - 2)
    eff = np.zeros(len(q) - 1)
    for k in range(len(q) - 1):
        m = idx == k
        if m.sum() == 0:
            continue
        Xl, Xr = X[m].copy(), X[m].copy()
        Xl[:, j], Xr[:, j] = q[k], q[k + 1]
        eff[k] = float(np.mean(pred(Xr) - pred(Xl)))
    ale = np.concatenate([[0.0], np.cumsum(eff)])
    widths = np.diff(q)
    center = float(np.sum(eff * widths) / np.sum(widths))
    # 输出每个箱边界的 ALE 值（长度 = len(q)），中心化
    ale = ale - center
    mid = (q[:-1] + q[1:]) / 2.0
    return mid, ale[1:]


def to_original(z: float, meta: Dict, col: str) -> float:
    mu = meta["prep"]["mean"].get(col, 0.0)
    sd = meta["prep"]["scale"].get(col, 1.0) or 1.0
    return float(mu + z * sd)


# -----------------------------------------------------------------------------
# 图
# -----------------------------------------------------------------------------
def fig_shap(imp_all: pd.DataFrame, log):
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.2))
    for ax, target in zip(axes, EXPLAIN_TARGETS):
        s = imp_all[(imp_all["target"] == target)].groupby("feature")["mean_abs_shap"].max()
        s = s.sort_values(ascending=False).head(15)[::-1]
        cols = ["#c9b48f" if f in WEATHER_ALL else "#9fb6c9" for f in s.index]
        ax.barh(s.index, s.values, color=cols)
        ax.set_title(f"{target} 异常：LightGBM 特征贡献（SHAP 平均绝对值）")
        ax.set_xlabel("mean |SHAP|（模型贡献，非因果效应）")
    fig.suptitle("图 F43：SHAP 特征贡献排名（test=2026，模型=STEP 23 持久化的 LightGBM）\n"
                 "沙色 = 天气类特征；蓝色 = 自回归 / 日历 / 品种类特征；"
                 "SHAP 高不等于因果关系（§五十五）",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, "F43_shap_importance.png")


def fig_ale(pdp_df: pd.DataFrame, ale_df: pd.DataFrame, log):
    plt = setup_matplotlib()
    sub = ale_df[(ale_df["feature_set"] == "F_now")]
    if sub.empty:
        sub = ale_df[ale_df["feature_set"] == "F_wx"]
    feats = list(sub.groupby("feature")["mean_abs_shap"].max()
                 .sort_values(ascending=False).head(4).index)
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.6))
    for ax, f in zip(axes.ravel(), feats):
        for target, color in (("price", "#2f6f9f"), ("volume", "#a8624a")):
            a = sub[(sub["feature"] == f) & (sub["target"] == target)].sort_values("z_value")
            if a.empty:
                continue
            ax.plot(a["z_value"], a["ale"], marker="o", ms=3, lw=1.6, color=color,
                    label=f"ALE：{target}")
            p = pdp_df[(pdp_df["feature"] == f) & (pdp_df["target"] == target)
                       & (pdp_df["feature_set"] == sub["feature_set"].iloc[0])].sort_values("z_value")
            if not p.empty:
                ax.plot(p["z_value"], p["pdp_centered"], ls="--", lw=1.1, color=color, alpha=0.6,
                        label=f"PDP：{target}")
        ax.axhline(0, color="#888888", lw=0.9)
        ax.set_title(f)
        ax.set_xlabel("特征值（标准化 z；0 = 全序列均值）")
        ax.set_ylabel("对预测值的贡献（目标单位）")
        ax.legend(fontsize=7.5)
    fig.suptitle("图 F44：ALE 曲线（实线，主）与 PDP 曲线（虚线，对照），口径 F_now\n"
                 "特征间相关时以 ALE 为准（§五十四）；曲线为模型贡献，不构成因果效应",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, "F44_ale_pdp_curves.png")


def fig_ale_by_crop(crop_df: pd.DataFrame, log):
    plt = setup_matplotlib()
    if crop_df.empty:
        return
    feats = list(crop_df.groupby("feature")["ale_abs_mean"].max().sort_values(ascending=False)
                 .head(3).index)
    fig, axes = plt.subplots(1, len(feats), figsize=(5.0 * len(feats), 4.4), squeeze=False)
    cmap = plt.get_cmap("tab10")
    for ax, f in zip(axes[0], feats):
        d = crop_df[crop_df["feature"] == f]
        for i, (cr, g) in enumerate(d.groupby("crop")):
            g = g.sort_values("z_value")
            ax.plot(g["z_value"], g["ale"], lw=1.5, color=cmap(i % 10), label=cr)
        ax.axhline(0, color="#888888", lw=0.9)
        ax.set_title(f)
        ax.set_xlabel("特征值（标准化 z）")
        ax.set_ylabel("ALE")
    axes[0][0].legend(fontsize=7, ncol=2)
    fig.suptitle("图 F45：逐品种 ALE 响应曲线（各品种单独训练 LightGBM，F_wx 口径，价格异常）\n"
                 "探索性（品种内样本约 985 行）；曲线差异不等于品种间因果异质性",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, "F45_ale_by_crop.png")


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------
def main():
    with StepTimer("15_model_explain", LOG):
        log = LOG
        log.info("=" * 78)
        log.info("STEP 24 Phase 13 解释模型（SHAP / PDP / ALE；§五十四~§五十五）")

        df, _ = P12.build_design(log)
        df = P12.add_crop_dummies(df)
        test = df[df["date"] > VALID_END].copy()
        train = df[df["date"] <= TRAIN_END].copy()
        log.info("解释数据：test %d 行（含全部 10 品种）；训练 %d 行", len(test), len(train))

        imp_all, pdp_all, ale_all, shapcrop_all, curve_rows = [], [], [], [], []
        for target in EXPLAIN_TARGETS:
            for fs in EXPLAIN_SETS:
                try:
                    meta = load_prep(target, fs)
                    booster = load_booster(target, fs)
                except FileNotFoundError as exc:
                    log.warning("跳过 %s/%s：%s", target, fs, exc)
                    continue
                cols = meta["features"]
                Xte = transform(test, meta)
                pred = lambda X: booster.predict(X)  # noqa: E731

                imp, sv = shap_table(booster, Xte, cols, test, target, fs)
                imp_all.append(imp)
                shapcrop_all.append(shap_by_crop(sv, cols, test, target, fs))

                # 天气特征排名（问题 1）
                w = imp[imp["is_weather"]].head(TOP_K_WEATHER)
                log.info("%s/%s：SHAP 第 1 = %s（占比 %.1f%%）；天气 Top5 = %s",
                         target, fs, imp.iloc[0]["feature"],
                         100 * imp.iloc[0]["share_of_total"], list(w["feature"]))

                for _, r in w.iterrows():
                    j = cols.index(r["feature"])
                    grid = np.unique(np.quantile(Xte[:, j], np.linspace(0, 1, 25)))
                    pdp_v = pdp_1d(pred, Xte, j, grid)
                    pdp_c = pdp_v - np.mean(pdp_v)
                    mid, ale = ale_1d(pred, Xte, j)
                    for z, v in zip(grid, pdp_v):
                        pdp_all.append({"target": target, "feature_set": fs,
                                        "feature": r["feature"], "z_value": float(z),
                                        "original_value": to_original(z, meta, r["feature"]),
                                        "pdp": float(v), "pdp_centered": float(pdp_c[list(grid).index(z)]),
                                        "mean_abs_shap": float(r["mean_abs_shap"])})
                    if len(mid):
                        for z, v in zip(mid, ale):
                            ale_all.append({"target": target, "feature_set": fs,
                                            "feature": r["feature"], "z_value": float(z),
                                            "original_value": to_original(z, meta, r["feature"]),
                                            "ale": float(v),
                                            "mean_abs_shap": float(r["mean_abs_shap"])})

        imp_df = pd.concat(imp_all, ignore_index=True)
        save_table(imp_df, "model_shap_importance.csv")
        save_table(pd.concat(shapcrop_all, ignore_index=True), "model_shap_by_crop.csv")
        pdp_df = pd.DataFrame(pdp_all)
        ale_df = pd.DataFrame(ale_all)
        save_table(pdp_df, "model_pdp_curves.csv")
        save_table(ale_df, "model_ale_curves.csv")

        # 问题 3：逐品种响应曲线（价格异常 / F_wx / 训练 <=2024）
        crop_rows = []
        top_w = (imp_df[(imp_df["target"] == "price") & (imp_df["feature_set"] == "F_wx")
                        & (imp_df["is_weather"])]
                 .head(2)["feature"].tolist())
        if top_w:
            meta = load_prep("price", "F_wx")
            cols = meta["features"]
            Xtr = transform(train, meta)
            ytr = train[P12.TARGETS["price"]].to_numpy(dtype=float)
            import lightgbm as lgb
            for cr, gtr in train.assign(_i=np.arange(len(train))).groupby("crop"):
                idx = gtr["_i"].to_numpy()
                m = lgb.LGBMRegressor(**P12.LGBM_PARAMS)
                m.fit(Xtr[idx], ytr[idx])
                Xc = Xtr[idx]
                for f in top_w:
                    j = cols.index(f)
                    mid, ale = ale_1d(lambda X: m.predict(X), Xc, j)
                    if not len(mid):
                        continue
                    for z, v in zip(mid, ale):
                        crop_rows.append({"crop": cr, "target": "price", "feature_set": "F_wx",
                                          "feature": f, "z_value": float(z),
                                          "original_value": to_original(z, meta, f),
                                          "ale": float(v), "n_train_crop": int(len(idx))})
            crop_df = pd.DataFrame(crop_rows)
            if not crop_df.empty:
                crop_df["ale_abs_mean"] = (crop_df.groupby(["crop", "feature"])["ale"]
                                           .transform(lambda s: float(np.mean(np.abs(s)))))
            save_table(crop_df, "model_ale_by_crop.csv")
            fig_ale_by_crop(crop_df, log)

        fig_shap(imp_df, log)
        fig_ale(pdp_df, ale_df, log)

        # ---- 报告 ----
        def _rank(t, fs, only_weather=False, n=10):
            d = imp_df[(imp_df["target"] == t) & (imp_df["feature_set"] == fs)]
            if only_weather:
                d = d[d["is_weather"]]
            d = d.head(n)[["rank", "feature", "is_weather", "mean_abs_shap", "share_of_total"]]
            d = d.copy()
            for c in ("mean_abs_shap", "share_of_total"):
                d[c] = d[c].map(lambda v: f"{v:.4f}")
            d["is_weather"] = d["is_weather"].map(lambda v: "天气" if v else "非天气")
            head = "| " + " | ".join(d.columns) + " |"
            sep = "| " + " | ".join("---" for _ in d.columns) + " |"
            body = ["| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)]
            return "\n".join([head, sep] + body)

        # 天气特征 ALE 斜率（风险开始快速变化：斜率绝对值最大处）
        slope_rows = []
        for (t, fs_, f), g in ale_df.groupby(["target", "feature_set", "feature"]):
            g = g.sort_values("z_value")
            if len(g) < 4:
                continue
            dz = np.diff(g["z_value"].to_numpy())
            da = np.diff(g["ale"].to_numpy())
            sl = np.where(dz == 0, np.nan, da / dz)
            k = int(np.nanargmax(np.abs(sl)))
            i = k + 1
            slope_rows.append({
                "target": t, "feature_set": fs_, "feature": f,
                "n_bins": len(g),
                "ale_range": float(g["ale"].max() - g["ale"].min()),
                "max_abs_slope_z": float(sl[k]),
                "z_at_max_slope": float(g["z_value"].iloc[i]),
                "original_value_at_max_slope": float(g["original_value"].iloc[i]),
                "z_at_ale_min": float(g.loc[g["ale"].idxmin(), "z_value"]),
                "z_at_ale_max": float(g.loc[g["ale"].idxmax(), "z_value"]),
            })
        slope_df = pd.DataFrame(slope_rows)
        save_table(slope_df, "model_ale_slope.csv")

        txt = f"""# 13 解释模型（Phase 13，§五十四~§五十五）

## 0 必读声明（§五十五）

- 本文件所有 SHAP / PDP / ALE 结果**只表示变量在预测模型中的贡献**，
  **不表示因果关系**；`causal_claim_allowed = false` 贯穿全部输出表。
- 正式报告引用本文件时，必须同时引用 STEP 23 第 7 节的持续性-天气增量分解：
  若模型的样本外解释力主要来自自回归项（昨日异常），则天气特征的 SHAP 排名**不能**
  被解读为「天气影响价格」。
- 曲线仅描述模型行为，模型本身在外样本上可能并没有天气解释力（R2 可能 <= 0）。

## 1 解释对象

- 模型：STEP 23 训练并持久化的 LightGBM（`models/mainsplit_hist_*`），训练期 <= 2024-12-31；
- 解释数据：test 期（2026-01-01 至 2026-09-14，{len(test)} 行，10 品种）；
- 特征口径：`F_lag`（主口径，含自回归）/ `F_wx`（仅天气滞后）/ `F_now`（含当日天气）；
- ALE 分箱 = {ALE_BINS} 个分位箱；PDP 网格 = 25 个分位点；曲线均中心化。

## 2 问题 1：哪些天气变量最重要（SHAP 平均绝对值）

### 2.1 价格异常（全部特征）

{_rank("price", "F_lag", n=10)}

### 2.2 价格异常（仅天气特征）

{_rank("price", "F_wx", only_weather=True, n=10)}

### 2.3 成交量异常（全部特征）

{_rank("volume", "F_lag", n=10)}

### 2.4 成交量异常（仅天气特征）

{_rank("volume", "F_wx", only_weather=True, n=10)}

> 读法：若「全部特征」排名前列几乎都是自回归 / 日历 / 品种特征，而天气特征 SHAP 很小，
> 则该模型的可预测性来自序列持续性而非天气（与 STEP 23 的分解一致）。

## 3 问题 2：什么区间风险开始快速变化（ALE 斜率）

ALE 曲线斜率绝对值最大处 = 模型输出随该变量变化最快的区间（**模型内部行为，非观测因果**）。

{P12._md(slope_df.round(4)) if len(slope_df) else "NA"}

ALE 与 PDP 曲线明细见 `model_ale_curves.csv`、`model_pdp_curves.csv`（F44）。
本数据天气类特征间相关中等偏高，按 §五十四 **以 ALE 为准，PDP 仅作对照**。

## 4 问题 3：不同蔬菜的响应曲线是否不同

逐品种单独训练 LightGBM（`F_wx` 口径、价格异常、训练 <=2024、约 985 行/品种），
对 SHAP 排名前 2 的天气特征输出 ALE 曲线（F45，明细 `model_ale_by_crop.csv`）。

- 若各品种曲线方向/幅度接近 → 未观察到品种间响应差异；
- 若差异明显，仍属**探索性**（品种内样本小、单一模型族、无多重检验校正），
  只能写「响应曲线存在差异」，不得写「某品种对某天气因子的因果敏感度更高」。

## 5 图表

- F43：SHAP 特征贡献排名（价格 / 成交量）
- F44：ALE（主）与 PDP（对照）曲线，口径 F_now
- F45：逐品种 ALE 响应曲线（探索性）

## 6 局限

1. 解释的是**模型**，不是数据生成过程；LightGBM 的贡献分配依赖其树结构与正则化参数；
2. test 期仅 2026 年 1-9 月，ALE 曲线在极端端点的箱样本很少，端点噪声大；
3. 特征间相关（如各滞后窗降水）会使 PDP 有偏，故以 ALE 为主；
4. 逐品种模型样本小（约 985 行），且未做多重检验校正，属探索性（Level B）。

---
生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}
"""
        p = PATHS.report("13_MODEL_EXPLAIN.md")
        p.write_text(txt, encoding="utf-8")
        log.info("报告已写出: %s", p)

        # 结果登记（只登记「天气特征在模型中的贡献」这一层级的事实）
        rows = []
        for target in EXPLAIN_TARGETS:
            d = imp_df[(imp_df["target"] == target) & (imp_df["feature_set"] == "F_wx")
                       & (imp_df["is_weather"])].head(1)
            if d.empty:
                continue
            r = d.iloc[0]
            rows.append({
                "result_id": f"EXPLAIN-{target.upper()}-TOPWX",
                "research_question": "RQ 天气变量重要性（模型内）",
                "crop": "10 品种（含 crop FE）",
                "period": "test 2026-01-01~2026-09-14",
                "method": f"SHAP（LightGBM，{r['feature_set']} 口径）",
                "metric": "mean|SHAP| 占比",
                "estimate": round(float(r["share_of_total"]), 4),
                "ci_low": None, "ci_high": None, "p_value": None,
                "robustness": "ALE 与 PDP 曲线互验（F44）；逐品种曲线见 F45",
                "figure": "F43/F44/F45", "table": "model_shap_importance.csv",
                "evidence_level": "Level B（模型贡献，非因果）",
                "notes": f"排名第 1 的天气特征 = {r['feature']}；"
                         f"causal_claim_allowed=false；必须与 STEP 23 增量分解同时引用",
            })
        if rows:
            register_results(rows)
        log.info("STEP 24 完成")


if __name__ == "__main__":
    main()
