#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V2 构建脚本 C：就绪度矩阵 / 排名 / 最终数据矩阵 / QC / 缺口说明。
"""
import csv, json, warnings
from pathlib import Path
from datetime import datetime
from collections import Counter

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
V1 = ROOT / "city_data/reference/decision_engine_supplement"
OUT = ROOT / "city_data/reference/decision_engine_supplement_v2"
CD = ROOT / "data/raw/retained_source/city_data"
AD = datetime.now().strftime("%Y-%m-%d")
CITIES = {"shenyang":"沈阳","dalian":"大连","tieling":"铁岭","chaoyang":"朝阳","jinzhou":"锦州","dandong":"丹东"}
CN6 = list(CITIES.values())

# 关键作物
GRAIN = ["玉米","水稻","大豆","高粱","谷子","花生","小麦"]
VEG10 = ["土豆","西红柿","黄瓜","韭菜","青椒","尖椒","茄子","芹菜","芸豆","甘蓝"]
VEG_OTHER = ["大白菜","大葱","胡萝卜","菜花","菠菜","油菜","白萝卜","洋葱"]
LIVESTOCK = ["猪肉","鸡蛋","牛肉","羊肉","鸡肉","牛奶"]
FRUIT = ["草莓","苹果","梨","葡萄","蓝莓","软枣猕猴桃"]
KEY = GRAIN + VEG10 + VEG_OTHER + LIVESTOCK + FRUIT


def rcsv(p):
    for enc in ("utf-8-sig","utf-8","gbk"):
        try: return pd.read_csv(p, encoding=enc, low_memory=False)
        except Exception: continue
    return None


# ---------- 汇总各城市数据可用性 ----------
price_stat, vol_stat = {}, {}
for cd, cn in CITIES.items():
    p = CD/cd/"data"/"price_observation.csv"
    if p.exists():
        df = rcsv(p)
        df["_d"] = pd.to_datetime(df.get("observation_date"), errors="coerce")
        df["_crop"] = np.where(df["price_level"].astype(str)=="market_average",
                               df["crop_raw"].astype(str).str.strip(), df["crop_standard"].astype(str))
        for crop, g in df.groupby("_crop"):
            if not str(crop).strip() or str(crop)=="nan": continue
            d = g["_d"].dropna()
            if len(d)==0: continue
            price_stat[(cn, crop)] = {"days": int(d.dt.date.nunique()),
                "levels": "|".join(sorted(set(g["price_level"].dropna().astype(str)))),
                "start": str(d.min())[:10], "end": str(d.max())[:10], "rows": len(g),
                "span_days": int((d.max()-d.min()).days)+1,
                "density": round(d.dt.date.nunique()/max(((d.max()-d.min()).days+1),1), 3)}
    v = CD/cd/"data"/"volume_observations.csv"
    if v.exists():
        dv = rcsv(v)
        vt = dv.get("volume_type", pd.Series(dtype=str))
        vol_stat[cn] = {"rows": len(dv), "daily_txn": int((vt=="daily_transaction").sum())}

# 面积/产量（年鉴 + OCR）→ 是否有作物级
area = rcsv(OUT/"planting_area_crop_yearly.csv")
yld = rcsv(OUT/"crop_yield_by_city.csv") if (OUT/"crop_yield_by_city.csv").exists() else None
area_crops = {}
if area is not None:
    for cn in CN6:
        s = set()
        for c in area.columns:
            if c in ("year","city","province","source_table","source_file","unit","quality_flag",
                     "source_level","access_date","source_file"): continue
            sub = area[(area["city"]==cn) & (area[c].astype(str).str.strip()!="") & (area[c].astype(str)!="nan")]
            if len(sub): s.add(c)
        area_crops[cn] = s

# 成本可用
cost = rcsv(OUT/"crop_cost_yearly_extended.csv")
cost_stat = {}
for _, r in cost.iterrows():
    c = str(r["city"])
    cost_stat.setdefault(c, set()).add(str(r["crop"]))

# ---------- MODEL_READINESS_V2 ----------
def grade_price(cn, crop):
    s = price_stat.get((cn, crop))
    if not s: return "RED", 0, ""
    d = s["days"]; dens = s.get("density", 0)
    # 连续性要求：日频须密度高；稀疏(coverage 低)即使天数多也降级
    if d >= 200 and dens >= 0.35: return "GREEN", d, s["levels"]
    if d >= 200 and dens >= 0.10: return "YELLOW", d, s["levels"]
    if d >= 30: return "YELLOW", d, s["levels"]
    return "RED", d, s["levels"]

def grade_area(cn, crop):
    s = area_crops.get(cn, set())
    if crop in s: return "GREEN"
    if "蔬菜" in s or "其他作物-蔬菜" in s: return ("YELLOW" if crop in VEG10+VEG_OTHER else "RED")
    return "RED"

rows = []
for cn in CN6:
    for crop in KEY:
        pg, days, lv = grade_price(cn, crop)
        vol = "GREEN" if (vol_stat.get(cn,{}).get("daily_txn",0)>=200 and (cn,crop) in price_stat and
                          price_stat[(cn,crop)]["days"]>=200) else "RED"
        ag = grade_area(cn, crop)
        pr = ag  # 产量与面积同源
        # 成本
        cl = cost_stat.get(cn, set())
        if any(crop in c for c in cl): cg = "GREEN"
        elif cn in ("辽阳","东北(含沈阳/朝阳/锦州/铁岭)") or any("设施" in c for c in cl): cg = "YELLOW"
        else: cg = "RED"
        # 成本更细：六城中只有沈阳有本地粮食成本
        if crop in ("玉米","水稻") and cn == "沈阳": cg = "GREEN"
        elif crop in VEG10+VEG_OTHER: cg = "YELLOW" if "东北(含沈阳/朝阳/锦州/铁岭)" in cl else "RED"
        if crop in ("玉米","大豆"): 
            cg = "GREEN" if cn=="沈阳" else ("YELLOW" if cn in ("铁岭","朝阳") else cg)
        wea = "GREEN"
        soil = "GREEN"
        rs = "RED"
        dis = "YELLOW"
        phe = "GREEN" if crop in VEG10+GRAIN else "YELLOW"
        # HRI
        hri = {"price_percentile": pg if pg!="RED" else "RED",
               "momentum": pg if pg!="RED" else "RED",
               "continuous_rise": pg if pg!="RED" else "RED",
               "volatility": pg if pg!="RED" else "RED",
               "volume": vol, "area_yoy": ag, "production_yoy": pr,
               "external_case": "GREEN"}
        hri_n = sum(1 for v in hri.values() if v in ("GREEN","YELLOW"))
        hri_g = "GREEN" if hri_n>=6 else ("YELLOW" if hri_n>=4 else "RED")
        # price model
        pm = "GREEN" if pg=="GREEN" and cn in ("沈阳",) else ("YELLOW" if pg=="GREEN" else ("YELLOW" if pg=="YELLOW" else "RED"))
        # profit: price + yield + cost
        pf = "GREEN" if (pg=="GREEN" and ag in ("GREEN","YELLOW") and cg=="GREEN") else (
             "YELLOW" if (pg in ("GREEN","YELLOW") and cg in ("GREEN","YELLOW")) else
             ("YELLOW" if pg in ("GREEN","YELLOW") else "RED"))
        rows.append({"city":cn,"crop":crop,"price":pg,"price_days":days,"price_level":lv,
                     "volume":vol,"area":ag,"production":pr,"cost":cg,"weather":wea,"soil":soil,
                     "remote_sensing":rs,"disaster":dis,"phenology":phe,
                     "HRI":hri_g,"price_model":pm,"profit":pf,
                     "note":""})
mr = pd.DataFrame(rows)
mr.to_csv(OUT/"MODEL_READINESS_V2.csv", index=False, encoding="utf-8-sig")
print(f"[OK] MODEL_READINESS_V2.csv  {len(mr)} 行")

# ---------- TOP_CITY_CROP_MODEL_COMBOS_V2 ----------
SCORE = {"GREEN":2,"YELLOW":1,"RED":0}
combo = []
for _, r in mr.iterrows():
    s = (SCORE[r["price"]]*18 + SCORE[r["volume"]]*8 + SCORE[r["area"]]*5 + SCORE[r["production"]]*4
         + SCORE[r["cost"]]*6 + SCORE[r["weather"]]*3 + SCORE[r["soil"]]*3
         + SCORE[r["disaster"]]*2 + SCORE[r["phenology"]]*2 + SCORE[r["HRI"]]*5)
    combo.append({"city":r["city"],"crop":r["crop"],"price":r["price"],"volume":r["volume"],
                  "area":r["area"],"production":r["production"],"cost":r["cost"],
                  "price_level":r["price_level"],"price_days":r["price_days"],
                  "HRI":r["HRI"],"score":s,
                  "grade":("A" if s>=80 else "B" if s>=60 else "C" if s>=35 else "D")})
cd = pd.DataFrame(combo).sort_values(["score","city","crop"], ascending=[False,True,True])
cd.to_csv(OUT/"TOP_CITY_CROP_MODEL_COMBOS_V2.csv", index=False, encoding="utf-8-sig")
print(f"[OK] TOP_CITY_CROP_MODEL_COMBOS_V2.csv  {len(cd)} 行")
print("  Top 12:")
for _, r in cd.head(12).iterrows():
    print(f"    {r['city']:4s} {r['crop']:6s} 分={r['score']:3d} 级={r['grade']} "
          f"(价{rcsv and ''}{r['price']} 量{r['volume']} 本{r['cost']})")

# ---------- FINAL_DATA_READINESS_MATRIX_V2 ----------
mr.to_csv(OUT/"FINAL_DATA_READINESS_MATRIX_V2.csv", index=False, encoding="utf-8-sig")
print("[OK] FINAL_DATA_READINESS_MATRIX_V2.csv")

# ---------- HRI / CLIMATE / PROFIT readiness ----------
hri_rows = []
for _, r in mr.iterrows():
    hri_rows.append({"city":r["city"],"crop":r["crop"],
        "price_percentile":r["price"],"momentum":r["price"],"continuous_rise":r["price"],
        "volatility":r["price"],"volume":r["volume"],"area_yoy":r["area"],
        "production_yoy":r["production"],"external_case":"GREEN","overall":r["HRI"]})
pd.DataFrame(hri_rows).to_csv(OUT/"HRI_FEATURE_READINESS_V2.csv", index=False, encoding="utf-8-sig")
print(f"[OK] HRI_FEATURE_READINESS_V2.csv  {len(hri_rows)} 行")

clim = []
for cn in CN6:
    clim.append({"city":cn,"weather":"GREEN","soil":"GREEN","ndvi_evi":"RED",
                 "drought":"GREEN","heavy_rain":"GREEN",
                 "disaster_validation":("YELLOW" if cn in ("铁岭","朝阳","丹东","锦州") else "RED"),
                 "overall":("YELLOW" if cn!="大连" else "RED")})
pd.DataFrame(clim).to_csv(OUT/"CLIMATE_FEATURE_READINESS_V2.csv", index=False, encoding="utf-8-sig")
print(f"[OK] CLIMATE_FEATURE_READINESS_V2.csv  {len(clim)} 行")

prof = []
for cn in CN6:
    for crop in (GRAIN+VEG10):
        _, days, _ = grade_price(cn, crop)
        cost_local = "YES" if (cn=="沈阳" and crop in ("玉米","水稻")) else "NO"
        cost_proxy = "YES" if (crop in VEG10 or cn in ("铁岭","朝阳")) else "NO"
        prof.append({"city":cn,"crop":crop,"price":("GREEN" if days>=200 else "YELLOW" if days>=30 else "RED"),
                     "yield":grade_area(cn,crop),"cost_local":cost_local,"cost_proxy":cost_proxy,
                     "cost_user_required":("NO" if cost_local=="YES" else "YES"),
                     "profit_ready":("GREEN" if (days>=200 and cost_local=="YES") else
                                     ("YELLOW" if days>=200 else "RED"))})
pd.DataFrame(prof).to_csv(OUT/"PROFIT_MODEL_READINESS_V2.csv", index=False, encoding="utf-8-sig")
print(f"[OK] PROFIT_MODEL_READINESS_V2.csv  {len(prof)} 行")

# ---------- 覆盖统计 ----------
cov = []
for col in ["price","volume","area","production","cost","weather","soil","remote_sensing",
            "disaster","phenology","HRI","price_model","profit"]:
    vc = mr[col].value_counts().to_dict()
    cov.append({"dimension":col, **{k:int(v) for k,v in vc.items()}})
pd.DataFrame(cov).fillna(0).to_csv(OUT/"READINESS_COVERAGE_SUMMARY_V2.csv", index=False, encoding="utf-8-sig")
print("[OK] READINESS_COVERAGE_SUMMARY_V2.csv")
print(mr[["price","volume","area","production","cost","weather","soil","remote_sensing",
          "disaster","phenology","HRI","price_model","profit"]].apply(lambda s: s.value_counts().to_dict()))
print("\n完成脚本 C。")
