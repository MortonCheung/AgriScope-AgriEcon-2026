"""Long-horizon RC2: explicit targets, purged evaluation and frozen inference.

Only ``--retrain`` fits estimators. Historical 2026 is a reused retrospective
audit, never an untouched test. The production gate needs future observations.
No Final source, weights, reports or datasets are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

_PIPE = Path(__file__).resolve().parents[0]          # pipelines/long_horizon
ROOT = Path(__file__).resolve().parents[3]           # monorepo 根（data/ 与 models/ 所在）
ARTIFACTS = _PIPE / "artifacts" / "v2"
MODEL_DIR = ROOT / "models" / "long_horizon"
INDEX_PATH = MODEL_DIR / "index.json"
DATA_PATH = ROOT / "data" / "model_ready" / "snapshots" / "final_v1" / "datasets" / "decision_dataset_沈阳.parquet"
HORIZONS = (30, 60, 90, 120, 150, 180)
TARGET_TYPES = ("cycle_market_average", "harvest_market_price")
MODEL_VERSION = "long_horizon_v2_rc2"
FEATURES = ["price_per_kg", "sin_doy", "cos_doy", "future_sin_doy", "future_cos_doy",
            "lag7", "lag14", "lag30", "lag60", "lag90", "lag365",
            "ma7_obs", "ma14_obs", "ma30_obs", "ma60_obs", "std30_obs",
            "return30", "return90", "seasonal_naive", "same_season_mean", "same_season_median"]
BASELINES = ("last_value", "seasonal_naive", "same_season_mean", "same_season_median")
PHASES = (
    {"name": "development", "start": "2023-01-01", "end": "2023-12-31", "train_end": "2022-12-31"},
    {"name": "tuning", "start": "2024-01-01", "end": "2024-12-31", "train_end": "2023-12-31"},
    {"name": "calibration", "start": "2025-01-01", "end": "2025-12-31", "train_end": "2024-12-31"},
    {"name": "retrospective_audit_reused", "start": "2026-01-01", "end": "2026-09-14", "train_end": "2025-12-31"},
)
CONFIG = {
    "schema_version": "2.0.1", "model_version": MODEL_VERSION, "random_seed": 17,
    "phases": PHASES, "horizons": HORIZONS, "features": FEATURES,
    "history_status": "EVALUATION_CONTAMINATED_BY_PRIOR_SELECTION",
    "untouched_period": None, "prospective_origin_not_before": "2026-10-08",
    "target_candidates": ["endpoint", "harvest_centered_7", "harvest_centered_14", "harvest_centered_30",
                          "harvest_post_7", "harvest_post_14", "harvest_post_30", "cycle_market_average"],
    "harvest_admissible": ["harvest_centered_7", "harvest_centered_14", "harvest_post_7", "harvest_post_14"],
    "target_selection_rule": "development+tuning baseline mean WAPE; best within 2% tie: post14, centered14, post7, centered7",
    "business_constraint": "7/14-day sales windows are operational default; 30-day sales duration is not confirmed and is study-only",
    "min_target_observed_fraction": 0.5, "max_internal_target_gap_days": 10,
    "endpoint_max_backward_gap_days": 3, "min_training_rows": 200,
    "models": {"linear": {}, "elasticnet": {"alpha": 0.02, "l1_ratio": 0.5, "max_iter": 4000},
               "extra_trees": {"n_estimators": 64, "max_depth": 10, "min_samples_leaf": 10},
               "catboost": {"iterations": 80, "depth": 4, "loss_function": "MAE", "thread_count": 2}},
    "practical_gate": {"absolute_gain_pp": 1.0, "relative_gain_fraction": 0.05,
                       "winning_period_fraction": 0.75, "min_periods": 3,
                       "worst_period_degradation_pp": 2.0, "min_final_exposure_blocks": 12,
                       "paired_gain_ci_lower_gt": 0.0, "bootstrap_repetitions": 1000,
                       "calibration_exposure_blocks": 20, "nominal_coverage": 0.8,
                       "coverage_min": 0.7, "coverage_max": 0.9},
    "refit_policy": "selection frozen, then refit matured historical labels; refit model is not re-evaluated on history",
    "selection_score": "tuning WAPE + 0.5*abs(tuning WAPE-development WAPE); baseline simplicity tie within 0.05pp",
    "decision_outcome": "relative harvest price return, equal allocation, no profit claim",
    "invalid_forecast_policy": "nonfinite/nonpositive candidate and inference output visibly fallback to PIT last_value; no arbitrary price floor",
    "decision_comparison_pool": "all compared policies share complete crop/date availability",
}


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


CONFIG_HASH = _hash(CONFIG)


def _json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(x) for x in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(obj).date())
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def target_spec(name: str, horizon: int) -> dict:
    """Return inclusive integer day offsets. Named windows contain exactly w days."""
    if name == "cycle_market_average":
        start, end, width = 1, horizon, horizon
    elif name == "endpoint":
        start = end = horizon
        width = 1
    elif name.startswith("harvest_"):
        _, side, w = name.split("_")
        width = int(w)
        if side == "centered":
            start = horizon - width // 2
        elif side == "post":
            start = horizon
        else:
            raise ValueError(f"unknown target {name}")
        end = start + width - 1
    else:
        raise ValueError(f"unknown target {name}")
    if horizon not in HORIZONS or start <= 0:
        raise ValueError("unsupported horizon or non-future target")
    return {"name": name, "start_offset": start, "end_offset": end, "calendar_days": width,
            "end_exclusive_offset": end + 1, "exposure_spacing_days": max(horizon, end)}


def _normalize(history: pd.DataFrame) -> pd.DataFrame:
    d = history[["date", "crop", "price_per_kg"]].copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    d["price_per_kg"] = pd.to_numeric(d["price_per_kg"], errors="coerce")
    d = d[d["price_per_kg"].notna() & np.isfinite(d["price_per_kg"]) & (d["price_per_kg"] > 0)]
    if d.duplicated(["crop", "date"]).any():
        raise ValueError("duplicate crop/date observations require explicit upstream normalization")
    return d.sort_values(["crop", "date"]).reset_index(drop=True)


def build_base_features(history: pd.DataFrame) -> pd.DataFrame:
    """Rebuild PIT features from observed price history. No target columns required."""
    d = _normalize(history)
    for _, g in d.groupby("crop", sort=False):
        ix = g.index
        dates = g.date.values.astype("datetime64[D]")
        px = g.price_per_kg.to_numpy(float)
        for lag in (7, 14, 30, 60, 90, 365):
            pos = np.searchsorted(dates, dates - np.timedelta64(lag, "D"), side="right") - 1
            d.loc[ix, f"lag{lag}"] = np.where(pos >= 0, px[np.maximum(pos, 0)], np.nan)
        series = pd.Series(px)
        for n in (7, 14, 30, 60):
            d.loc[ix, f"ma{n}_obs"] = series.rolling(n, min_periods=1).mean().to_numpy()
        d.loc[ix, "std30_obs"] = series.rolling(30, min_periods=2).std().fillna(0).to_numpy()
    day = d.date.dt.dayofyear
    d["sin_doy"], d["cos_doy"] = np.sin(2*np.pi*day/365.25), np.cos(2*np.pi*day/365.25)
    for n in (30, 90):
        d[f"return{n}"] = d.price_per_kg / d[f"lag{n}"] - 1
    return d


def add_targets(features: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Observed-only labels; reject incomplete tails and sparse sales windows."""
    d = features.copy()
    d["label_start"] = d.date + pd.to_timedelta(spec["start_offset"], unit="D")
    d["label_end"] = d.date + pd.to_timedelta(spec["end_offset"], unit="D")
    d["actual"] = np.nan
    d["target_observations"] = 0
    d.attrs["target_definition"] = spec["name"]
    for _, g in d.groupby("crop", sort=False):
        dates = g.date.values.astype("datetime64[D]")
        px = g.price_per_kg.to_numpy(float)
        lo_dates = g.label_start.values.astype("datetime64[D]")
        hi_dates = g.label_end.values.astype("datetime64[D]")
        lo = np.searchsorted(dates, lo_dates, side="left")
        hi = np.searchsorted(dates, hi_dates, side="right")
        for j, ix in enumerate(g.index):
            if hi_dates[j] > dates[-1]:
                continue
            if spec["name"] == "endpoint":
                p = hi[j]-1
                if p >= 0 and dates[p] > dates[j] and (hi_dates[j]-dates[p]).astype(int) <= CONFIG["endpoint_max_backward_gap_days"]:
                    d.loc[ix, "actual"] = px[p]
                    d.loc[ix, "target_observations"] = 1
                continue
            count = hi[j]-lo[j]
            d.loc[ix, "target_observations"] = count
            if count < math.ceil(spec["calendar_days"]*CONFIG["min_target_observed_fraction"]):
                continue
            selected_dates = dates[lo[j]:hi[j]]
            if len(selected_dates) > 1 and np.diff(selected_dates).astype(int).max() > CONFIG["max_internal_target_gap_days"]:
                continue
            d.loc[ix, "actual"] = float(px[lo[j]:hi[j]].mean())
    return d


