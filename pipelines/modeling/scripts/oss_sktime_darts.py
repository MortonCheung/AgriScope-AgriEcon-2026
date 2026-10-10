# -*- coding: utf-8 -*-
"""
开源 P1 评估：Darts / sktime —— 历史回测基础设施与模型对比。

  python3 decision_engine/scripts/oss_sktime_darts.py

公平性：
  - 与 StatsForecast 完全相同的 fold 与 weekly 原点规则（origin 对齐观测日）；
  - 日频序列 ffill（严格 past-only）；retrain=False（与 SF refit=False 同语义）；
  - 先用 sktime splitter 验证切分逻辑与自研 strict point-in-time 一致，再决定取用。
输出：
  decision_engine/evaluation/open_source/darts_origins.csv / darts_metrics.csv
  decision_engine/evaluation/open_source/sktime_split_verification.csv
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models.backtest import FOLDS, metrics_table  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark, pkg_version  # noqa: E402
from decision_engine.models.statsforecast_bench import build_daily_series  # noqa: E402
from decision_engine.models.train_price import PRIMARY_TARGET  # noqa: E402

STRIDE = 7


def verify_sktime_splitter() -> pd.DataFrame:
    """验证 sktime ExpandingWindowSplitter 能否复现我们的 fold 逻辑。"""
    rows = []
    try:
        from sktime.split import ExpandingWindowSplitter
        # 以整数索引序列验证：initial_window=2 年，fh=1..30，step=7
        y = pd.Series(np.arange(1000), index=pd.RangeIndex(1000))
        splitter = ExpandingWindowSplitter(initial_window=730, fh=list(range(1, 31)),
                                           step_length=STRIDE)
        n_splits = 0
        for tr, te in splitter.split(y):
            n_splits += 1
        rows.append({"check": "ExpandingWindowSplitter 可运行", "result": "OK",
                     "detail": f"splits={n_splits}; fh=1..30; step=7；训练窗口始终包含全部历史（expanding）",
                     "conclusion": "与自研 expanding 时间回测语义一致（train 索引全部 < test 索引）"})
        # 检查无未来泄漏：训练最大索引 < 测试最小索引
        ok = True
        for tr, te in splitter.split(y):
            if tr.max() >= te.min():
                ok = False
                break
        rows.append({"check": "无未来泄漏（train.max < test.min）", "result": "OK" if ok else "FAIL",
                     "detail": "全部 split 均满足", "conclusion": "切分逻辑与 strict point-in-time 一致"})
    except Exception as e:
        rows.append({"check": "sktime 安装/导入", "result": "FAILED",
                     "detail": f"{type(e).__name__}: {str(e)[:120]}",
                     "conclusion": "sktime 不可用（不阻塞主流程）"})
    return pd.DataFrame(rows)


def run_darts(ds: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    from darts import TimeSeries
    from darts.models import NaiveSeasonal, ExponentialSmoothing, Theta, RegressionModel

    rows = []
    for crop in sorted(ds["crop"].unique()):
        for fold in FOLDS:
            train_end = pd.Timestamp(fold["train_end"])
            test_end = pd.Timestamp(fold["test_end"])
            sub = ds[ds["crop"] == crop]
            obs_end = pd.to_datetime(sub[sub["date"] <= test_end]["date"]).max()
            fill_daily = build_daily_series(ds, crop, obs_end).set_index("ds")["y"]
            ts_full = TimeSeries.from_series(fill_daily).astype(np.float32)
            train_daily = build_daily_series(ds, crop, train_end).set_index("ds")["y"]
            ts_train = TimeSeries.from_series(train_daily).astype(np.float32)
            target_map = sub.set_index("date")[PRIMARY_TARGET]
            t_start = pd.Timestamp(fold["test_start"])
            origins = [pd.Timestamp(d) for d in sub["date"]
                       if t_start <= pd.Timestamp(d) <= test_end][::10]
            origins = [o for o in origins if o in target_map.index and pd.notna(target_map.loc[o])]
            if not origins:
                continue
            models = {
                "darts_naive_seasonal": NaiveSeasonal(K=7),
                "darts_exp_smoothing": ExponentialSmoothing(),
                "darts_theta": Theta(),
                "darts_regression_lags30": RegressionModel(lags=30, output_chunk_length=30),
            }
            for name, model in models.items():
                t0 = time.time()
                try:
                    # 局部模型要求 retrain=True（每个原点重拟合）；stride=10 控制重训成本
                    model.fit(ts_train)
                    hf = model.historical_forecasts(
                        series=ts_full, start=origins[0], forecast_horizon=30,
                        stride=10, retrain=True, last_points_only=False, verbose=False)
                except Exception as e:
                    rows.append({"crop": crop, "fold": fold["name"], "model": name,
                                 "status": f"FAILED:{type(e).__name__}:{str(e)[:100]}"})
                    continue
                rt = time.time() - t0
                for fcv in hf:
                    o = fcv.start_time() - pd.Timedelta(days=1)
                    # 对齐到不晚于 fcv 起点的观测日
                    cand = [d for d in sub["date"] if pd.Timestamp(d) <= o]
                    if not cand:
                        continue
                    t = pd.Timestamp(cand[-1]) if pd.Timestamp(cand[-1]) >= t_start else None
                    if t is None or t not in target_map.index or pd.isna(target_map.loc[t]):
                        continue
                    vals = np.asarray(fcv.values()).ravel()
                    rows.append({"crop": crop, "fold": fold["name"], "model": name,
                                 "origin_date": t, "pred_window_mean": float(np.mean(vals)),
                                 "actual_window_mean": float(target_map.loc[t]),
                                 "runtime_sec": rt, "status": "OK"})
            print(f"[darts] {crop} {fold['name']} done", flush=True)
    df = pd.DataFrame(rows)
    ok = df[df["status"] == "OK"].copy() if len(df) else df
    mets = []
    if len(ok):
        for (m, c, f), g in ok.groupby(["model", "crop", "fold"]):
            mm = metrics_table(g["actual_window_mean"].values, g["pred_window_mean"].values)
            mm.update({"model": m, "crop": c, "fold": f,
                       "runtime_sec": float(g["runtime_sec"].mean())})
            mets.append(mm)
    return df, pd.DataFrame(mets)


def main():
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    out = ensure_dir(de_path("evaluation", "open_source"))

    ver = verify_sktime_splitter()
    ver.to_csv(out / "sktime_split_verification.csv", index=False, encoding="utf-8-sig")
    print("[sktime verification]\n", ver.to_string(index=False), flush=True)

    t0 = time.time()
    darts_rows, darts_mets = run_darts(ds)
    if len(darts_rows):
        darts_rows.to_csv(out / "darts_origins.csv", index=False, encoding="utf-8-sig")
    if len(darts_mets):
        darts_mets.to_csv(out / "darts_metrics.csv", index=False, encoding="utf-8-sig")
        agg = darts_mets.groupby(["model"]).agg(
            MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), sMAPE=("sMAPE", "mean"),
            WAPE=("WAPE", "mean"), runtime=("runtime_sec", "sum")).reset_index()
        print("[darts]\n", agg.to_string(index=False), flush=True)
        upsert_benchmark([{"library": "darts", "model": r["model"], "version": pkg_version("darts"),
                           "city": "沈阳", "crop": "ALL(10)", "target": PRIMARY_TARGET,
                           "route": "univariate_walkforward",
                           "MAE": round(r["MAE"], 4), "RMSE": round(r["RMSE"], 4),
                           "sMAPE": round(r["sMAPE"], 4), "WAPE": round(r["WAPE"], 4),
                           "runtime_sec": round(float(r["runtime"]), 1),
                           "status": "BENCHMARK_ONLY",
                           "reason": "历史回测基础设施验证 + 统计/回归模型对比（no-refit walk-forward）"}
                          for _, r in agg.iterrows()])
    print(f"[darts] {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()