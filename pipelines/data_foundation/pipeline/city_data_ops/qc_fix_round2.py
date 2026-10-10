"""第二轮 QC 规范化：
1) 物候表：旧行把中文阶段标签错放在 derived_from_text 列 → 归位到 stage，derived_from_text 统一 true/false。
2) 丹东 price：删除 191 条业务主键真重复。
均只改 interim（派生层），原始 raw 不动；先备份。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
CITIES = ["dalian", "tieling", "dandong", "jinzhou", "chaoyang"]

CN2EN = {
    "插秧": "transplant", "春播": "sowing", "播种": "sowing", "春耕": "land_prep",
    "灌浆": "grain_filling", "秋收": "harvest", "收获": "harvest", "收割": "harvest",
    "分蘖": "tillering", "出苗": "emergence", "扬花": "flowering", "开花": "flowering",
    "测产": "yield_measurement", "返青": "regreening", "拔节": "jointing", "抽雄": "tasseling",
}


def fix_phenology() -> None:
    for c in CITIES:
        p = ROOT / c / "workspace" / "data" / "interim" / "phenology_events.csv"
        if not p.exists():
            continue
        d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        if "derived_from_text" not in d.columns:
            continue
        before = d["derived_from_text"].astype(str)
        # 中文标签 → 归位
        mask_cn = ~before.str.lower().isin(["true", "false", "nan", ""])
        n_fix = int(mask_cn.sum())
        if n_fix:
            # 若 stage 为空，用中文标签补 stage
            need = mask_cn & (d["stage"].isna() | (d["stage"].astype(str).str.strip() == ""))
            d.loc[need, "stage"] = d.loc[need, "derived_from_text"].map(
                lambda x: CN2EN.get(str(x), str(x)))
            d.loc[mask_cn, "derived_from_text"] = "true"
        d["derived_from_text"] = d["derived_from_text"].astype(str).str.lower().replace(
            {"nan": "", "": ""})
        if n_fix:
            shutil.copy2(p, p.with_suffix(f".bak_{STAMP}.csv"))
            d.to_csv(p, index=False, encoding="utf-8-sig")
        print(f"  [pheno] {c}: 归位 {n_fix} 行, 现 {len(d)} 行")


def fix_dandong_price() -> None:
    p = ROOT / "dandong" / "workspace" / "data" / "interim" / "price_observation.csv"
    if not p.exists():
        return
    d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    key = ["city", "county", "observation_date", "crop_raw", "market_name",
           "source_id", "price_level", "price_original", "unit_original"]
    key = [k for k in key if k in d.columns]
    n0 = len(d)
    d = d.drop_duplicates(subset=key, keep="first").reset_index(drop=True)
    if len(d) != n0:
        shutil.copy2(p, p.with_suffix(f".bak_{STAMP}.csv"))
        d.to_csv(p, index=False, encoding="utf-8-sig")
    print(f"  [price] 丹东: {n0} → {len(d)}（去重 {n0-len(d)}）")


if __name__ == "__main__":
    print("=== 物候列规范化 ===")
    fix_phenology()
    print("=== 丹东价格去重 ===")
    fix_dandong_price()
