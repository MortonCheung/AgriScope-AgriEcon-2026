"""统一价格观测事实层构建器（AgriScope）。

目标：把来自不同来源（官方/部门/平台/第三方）的价格观测，统一为单一 schema。
原则：
  - schema 统一，来源不统一（允许 city 级 / market 级 / farm_gate 级并存）
  - 保留 price_original + unit_original，绝不用 price_per_kg 覆盖原值
  - price_level 严格区分：farm_gate / wholesale / market_average / retail_market / supermarket /
    ecommerce / instant_retail / community_groupbuy
  - 同一天同一 city+crop+market+source+price_level 的多条来源不去重（不同层级是不同观测）

输入（city_data/reference/staging + city_data/reference/marts 现有）：
  city_data/reference/marts/fact_price_city.csv        沈阳/朝阳/锦州/铁岭/大连/丹东（基础，已含多源）
  city_data/reference/staging/jinzhou_price_ocr_unique.csv   锦州菜篮子 OCR（每唯一图一条）
  city_data/reference/staging/lnnync_grain_weekly.csv / lnnync_veg_weekly.csv   省农业农村厅 省级+区县极值
  city_data/reference/staging/lnnync_veg_market_nodes.csv   省农业农村厅 市场级极值节点（含大连果菜/南关岭）
  city_data/reference/staging/铁岭_price_tielingxian.csv、tieling_price_county_nodes.csv
  city_data/reference/staging/dandong_price_monthly_fgw.csv、dandong_price_articles.csv、dandong_price_lnnync_nodes.csv
  city_data/reference/staging/dalian_price_weekly.csv、dalian_price_monthly.csv、dalian_mofcom_price.csv、dalian_nanguanling_wholesale.csv
  city_data/reference/staging/chaoyang_price_daily.csv、朝阳_price_lnfgw.csv、锦州_price_lnfgw.csv、铁岭_price_lnfgw.csv、铁岭_price_lnnync.csv
  city_data/reference/staging/moa_wholesale_prices.csv
  city_data/reference/staging/jinzhou_price_basket_weekly.csv
  data/raw/prices/b2b/cnhnb_hangqing_rows.jsonl

输出：city_data/reference/marts/fact_price_observation.csv / .parquet
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STAGING = ROOT / "city_data/reference/staging"
MARTS = ROOT / "city_data/reference/marts"
MARTS.mkdir(parents=True, exist_ok=True)

RETRIEVAL = datetime.now().isoformat(timespec="seconds")

UNIFIED = [
    "city", "county", "market_name", "store_name", "platform",
    "crop_raw", "crop_standard", "sku_name", "specification", "package_size",
    "price_original", "unit_original", "price_per_kg", "price_level",
    "observation_date", "observation_time", "frequency",
    "source_type", "source_name", "source_url", "source_id", "retrieval_time",
    "promotion_flag", "member_price_flag", "derived_flag",
    "quality_grade", "raw_file", "geo_level", "record_kind", "note",
]

_500G = {"元/500g", "元/500克", "元/500克(默认)", "元/500克（周报默认）", "元/斤", "元/500G"}
_KG = {"元/公斤", "元/kg", "元/千克", "元/KG"}


def to_per_kg(price, unit):
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    u = str(unit or "").strip()
    if u in _500G:
        return round(p * 2, 4)
    if u in _KG:
        return round(p, 4)
    if u == "元/吨":
        return round(p / 1000, 4)
    if u == "元/两":
        return round(p * 20, 4)
    return None


def resolve_level(price_type, market_name, source_id=""):
    mn = str(market_name or "")
    pt = str(price_type or "").lower()
    if pt in ("wholesale",) or "批发" in mn:
        return "wholesale"
    if pt in ("market_average",) or "均价" in mn or "平均" in mn:
        return "market_average"
    if pt in ("farm_gate",):
        return "farm_gate"
    if "超市" in mn or "香橙源" in mn or "V+优果" in mn or "真新鲜" in mn:
        return "supermarket"
    if pt in ("retail",):
        return "retail_market"
    return "retail_market"


def _mkrow(**kw):
    row = {k: None for k in UNIFIED}
    row.update(kw)
    return row


def from_fact_price_city() -> list[dict]:
    f = MARTS / "fact_price_city.csv"
    if not f.exists():
        return []
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    out = []
    for r in d.itertuples(index=False):
        mn = getattr(r, "market_name", None)
        out.append(_mkrow(
            city=r.city, county=getattr(r, "district", None),
            market_name=mn, store_name=mn if ("超市" in str(mn)) else None,
            crop_raw=getattr(r, "crop_raw", None),
            crop_standard=getattr(r, "variety", None) or getattr(r, "crop_raw", None),
            price_original=getattr(r, "price", None),
            unit_original=getattr(r, "unit_raw", None),
            price_per_kg=getattr(r, "price_per_kg", None),
            price_level=resolve_level(getattr(r, "price_type", None), mn, getattr(r, "source_id", "")),
            observation_date=str(getattr(r, "date", ""))[:10],
            frequency="irregular_official",
            source_type="official_government",
            source_name=getattr(r, "source_name", None),
            source_url=getattr(r, "source_url", None),
            source_id=getattr(r, "source_id", None),
            retrieval_time=RETRIEVAL,
            quality_grade=getattr(r, "quality_grade", None),
            raw_file=getattr(r, "raw_file", None),
            geo_level=getattr(r, "geo_level", None),
        ))
    return out


def from_jinzhou_ocr() -> list[dict]:
    f = STAGING / "jinzhou_price_ocr_unique.csv"
    if not f.exists():
        return []
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    out = []
    for r in d.itertuples(index=False):
        mn = r.market_name
        out.append(_mkrow(
            city="锦州", county=None, market_name=mn,
            store_name=mn if ("超市" in str(mn)) else None,
            crop_raw=r.crop_raw, crop_standard=r.crop,
            specification=r.layout,
            price_original=r.price, unit_original=r.unit_raw, price_per_kg=r.price_per_kg,
            price_level=resolve_level(r.price_type, mn, r.source_id),
            observation_date=str(r.date)[:10], frequency="irregular_official",
            source_type="official_government", source_name=r.source_name,
            source_url="https://www.jz.gov.cn/", source_id=r.source_id,
            retrieval_time=RETRIEVAL, quality_grade=r.quality_grade,
            raw_file=f"data/raw/prices/jinzhou_deep/ocr/{r.image_id}.txt",
            geo_level=r.geo_level, record_kind=r.price_scope,
            note=f"image_id={r.image_id};decimal_fixed={r.decimal_fixed};outlier_low={r.outlier_low}",
        ))
    return out


def from_lnnync_like(path, source_id, default_level, market_col=None, county_col="district") -> list[dict]:
    f = STAGING / path
    if not f.exists():
        return []
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    out = []
    for r in d.itertuples(index=False):
        rd = r._asdict()
        mn = rd.get(market_col) if market_col else None
        if not mn and "market" in rd:
            mn = rd.get("market")
        kind = rd.get("record_kind")
        lvl = default_level
        if kind and "wholesale" in str(kind):
            lvl = "wholesale"
        elif kind and "farm_gate" in str(kind):
            lvl = "farm_gate"
        out.append(_mkrow(
            city=rd.get("city"), county=rd.get(county_col),
            market_name=mn, crop_raw=rd.get("crop"), crop_standard=rd.get("crop"),
            price_original=rd.get("price"), unit_original=rd.get("unit"),
            price_per_kg=rd.get("price_per_kg"),
            price_level=lvl, observation_date=str(rd.get("date"))[:10],
            frequency="weekly",
            source_type="official_government", source_name=rd.get("source_name"),
            source_url=rd.get("source_url"), source_id=source_id,
            retrieval_time=RETRIEVAL, quality_grade=rd.get("quality_grade", "B"),
            raw_file=rd.get("raw_file"), geo_level=rd.get("geo_level"),
            record_kind=kind, note=rd.get("note"),
        ))
    return out


def from_dalian_weekly() -> list[dict]:
    f = STAGING / "dalian_price_weekly.csv"
    if not f.exists():
        return []
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    out = []
    for r in d.itertuples(index=False):
        out.append(_mkrow(
            city="大连", county=None, market_name="市发展改革研究中心监测点",
            crop_raw=r.product_raw, crop_standard=r.product_standard,
            price_original=r.price_raw, unit_original=r.unit_raw,
            price_per_kg=to_per_kg(r.price_raw, r.unit_raw),
            price_level="retail_market", observation_date=str(r.article_date)[:10],
            frequency="weekly", source_type="official_government",
            source_name=r.source_name, source_url=r.source_url, source_id=r.source_id,
            retrieval_time=RETRIEVAL, quality_grade=r.quality_grade,
            raw_file=f"data/raw/prices/dalian_dfgw_weekly/{getattr(r,'article_date','')}",
            geo_level="city",
        ))
    return out


def from_dalian_monthly() -> list[dict]:
    f = STAGING / "dalian_price_monthly.csv"
    if not f.exists():
        return []
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    out = []
    for r in d.itertuples(index=False):
        out.append(_mkrow(
            city="大连", county=None, market_name="发改委监测点",
            crop_raw=r.product_raw, crop_standard=r.product_standard,
            price_original=r.price_raw, unit_original=r.unit_raw,
            price_per_kg=to_per_kg(r.price_raw, r.unit_raw),
            price_level="retail_market", observation_date=str(r.period_date)[:10],
            frequency="monthly", source_type="official_government",
            source_name=r.source_name, source_url=r.source_url, source_id=r.source_id,
            retrieval_time=RETRIEVAL, quality_grade=r.quality_grade, geo_level="city",
        ))
    return out


def from_tieling_xian() -> list[dict]:
    f = STAGING / "铁岭_price_tielingxian.csv"
    if not f.exists():
        return []
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    out = []
    for r in d.itertuples(index=False):
        out.append(_mkrow(
            city="铁岭", county="铁岭县", market_name="铁岭县发改局监测",
            crop_raw=r.product_raw, crop_standard=r.product_standard,
            specification=r.spec, price_original=r.price_raw, unit_original=r.unit_raw,
            price_per_kg=to_per_kg(r.price_raw, r.unit_raw),
            price_level="retail_market", observation_date=str(r.article_date)[:10],
            frequency="monthly", source_type="official_government",
            source_name=r.source_name, source_url=r.source_url, source_id="SRC-TLX",
            retrieval_time=RETRIEVAL, quality_grade=r.quality_grade,
            geo_level="county",
        ))
    return out


# 惠农网已确认的辽宁县域 areaId → (city, county) 映射
CNHNB_AREA = {
    1562: ("丹东", "东港市"), 1600: ("铁岭", "昌图县"),
    1533: ("大连", "庄河市"), 1571: ("锦州", "北镇市"),
    1606: ("朝阳", "凌源市"),
}


def _cnhnb_geo(j: dict):
    aid = j.get("areaId")
    if aid in CNHNB_AREA:
        return CNHNB_AREA[aid]
    addr = str(j.get("addressDetail") or "")
    m = re.search(r"辽宁(?:省)?([\u4e00-\u9fff]{2,4}市)([\u4e00-\u9fff]{1,5}(?:市|县|区))?", addr)
    if m:
        return m.group(1).replace("市", ""), (m.group(2) or None)
    qa = str(j.get("query_area") or "")
    if qa:
        return None, qa
    return None, None


def from_cnhnb() -> list[dict]:
    f = ROOT / "data/raw" / "prices" / "b2b" / "cnhnb_hangqing_rows.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        j = json.loads(line)
        city, county = _cnhnb_geo(j)
        addr = str(j.get("addressDetail") or "")
        ms = j.get("collectDate") or j.get("createTime")
        try:
            dt = datetime.fromtimestamp(int(ms) / 1000).date().isoformat()
        except Exception:
            dt = None
        unit = j.get("unit") or ""
        unit_raw = f"元/{unit}" if unit else ""
        out.append(_mkrow(
            city=city, county=county, market_name="惠农网商户供货", platform="cnhnb",
            crop_raw=j.get("breedName") or j.get("cateName"),
            crop_standard=j.get("breedName") or j.get("cateName"),
            specification=j.get("cateName"),
            price_original=j.get("avgPrice"),
            unit_original=unit_raw,
            price_per_kg=to_per_kg(j.get("avgPrice"), unit_raw),
            price_level="farm_gate", observation_date=dt, frequency="daily",
            source_type="third_party_b2b", source_name="惠农网行情",
            source_url=f"https://www.cnhnb.com/hangqing/q-0-0-0-{j.get('areaId')}-{str(dt).replace('-','')}/",
            source_id="SRC-CNHNB-HANGQING", retrieval_time=RETRIEVAL, quality_grade="C",
            geo_level="county",
            note=f"supply商户供货价;样本数={j.get('statisNum')};min={j.get('minPrice')};max={j.get('maxPrice')}",
        ))
    return out


def from_generic_unified(path: str, extra: dict | None = None) -> list[dict]:
    """读取已经是（或接近）统一 schema 的 staging 文件，直接并入。"""
    f = STAGING / path
    if not f.exists():
        return []
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    # 日期列别名
    for alias in ("observation_date", "date", "period_date", "publish_date", "article_date"):
        if alias in d.columns:
            d["observation_date"] = d[alias]
            break
    out = []
    for r in d.itertuples(index=False):
        rd = r._asdict()
        row = {k: rd.get(k) for k in UNIFIED if k in rd}
        row.setdefault("price_level", None)
        row["retrieval_time"] = row.get("retrieval_time") or RETRIEVAL
        if extra:
            row.update(extra)
        out.append(_mkrow(**row))
    return out


def main() -> None:
    rows = []
    rows += from_fact_price_city()
    n1 = len(rows)
    rows += from_jinzhou_ocr()
    n2 = len(rows) - n1
    n3 = 0
    rows += from_lnnync_like("lnnync_grain_weekly.csv", "SRC-LNNYNC-GRAIN", "wholesale")
    rows += from_lnnync_like("lnnync_veg_weekly.csv", "SRC-LNNYNC-VEG", "wholesale")
    rows += from_lnnync_like("lnnync_veg_market_nodes.csv", "SRC-LNNYNC-VEG-MARKET", "wholesale", market_col="market")
    rows += from_dalian_weekly()
    rows += from_dalian_monthly()
    # 大连 12316 金农热线（批发/零售/产地三层，2016-2026）
    rows += from_generic_unified("dalian_12316_prices.csv")
    # 电商/即时零售快照（当前快照层）
    rows += from_generic_unified("ecommerce_price_snapshot.csv")
    rows += from_cnhnb()

    df = pd.DataFrame(rows, columns=UNIFIED)
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["city", "observation_date"])

    # --- 县名归一化 ---
    def norm_county(city, county):
        if pd.isna(county):
            return None
        c = str(county).strip()
        for pre in (str(city) + "市", str(city)):
            while c.startswith(pre) and len(c) > len(pre):
                c = c[len(pre):]
        for junk in ("市场", "超市", "批发", "果菜", "蔬菜", "、", "，"):
            if junk in c:
                return None
        c = c.replace("普兰店市", "普兰店区")
        return c or None

    df["county"] = [norm_county(c, k) for c, k in zip(df["city"], df["county"])]

    # --- 精确业务主键去重（同一来源+层级+日期+商品(含原文)+市场+价格 视为真重复）---
    key = ["city", "county", "observation_date", "crop_raw", "crop_standard", "specification",
           "market_name", "source_id", "price_level", "price_original"]
    before = len(df)
    df = df.drop_duplicates(subset=key, keep="first").reset_index(drop=True)
    dup_removed = before - len(df)

    df = df.sort_values(["city", "observation_date", "crop_standard", "price_level"]).reset_index(drop=True)

    df.to_csv(MARTS / "fact_price_observation.csv", index=False, encoding="utf-8-sig")
    try:
        df.to_parquet(MARTS / "fact_price_observation.parquet", index=False)
    except Exception as e:
        print("[warn] parquet 写入失败:", e)

    print(f"[OK] 统一价格观测 {len(df)} 行 → city_data/reference/marts/fact_price_observation.csv")
    print(f"     其中 基础表 {n1} + 锦州OCR {n2}；去重移除 {dup_removed} 条")
    print("\n=== 按 city ===")
    print(df["city"].value_counts().to_string())
    print("\n=== 按 price_level ===")
    print(df["price_level"].value_counts().to_string())
    print("\n=== price_per_kg 覆盖 ===")
    print(f"  非空 {df['price_per_kg'].notna().sum()} / {len(df)}")
    print("\n=== 各城市 price_level ===")
    print(df.groupby(["city", "price_level"]).size().to_string())


if __name__ == "__main__":
    main()
