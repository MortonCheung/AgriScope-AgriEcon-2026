"""STEP D2 — 区县农作物播种面积 / 总产量 / 单产量：年鉴表格解析。

数据源：《沈阳统计年鉴》（沈阳市统计局）农业章三张分区县表——
  · 农作物播种面积（单位 公顷）
  · 农作物总产量（单位 吨）
  · 农作物单产量（单位 公斤/公顷）
三张表结构一致：**行 = 作物，列 = 地区（沈阳市 + 8 个农业区县）**。

定位方式：含「农作物总播种面积」且含「苏家屯区」的页 = 面积表，
其后连续两页 = 产量表、单产量表（已逐卷核对，表号各卷不同）。

解析方法（可复现于任何一卷）：
  1. PyMuPDF 取 words（含 bbox）；
  2. 按 y 聚类成行（tol=5px，行高≈19px；作物标签与数值同处一行）；
  3. 表头行（含 沈阳市/苏家屯区/…）给出各区县列的 x 中心；
  4. 行内按 x 合并相邻碎词（如 "1"+"358" → 1358），按最近列中心归位；
     PDF 各列右对齐，故中心法 + 容差足够（已用新民市 2023 官方数字逐项验证，误差 0）。

作物名规范化（保持与官方口径一致，仅消除各卷写法差异）：
  · 「薯类」≡「薯类（折粮）」（2023/2024 卷面积表省略"折粮"字样）
  · 「春小麦」为「小麦」的子项，两值逐行完全相等（37/37 验证）→ 归并到「小麦」
  · 「向日葵籽」≡「葵花籽」
  其余保留原始标签 crop_label_raw，可回溯。

红线：
  - 只做「读取官方文件 → 结构化」，不插值、不推算、不补数；
  - 空单元格一律留空（年鉴留空表示 0 或无数据，不猜）；
  - 原始单位原样记录，不在本层换算；
  - 保留市级合计（沈阳市）行到独立 QA 表，供「区县合计 vs 市级」一致性检查。

产出（data/processed/）：
  district_crop_area.csv / district_crop_production.csv / district_crop_yield.csv
  district_yearbook_city_total.csv     （市级合计，QA 用）
  outputs/tables/district_yearbook_parse_report.csv  （逐卷逐表审计）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, StepTimer, get_logger, save_table  # noqa: E402

MOD = "21_district_yearbook_parse"
LOG = get_logger(MOD)
YB_DIR = PATHS.project["data_raw_district"] / "yearbooks"
PROC = PATHS.project["data_processed"]

DISTRICTS = ["苏家屯区", "浑南区", "沈北新区", "于洪区", "辽中区", "康平县", "法库县", "新民市"]
CITY = "沈阳市"


def save_processed(df: pd.DataFrame, artifact_key: str, table_name: str) -> None:
    """标准化数据写 data/processed/（任务书 §十一 主位置）；同时在 outputs/tables/ 留副本。"""
    p = PATHS.artifacts[artifact_key]
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False, encoding="utf-8-sig")
    try:
        df.to_parquet(p.with_suffix(".parquet"), index=False)
    except Exception:  # noqa: BLE001
        pass
    save_table(df, table_name)
    LOG.info("已写 %s（%d 行）", p.name, len(df))


CROP_MAP = {
    "农作物总播种面积": "农作物总播种面积",
    "粮食作物": "粮食", "粮食作物合计": "粮食",
    "谷物": "谷物", "稻谷": "稻谷", "小麦": "小麦", "春小麦": "小麦",
    "玉米": "玉米", "其他谷物": "其他谷物", "其它谷物": "其他谷物",
    "谷子": "谷子", "高粱": "高粱", "荞麦": "荞麦",
    "豆类": "豆类", "豆类合计": "豆类", "大豆": "大豆", "绿豆": "绿豆", "红小豆": "红小豆",
    "薯类": "薯类(折粮)", "薯类(折粮)": "薯类(折粮)", "薯类（折粮）": "薯类(折粮)",
    "马铃薯": "马铃薯",
    "油料": "油料", "油料作物": "油料", "花生": "花生", "芝麻": "芝麻",
    "葵花籽": "葵花籽", "向日葵籽": "葵花籽",
    "蔬菜(含菜用瓜)及食用菌": "蔬菜及食用菌", "蔬菜（含菜用瓜）及食用菌": "蔬菜及食用菌",
    "蔬菜及食用菌": "蔬菜及食用菌",
    "瓜果类": "瓜果", "西瓜": "西瓜", "甜瓜": "甜瓜", "草莓": "草莓",
    "棉花": "棉花", "糖类": "糖料", "糖料": "糖料", "甜菜": "甜菜", "麻类": "麻类",
    "青饲料": "青饲料", "药材类合计": "药材", "其它农作物": "其它农作物",
}
PREFIX = re.compile(r"^[一二三四五六七八九十]+、|^#|^其中[:：]|^其中|^（[一二三四五六七八九十]）|^\([一二三四五六七八九十]\)|^\d+\.")


def _clean_label(s: str) -> str:
    return PREFIX.sub("", s.strip().replace(" ", "")).strip()


def norm_crop(label: str) -> str:
    return CROP_MAP.get(_clean_label(label), _clean_label(label))


# -----------------------------------------------------------------------------
# PDF 表格重建
# -----------------------------------------------------------------------------
def _rows(pdf_page, ytol: float = 5.0) -> List[List[Tuple]]:
    ws = sorted(pdf_page.get_text("words"), key=lambda t: (t[1], t[0]))
    rows, cur = [], []
    for w in ws:
        if cur and abs(w[1] - cur[-1][1]) > ytol:
            rows.append(cur)
            cur = []
        cur.append(w)
    if cur:
        rows.append(cur)
    return rows


def _merge(row: List[Tuple], gap: float = 15.0) -> List[Tuple[float, float, str]]:
    out: List[List] = []
    for w in sorted(row, key=lambda t: t[0]):
        if out and (w[0] - out[-1][1]) < gap:
            out[-1][1] = w[2]
            out[-1][2] += w[4]
        else:
            out.append([w[0], w[2], w[4]])
    return [(o[0], o[1], o[2]) for o in out]


def parse_table(page) -> Tuple[Optional[List[str]], List[Tuple[str, Dict[str, str]]]]:
    rows = [_merge(r) for r in _rows(page)]
    hdr_idx, cols = None, None
    for i, r in enumerate(rows):
        toks = [t[2] for t in r]
        if CITY in toks and "苏家屯区" in toks:
            hdr_idx = i
            cols = [(t[2], (t[0] + t[1]) / 2) for t in r if t[2] in ([CITY] + DISTRICTS)]
            break
    if hdr_idx is None or not cols:
        return None, []
    order = [c for c, _ in cols]
    centers = {c: x for c, x in cols}
    cut = min(centers.values()) - 60

    out = []
    for r in rows[hdr_idx + 1:]:
        if not any(t[1] < cut and _clean_label(t[2]) for t in r):
            continue
        label = "".join(t[2] for t in r if t[1] < cut).strip()
        if not label or label == "项目":
            continue
        vals = {}
        for x0, x1, txt in r:
            if x0 < cut:
                continue
            s = txt.strip()
            if not re.fullmatch(r"-?[\d\s,]+", s):
                continue
            v = s.replace(" ", "").replace(",", "")
            nearest = min(centers.items(), key=lambda kv: abs(kv[1] - (x0 + x1) / 2))
            if abs(nearest[1] - (x0 + x1) / 2) > 70:
                continue
            vals[nearest[0]] = v
        if vals:
            out.append((label, vals))
    return order, out


def find_three_tables(doc):
    for i in range(len(doc)):
        t = doc[i].get_text().replace("\n", "")
        if ("农作物总播种面积" in t) and ("苏家屯区" in t) and i + 2 < len(doc):
            return i, i + 1, i + 2
    return None


def unit_of(page, default: str) -> str:
    t = page.get_text()
    # 注意顺序：必须先判 "公斤/公顷"，否则会被子串 "公顷" 抢先匹配
    for u in ["公斤/公顷", "万吨", "公顷", "吨", "亩"]:
        if u in t:
            return u
    return default


def parse_volume(pdf: Path, vol: int, dyear: int, log) -> Tuple[dict, dict]:
    import fitz
    doc = fitz.open(str(pdf))
    found = find_three_tables(doc)
    res = {"area": [], "production": [], "yield": []}
    meta = {"volume": vol, "data_year": dyear, "file": pdf.name}
    if not found:
        log.warning("%s：未定位到三张区县农业表", pdf.name)
        meta["located"] = False
        return res, meta
    a, p, y = found
    meta.update({"located": True, "area_page": a, "prod_page": p, "yield_page": y})
    for key, idx, default_unit in (("area", a, "公顷"), ("production", p, "吨"),
                                   ("yield", y, "公斤/公顷")):
        page = doc[idx]
        order, recs = parse_table(page)
        unit = unit_of(page, default_unit)
        meta[f"{key}_unit"] = unit
        meta[f"{key}_nrows"] = len(recs)
        meta[f"{key}_districts"] = ",".join(order) if order else ""
        if not recs:
            log.warning("%s 表 %s 解析 0 行", pdf.name, key)
            continue
        for label, vals in recs:
            crop = norm_crop(label)
            if not crop:
                continue
            for dname in [CITY] + DISTRICTS:
                if dname in vals:
                    res[key].append({"year": dyear, "district": dname, "crop": crop,
                                     "crop_label_raw": label, "value_raw": vals[dname],
                                     "unit": unit})
    return res, meta


def _tidy(rows: list, valname: str, unitname: str) -> pd.DataFrame:
    d = pd.DataFrame(rows)
    if d.empty:
        return d
    d["value"] = pd.to_numeric(d["value_raw"], errors="coerce")
    d = d.rename(columns={"value": valname, "unit": unitname})
    d = d[["year", "district", "crop", "crop_label_raw", valname, unitname, "value_raw"]]
    # 归并后可能产生重复键（如 小麦/春小麦 合并）→ 去重（值经核验完全相等）
    return d.sort_values(["year", "district", "crop"]).drop_duplicates(
        subset=["year", "district", "crop"], keep="first").reset_index(drop=True)


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        pdfs = sorted(YB_DIR.glob("SY_yearbook_*.pdf"))
        if not pdfs:
            raise FileNotFoundError(f"未找到年鉴 PDF：{YB_DIR}")
        all_rows = {"area": [], "production": [], "yield": []}
        metas = []
        for pdf in pdfs:
            m = re.search(r"yearbook_(\d+)_data(\d+)", pdf.name)
            vol, dyear = int(m.group(1)), int(m.group(2))
            res, meta = parse_volume(pdf, vol, dyear, log)
            for k in all_rows:
                all_rows[k].extend(res[k])
            metas.append(meta)
            log.info("%s（数据年 %d）：面积 %d / 产量 %d / 单产 %d 行",
                     pdf.name, dyear, len(res["area"]), len(res["production"]), len(res["yield"]))

        def split(rows: list, valname: str, unitname: str, table: str, notes: str):
            d = _tidy(rows, valname, unitname)
            if d.empty:
                return d, d
            d["source"] = "沈阳市统计局《沈阳统计年鉴》"
            d["source_table"] = table
            d["source_grade"] = "A"
            d["notes"] = notes
            return d[d["district"] != CITY], d[d["district"] == CITY]

        area, area_city = split(all_rows["area"], "sown_area", "area_unit",
                                "农作物播种面积（分区县）", "原始单位=公顷；空值=年鉴留空，未插补")
        prod, prod_city = split(all_rows["production"], "production", "production_unit",
                                "农作物总产量（分区县）", "原始单位=吨；空值=年鉴留空，未插补")
        yld, yld_city = split(all_rows["yield"], "yield_value", "yield_unit",
                              "农作物单产量（分区县）", "官方公布单产；原始单位=公斤/公顷")
        if len(yld):
            yld["yield_method"] = "official"

        save_processed(area, "district_crop_area", "district_crop_area.csv")
        save_processed(prod, "district_crop_production", "district_crop_production.csv")
        save_processed(yld, "district_crop_yield", "district_crop_yield.csv")
        city = pd.concat([
            area_city.assign(measure="sown_area").rename(
                columns={"sown_area": "value", "area_unit": "unit"}),
            prod_city.assign(measure="production").rename(
                columns={"production": "value", "production_unit": "unit"}),
            yld_city.assign(measure="yield").rename(
                columns={"yield_value": "value", "yield_unit": "unit"}),
        ], ignore_index=True)
        city = city[["year", "crop", "measure", "value", "unit", "value_raw"]]
        city.to_csv(PROC / "district_yearbook_city_total.csv", index=False, encoding="utf-8-sig")
        save_table(city, "district_yearbook_city_total.csv")
        log.info("市级合计 QA 表：%d 行", len(city))

        meta_df = pd.DataFrame(metas)
        save_table(meta_df, "district_yearbook_parse_report.csv")

        log.info("合计：面积 %d 行（%d 年）；产量 %d 行；单产 %d 行",
                 len(area), area["year"].nunique() if len(area) else 0, len(prod), len(yld))
        if len(area):
            log.info("年份：%s；区县 %d；作物 %d",
                     sorted(area["year"].unique()), area["district"].nunique(),
                     area["crop"].nunique())


if __name__ == "__main__":
    main()