def add_seasonal_features(features: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Align seasonal baselines to future sales dates, using prior-year windows only."""
    d = features.copy()
    for key in ("seasonal_naive", "same_season_mean", "same_season_median"):
        d[key] = np.nan
    for _, g in d.groupby("crop", sort=False):
        dates = g.date.values.astype("datetime64[D]")
        px = g.price_per_kg.to_numpy(float)
        for j, ix in enumerate(g.index):
            values, previous = [], []
            for year_back in range(1, 7):
                start = dates[j] + np.timedelta64(spec["start_offset"]-365*year_back, "D")
                end = dates[j] + np.timedelta64(spec["end_offset"]-365*year_back, "D")
                if end > dates[j]:
                    continue
                lo, hi = np.searchsorted(dates, start, side="left"), np.searchsorted(dates, end, side="right")
                arr = px[lo:hi]
                if spec["name"] == "endpoint" and not len(arr):
                    p = hi-1
                    if p >= 0 and (end-dates[p]).astype(int) <= CONFIG["endpoint_max_backward_gap_days"]:
                        arr = px[p:p+1]
                if len(arr):
                    values.extend(arr.tolist())
                    if year_back == 1:
                        previous = arr.tolist()
            if previous:
                d.loc[ix, "seasonal_naive"] = float(np.mean(previous))
            if values:
                d.loc[ix, "same_season_mean"] = float(np.mean(values))
                d.loc[ix, "same_season_median"] = float(np.median(values))
    center = d.date + pd.to_timedelta((spec["start_offset"]+spec["end_offset"])/2, unit="D")
    d["future_sin_doy"] = np.sin(2*np.pi*center.dt.dayofyear/365.25)
    d["future_cos_doy"] = np.cos(2*np.pi*center.dt.dayofyear/365.25)
    return d


def training_mask(d: pd.DataFrame, cutoff) -> pd.Series:
    """A label must be fully observed at model-fit time, not merely its anchor."""
    cutoff = pd.Timestamp(cutoff)
    return (d.date <= cutoff) & (d.label_end <= cutoff) & d.actual.notna()


def evaluation_mask(d: pd.DataFrame, phase: dict) -> pd.Series:
    """Keep all outcome observations inside the phase; prevent phase crossing."""
    return (d.date >= pd.Timestamp(phase["start"])) & (d.date <= pd.Timestamp(phase["end"])) & (d.label_end <= pd.Timestamp(phase["end"])) & d.actual.notna()


def exposure_rows(d: pd.DataFrame, spacing: int) -> pd.DataFrame:
    indices, previous = [], None
    for ix, dt in d.sort_values("date")["date"].items():
        if previous is None or (pd.Timestamp(dt)-previous).days >= spacing:
            indices.append(ix)
            previous = pd.Timestamp(dt)
    return d.loc[indices].copy()


def sample_accounting(d: pd.DataFrame, spec: dict, horizon: int, target_type: str) -> pd.DataFrame:
    rows = []
    for crop, g in d.groupby("crop"):
        for phase in PHASES:
            eligible = g[evaluation_mask(g, phase)]
            end = min(pd.Timestamp(phase["end"]), g.date.max())-pd.Timedelta(spec["end_offset"], "D")
            start = max(pd.Timestamp(phase["start"]), g.date.min())
            calendar = max((end-start).days+1, 0)
            rows.append({"crop": crop, "horizon": horizon, "target": target_type, "target_definition": spec["name"],
                         "fold": phase["name"], "calendar_candidates": calendar, "observed_candidates": len(eligible),
                         "nonoverlap_samples": len(exposure_rows(eligible, spec["calendar_days"])),
                         "effective_test_samples": len(exposure_rows(eligible, spec["exposure_spacing_days"])),
                         "actual_independent_test_samples": 0, "final_effective_n": 0,
                         "count_semantics": "retrospective exposure blocks; independence not proven",
                         "exposure_spacing_days": spec["exposure_spacing_days"],
                         "first_origin":eligible.date.min() if len(eligible) else None,
                         "last_origin":eligible.date.max() if len(eligible) else None,
                         "first_target_date":eligible.label_start.min() if len(eligible) else None,
                         "last_target_date":eligible.label_end.max() if len(eligible) else None,
                         "mean_observed_target_fraction":float(eligible.target_observations.mean()/spec["calendar_days"]) if len(eligible) else None,
                         "full_history_nonoverlap": len(exposure_rows(g[g.actual.notna()], spec["calendar_days"])),
                         "train_rows": int(training_mask(g, phase["train_end"]).sum())})
    return pd.DataFrame(rows)


def factories() -> dict:
    cfg = CONFIG["models"]
    out = {
        "linear": lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LinearRegression()),
        "elasticnet": lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), ElasticNet(**cfg["elasticnet"], random_state=17)),
        "extra_trees": lambda: make_pipeline(SimpleImputer(strategy="median"), ExtraTreesRegressor(**cfg["extra_trees"], random_state=17, n_jobs=2)),
    }
    try:
        from catboost import CatBoostRegressor
        out["catboost"] = lambda: make_pipeline(SimpleImputer(strategy="median"), CatBoostRegressor(**cfg["catboost"], random_seed=17, verbose=False, allow_writing_files=False))
    except ImportError:
        pass
    return out


def metrics(d: pd.DataFrame, denominator=None) -> dict:
    y, p, anchor = d.actual.to_numpy(float), d.prediction.to_numpy(float), d.anchor_price.to_numpy(float)
    good = np.isfinite(y) & np.isfinite(p)
    y, p, anchor = y[good], p[good], anchor[good]
    if not len(y):
        return {"n": 0, "WAPE": np.nan, "MAE": np.nan, "sMAPE": np.nan, "MASE": np.nan, "bias": np.nan, "direction_accuracy": np.nan}
    mae = float(np.abs(y-p).mean())
    return {"n": len(y), "WAPE": float(100*np.abs(y-p).sum()/np.abs(y).sum()), "MAE": mae,
            "sMAPE": float(100*np.mean(2*np.abs(y-p)/(np.abs(y)+np.abs(p)))),
            "MASE": mae/denominator if denominator and denominator > 0 else np.nan,
            "bias": float(np.mean(p-y)), "direction_accuracy": float(np.mean(np.sign(p-anchor)==np.sign(y-anchor)))}


def evaluate(d: pd.DataFrame, horizon: int, target_type: str, phases=PHASES, trained=True) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    pred_parts, met_rows, failures = [], [], []
    facs = factories() if trained else {}
    for phase in phases:
        for crop, g in d.groupby("crop", sort=False):
            tr, te = g[training_mask(g, phase["train_end"])], g[evaluation_mask(g, phase)]
            if not len(te):
                continue
            denom = float(np.abs(np.diff(tr.price_per_kg)).mean()) if len(tr)>1 else np.nan
            for method in (*BASELINES, *facs):
                if method in BASELINES:
                    p = te.price_per_kg.to_numpy() if method == "last_value" else te[method].to_numpy()
                else:
                    if len(tr) < CONFIG["min_training_rows"]:
                        failures.append({"crop": crop, "horizon": horizon, "target": target_type, "phase": phase["name"], "method": method, "reason": "INSUFFICIENT_TRAIN_ROWS"})
                        continue
                    try:
                        model = facs[method]()
                        model.fit(tr[FEATURES], tr.actual)
                        p = np.asarray(model.predict(te[FEATURES]),dtype=float)
                    except Exception as exc:
                        failures.append({"crop": crop, "horizon": horizon, "target": target_type, "phase": phase["name"], "method": method, "reason": type(exc).__name__, "detail": str(exc)[:180]})
                        continue
                invalid = ~np.isfinite(p) | (p<=0)
                p = np.where(invalid,te.price_per_kg.to_numpy(float),p)
                out = te[["date", "crop", "actual", "label_start", "label_end", "price_per_kg"]].rename(columns={"price_per_kg": "anchor_price"}).copy()
                out["prediction"] = p
                out["fallback_used"] = invalid
                out["actual_method"] = np.where(invalid,"last_value",method)
                out = out[np.isfinite(out.prediction)]
                out["phase"], out["method"], out["horizon"], out["target_type"] = phase["name"], method, horizon, target_type
                pred_parts.append(out)
                m = metrics(out, denom)
                m.update({"crop": crop, "horizon": horizon, "target_type": target_type, "method": method,
                          "phase": phase["name"], "evaluation_role": "reused_retrospective" if phase==PHASES[-1] else phase["name"],
                          "target_definition": d.attrs.get("target_definition",target_type), "train_rows": len(tr), "max_training_label_end": tr.label_end.max()})
                m["fallback_n"] = int(invalid.sum())
                met_rows.append(m)
    return pd.concat(pred_parts, ignore_index=True) if pred_parts else pd.DataFrame(), pd.DataFrame(met_rows), failures


def select_method(mets: pd.DataFrame) -> tuple[str, str, float]:
    """Selection uses development and tuning only; calibration/audit cannot enter."""
    m = mets[mets.phase.isin(["development", "tuning"])].pivot(index="method", columns="phase", values="WAPE").dropna()
    if m.empty:
        return "last_value", "last_value", np.nan
    m["score"] = m.tuning + 0.5*(m.tuning-m.development).abs()
    best_score = m.score.min()
    tied = m[m.score <= best_score+0.05]
    preference = {name: i for i, name in enumerate((*BASELINES, "elasticnet", "linear", "extra_trees", "catboost"))}
    winner = min(tied.index, key=lambda name: preference[name])
    baseline = m.loc[m.index.isin(BASELINES)].score.idxmin()
    return winner, baseline, float(m.loc[winner, "score"])


def paired_bootstrap(model: pd.DataFrame, baseline: pd.DataFrame, spacing: int) -> dict:
    pair = model.merge(baseline[["date", "prediction"]], on="date", suffixes=("", "_baseline"))
    pair = exposure_rows(pair, spacing)
    n = len(pair)
    if n < 4:
        return {"n": n, "gain_ci_low_pp": None, "gain_ci_high_pp": None, "ci_status": "INSUFFICIENT_EXPOSURE_BLOCKS"}
    rng = np.random.default_rng(CONFIG["random_seed"])
    y, pm, pb = pair.actual.to_numpy(), pair.prediction.to_numpy(), pair.prediction_baseline.to_numpy()
    draws = rng.integers(0, n, size=(CONFIG["practical_gate"]["bootstrap_repetitions"], n))
    gain = 100*(np.abs(y[draws]-pb[draws]).sum(axis=1)-np.abs(y[draws]-pm[draws]).sum(axis=1))/np.abs(y[draws]).sum(axis=1)
    low, high = np.percentile(gain, [2.5, 97.5])
    return {"n": n, "gain_ci_low_pp": float(low), "gain_ci_high_pp": float(high), "ci_status": "EXPLORATORY_REUSED_RETROSPECTIVE"}


def calibrate(p: pd.DataFrame, spec: dict) -> dict:
    p = p[(p.phase=="calibration") & (p.prediction>0)].sort_values("date")
    independent = exposure_rows(p, spec["exposure_spacing_days"])
    if not len(p):
        return {"q10": 1.0, "q90": 1.0, "calibration_n": 0, "calibration_effective_n": 0, "status": "NO_CALIBRATION"}
    # Dense residuals can describe a scenario range; they do not establish coverage.
    ratio = p.actual/p.prediction
    return {"q10": float(min(ratio.quantile(0.1), 1.0)), "q90": float(max(ratio.quantile(0.9), 1.0)),
            "calibration_n": len(p), "calibration_effective_n": len(independent), "status": "SCENARIO_RANGE_DENSE_RESIDUALS"}


def gate_result(p: pd.DataFrame, b: pd.DataFrame, rng: dict, spec: dict) -> dict:
    audit, base = p[p.phase==PHASES[-1]["name"]].copy(), b[b.phase==PHASES[-1]["name"]].copy()
    if not len(audit) or not len(base):
        return {"absolute_gain": None, "relative_gain": None, "retrospective_effective_n": 0, "final_effective_n": 0,
                "untouched_metric": None, "gate_pass": False, "reason": "NO_UNTOUCHED_EVIDENCE", "range_coverage_retrospective": None,
                "gain_ci_low_pp": None, "gain_ci_high_pp": None, "worst_period_degradation_pp": None, "worst_period": None,"winning_period_fraction": None}
    pair = audit.merge(base[["date", "prediction"]], on="date", suffixes=("", "_baseline"))
    am = metrics(pair)
    bp = pair.copy(); bp["prediction"] = bp.prediction_baseline
    bm = metrics(bp)
    gain = bm["WAPE"]-am["WAPE"]
    relative = gain/bm["WAPE"] if bm["WAPE"] else 0.0
    period_gains, period_names = [],[]
    for name, q in pair.groupby(pair.date.dt.to_period("Q")):
        qb = q.copy(); qb["prediction"] = qb.prediction_baseline
        period_gains.append(metrics(qb)["WAPE"]-metrics(q)["WAPE"])
        period_names.append(str(name))
    coverage = float(((pair.actual >= pair.prediction*rng["q10"]) & (pair.actual <= pair.prediction*rng["q90"])).mean())
    ci = paired_bootstrap(audit, base, spec["exposure_spacing_days"])
    threshold = CONFIG["practical_gate"]
    practical = gain >= threshold["absolute_gain_pp"] and relative >= threshold["relative_gain_fraction"]
    stability = len(period_gains)>=threshold["min_periods"] and np.mean(np.asarray(period_gains)>0)>=threshold["winning_period_fraction"]
    worst = float(-min(period_gains)) if period_gains else None
    reasons = ["NO_UNTOUCHED_EVIDENCE", "PRIOR_HOLDOUT_REUSED"]
    if not practical: reasons.append("NO_MEANINGFUL_GAIN")
    if not stability: reasons.append("INSUFFICIENT_STABILITY")
    if ci["n"] < threshold["min_final_exposure_blocks"]: reasons.append("INSUFFICIENT_EXPOSURE_BLOCKS")
    if ci["gain_ci_low_pp"] is None or ci["gain_ci_low_pp"] <= 0: reasons.append("PAIRED_CI_NOT_POSITIVE")
    if worst is not None and worst > threshold["worst_period_degradation_pp"]: reasons.append("WORST_PERIOD_DEGRADATION")
    return {"absolute_gain": gain, "relative_gain": relative, "retrospective_effective_n": ci["n"], "final_effective_n": 0,
            "untouched_metric": None, "gate_pass": False, "reason": ";".join(reasons),
            "range_coverage_retrospective": coverage, "gain_ci_low_pp": ci["gain_ci_low_pp"], "gain_ci_high_pp": ci["gain_ci_high_pp"],
            "worst_period_degradation_pp": worst, "winning_period_fraction": float(np.mean(np.asarray(period_gains)>0)) if period_gains else None,
            "worst_period":period_names[int(np.argmin(period_gains))] if period_gains else None,
            "audit_WAPE": am["WAPE"], "baseline_metric": bm["WAPE"], "audit_n": len(pair),
            "n_periods": len(period_gains), "practical_gain_retrospective": practical}


def load_bundle(index_path: Path | str = INDEX_PATH) -> dict:
    """Load versioned, trusted local artifacts. Caller must verify runtime manifest."""
    path = Path(index_path)
    index = json.loads(path.read_text(encoding="utf-8"))
    if index.get("model_version") != MODEL_VERSION or index.get("config_hash") != CONFIG_HASH:
        raise ValueError("long-horizon model/config version mismatch")
    index["_index_dir"] = str(path.parent)
    index["_models"] = {}
    for entry in index["entries"]:
        if entry.get("artifact"):
            artifact = path.parent / entry["artifact"]
            payload = artifact.read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry["artifact_sha256"]:
                raise ValueError("long-horizon model artifact checksum mismatch")
            index["_models"][entry["key"]] = pickle.loads(payload)
    return index


def predict_at(bundle: dict, history_df: pd.DataFrame, crop: str, horizon: int, target_type: str) -> dict:
    """Inference only. The last observed crop date is the forecast origin."""
    if horizon not in HORIZONS or target_type not in TARGET_TYPES:
        raise ValueError("unsupported long-horizon target/horizon")
    key = f"{crop}|{horizon}|{target_type}"
    entry = next((e for e in bundle["entries"] if e["key"] == key), None)
    if entry is None:
        raise ValueError("unsupported crop")
    history = _normalize(history_df)
    history = history[history.crop==crop]
    if history.empty:
        raise ValueError("no crop history")
    spec = target_spec(entry["target_definition"], horizon)
    features = add_seasonal_features(build_base_features(history), spec)
    row = features.iloc[[-1]]
    method, fallback = entry["method"], False
    if method in BASELINES:
        value = float(row.price_per_kg.iloc[0] if method=="last_value" else row[method].iloc[0])
    else:
        model = bundle.get("_models", {}).get(key)
        try:
            value = float(model.predict(row[FEATURES])[0]) if model is not None else np.nan
        except (ValueError,TypeError,RuntimeError):
            value = np.nan
    if not np.isfinite(value) or value <= 0:
        # Fallback is visible and remains scenario-only, with its own fitted range.
        method = entry["fallback"]
        value = float(row.price_per_kg.iloc[0] if method=="last_value" else row[method].iloc[0])
        fallback = True
        if not np.isfinite(value) or value<=0:
            method, value = "last_value", float(row.price_per_kg.iloc[0])
    bounds = entry["fallback_range"] if fallback else entry["range"]
    lo, hi = value*float(bounds["q10"]), value*float(bounds["q90"])
    disagreement = {name: _clean(float(row.price_per_kg.iloc[0] if name=="last_value" else row[name].iloc[0])) for name in BASELINES}
    disagreement.update({"statistical": value, "seasonal": disagreement["seasonal_naive"], "llm": None, "hybrid": None})
    numeric = [float(x) for x in disagreement.values() if x is not None and np.isfinite(x)]
    return {"point": value, "low": min(lo, value), "high": max(hi, value), "unit": "元/公斤",
            "method": entry["method"], "actual_method": method, "fallback_used": fallback,
            "status": entry["production_status"], "production_status": entry["production_status"],
            "confidence": entry["confidence"], "range_type": "scenario_range", "target_type": target_type,
            "target_definition": spec["name"], "window_definition": spec["name"],
            "window_start_offset": spec["start_offset"], "window_end_offset": spec["end_exclusive_offset"],
            "label_end_offset": spec["end_offset"],
            "window_end_exclusive_offset": spec["end_exclusive_offset"], "expected_harvest_horizon": horizon,
            "as_of": str(row.date.iloc[0].date()), "evidence_status": "RETROSPECTIVE_ONLY_NO_UNTOUCHED",
            "retrospective_effective_n": entry["retrospective_effective_n"], "final_effective_n": 0,
            "sample_n": entry.get("sample_n",0), "effective_n": entry["retrospective_effective_n"],
            "untouched_metric": None, "model_version": MODEL_VERSION, "registry_version": bundle["registry_version"],
            "model_disagreement": disagreement, "model_disagreement_pct": float(np.std(numeric)/np.mean(numeric)*100) if numeric else None,
            "reason": entry["reason"]}


def _csv(df: pd.DataFrame, name: str) -> None:
    df.to_csv(ROOT/name, index=False, encoding="utf-8-sig")
    df.to_csv(ARTIFACTS/name, index=False, encoding="utf-8-sig")


def _md(name: str, text: str) -> None:
    (ROOT/name).write_text(text.rstrip()+"\n", encoding="utf-8")
    (ARTIFACTS/name).write_text(text.rstrip()+"\n", encoding="utf-8")


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "无可用样本。"
    columns = list(df.columns)
    rows = ["| " + " | ".join(columns) + " |", "|"+"---|"*len(columns)]
    for _, r in df.iterrows():
        cells = [f"{v:.3f}" if isinstance(v, (float, np.floating)) and np.isfinite(v) else "N/A" if pd.isna(v) else str(v) for v in r]
        rows.append("| "+" | ".join(cells)+" |")
    return "\n".join(rows)


def decision_replay(preds: pd.DataFrame, registry: pd.DataFrame, history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Equal-weight market-price-return ranking. No unknown crop cost/yield profit."""
    audit_name = PHASES[-1]["name"]
    selected_parts = []
    for _, r in registry[registry.target_type=="harvest_market_price"].iterrows():
        p = preds[(preds.crop==r.crop)&(preds.horizon==r.horizon)&(preds.target_type==r.target_type)&(preds.method==r.method)&(preds.phase==audit_name)].copy()
        p["policy"] = "statistical_long"
        selected_parts.append(p)
        b = preds[(preds.crop==r.crop)&(preds.horizon==r.horizon)&(preds.target_type==r.target_type)&(preds.method==r.baseline_method)&(preds.phase==audit_name)].copy()
        b["policy"] = "seasonal_baseline" if r.baseline_method!="last_value" else "selected_simple_baseline"
        # Report both a true seasonal benchmark and the selected simple benchmark.
        b["policy"] = "selected_simple_baseline"
        selected_parts.append(b)
        season = preds[(preds.crop==r.crop)&(preds.horizon==r.horizon)&(preds.target_type==r.target_type)&(preds.method=="seasonal_naive")&(preds.phase==audit_name)].copy()
        season["policy"] = "seasonal_baseline"
        selected_parts.append(season)
    pool = pd.concat(selected_parts, ignore_index=True)
    rows, rank_rows = [], []
    rng = np.random.default_rng(17)
    for h, g in pool.groupby("horizon"):
        dates = sorted(g.date.unique())
        for date in dates:
            one = g[g.date==date]
            reference = one[one.policy=="statistical_long"].drop_duplicates("crop").copy()
            if reference.crop.nunique()!=history.crop.nunique():
                continue
            expected_policies={"statistical_long","selected_simple_baseline","seasonal_baseline"}
            reference_crops=set(reference.crop)
            if any(set(one[one.policy==policy].crop)!=reference_crops for policy in expected_policies):
                continue
            short = preds[(preds.date==date)&(preds.horizon==30)&(preds.target_type=="cycle_market_average")&
                          (preds.method=="same_season_mean")&(preds.phase==audit_name)].drop_duplicates("crop")
            if set(short.crop)!=reference_crops:
                continue
            reference["realized_return"] = reference.actual/reference.anchor_price-1
            oracle = float(reference.realized_return.max())
            random_expected = float(reference.realized_return.mean())
            for policy, p in one.groupby("policy"):
                p = p.drop_duplicates("crop")
                if len(p)!=len(reference):
                    continue
                expected = p.prediction/p.anchor_price-1
                realized = p.actual/p.anchor_price-1
                chosen = expected.sort_values(ascending=False, kind="mergesort").index[0]
                val = float(realized.loc[chosen])
                corr = expected.rank().corr(realized.rank()) if expected.nunique()>1 else np.nan
                rank_rows.append({"date": date, "horizon": h, "policy": policy, "spearman_rank": corr,
                                  "direction_accuracy": float((np.sign(expected)==np.sign(realized)).mean())})
                rows.append({"date": date, "horizon": h, "policy": policy, "chosen_crop": p.loc[chosen,"crop"],
                             "relative_harvest_return": val, "regret": oracle-val, "oracle_return": oracle,
                             "random_expected_return": random_expected,"top1_accuracy":float(np.isclose(val,oracle)),
                             "evidence_status": "REUSED_RETROSPECTIVE_MARKET_PROXY"})
            # Short-only proxy is a PIT seasonal 30-day profile. It is never the frozen production Final model.
            if len(short)==len(reference):
                expected = short.prediction/short.anchor_price-1
                chosen_crop = str(short.loc[expected.idxmax(),"crop"]) if expected.notna().any() else str(short.iloc[0].crop)
                outcome = float(reference[reference.crop==chosen_crop].realized_return.iloc[0])
                rows.append({"date": date, "horizon": h, "policy": "short_only_30d_seasonal_proxy", "chosen_crop": chosen_crop,
                             "relative_harvest_return": outcome, "regret": oracle-outcome, "oracle_return": oracle,
                             "random_expected_return": random_expected,"top1_accuracy":float(np.isclose(outcome,oracle)),
                             "evidence_status": "REUSED_RETROSPECTIVE_MARKET_PROXY"})
            for policy, crop, value in [("random_expected", "equal_weight_expectation", random_expected),
                                        ("random_seed17", str(reference.iloc[int(rng.integers(len(reference)))].crop), None)]:
                if value is None:
                    value = float(reference[reference.crop==crop].realized_return.iloc[0])
                rows.append({"date": date, "horizon": h, "policy": policy, "chosen_crop": crop,
                             "relative_harvest_return": value, "regret": oracle-value, "oracle_return": oracle,
                             "random_expected_return": random_expected,"top1_accuracy":float(np.isclose(value,oracle)),
                             "evidence_status": "REUSED_RETROSPECTIVE_MARKET_PROXY"})
    replay = pd.DataFrame(rows)
    if replay.empty:
        return replay, pd.DataFrame()
    replay["month"] = replay.date.dt.to_period("M").astype(str)
    summary = replay.groupby(["horizon", "policy"]).agg(n=("regret","size"), mean_return=("relative_harvest_return","mean"),
                         mean_regret=("regret","mean"), worst_regret=("regret","max"), worst_return=("relative_harvest_return","min"),
                         downside_p10=("relative_harvest_return",lambda x:x.quantile(.1)), top1_accuracy=("top1_accuracy","mean")).reset_index()
    stability_rows=[]
    for (h,policy),g in replay.groupby(["horizon","policy"]):
        g=g.sort_values("date")
        name=registry[(registry.horizon==h)&(registry.target_type=="harvest_market_price")].iloc[0].target_definition
        spacing=target_spec(name,int(h))["exposure_spacing_days"]
        stability_rows.append({"horizon":h,"policy":policy,"retrospective_exposure_blocks":len(exposure_rows(g,spacing)),
                               "selection_turnover":float((g.chosen_crop!=g.chosen_crop.shift()).iloc[1:].mean()) if len(g)>1 else None,
                               "crop_concentration":float(g.chosen_crop.value_counts(normalize=True).max()),
                               "actual_independent_samples":0})
    summary=summary.merge(pd.DataFrame(stability_rows),on=["horizon","policy"])
    ranks = pd.DataFrame(rank_rows)
    if not ranks.empty:
        summary = summary.merge(ranks.groupby(["horizon","policy"]).agg(rank_accuracy=("spearman_rank","mean"),direction_accuracy=("direction_accuracy","mean")).reset_index(), how="left")
    summary["llm_status"] = "NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE"
    return replay, summary


def retrain() -> dict:
    """Explicit research/refit command. Write the protocol before any audit output."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    frozen_path = ARTIFACTS / "evaluation_protocol.json"
    if frozen_path.exists():
        old = json.loads(frozen_path.read_text())
        if old["config_hash"] != CONFIG_HASH:
            raise RuntimeError("protocol changed after audit; new historical evidence cannot be called untouched")
    _json(frozen_path, {"config_hash": CONFIG_HASH, "locked_at": datetime.now(timezone.utc).isoformat(), "config": CONFIG})
    _json(ROOT/"models/long_horizon/evaluation_protocol_v2.json", {"config_hash": CONFIG_HASH, "config": CONFIG})
    history = _normalize(pd.read_parquet(DATA_PATH))
    training_hash = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()
    features = build_base_features(history)
    # Target study consumes development and tuning only, never calibration/audit.
    study_rows, prepared = [], {}
    for h in HORIZONS:
        for candidate in CONFIG["target_candidates"]:
            spec = target_spec(candidate, h)
            ds = add_seasonal_features(add_targets(features, spec), spec)
            _, m, _ = evaluate(ds, h, candidate, phases=PHASES[:2], trained=False)
            for phase, phase_m in m.groupby("phase"):
                study_rows.append({"horizon":h,"candidate":candidate,"phase":phase,"mean_WAPE":phase_m.WAPE.mean(),
                                   "mean_MAE":phase_m.MAE.mean(),"mean_sMAPE":phase_m.sMAPE.mean(),"n_predictions":int(phase_m.n.sum()),
                                   "business_eligible":candidate in CONFIG["harvest_admissible"],"window_days":spec["calendar_days"]})
            prepared[(h,candidate)] = ds
        print(f"target study h={h} complete", flush=True)
    study = pd.DataFrame(study_rows)
    scores = study[study.business_eligible].groupby("candidate").mean_WAPE.mean()
    tied = scores[scores<=scores.min()*1.02]
    order = ["harvest_post_14","harvest_centered_14","harvest_post_7","harvest_centered_7"]
    harvest_definition = next(name for name in order if name in tied.index)
    selection_lock = {"harvest_definition":harvest_definition,"target_scores":scores.to_dict(),"selection_data":"development+tuning only",
                      "config_hash":CONFIG_HASH,"locked_at":datetime.now(timezone.utc).isoformat()}
    _json(ARTIFACTS/"target_selection_lock.json", _clean(selection_lock))
    # Model selection is completed for every entry before any calibration/audit run.
    selection = {}; pred_parts=[]; met_parts=[]; failures=[]; accounts=[]
    for h in HORIZONS:
        for target_type in TARGET_TYPES:
            definition = "cycle_market_average" if target_type=="cycle_market_average" else harvest_definition
            ds = prepared[(h,definition)]
            p, m, f = evaluate(ds,h,target_type,phases=PHASES[:2])
            pred_parts.append(p); met_parts.append(m); failures.extend(f)
            for crop, crop_m in m.groupby("crop"):
                method, baseline, score = select_method(crop_m)
                selection[f"{crop}|{h}|{target_type}"]={"method":method,"baseline":baseline,"selection_score":score}
            accounts.append(sample_accounting(ds,target_spec(definition,h),h,target_type))
            print(f"model selection h={h} target={target_type} complete",flush=True)
    _json(ARTIFACTS/"model_selection_lock.json",{"config_hash":CONFIG_HASH,"target":harvest_definition,"selection":_clean(selection),"locked_at":datetime.now(timezone.utc).isoformat()})
    # Only now evaluate calibration and reused retrospective audit, without selection changes.
    for h in HORIZONS:
        for target_type in TARGET_TYPES:
            definition = "cycle_market_average" if target_type=="cycle_market_average" else harvest_definition
            p,m,f = evaluate(prepared[(h,definition)],h,target_type,phases=PHASES[2:])
            pred_parts.append(p);met_parts.append(m);failures.extend(f)
            print(f"calibration/audit h={h} target={target_type} complete",flush=True)
    preds,mets = pd.concat(pred_parts,ignore_index=True),pd.concat(met_parts,ignore_index=True)
    entries=[];registry_rows=[]; facs=factories()
    for key,sel in selection.items():
        crop,h,target_type=key.split("|");h=int(h)
        definition="cycle_market_average" if target_type=="cycle_market_average" else harvest_definition
        spec=target_spec(definition,h)
        cp=preds[(preds.crop==crop)&(preds.horizon==h)&(preds.target_type==target_type)]
        method,baseline=sel["method"],sel["baseline"]
        p,b=cp[cp.method==method],cp[cp.method==baseline]
        rng=calibrate(p,spec)
        brng=calibrate(cp[cp.method=="last_value"],spec)
        gate=gate_result(p,b,rng,spec)
        phase_metrics={phase:metrics(p[p.phase==phase])["WAPE"] for phase in [x["name"] for x in PHASES]}
        status="EXPLORATORY_SCENARIO_ONLY" if h>=150 else "SCENARIO_ONLY"
        row={"crop":crop,"horizon":h,"target_type":target_type,"target_definition":definition,"method":method,
             "development_metric":phase_metrics["development"],"selection_metric":phase_metrics["tuning"],
             "calibration_metric":phase_metrics["calibration"],"retrospective_metric":phase_metrics[PHASES[-1]["name"]],
             "selection_score":sel["selection_score"],"baseline_method":baseline,**gate,
             "sample_n":gate.get("audit_n",0),"effective_n":gate["retrospective_effective_n"],
             "confidence":"low","range_type":"scenario_range","production_status":status,"llm_used":False,
             "fallback":"last_value","range":rng,"fallback_range":brng,"key":key,
             "window_start_offset":spec["start_offset"],"window_end_offset":spec["end_offset"],
             "calibration_effective_n":rng["calibration_effective_n"],"config_hash":CONFIG_HASH}
        registry_rows.append(row.copy())
        # Production refit is distinct from evaluated models; all labels must be mature.
        ds=prepared[(h,definition)]
        tr=ds[(ds.crop==crop)&training_mask(ds,history.date.max())]
        artifact=None; artifact_hash=None
        if method in facs:
            model=facs[method]();model.fit(tr[FEATURES],tr.actual)
            artifact=f"crop{sorted(history.crop.unique()).index(crop):02d}_h{h}_{target_type}.pkl"
            payload=pickle.dumps(model,protocol=pickle.HIGHEST_PROTOCOL)
            (MODEL_DIR/artifact).write_bytes(payload);artifact_hash=hashlib.sha256(payload).hexdigest()
        row.update({"artifact":artifact,"artifact_sha256":artifact_hash,"production_refit_rows":len(tr),
                    "production_refit_cutoff":str(history.date.max().date()),"evaluated_model_role":"per-phase purged fit",
                    "production_model_role":"post-evaluation historical refit; no claimed holdout score"})
        entries.append(_clean(row))
    registry=pd.DataFrame(registry_rows)
    accounts=pd.concat(accounts,ignore_index=True)
    _csv(study,"LONG_HORIZON_V2_TARGET_STUDY.csv")
    _csv(mets,"LONG_HORIZON_V2_METRICS.csv")
    _csv(registry.drop(columns=["range","fallback_range"]),"LONG_HORIZON_V2_REGISTRY.csv")
    _csv(accounts,"LONG_HORIZON_SAMPLE_ACCOUNTING.csv")
    preds.to_parquet(ARTIFACTS/"predictions.parquet",index=False)
    _json(ARTIFACTS/"training_failures.json",failures)
    registry_version=_hash(_clean(entries))[:16]
    index={"schema_version":"2.0","model_version":MODEL_VERSION,"config_hash":CONFIG_HASH,
           "training_data_version":training_hash[:16],"training_data_sha256":training_hash,
           "training_cutoff":str(history.date.max().date()),"harvest_definition":harvest_definition,
           "registry_version":registry_version,"method_registry_version":registry_version,"features":FEATURES,"entries":entries,
           "evaluation_status":"RETROSPECTIVE_ONLY_NO_UNTOUCHED","generated_at":datetime.now(timezone.utc).isoformat(),
           "prospective_protocol":CONFIG["practical_gate"],"prospective_origin_not_before":CONFIG["prospective_origin_not_before"]}
    _json(INDEX_PATH,index)
    # Compute price-decision replay on the same paired crop/date outcome pool.
    replay,decision_summary=decision_replay(preds,registry,history)
    if not replay.empty: replay.to_csv(ARTIFACTS/"decision_replay.csv",index=False)
    _csv(decision_summary,"DECISION_LONG_HORIZON_BACKTEST.csv")
    reports(history,study,mets,registry,accounts,decision_summary,harvest_definition,training_hash,failures)
    return {"model_version":MODEL_VERSION,"registry_rows":len(registry),"metrics_rows":len(mets),
            "harvest_definition":harvest_definition,"training_failures":len(failures),"index":str(INDEX_PATH)}


def reports(history,study,mets,registry,accounts,decision_summary,definition,training_hash,failures):
    head=f"> RC2，模型 `{MODEL_VERSION}`，数据 `{training_hash[:16]}`，预注册协议 `{CONFIG_HASH}`。\n> 历史 2024/2025/2026 已参与 RC1 target/model 选择；本轮没有真正 untouched 历史段。\n> 2026 指标是 **reused retrospective audit**；`untouched_metric=null`、`final_effective_n=0`。\n"
    target_scores=study.groupby(["candidate","business_eligible"]).mean_WAPE.mean().reset_index()
    _md("LONG_HORIZON_V2_TARGET_REPORT.md",f"# Long-Horizon V2 Target\n\n{head}\n"
        "`cycle_market_average` = 决策后 `(t,t+H]` 已观测批发价算术均值，回答周期市场中枢。\n"
        f"`harvest_market_price` = `{definition}`，回答预计上市时点附近实际销售窗口的批发市场价。\n"
        "物候没有可信沈阳日粒度依据；H/预计上市日必须来自用户，不按作物猜测。\n\n"
        "所有窗口按整数日偏移程序定义：centered14 = `[t+H-7,t+H+7)`，共14日；post14 = `[t+H,t+H+14)`，共14日。\n"
        "7/30日同样使用半开区间；奇数 centered7 = `[H-3,H+4)`。endpoint 采用 H 日最近向前观测，最大回退3日。\n"
        "目标仅取已有观测，不插值。窗口必须完整成熟，观测覆盖至少50%，内部断档不超过10日。\n\n"
        "选择只使用 development2023+tuning2024。30日窗保留研究对照，但默认销售持续整月缺乏用户确认，不能仅因平滑导致误差低就成为默认Harvest。"
        "合格7/14日窗取平均baseline WAPE最低，2%相对容差内按预锁定业务偏好 post14/centered14/post7/centered7。\n\n"+_table(target_scores))
    _md("HARVEST_WINDOW_REPORT.md",f"# Harvest Window\n\n{head}\n正式窗口 `{definition}`，下表为实际程序偏移（右端排除）。\n\n"+
        _table(pd.DataFrame([{**target_spec(definition,h),"horizon":h} for h in HORIZONS]))+
        "\n\n这只是历史批发市场价，不等于农户田头销售价，也不保证某作物生长周期。120/150/180显示情景或探索性结果。")
    selected_mets=mets.merge(registry[["crop","horizon","target_type","method"]],on=["crop","horizon","target_type","method"])
    audit=selected_mets[selected_mets.phase==PHASES[-1]["name"]]
    summary=audit.groupby(["horizon","target_type"]).agg(WAPE=("WAPE","mean"),MAE=("MAE","mean"),sMAPE=("sMAPE","mean"),
                                                          MASE=("MASE","mean"),bias=("bias","mean"),direction_accuracy=("direction_accuracy","mean")).reset_index()
    _md("LONG_HORIZON_V2_EVALUATION_REPORT.md",f"# Long-Horizon V2 Evaluation\n\n{head}\n"
        "训练初始历史2021–2022；development2023用于候选研究，tuning2024用于模型选择，calibration2025仅确定残差范围，2026-01-01至09-14为已被查看的回顾审计。\n"
        "每阶段训练必须 `label_end <= train_end`，测试目标全部 `label_end <= phase_end`，不跨阶段。选择先写锁文件，再运行calibration/audit。\n"
        "比较 Last Value、target-aligned Seasonal Naive、历史同目标窗mean/median、Linear、ElasticNet、ExtraTrees、CatBoost。\n"
        "年度阶段比嵌套walk-forward更易审计且校准角色独立；nested设计可以减少程序级selection optimism，却不能恢复已查看历史的独立性，且180d一年只约1–2个exposure blocks。\n\n"
        "以下为逐作物均值的2026回顾审计，不是独立预测精度；所有phase/crop/method详细指标见CSV。\n\n"+_table(summary)+
        f"\n\n训练失败实际记录 `{len(failures)}`（逐项位于artifacts/v2/training_failures.json）。当前Final模型未改动。"
        " production refit只在方法冻结后使用全部成熟历史标签；其权重不是历史逐阶段 evaluated model，不能拿它在旧测试段重报分数。\n"
        "未来真正独立检验：协议冻结后发行不可变预测并记录模型/target/config/input hash，观察成熟上市窗口；未来资料不准用于调窗口、权重或门槛。")
    count_summary=accounts[accounts.fold==PHASES[-1]["name"]].groupby(["horizon","target"]).agg(
        observed_candidates=("observed_candidates","mean"),nonoverlap_samples=("nonoverlap_samples","mean"),
        retrospective_exposure_blocks=("effective_test_samples","mean"),actual_independent_samples=("actual_independent_test_samples","max")).reset_index()
    _md("SAMPLE_ACCOUNTING_REPORT.md",f"# Sample Accounting\n\n{head}\n"
        f"冻结数据 {history.date.min().date()} 至 {history.date.max().date()}，每作物 {len(history)//history.crop.nunique()} 观测；缺失日不生成价格。\n"
        "唯一数量来源 `LONG_HORIZON_SAMPLE_ACCOUNTING.csv`。calendar_candidates=阶段内理论成熟日历origin；observed_candidates=有真实origin且目标质控通过；"
        "nonoverlap_samples=target价格窗不相交的贪心样本；effective_test_samples=origin间距至少max(H,target_end_offset)的保守exposure blocks。"
        "后者不是已证明统计独立，不能扩大成window14每14天就是独立120d预测。full_history_nonoverlap单列，不能代替evaluation count。\n\n"+_table(count_summary)+
        "\n\n跨作物同日价格共同市场波动，不把10作物倍增为10倍独立时间样本。当前全部actual independent final samples为0。")
    _md("PRODUCTION_GATE_REPORT.md",f"# Production Gate\n\n{head}\n"
        "门槛在2026 audit前预注册：绝对WAPE改善≥1pp且相对≥5%；至少3时期、≥75%时期改善；最差时期退化≤2pp；"
        "final保守exposure blocks≥12，paired block bootstrap 95% gain CI下界>0。区间另需calibration exposure blocks≥20，"
        "名义80%覆盖率独立检验在70%–90%之间。当前历史重用直接否决PRODUCTION_POINT；密集残差只能是scenario_range。\n\n"
        "1pp/5%为预先确定的工程容差，避免0.003pp数值噪声升级，不是声称由final结果学出的最优阈值。Bootstrap按H跨度稀疏origin成对重采样，"
        "样本小于4不输出CI；现有CI仅探索性，不能作为独立显著证据。\n\n"
        f"状态：{registry.production_status.value_counts().to_dict()}。confidence全部low：缺真正未见证据、样本小、区间未独立验证，不能只凭horizon写medium/high。\n\n"
        "未来符合冻结协议的数据到齐后可以独立评估，当前代码不自动升级；需要单独审核并发布新registry。")
    _md("LONG_HORIZON_V2_METHOD_MAP.md",f"# Long-Horizon V2 Method Map\n\n{head}\n"+
        _table(registry[["crop","horizon","target_type","target_definition","method","production_status","confidence","retrospective_metric","baseline_method","absolute_gain","effective_n","final_effective_n"]]))
    _md("DECISION_LONG_HORIZON_BACKTEST.md",f"# Long-Horizon Decision Replay\n\n{head}\n"
        "相同cutoff、同10作物、同真实Harvest outcome下，按预测价格/current price−1排序，选择一个作物；realized outcome=Harvest实际价格/current price−1。"
        "regret=当日事后最佳作物relative price return−所选作物return。不混用不同作物绝对元/公斤，不能宣称利润或最佳农业决策。\n"
        "对照statistical_long、target-aligned seasonal、开发选定simple baseline、short_only_30d_seasonal_proxy、随机期望、seed17随机。"
        "short-only是当时历史季节30日均价proxy，不使用全历史训练的冻结Final权重，避免未来泄漏；不是正式短期Decision v1策略胜负证明。"
        "LLM/hybrid缺真实数值证据，明确NOT_EVALUATED，不拿stub填补。成本/产量/设施/作物可种性未知，不能模拟真实利润。\n\n"+
        _table(decision_summary)+"\n\n强推荐限制：全部长期registry仍scenario；历史regret改善只说明市场相对价格proxy，未来独立决策效果尚未证实。"
        "稠密cutoff的策略平均值/最坏值是描述统计，共享未来窗口，n行数不是独立决策样本数。\n"
        + _decision_interpretation(decision_summary))


def _decision_interpretation(summary: pd.DataFrame) -> str:
    observations=[]
    for h,g in summary.groupby("horizon"):
        model=g[g.policy=="statistical_long"]
        baseline=g[g.policy=="seasonal_baseline"]
        if not len(model) or not len(baseline):continue
        m,b=float(model.iloc[0].mean_regret),float(baseline.iloc[0].mean_regret)
        observations.append(f"- {int(h)}d：长期统计策略 regret {m:.4f}，季节基线 {b:.4f}；"
                            +("回顾样本中统计策略较好" if m<b else "统计策略未改善季节基线")
                            +f"，仅{int(model.iloc[0].retrospective_exposure_blocks)}个保守exposure blocks。")
    return "\n按真实回放判定（不据此重新选模型或调策略）：\n\n"+"\n".join(observations)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Explicit long-horizon V2 research/refit; inference never trains")
    parser.add_argument("--retrain",action="store_true",help="run pre-registered target selection/evaluation and production refit")
    args=parser.parse_args()
    if not args.retrain:
        parser.error("training requires explicit --retrain; use load_bundle()/predict_at() for inference")
    print(json.dumps(retrain(),ensure_ascii=False),flush=True)
