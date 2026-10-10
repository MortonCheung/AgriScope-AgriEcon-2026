# -*- coding: utf-8 -*-
"""Phase 15 / 开源 P0: 模型解释（EBM 内在解释 + SHAP + 线性系数）。

注意：解释的是「模型决策依据」，不是因果效应。
输出 feature importance 时一律表述为「对模型预测的贡献」，禁止写成「导致价格上涨」。
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path


def _final_estimator(pipe):
    if hasattr(pipe, "steps"):
        return pipe.steps[-1][1]
    return pipe


def _transform(pipe, X: pd.DataFrame) -> np.ndarray:
    """通过 pipeline 的前置步骤（imputer/scaler）变换特征。"""
    Xt = X
    if hasattr(pipe, "steps"):
        for name, step in pipe.steps[:-1]:
            Xt = step.transform(Xt)
    return np.asarray(Xt)


def explain_model(artifact: Dict, X: pd.DataFrame, sample_n: int = 300,
                  seed: int = 42, local_rows: Optional[pd.DataFrame] = None) -> Dict:
    """返回 {kind, global_importance (pd.DataFrame), shap_values(可选), local(可选), note}"""
    pipe = artifact.get("model")
    feature_cols = artifact["feature_cols"]
    est = _final_estimator(pipe)
    Xf = X[feature_cols]
    out: Dict = {"algorithm": artifact.get("algorithm"), "kind": None, "note": None}

    # ---- EBM：内在可解释 ----
    if est.__class__.__name__ == "ExplainableBoostingRegressor":
        try:
            eg = est.explain_global()
            d = eg.data()
            imp = pd.DataFrame({"feature": d["names"], "importance": d["scores"]}) \
                .sort_values("importance", ascending=False)
            out["kind"] = "ebm_global"
            out["global_importance"] = imp
            out["note"] = "EBM 学到的可加形状函数重要性（对预测的贡献，不是因果）"
            if local_rows is not None:
                el = est.explain_local(local_rows[feature_cols])
                dd = el.data(0)
                out["local"] = {"names": dd["names"], "scores": list(np.asarray(dd["scores"]).ravel())}
            # 交互项
            try:
                inter = eg.data()  # EBM global 已汇总；交互项在 est.term_names_/attribute
                names = getattr(est, "term_names_", None)
                out["term_names"] = list(names) if names is not None else None
            except Exception:
                pass
            return out
        except Exception as e:
            out["note"] = f"EBM explain failed: {e}"

    # ---- 树模型 / Boosting：SHAP ----
    if est.__class__.__name__ in ("RandomForestRegressor", "ExtraTreesRegressor",
                                  "HistGradientBoostingRegressor", "LGBMRegressor",
                                  "XGBRegressor", "CatBoostRegressor"):
        try:
            import shap
            Xt = _transform(pipe, Xf)
            rng = np.random.RandomState(seed)
            idx = rng.choice(len(Xt), size=min(sample_n, len(Xt)), replace=False)
            Xs = Xt[idx]
            explainer = shap.TreeExplainer(est)
            sv = explainer.shap_values(Xs)
            sv = np.asarray(sv)
            if sv.ndim == 3:
                sv = sv[:, :, 0]
            imp = pd.DataFrame({"feature": feature_cols,
                                "mean_abs_shap": np.abs(sv).mean(axis=0)}) \
                .sort_values("mean_abs_shap", ascending=False)
            out["kind"] = "shap_tree"
            out["global_importance"] = imp
            out["shap_values"] = pd.DataFrame(sv, columns=feature_cols)
            out["shap_base_value"] = float(np.asarray(explainer.expected_value).ravel()[0])
            out["note"] = "SHAP 值（对模型预测的贡献，不是因果效应）"
            if local_rows is not None:
                Xl = _transform(pipe, local_rows[feature_cols])
                lv = np.asarray(explainer.shap_values(Xl))
                if lv.ndim == 3:
                    lv = lv[:, :, 0]
                out["local"] = {"shap": lv.tolist(), "feature_cols": feature_cols}
            return out
        except Exception as e:
            out["note"] = f"SHAP failed: {e}; fallback to permutation importance"

    # ---- 线性模型：系数 ----
    if est.__class__.__name__ in ("Ridge", "ElasticNet", "LinearRegression"):
        coef = np.ravel(getattr(est, "coef_", []))
        imp = pd.DataFrame({"feature": feature_cols[:len(coef)], "coef": coef}) \
            .assign(abs_coef=lambda d: d["coef"].abs()) \
            .sort_values("abs_coef", ascending=False)
        out["kind"] = "linear_coef"
        out["global_importance"] = imp
        out["note"] = "线性系数（标准化特征；表示模型权重，不是因果）"
        return out

    out["kind"] = "none"
    out["note"] = "该模型族无内置解释器"
    return out


def permutation_importance(artifact: Dict, X: pd.DataFrame, y: np.ndarray,
                           n_repeats: int = 5, seed: int = 42) -> pd.DataFrame:
    from sklearn.inspection import permutation_importance as pi
    r = pi(artifact["model"], X[artifact["feature_cols"]], y,
           n_repeats=n_repeats, random_state=seed, n_jobs=-1, scoring="neg_mean_absolute_error")
    return pd.DataFrame({"feature": artifact["feature_cols"],
                         "importance_mean": r.importances_mean,
                         "importance_std": r.importances_std}) \
        .sort_values("importance_mean", ascending=False)