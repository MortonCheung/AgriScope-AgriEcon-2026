# -*- coding: utf-8 -*-
"""
Phase 0: 冻结输入快照。

- 按 config/paths.yaml 的 snapshot_globs 枚举输入文件；
- 复制到 decision_engine/data/snapshots/v1/（保留相对路径），只读输入源不改动；
- 记录：文件路径 / 大小 / 修改时间 / SHA256 / 行数 / 字段 / 时间范围 / 复制后路径；
- 输出 decision_engine/data/manifests/input_manifest.csv
"""
from __future__ import annotations
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import ROOT, de_path, ensure_dir, paths, sha256_file  # noqa: E402

TIME_HINTS = ["date", "observation_date", "event_date", "pub_date", "year", "week"]


def time_range(df: pd.DataFrame):
    lo, hi, col = None, None, None
    for c in TIME_HINTS:
        if c in df.columns:
            col = c
            try:
                if c == "year":
                    s = pd.to_numeric(df[c], errors="coerce")
                    return str(int(s.min())), str(int(s.max())), c
                s = pd.to_datetime(df[c], errors="coerce")
                if s.notna().any():
                    return str(s.min().date()), str(s.max().date()), c
            except Exception:
                continue
    # 组合 year+week + pub_date
    if "year" in df.columns and "pub_date" in df.columns:
        s = pd.to_datetime(df["pub_date"], errors="coerce")
        return str(s.min().date()), str(s.max().date()), "pub_date"
    return lo, hi, col


def main(version: str = "v1", globs_key: str = "snapshot_globs", manifest_name: str | None = None):
    cfg = paths()
    snap_dir = de_path("data", "snapshots", version)
    ensure_dir(snap_dir)
    manifest_dir = ensure_dir(de_path("data", "manifests"))

    rows = []
    for g in cfg[globs_key]:
        matches = sorted(ROOT.glob(g))
        if not matches:
            rows.append({"source_path": g, "status": "NOT_FOUND"})
            continue
        for src in matches:
            if not src.is_file():
                continue
            rel = src.relative_to(ROOT)
            dst = snap_dir / rel
            ensure_dir(dst.parent)
            shutil.copy2(src, dst)
            try:
                df = pd.read_csv(src, low_memory=False, nrows=500000)
                n_rows, n_cols = len(df), len(df.columns)
                fields = ";".join(map(str, df.columns))
                t0, t1, tcol = time_range(df)
            except Exception as e:
                n_rows = n_cols = None
                fields = f"READ_ERROR:{e}"
                t0 = t1 = tcol = None
            st = src.stat()
            rows.append({
                "source_path": str(rel),
                "snapshot_path": str(dst.relative_to(ROOT)),
                "size_bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "sha256": sha256_file(src),
                "rows": n_rows,
                "cols": n_cols,
                "fields": fields,
                "time_start": t0,
                "time_end": t1,
                "time_field": tcol,
                "snapshot_version": version,
                "status": "COPIED",
            })
            print(f"[snapshot] {rel}  rows={n_rows}  {t0}~{t1}")

    man = pd.DataFrame(rows)
    out = manifest_dir / (manifest_name or "input_manifest.csv")
    man.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n[snapshot] files={len(man)} -> {out}")
    return man


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--globs-key", default="snapshot_globs")
    ap.add_argument("--manifest", default=None)
    a = ap.parse_args()
    main(a.version, a.globs_key, a.manifest)