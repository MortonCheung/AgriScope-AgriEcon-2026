"""STEP D8 — 区县统计公报解析与「年鉴 × 公报」交叉校验。

目的（任务书 §十三-5：同一数据多来源验证）：
  · 从区县统计公报原文中抽取关键农业指标（粮食/蔬菜/油料 的 面积与产量）；
  · 与《沈阳统计年鉴》分区县表对照，报告一致/差异；
  · 提供 2025 年（年鉴尚未覆盖）的区县农业数据。

单位换算（必须显式记录，不覆盖原文）：
  面积：万亩 → 公顷 ×(10000/15)=666.6667；万公顷 → 公顷 ×10000；公顷 → 公顷
  产量：亿斤 → 吨 ×50000；万吨 → 吨 ×10000；万斤 → 吨 ×5；吨 → 吨
  原文数值与原文单位一律保留在 `value_raw` / `unit_raw`。

红线：仅抽取**原文明确写出**的数字；抽不到即空；不做任何推算补齐。

产出（data/processed/）：
  district_bulletin_crop.csv          公报抽取结果（year × district × crop × metric）
  district_bulletin_vs_yearbook.csv   与年鉴对照
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, StepTimer, get_logger, save_table  # noqa: E402

MOD = "27_district_bulletin_parse"
LOG = get_logger(MOD)
RAW = PATHS.project["data_raw_district"] / "bulletins"
PROC = PATHS.project["data_processed"]

AREA_FACTOR = {"万亩": 10000.0 / 15.0, "万公顷": 10000.0, "公顷": 1.0, "亩": 1.0 / 15.0,
               "千公顷": 1000.0}
PROD_FACTOR = {"亿斤": 50000.0, "万吨": 10000.0, "万斤": 5.0, "吨": 1.0, "亿公斤": 100000.0,
               "公斤": 0.001}

# (指标键, 作物, 正则片段)
PATTERNS = [
    ("sown_area", "粮食", r"(?:全年)?粮食(?:作物)?(?:种植|播种)面积"),
    ("sown_area", "蔬菜及食用菌", r"(?:全年)?蔬菜(?:及食用菌)?(?:种植|播种)面积"),
    ("sown_area", "油料", r"(?:全年)?油料(?:作物)?(?:种植|播种)面积"),
    ("production", "粮食", r"(?:全年)?粮食(?:总)?产量"),
    ("production", "蔬菜及食用菌", r"(?:全年)?蔬菜(?:及食用菌)?产量"),
    ("production", "油料", r"(?:全年)?油料(?:作物)?产量"),
    ("production", "玉米", r"(?:全年)?玉米产量"),
    ("production", "稻谷", r"(?:全年)?(?:水稻|稻谷)产量"),
]


def text_of(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(path))
            return re.sub(r"\s+", " ", " ".join(doc[i].get_text() for i in range(len(doc))))
        except Exception:  # noqa: BLE001
            return ""
    if path.suffix.lower() == ".html":
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            from bs4 import BeautifulSoup
            t = BeautifulSoup(raw, "lxml").get_text(" ")
        except Exception:  # noqa: BLE001
            t = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", t)
    return ""


def extract(txt: str) -> List[Dict]:
    out = []
    for metric, crop, frag in PATTERNS:
        facs = AREA_FACTOR if metric == "sown_area" else PROD_FACTOR
        un = "万亩|万公顷|千公顷|公顷|亩" if metric == "sown_area" else "亿斤|万吨|万斤|吨|亿公斤|公斤"
        pat = re.compile(frag + r"[^，。；、]{0,24}?([\d]+(?:\.\d+)?)\s*(" + un + r")")
        m = pat.search(txt)
        if not m:
            continue
        v, u = float(m.group(1)), m.group(2)
        f = facs.get(u)
        if f is None:
            continue
        out.append({"crop": crop, "metric": metric, "value_raw": v, "unit_raw": u,
                    "value_std": v * f,
                    "std_unit": "公顷" if metric == "sown_area" else "吨"})
    return out


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        rows = []
        for d in sorted(RAW.iterdir()):
            if not d.is_dir():
                continue
            files = sorted(list(d.glob("bulletin_*.html")) + list(d.glob("bulletin_*.pdf")))
            for f in files:
                m = re.search(r"bulletin_(\d+|unknown)", f.stem)
                y = m.group(1)
                if y == "unknown":
                    continue
                txt = text_of(f)
                if len(txt) < 200:
                    continue
                for rec in extract(txt):
                    rec.update({"year": int(y), "district": d.name, "file": f.name})
                    rows.append(rec)
        b = pd.DataFrame(rows)
        if b.empty:
            log.warning("未从公报中抽取到任何农业指标")
            return
        b = b[["year", "district", "crop", "metric", "value_raw", "unit_raw",
               "value_std", "std_unit", "file"]].sort_values(["district", "year", "crop", "metric"])
        b.to_csv(PROC / "district_bulletin_crop.csv", index=False, encoding="utf-8-sig")
        save_table(b, "district_bulletin_crop.csv")
        log.info("公报抽取：%d 行；区县 %s；年份 %s", len(b),
                 sorted(b["district"].unique()), sorted(b["year"].unique()))

        # 与年鉴对照
        area = pd.read_csv(PROC / "district_crop_area.csv")
        prod = pd.read_csv(PROC / "district_crop_production.csv")
        yb = pd.concat([
            area[["year", "district", "crop"]].assign(metric="sown_area",
                                                       yb=area["sown_area"]),
            prod[["year", "district", "crop"]].assign(metric="production",
                                                       yb=prod["production"]),
        ], ignore_index=True)
        cmp = b.merge(yb, on=["year", "district", "crop", "metric"], how="left")
        cmp["rel_diff_vs_yearbook"] = np.where(
            cmp["yb"].gt(0), (cmp["value_std"] - cmp["yb"]) / cmp["yb"], np.nan)
        # 校验标记：越界抓取（同一文件含多层级数字，first-match 可能取到市级/省级）
        def _flag(r):
            d = r["rel_diff_vs_yearbook"]
            if pd.isna(d):
                return "no_yearbook_compare"
            if abs(d) > 1.0:
                return "suspect_scope(>100%)"
            if abs(d) > 0.05:
                return "diff>5%"
            return "ok"
        cmp["check_flag"] = cmp.apply(_flag, axis=1)
        cmp = cmp.rename(columns={"value_std": "bulletin_std", "yb": "yearbook_value"})
        cmp = cmp[["year", "district", "crop", "metric", "value_raw", "unit_raw",
                   "bulletin_std", "std_unit", "yearbook_value", "rel_diff_vs_yearbook",
                   "check_flag"]]
        cmp.to_csv(PROC / "district_bulletin_vs_yearbook.csv", index=False, encoding="utf-8-sig")
        save_table(cmp, "district_bulletin_vs_yearbook.csv")
        vc = cmp["check_flag"].value_counts().to_dict()
        log.info("对照标记：%s", vc)
        log.info("可比 %d 行；|相对差|≤5%% %d；>10%% %d",
                 int(cmp["rel_diff_vs_yearbook"].notna().sum()),
                 int((cmp["check_flag"] == "ok").sum()),
                 int((cmp["check_flag"].isin(["diff>5%", "suspect_scope(>100%)"])).sum()))


if __name__ == "__main__":
    main()
