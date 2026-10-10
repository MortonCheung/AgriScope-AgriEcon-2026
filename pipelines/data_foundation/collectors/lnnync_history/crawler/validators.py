"""数据质量自动校验（施工手册第二十三节）。

检查项：重复记录 / 空日期 / 空产品名 / 空价格 / 价格<=0 / 异常巨大价格 /
无法识别单位 / 无法识别地点 / 同一文章重复解析 / 周次异常 / 发布日期异常 /
统计周期异常 / 周次连续性。

连续性缺口只标记 missing_week_candidate，**不判定为抓取遗漏**
（官方可能本来就没发布该周），供人工复查。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from . import PROJECT_ROOT, get_logger

log = get_logger("crawler.validators")

REPORT_PATH = PROJECT_ROOT / "logs" / "validation_report.json"

# 价格合理性上界（元/公斤）：按品类设定，超过即视为异常值候选
PRICE_BOUND = {
    "grain_oil": 200.0,
    "vegetable": 200.0,
    "fruit": 300.0,
    "agri_input": 20000.0,   # 农资以「元/吨」计价，换算后仍可能较大
}


def _to_date(s):
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def validate(articles_df: pd.DataFrame, prices_df: pd.DataFrame) -> dict:
    report: dict = {
        "summary": {},
        "checks": {},
        "missing_week_candidates": [],
    }

    n_articles = len(articles_df)
    n_prices = len(prices_df)
    report["summary"] = {
        "articles": int(n_articles),
        "price_records": int(n_prices),
    }

    # ---- 1. 重复记录（同一文章+产品+地点+记录类型的完全重复） ----
    key_cols = ["article_id", "product", "product_variant", "location_raw", "record_type", "price"]
    existing = [c for c in key_cols if c in prices_df.columns]
    dup_mask = prices_df.duplicated(subset=existing, keep=False) if existing else pd.Series(False, index=prices_df.index)
    report["checks"]["duplicate_records"] = {
        "count": int(dup_mask.sum()),
        "examples": prices_df[dup_mask][existing].head(5).to_dict("records") if dup_mask.any() else [],
    }

    # ---- 2. 空日期 ----
    empty_pub = articles_df["publication_date"].isna() | (articles_df["publication_date"].astype(str).str.strip() == "")
    empty_start = prices_df["period_start"].isna() | (prices_df["period_start"].astype(str).str.strip() == "")
    report["checks"]["empty_dates"] = {
        "articles_missing_publication_date": int(empty_pub.sum()),
        "records_missing_period_start": int(empty_start.sum()),
    }

    # ---- 3. 空产品名 ----
    empty_prod = prices_df["product"].isna() | (prices_df["product"].astype(str).str.strip() == "")
    report["checks"]["empty_product"] = {
        "count": int(empty_prod.sum()),
        "examples": prices_df[empty_prod][["article_id", "source_text"]].head(5).to_dict("records")
        if empty_prod.any() else [],
    }

    # ---- 4. 空价格 / 价格<=0 ----
    p = pd.to_numeric(prices_df["price"], errors="coerce")
    null_price = p.isna()
    nonpos = p.notna() & (p <= 0)
    report["checks"]["price_missing_or_nonpositive"] = {
        "missing": int(null_price.sum()),
        "non_positive": int(nonpos.sum()),
    }

    # ---- 5. 异常巨大价格（按品类上界，且以标准单位比较） ----
    huge = pd.Series(False, index=prices_df.index)
    if "standard_price" in prices_df.columns:
        sp = pd.to_numeric(prices_df["standard_price"], errors="coerce")
        for cat, bound in PRICE_BOUND.items():
            m = (prices_df["category_key"] == cat) & sp.notna() & (sp > bound)
            huge |= m
    report["checks"]["abnormal_huge_price"] = {
        "count": int(huge.sum()),
        "examples": prices_df[huge][["article_id", "product", "price", "original_unit", "standard_price"]]
        .head(5).to_dict("records") if huge.any() else [],
    }

    # ---- 6. 无法识别单位 ----
    bad_unit = prices_df["original_unit"].isna() | (prices_df["original_unit"].astype(str).str.strip() == "")
    unconverted = pd.Series(False, index=prices_df.index)
    if "standard_price" in prices_df.columns:
        unconverted = pd.to_numeric(prices_df["standard_price"], errors="coerce").isna() & p.notna()
    report["checks"]["unit_issues"] = {
        "missing_unit": int(bad_unit.sum()),
        "unit_not_convertible": int(unconverted.sum()),
        "unit_distribution": {str(k): int(v) for k, v in prices_df["original_unit"].value_counts().items()},
    }

    # ---- 7. 无法识别地点 ----
    unknown_loc = prices_df["geo_level"].isin(["unknown"])
    market_loc = prices_df["geo_level"].isin(["market"])
    report["checks"]["location_issues"] = {
        "geo_level_unknown": int(unknown_loc.sum()),
        "geo_level_market": int(market_loc.sum()),
        "geo_level_distribution": {str(k): int(v) for k, v in prices_df["geo_level"].value_counts().items()},
    }

    # ---- 8. 同一文章重复解析（同一 article_id 在 articles 表中出现多次） ----
    dup_art = articles_df["article_id"].duplicated(keep=False)
    report["checks"]["duplicate_articles"] = {"count": int(dup_art.sum())}

    # ---- 9. 周次 / 日期 / 统计周期异常 ----
    week = pd.to_numeric(articles_df["week"], errors="coerce")
    bad_week = week.isna() | (week < 1) | (week > 53)
    ps = pd.to_datetime(articles_df["period_start"], errors="coerce")
    pe = pd.to_datetime(articles_df["period_end"], errors="coerce")
    pd_pub = pd.to_datetime(articles_df["publication_date"], errors="coerce")
    bad_period = ps.isna() | pe.isna() | (pe < ps)
    long_period = ((pe - ps).dt.days > 14) & ps.notna() & pe.notna()
    pub_before_end = (pd_pub < pe) & pd_pub.notna() & pe.notna()
    report["checks"]["temporal_issues"] = {
        "bad_week": int(bad_week.sum()),
        "bad_period_range": int(bad_period.sum()),
        "period_longer_than_14d": int(long_period.sum()),
        "published_before_period_end": int(pub_before_end.sum()),
        "year_distribution": {str(k): int(v) for k, v in articles_df["year"].value_counts(dropna=False).sort_index().items()},
    }

    # ---- 10. 周次连续性 ----
    gaps = []
    for cat, grp in articles_df.dropna(subset=["year", "week"]).groupby("category_key"):
        weeks_by_year = defaultdict(set)
        for _, r in grp.iterrows():
            try:
                weeks_by_year[int(r["year"])].add(int(r["week"]))
            except (TypeError, ValueError):
                continue
        for y, ws in sorted(weeks_by_year.items()):
            if not ws:
                continue
            lo, hi = min(ws), max(ws)
            missing = sorted(set(range(lo, hi + 1)) - ws)
            if missing:
                gaps.append({
                    "category_key": str(cat),
                    "year": int(y),
                    "missing_weeks": missing,
                    "status": "missing_week_candidate",
                    "note": "可能官方未发布，需人工复核，不直接判定为抓取遗漏",
                })
    report["missing_week_candidates"] = gaps

    # ---- 11. 解析状态分布 ----
    report["checks"]["parse_status"] = {
        str(k): int(v) for k, v in articles_df["parse_status"].value_counts().items()
    }
    report["checks"]["record_type_distribution"] = {
        str(k): int(v) for k, v in prices_df["record_type"].value_counts().items()
    }

    # ---- 12. 空记录文章 ----
    empty_articles = articles_df[articles_df["parse_status"] == "failed"]
    report["checks"]["articles_without_records"] = {
        "count": int(len(empty_articles)),
        "examples": empty_articles[["article_id", "title", "source_url"]].head(10).to_dict("records"),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("质量报告已写入 %s", REPORT_PATH)
    return report
