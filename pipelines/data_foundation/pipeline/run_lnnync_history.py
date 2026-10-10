#!/usr/bin/env python3
"""辽宁省农业农村厅农产品历史价格数据采集 —— 命令行入口。

用法：
    python run.py crawl      # 发现并下载新增文章（增量；自动解析新文章）
    python run.py parse      # 重新解析已保存的 HTML（不联网）
    python run.py validate   # 数据质量检查
    python run.py report     # 生成统计报告与作物覆盖度报告
    python run.py all        # crawl → parse → validate → export → report
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler import PROJECT_ROOT, get_logger, setup_logging  # noqa: E402
from crawler import article as article_mod  # noqa: E402
from crawler import listing as listing_mod  # noqa: E402
from crawler import validators  # noqa: E402
from crawler.client import HttpClient  # noqa: E402
from crawler.parser import ParsedArticle, parse_article, record_to_row, write_parse_errors  # noqa: E402

log = get_logger("run")

CONFIG = PROJECT_ROOT / "config" / "sources.yaml"
INTERMEDIATE = PROJECT_ROOT / "data" / "intermediate"
PROCESSED = PROJECT_ROOT / "data" / "processed"
RAW = PROJECT_ROOT / "data" / "raw"

PRICE_COLUMNS = [
    "article_id", "year", "week", "period_start", "period_end", "publication_date",
    "category", "category_key", "product", "product_variant",
    "province", "city", "county", "location_raw", "geo_level",
    "record_type", "price_type",
    "price", "original_unit", "standard_price", "standard_unit",
    "mom_change_pct", "yoy_change_pct", "national_price", "provincial_price",
    "source_text", "source_url",
]
ARTICLE_COLUMNS = [
    "article_id", "category", "category_key", "year", "week", "period_start", "period_end",
    "publication_date", "title", "market_analysis", "future_outlook",
    "source_url", "fetched_at", "parse_status",
]
TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]


def load_config() -> dict:
    with CONFIG.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def make_client(cfg: dict) -> HttpClient:
    r = cfg["request"]
    return HttpClient(
        min_interval=r["min_interval_sec"],
        max_interval=r["max_interval_sec"],
        connect_timeout=r["connect_timeout"],
        read_timeout=r["read_timeout"],
        max_retries=r["max_retries"],
        backoff=r["backoff_sec"],
        retry_on_status=r["retry_on_status"],
        user_agent=r["user_agent"],
    )


# ---- crawl --------------------------------------------------------------
def cmd_crawl(incremental: bool = True) -> None:
    cfg = load_config()
    base = cfg["site"]["base_url"]
    known = listing_mod.load_known_urls()
    client = make_client(cfg)

    newly: list[dict] = []
    all_refs = []
    for cat in cfg["categories"]:
        if not cat.get("enabled"):
            continue
        log.info("=" * 60)
        log.info("[%s] 开始遍历分类", cat["name"])
        refs = listing_mod.discover_category(
            client, cat["key"], cat["name"], cat["path"], base,
            known_urls=known, incremental=incremental,
        )
        all_refs.extend(refs)
        new_refs = [r for r in refs if r.url not in known]
        log.info("[%s] 发现 %d 篇，其中新增 %d 篇", cat["name"], len(refs), len(new_refs))
        newly.extend([r for r in new_refs])

    listing_mod.write_index(all_refs)

    # 只下载新增文章
    buffer = []
    ok = fail = 0
    for i, ref in enumerate(newly, 1):
        rec = article_mod.fetch_article(
            client, ref.url, ref.category, ref.category_key, ref.list_date, ref.title
        )
        if rec is None:
            fail += 1
            continue
        ok += 1
        buffer.append(rec)
        log.info("[%s] 正在抓取 %s…… [OK] HTTP 200", ref.category, ref.title[:30])
        if len(buffer) >= 100:
            article_mod.append_articles(buffer)
            buffer.clear()
    if buffer:
        article_mod.append_articles(buffer)

    print(f"\n下载完成：新增 {len(newly)} 篇，成功 {ok}，失败 {fail}")
    log.info("crawl 完成：新增 %d / 成功 %d / 失败 %d", len(newly), ok, fail)


# ---- parse --------------------------------------------------------------
def cmd_parse() -> None:
    """从本地已保存的 HTML 重建结构化数据（验收标准 F：删除 processed 后可离线重建）。"""
    recs = list(article_mod.load_fetched().values())
    if not recs:
        print("没有已下载的文章，请先执行 crawl")
        return
    print(f"开始解析 {len(recs)} 篇文章（离线，不联网）")

    parsed: list[ParsedArticle] = []
    for i, r in enumerate(recs, 1):
        try:
            parsed.append(parse_article(r))
        except Exception as exc:  # 单篇异常不影响整体
            log.exception("[%s] 解析异常：%s", r.get("article_id"), exc)
            pa = ParsedArticle(
                article_id=r.get("article_id", ""), category=r.get("category", ""),
                category_key=r.get("category_key", ""), year=None, week=None,
                period_start="", period_end="", publication_date=r.get("publication_date", ""),
                title=r.get("title", ""), market_analysis="", future_outlook="",
                source_url=r.get("url", ""), parse_status="failed", error_type="exception",
                raw_text=r.get("raw_text", ""),
            )
            parsed.append(pa)
        if i % 200 == 0:
            print(f"  已解析 {i}/{len(recs)}")

    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    rows = []
    for a in parsed:
        for rec in a.records:
            rows.append(record_to_row(rec))
    prices = pd.DataFrame(rows)
    if not prices.empty:
        prices = prices.reindex(columns=PRICE_COLUMNS)
    prices.to_csv(INTERMEDIATE / "parsed_records.csv", index=False, encoding="utf-8-sig")

    fetched = article_mod.load_fetched()
    arts = pd.DataFrame([{
        "article_id": a.article_id, "category": a.category, "category_key": a.category_key,
        "year": a.year, "week": a.week, "period_start": a.period_start, "period_end": a.period_end,
        "publication_date": a.publication_date, "title": a.title,
        "market_analysis": a.market_analysis, "future_outlook": a.future_outlook,
        "source_url": a.source_url,
        "fetched_at": fetched.get(a.article_id, {}).get("fetched_at", ""),
        "parse_status": a.parse_status,
    } for a in parsed])
    arts.to_csv(INTERMEDIATE / "articles_parsed.csv", index=False, encoding="utf-8-sig")

    write_parse_errors(parsed)

    status = Counter(a.parse_status for a in parsed)
    print(f"解析完成：成功 {status.get('success',0)}，部分 {status.get('partial',0)}，"
          f"失败 {status.get('failed',0)}；价格记录 {len(prices)} 条")


# ---- export -------------------------------------------------------------
def cmd_export() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    prices = pd.read_csv(INTERMEDIATE / "parsed_records.csv", dtype={"product_variant": "object"})
    arts = pd.read_csv(INTERMEDIATE / "articles_parsed.csv")

    prices = prices.reindex(columns=PRICE_COLUMNS)
    prices.to_csv(PROCESSED / "prices_long.csv", index=False, encoding="utf-8-sig")
    try:
        prices.to_parquet(PROCESSED / "prices_long.parquet", index=False)
    except Exception as exc:
        log.warning("Parquet 导出失败：%s", exc)
    arts.reindex(columns=ARTICLE_COLUMNS).to_csv(PROCESSED / "articles.csv", index=False, encoding="utf-8-sig")
    print(f"导出完成：prices_long.csv（{len(prices)} 条）、prices_long.parquet、articles.csv（{len(arts)} 篇）")


# ---- validate -----------------------------------------------------------
def cmd_validate() -> dict:
    prices = pd.read_csv(PROCESSED / "prices_long.csv")
    arts = pd.read_csv(PROCESSED / "articles.csv")
    report = validators.validate(arts, prices)
    print(json.dumps(report["checks"], ensure_ascii=False, indent=2)[:4000])
    print(f"\n周次缺口候选：{len(report['missing_week_candidates'])} 组（详见 logs/validation_report.json）")
    return report


# ---- report -------------------------------------------------------------
def cmd_report() -> None:
    prices = pd.read_csv(PROCESSED / "prices_long.csv")
    arts = pd.read_csv(PROCESSED / "articles.csv")
    PROCESSED.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 62)
    lines.append("辽宁农业价格数据采集完成")
    lines.append("=" * 62)
    lines.append("")
    lines.append(f"共发现文章：{len(arts)}")
    st = Counter(arts["parse_status"])
    lines.append(f"成功解析：{st.get('success', 0)}")
    lines.append(f"部分解析：{st.get('partial', 0)}")
    lines.append(f"解析失败：{st.get('failed', 0)}")
    lines.append(f"价格记录总数：{len(prices)}")
    d0 = str(arts["publication_date"].min())
    d1 = str(arts["publication_date"].max())
    lines.append("")
    lines.append(f"时间范围：{d0} ～ {d1}")
    lines.append("")

    lines.append("【分类覆盖】")
    for cat in sorted(arts["category"].dropna().unique()):
        na = int((arts["category"] == cat).sum())
        np_ = int((prices["category"] == cat).sum())
        lines.append(f"  {cat}：{na} 篇 / {np_} 条价格记录")
    lines.append("")

    lines.append("【产品与地理覆盖】")
    lines.append(f"  产品种类：{prices['product'].nunique()}")
    lines.append(f"  覆盖城市：{prices['city'].nunique()}")
    lines.append(f"  覆盖区县：{prices['county'].nunique()}")
    lines.append("")

    lines.append("【各产品记录数】")
    for p, c in prices["product"].value_counts().items():
        lines.append(f"  {p}：{c}")
    lines.append("")
    lines.append("【各城市记录数】")
    for p, c in prices["city"].value_counts(dropna=True).items():
        lines.append(f"  {p}：{c}")
    lines.append("")
    lines.append("【每年记录数】")
    for y, c in sorted(prices["year"].value_counts(dropna=False).items(), key=lambda x: str(x[0])):
        lines.append(f"  {y}：{c}")
    lines.append("")

    # ---- 六个目标城市 × 四品类 ----
    lines.append("【六个目标城市数据量】")
    pivot = (prices[prices["city"].isin(TARGET_CITIES)]
             .pivot_table(index="city", columns="category", values="price", aggfunc="count")
             .fillna(0).astype(int))
    for city in TARGET_CITIES:
        if city not in pivot.index:
            lines.append(f"  {city}：0")
            continue
        row = pivot.loc[city]
        lines.append(f"  {city}：" + "，".join(f"{c} {int(row.get(c, 0))}" for c in pivot.columns))
    lines.append("")

    # ---- crop_coverage_report.csv ----
    build_crop_coverage(prices)
    lines.append("作物覆盖度报告：data/processed/crop_coverage_report.csv")
    lines.append("")

    # ---- 最适合作物推荐（数据完整度优先）----
    cov = pd.read_csv(PROCESSED / "crop_coverage_report.csv")
    lines.append("【六个目标城市 · 数据最完整作物 TOP3】")
    for city in TARGET_CITIES:
        sub = cov[(cov["city"] == city) & (cov["record_count"] >= 30)]
        sub = sub.sort_values(["missing_ratio", "record_count"], ascending=[True, False]).head(3)
        if sub.empty:
            lines.append(f"  {city}：无满足阈值（≥30 条）的作物")
            continue
        for _, r in sub.iterrows():
            lines.append(f"  {city} / {r['product']}（{r['category']}）：{int(r['record_count'])} 条，"
                         f"{r['first_date']}～{r['last_date']}，缺失率 {r['missing_ratio']:.2%}")
    lines.append("")
    lines.append("结果：data/processed/prices_long.csv / prices_long.parquet")
    lines.append("质量报告：logs/validation_report.json")
    lines.append("=" * 62)

    out = "\n".join(lines)
    print(out)
    (PROJECT_ROOT / "logs" / "summary_report.txt").write_text(out, encoding="utf-8")
    (PROCESSED / "summary_report.txt").write_text(out, encoding="utf-8")


def build_crop_coverage(prices: pd.DataFrame) -> None:
    """生成 crop_coverage_report.csv（手册第二十七节）。

    missing_ratio = 1 - 该(城市,产品)实际覆盖周数 / 该品类在同等时间跨度内应覆盖周数。
    """
    prices = prices.copy()
    prices["yw"] = prices["year"].astype("Int64") * 100 + prices["week"].astype("Int64")
    all_weeks = prices.groupby("category_key")["yw"].apply(lambda s: set(s.dropna().astype(int)))

    rows = []
    grouped = prices.dropna(subset=["city"]).groupby(["city", "product", "category"])
    for (city, product, category), g in grouped:
        ws = set(g["yw"].dropna().astype(int))
        if not ws:
            continue
        lo, hi = min(ws), max(ws)
        expected = {w for w in all_weeks.get(g["category_key"].iloc[0], set()) if lo <= w <= hi}
        exp_n = len(expected) or 1
        first = g.loc[g["yw"] == lo, "period_start"].min()
        last = g.loc[g["yw"] == hi, "period_start"].max()
        rows.append({
            "city": city,
            "product": product,
            "category": category,
            "first_date": first,
            "last_date": last,
            "record_count": int(len(g)),
            "years_covered": int(g["year"].nunique()),
            "weeks_covered": int(len(ws)),
            "expected_weeks": int(exp_n),
            "missing_ratio": round(1 - len(ws) / exp_n, 4),
        })
    cov = pd.DataFrame(rows).sort_values(["city", "category", "record_count"], ascending=[True, True, False])
    cov.to_csv(PROCESSED / "crop_coverage_report.csv", index=False, encoding="utf-8-sig")


# ---- main ---------------------------------------------------------------
def main() -> None:
    setup_logging()
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "crawl":
        cmd_crawl()
    elif cmd == "parse":
        cmd_parse()
        cmd_export()
    elif cmd == "normalize":
        cmd_parse()
        cmd_export()
    elif cmd == "validate":
        cmd_validate()
    elif cmd == "export":
        cmd_export()
    elif cmd == "report":
        cmd_report()
    elif cmd == "all":
        cmd_crawl()
        cmd_parse()
        cmd_export()
        cmd_validate()
        cmd_report()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
