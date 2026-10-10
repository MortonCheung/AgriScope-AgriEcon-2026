"""run_district.py — 沈阳区县农业生产 + 气象数据层：一键可复现运行。

顺序（每个脚本独立可重跑；已有原始文件会自动 SKIP）：
  20_district_yearbook_fetch    下载《沈阳统计年鉴》各卷 PDF（区县农业表主源）
  21_district_yearbook_parse    解析 3-4/3-5/3-6 三张分区县表 → 面积/产量/单产
  22_district_coordinates       区县代表点坐标（pfsc 官方接口）
  23_district_weather           区县天气采集（Open-Meteo ERA5）+ 年度气象派生
  24_district_bulletin_fetch    区县公报/年鉴采集（交叉校验 + 2025）
  27_district_bulletin_parse    公报抽取与「年鉴 × 公报」对照
  28_district_early_years       2015-2017 补充（区县年鉴，康平县）
  25_district_panel             构建 district_yearly_agri_weather_panel
  26_district_qa                数据质量检查与报告

用法：
  .venv/bin/python run_district.py              # 全部
  .venv/bin/python run_district.py --from 23    # 从第 23 步开始
  .venv/bin/python run_district.py --only 25,26 # 只跑指定步骤
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PY = HERE.parent / ".venv" / "bin" / "python"

STEPS = [
    ("20", "20_district_yearbook_fetch"),
    ("21", "21_district_yearbook_parse"),
    ("22", "22_district_coordinates"),
    ("23", "23_district_weather"),
    ("24", "24_district_bulletin_fetch"),
    ("27", "27_district_bulletin_parse"),
    ("28", "28_district_early_years"),
    ("25", "25_district_panel"),
    ("26", "26_district_qa"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="沈阳区县农业—气象数据层流水线")
    ap.add_argument("--from", dest="start", help="从该步骤号开始（如 23）")
    ap.add_argument("--only", help="只跑这些步骤号，逗号分隔（如 25,26）")
    args = ap.parse_args()

    todo = STEPS
    if args.only:
        want = set(args.only.split(","))
        todo = [s for s in STEPS if s[0] in want]
    elif args.start:
        idx = [i for i, s in enumerate(STEPS) if s[0] == args.start]
        todo = STEPS[idx[0]:] if idx else STEPS

    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    status, t0 = {}, time.time()
    for num, mod in todo:
        print(f"\n=== {num} {mod} ===")
        t = time.time()
        r = subprocess.run([py, str(HERE / "src" / f"{mod}.py")], cwd=HERE)
        status[mod] = "OK" if r.returncode == 0 else f"FAIL({r.returncode})"
        print(f"--- {mod}: {status[mod]} ({time.time() - t:.1f}s)")

    print("\n" + "=" * 60)
    for m, s in status.items():
        print(f"  {m:32s} {s}")
    print(f"总耗时 {time.time() - t0:.1f}s")
    return 0 if all(v == "OK" for v in status.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
