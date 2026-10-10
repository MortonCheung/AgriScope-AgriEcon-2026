"""STEP D9 — 2015-2017 区县农业数据补充（区县统计年鉴）。

背景（重要）：
  《沈阳统计年鉴》官网 2016/2017/2018 卷（数据年 2015/2016/2017）的落地页**无附件**，
  即 2015-2017 年**市级年鉴口径的分区县农业表不可得**。为尽量向前补，
  改用**区县本级统计年鉴**（来源等级 B）：
    · 《康平县国民经济统计资料汇编》2016 卷（含 2016 与 2015 对照）
    · 《康平县国民经济统计资料汇编》2017 卷（含 2017 与 2016 对照）
  其中「国民经济主要指标」表直接给出县级 耕地面积 / 粮食作物播种面积 / 粮食作物总产量 /
  油料产量 / 蔬菜产量 / 水果产量，且**跨卷重复年份的数值完全一致**（2016 值在 2016 卷与
  2017 卷中相同）——这是本层的一次内部一致性校验。

只做「原文明确写出的数字」；不推算、不拆分、不插值。
本层作物口径与市级年鉴不同（仅总量级指标），故**单独成表**，并同时并入面板
（以 source_grade='B' 与 source_table 明确标注来源，不与 A 级混淆）。

产出（data/processed/）：
  district_early_years.csv        康平县 2015-2017 农业指标（含来源与校验）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, StepTimer, get_logger, save_table  # noqa: E402

MOD = "28_district_early_years"
LOG = get_logger(MOD)
SRC = PATHS.project["data_raw_district"] / "district_sources"
PROC = PATHS.project["data_processed"]

# 年鉴卷 → (文件名, 数据年, 对照年)
VOLUMES = [
    ("KP_yearbook_2016.pdf", 2016, 2015),
    ("KP_yearbook_2017.pdf", 2017, 2016),
]

# 指标（原始标签子串） → (crop, metric, 单位换算到 ha / t)
INDICATORS = [
    ("粮食作物播种面积", "粮食", "sown_area", "公顷", 1.0),
    ("粮食作物总产量", "粮食", "production", "吨", 1.0),
    ("油料产量", "油料", "production", "吨", 1.0),
    ("蔬菜产量", "蔬菜及食用菌", "production", "万吨", 10000.0),
    ("水果产量", "水果", "production", "吨", 1.0),
]


def page_with(title_kw: str, doc) -> int:
    for i in range(min(60, len(doc))):
        t = doc[i].get_text()
        if title_kw in t and "耕地面积" in t:
            return i
    return -1


def extract_volume(path: Path, dyear: int, pyear: int) -> List[Dict]:
    import fitz
    doc = fitz.open(str(path))
    idx = page_with("国民经济主要指标", doc)
    if idx < 0:
        LOG.warning("%s 未定位「国民经济主要指标」页", path.name)
        return []
    ws = doc[idx].get_text("words")
    # 数值列：当前年（x 约 270-320）、对照年（x 约 335-380）
    rows = {}
    for w in ws:
        x0, x1, txt = w[0], w[2], w[4]
        if not re.fullmatch(r"\d+(\.\d+)?", txt):
            continue
        rows.setdefault(round(w[1] / 4), []).append((x0, x1, txt))
    # 行标签
    labels = []
    for w in ws:
        if w[0] < 210 and re.search(r"[\u4e00-\u9fff]", w[4]):
            labels.append((round(w[1] / 4), w[4], w[0]))
    out = []
    for kw, crop, metric, unit, fac in INDICATORS:
        # 找到标签所在行
        hit = None
        for rk, txt, x in labels:
            if kw in txt:
                hit = (rk, x)
                break
        if hit is None:
            continue
        rk, xlab = hit
        # 取同一行（±2 格）内、x>250 的数值，按 x 排序取 前两个 = 当前年、对照年
        cand = []
        for k in (rk - 1, rk, rk + 1):
            for x0, x1, txt in rows.get(k, []):
                if x0 > 250:
                    cand.append((x0, float(txt)))
        cand.sort()
        if len(cand) < 2:
            continue
        cur, prev = cand[0][1], cand[1][1]
        for yr, v in ((dyear, cur), (pyear, prev)):
            out.append({"year": yr, "district": "康平县", "crop": crop, "metric": metric,
                        "value_raw": v, "unit_raw": unit, "value_std": v * fac,
                        "std_unit": "公顷" if metric == "sown_area" else "吨",
                        "source": f"《康平县国民经济统计资料汇编》{dyear}卷",
                        "source_table": "国民经济主要指标（二）·四、农村经济",
                        "source_grade": "B", "source_file": path.name})
    return out


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        rows = []
        for fn, dy, py in VOLUMES:
            p = SRC / fn
            if not p.exists():
                log.warning("缺少 %s，跳过", fn)
                continue
            r = extract_volume(p, dy, py)
            log.info("%s：抽取 %d 行", fn, len(r))
            rows.extend(r)
        if not rows:
            log.warning("未抽取到任何数据")
            return
        d = pd.DataFrame(rows)
        # 去重（同年同指标跨卷重复）并做一致性校验
        key = ["year", "district", "crop", "metric"]
        dup = d.groupby(key)["value_std"].nunique()
        conflict = dup[dup > 1]
        if len(conflict):
            log.warning("跨卷数值冲突：%s", conflict.to_dict())
        else:
            log.info("跨卷重复年份数值一致（内部校验通过）")
        d = d.sort_values(key + ["source_file"]).drop_duplicates(subset=key, keep="first")
        d = d[["year", "district", "crop", "metric", "value_std", "std_unit",
               "value_raw", "unit_raw", "source", "source_table", "source_grade"]]
        d.to_csv(PROC / "district_early_years.csv", index=False, encoding="utf-8-sig")
        save_table(d, "district_early_years.csv")
        log.info("已写 district_early_years.csv：%d 行；年份 %s", len(d), sorted(d["year"].unique()))
        log.info(d.to_string(index=False))


if __name__ == "__main__":
    main()
