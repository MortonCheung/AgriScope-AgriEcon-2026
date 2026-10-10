"""P4：生产单位归一化 QC + 价格商品维度映射 dim_crop_mapping。

1) production_yearly_qc.csv —— 不覆盖原始 interim，另存 QC 后表。
   修复 2017-2019「吨被标为万吨」：以作物名中的 (吨)/(万吨) 后缀为权威单位标记。
2) dim_crop_mapping.csv —— 价格/生产的 crop_raw → crop_standard 映射（含置信度，不强行合并）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
OUT = ROOT.parent / "archive" / "audits" / "gap_analysis_20260922"
OUT.mkdir(exist_ok=True)
CITIES = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
          "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}


def interim(city, name):
    p = ROOT / city / "data" / name
    return pd.read_csv(p, encoding="utf-8-sig", low_memory=False) if p.exists() else None


# ---------- 1. 生产单位 QC ----------
def production_qc():
    rows = []
    for c, cn in CITIES.items():
        d = interim(c, "production_yearly.csv")
        if d is None:
            continue
        for r in d.itertuples(index=False):
            rd = r._asdict()
            crop_raw = str(rd.get("crop") or "")
            src_unit = str(rd.get("unit_production") or "")
            prod = rd.get("production")
            prod_ton_col = rd.get("production_ton")
            flag = []
            # 权威单位：作物名后缀 > 显式单位
            if "(吨)" in crop_raw or "（吨）" in crop_raw:
                unit_original = "吨"
            elif "(万吨)" in crop_raw or "（万吨）" in crop_raw:
                unit_original = "万吨"
            elif src_unit in ("吨", "万吨"):
                unit_original = src_unit
            else:
                unit_original = None
            crop_std = re.sub(r"[（(](万吨|吨)[)）]", "", crop_raw).strip()
            # 计算 production_ton
            pton = None
            if pd.notna(prod_ton_col):
                pton = float(prod_ton_col)          # 2020-2025 已归一
            elif pd.notna(prod) and unit_original:
                pton = float(prod) * (10000 if unit_original == "万吨" else 1)
            # flag：显式单位写万吨，但作物名说吨
            if pd.notna(prod) and unit_original == "吨" and "万吨" in src_unit:
                flag.append("UNIT_MISLABEL: 值实为吨, 单位误标万吨")
            # 量级审查：标万吨但数值巨大(城市单作物年产>3000万吨不合理) → 疑为吨，置空不猜
            if pton is not None and unit_original == "万吨" and pton >= 3e7:
                flag.append(f"UNIT_REVIEW: 标万吨但值={pton/1e4:.0f}(量级异常,疑为吨),production_ton置空")
                pton = None
            rows.append({
                "city": cn, "year": rd.get("year"), "crop_raw": crop_raw,
                "crop_standard": crop_std,
                "planting_area_kha": rd.get("planting_area_kha"),
                "production_ton": pton,
                "unit_original": unit_original,
                "unit_production_source": src_unit,
                "qc_flag": "; ".join(flag),
                "source": rd.get("source"),
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "production_yearly_qc.csv", index=False, encoding="utf-8-sig")
    n = int((df["qc_flag"].astype(str).str.len() > 0).sum())
    print(f"[OK] production_yearly_qc.csv {df.shape}；单位错标修正标记 {n} 行")
    return df


# ---------- 2. dim_crop_mapping ----------
# 仅收录高置信同义词（可判断同物）；存疑不合并
ALIAS = {
    "番茄": "西红柿", "小番茄": None, "圣女果": None,
    "洋白菜": "甘蓝", "卷心菜": "甘蓝", "大头菜": "甘蓝", "圆白菜": "甘蓝",
    "青萝卜": "萝卜", "白萝卜": "萝卜", "红萝卜": "萝卜", "水萝卜": "萝卜",
    "圆葱": "洋葱", "葱头": "洋葱", "洋葱头": "洋葱",
    "茭瓜": "西葫芦", "角瓜": "西葫芦",
    "蒜苔": "蒜薹",
    "马铃薯": "土豆", "洋芋": "土豆",
    "菜花": "花椰菜", "花菜": "花椰菜",
    "大葱": "大葱", "铁杆大葱": "大葱",
    "尖椒": "尖椒", "青尖椒": "尖椒",
    "架豆王": "芸豆", "架豆": "芸豆", "四季豆": "芸豆", "豆角": "芸豆",
    "生菜": "生菜", "油麦菜": "油麦菜",
}
NON_AGRI_HINT = re.compile(r"苗|树|种子|种苗|木材|花卉|草|建材|农机|饲|兽药|化肥|农药|地膜|菌种")
ANIMAL = re.compile(r"猪|牛|羊|鸡|鸭|鹅|鱼|虾|蟹|蛋|奶|毛|皮")

# 主粮/蔬菜/水果/畜产（研究核心）
PRIMARY = re.compile(r"玉米|水稻|稻谷|大米|小麦|面粉|大豆|高粱|谷子|马铃薯|土豆|白菜|黄瓜|西红柿|番茄|茄子|青椒|尖椒|辣椒|芸豆|豆角|芹菜|韭菜|菠菜|甘蓝|油菜|萝卜|洋葱|胡萝卜|大葱|蒜薹|蒜|姜|菜花|生菜|冬瓜|南瓜|苹果|梨|桃|葡萄|草莓|樱桃|蓝莓|板栗|花生|鸡蛋|猪肉|牛肉|羊肉|鸡肉|牛奶|谷物|粮食|蔬菜|水果")


def build_dim():
    raws = {}
    for c in CITIES:
        d = interim(c, "price_observation.csv")
        if d is not None and "crop_raw" in d.columns:
            for x in d["crop_raw"].dropna().astype(str).unique():
                raws.setdefault(x, set()).add("price")
        d = interim(c, "production_yearly.csv")
        if d is not None and "crop" in d.columns:
            for x in d["crop"].dropna().astype(str).unique():
                raws.setdefault(x, set()).add("production")
    rows = []
    for raw, srcs in sorted(raws.items()):
        std = ALIAS.get(raw, raw)
        conf = "exact"
        note = ""
        if std is None:
            std = raw
            conf = "low"
            note = "存在歧义(可能为小果/不同规格),未合并"
        elif std != raw:
            conf = "high"
            note = "同义词归一"
        is_primary = bool(PRIMARY.search(std))
        if NON_AGRI_HINT.search(raw):
            is_primary = False
            if "/" not in note:
                note += "; 疑非食用农产品(苗/种/木等)"
        rows.append({
            "crop_raw": raw, "crop_standard": std,
            "crop_family": "",
            "category": "livestock" if ANIMAL.search(std) else "crop",
            "variety": "", "grade": "", "origin": "", "specification": "",
            "is_primary_agri_product": is_primary,
            "mapping_confidence": conf, "mapping_method": "curated_alias",
            "in_price": "price" in srcs, "in_production": "production" in srcs,
            "notes": note,
        })
    df = pd.DataFrame(rows).sort_values(["is_primary_agri_product", "crop_standard"], ascending=False)
    df.to_csv(OUT / "dim_crop_mapping.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] dim_crop_mapping.csv {df.shape}；primary={int(df['is_primary_agri_product'].sum())}，"
          f"归一(high)={int((df['mapping_confidence']=='high').sum())}，low={int((df['mapping_confidence']=='low').sum())}")
    return df


if __name__ == "__main__":
    production_qc()
    build_dim()
