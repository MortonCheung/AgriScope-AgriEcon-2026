"""把 city_data/reference/staging/ 中已采集但未入库的五城价格数据，按沈阳标准统一并入 fact_price_city。

沈阳标准（模板）字段：
  date, province, city, district, market_id, market_name,
  crop_raw, variety, price_type, price, unit_raw, price_per_kg,
  volume, source_id, source_name, source_url, raw_file, quality_grade

本轮新增的两条硬性约定：
  1. geo_level 必须标注（city / county）——铁岭县等县级数据**不得**冒充市级
  2. price_type 必须区分（retail / wholesale / market_average / farm_gate），不得混成一条序列
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STAGING = ROOT / "city_data/reference/staging"
MARTS = ROOT / "city_data/reference/marts"
MARTS.mkdir(parents=True, exist_ok=True)


def to_per_kg(price: float, unit: str) -> float | None:
    u = re.sub(r"\s+", "", str(unit or ""))
    if u in ("元/500g", "元/500克", "元/500g克", "元/斤"):
        return round(price * 2.0, 4)
    if u in ("元/kg", "元/公斤", "元/千克", "元/千克(kg)"):
        return round(price, 4)
    if u in ("元/5L", "元/5升", "元/6L", "元/500ml", "元/桶"):
        return None          # 容积单位无法换算为重量单价 → 留空而非猜测
    return None


def norm_date(x) -> str | None:
    s = str(x)
    m = re.match(r"(20\d\d)-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(20\d\d)[/年](\d{1,2})[月/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(20\d\d)[/-](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    return None


def pick_price_type(src: str, unit: str) -> str:
    """价格层级判定：优先依据来源性质，不明时保守标为 market_average。"""
    s = str(src or "")
    # 朝阳官方原文列名即"全市平均价格"（市区超市+农贸市场口径）→ market_average，
    # 既不是批发价也不宜简单归为零售价
    if "全市平均" in s or "平均价格" in s:
        return "market_average"
    if "批发" in s or "wholesale" in s:
        return "wholesale"
    if "超市" in s or "零售" in s or "集贸" in s or "农贸" in s:
        return "retail"
    if "收购" in s or "地头" in s:
        return "farm_gate"
    return "market_average"


def build(out_rows: list, df: pd.DataFrame, *, city: str,
          date_col: str, product_col: str, price_col: str, unit_col: str,
          source_id: str, source_name: str, source_url_col: str | None,
          geo_level: str = "city", district: str | None = None,
          spec_col: str | None = None, freq: str = "daily",
          raw_file_col: str | None = None, grade: str = "B",
          product_std_col: str | None = None) -> int:
    n = 0
    for _, r in df.iterrows():
        d = norm_date(r.get(date_col))
        if not d:
            continue
        try:
            p = float(str(r.get(price_col)).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        unit = str(r.get(unit_col) or "")
        prod = str(r.get(product_std_col) or r.get(product_col) or "").strip()
        if not prod:
            continue
        out_rows.append({
            "date": d,
            "province": "辽宁省",
            "city": city,
            "district": district if district is not None else (
                str(r.get("region")) if "region" in df.columns else None),
            "market_id": None,
            "market_name": f"{city}市监测点平均" if geo_level == "city" else f"{city}{district or ''}监测点",
            "geo_level": geo_level,
            "crop_raw": prod,
            "variety": str(r.get(spec_col)) if spec_col and spec_col in df.columns else "",
            "price_type": pick_price_type(source_name, unit),
            "frequency": freq,
            "price": p,
            "unit_raw": unit,
            "price_per_kg": to_per_kg(p, unit),
            "volume": None,
            "source_id": source_id,
            "source_name": source_name,
            "source_url": str(r.get(source_url_col)) if source_url_col else "",
            "raw_file": str(r.get(raw_file_col)) if raw_file_col and raw_file_col in df.columns else "",
            "quality_grade": grade,
        })
        n += 1
    return n


def main() -> None:
    rows: list[dict] = []
    log: list[tuple] = []

    specs = [
        # (文件, 城市, 日期列, 商品列, 价格列, 单位列, source_id, source_name, url列, geo_level, district, 规格列, 频率, 等级, 标准名列)
        ("dalian_mofcom_price.csv", "大连", "date", "crop_raw", "price", "unit_raw",
         "SRC-DL-MOFCOM", "商务部 大连商务预报(市场级批发价)", "", "market", None, None, "weekly", "A", None),
        ("chaoyang_price_daily.csv", "朝阳", "date", "crop_raw", "price", "unit_raw",
         "SRC-CY-DAILY", "朝阳市发改委 主要菜篮子产品每日价情(全市平均价格)", "source_url", "city", None, "variety", "daily", "A", None),
        ("dalian_price_monthly.csv", "大连", "period_date", "product_raw", "price_raw", "unit_raw",
         "SRC-DL-CIF", "中国价格信息网(36城市月度)", "source_url", "city", None, None, "monthly", "B", "product_standard"),
        ("dalian_price_weekly.csv", "大连", "article_date", "product_raw", "price_raw", "unit_raw",
         "SRC-DL-ARTICLE", "大连市政府/发展改革研究中心周报", "source_url", "city", None, None, "weekly", "B", "product_standard"),
        ("dandong_price_articles.csv", "丹东", "price_date", "product", "price", "unit",
         "SRC-DD-ARTICLE", "丹东价格监测文章", "source_url", "city", None, None, "daily", "B", None),
        ("jinzhou_price_basket_weekly.csv", "锦州", "pub_date", "product_raw", "price_raw", "unit_raw",
         "SRC-JZ-BASKET", "锦州市菜篮子信息发布平台", "source_url", "city", None, None, "weekly", "B", None),
        ("朝阳_price_lnfgw.csv", "朝阳", "article_date", "product_raw", "price_raw", "unit_raw",
         "SRC-LNFGW-CY", "辽宁省发改委(朝阳价格监测)", "source_url", "city", None, None, "daily", "B", "product_standard"),
        ("锦州_price_lnfgw.csv", "锦州", "article_date", "product_raw", "price_raw", "unit_raw",
         "SRC-LNFGW-JZ", "辽宁省发改委(锦州价格监测)", "source_url", "city", None, None, "daily", "B", "product_standard"),
        ("铁岭_price_lnfgw.csv", "铁岭", "article_date", "product_raw", "price_raw", "unit_raw",
         "SRC-LNFGW-TL", "辽宁省发改委(铁岭价格监测)", "source_url", "city", None, None, "daily", "B", "product_standard"),
        ("铁岭_price_lnnync.csv", "铁岭", "article_date", "product_raw", "price_raw", "unit_raw",
         "SRC-LNNYNC-TL", "辽宁省农业农村厅(铁岭)", "source_url", "city", None, "spec", "daily", "B", "product_standard"),
        # 铁岭县 = 县级，严禁冒充市级
        ("铁岭_price_tielingxian.csv", "铁岭", "article_date", "product_raw", "price_raw", "unit_raw",
         "SRC-TLX", "铁岭县价格监测", "source_url", "county", "铁岭县", "spec", "daily", "B", "product_standard"),
    ]

    for spec in specs:
        f = STAGING / spec[0]
        if not f.exists():
            log.append((spec[0], "文件不存在", 0))
            continue
        try:
            df = pd.read_csv(f)
        except Exception as e:
            log.append((spec[0], f"解析失败: {str(e)[:50]}", 0))
            continue
        n = build(rows, df, city=spec[1], date_col=spec[2], product_col=spec[3],
                  price_col=spec[4], unit_col=spec[5], source_id=spec[6],
                  source_name=spec[7], source_url_col=spec[8], geo_level=spec[9],
                  district=spec[10], spec_col=spec[11], freq=spec[12], grade=spec[13],
                  product_std_col=spec[14])
        log.append((spec[0], "OK", n))

    print("=== staging 价格入库日志 ===")
    for name, st, n in log:
        print(f"  {name:42s} {st:>12s}  入库 {n} 行")

    if not rows:
        print("[WARN] 无可入库数据")
        return
    new = pd.DataFrame(rows)

    # 与既有 fact_price_city 合并（去重：同 城市+日期+商品+来源 只保留一条）
    p = MARTS / "fact_price_city.parquet"
    old = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    if len(old):
        # 去重键必须包含 market_name：沈阳同一天同一商品有批发/超市/集市三条记录，
        # 若只用 (city, date, crop, source_id) 去重会误删约 4.4 万条真实记录。
        key = ["city", "date", "crop_raw", "source_id", "market_name"]
        for c in key:
            if c not in old.columns:
                old[c] = None
        before = len(old)
        comb = pd.concat([old, new], ignore_index=True)
        comb = comb.drop_duplicates(subset=key, keep="first")
        print(f"\n[OK] 合并：{before} + {len(new)} -> {len(comb)} 行（去重后新增 {len(comb)-before}）")
    else:
        comb = new
        print(f"\n[OK] 新建 fact_price_city {len(comb)} 行")

    comb.to_parquet(p, index=False)
    comb.to_csv(MARTS / "fact_price_city.csv", index=False, encoding="utf-8-sig")
    print("\n=== 合并后各城市覆盖 ===")
    g = comb.groupby("city").agg(
        records=("date", "size"), dates=("date", "nunique"),
        crops=("crop_raw", "nunique"))
    print(g.to_string())
    print("\n=== geo_level 分布（县级不得冒充市级）===")
    if "geo_level" in comb.columns:
        print(comb["geo_level"].fillna("(旧数据未标注)").value_counts().to_string())
    print("\n=== price_type 分布 ===")
    print(comb["price_type"].fillna("unknown").value_counts().to_string())


if __name__ == "__main__":
    main()
