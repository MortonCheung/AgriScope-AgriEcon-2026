"""六城市统计公报采集 + 农业生产数据解析（P0-2：2020—2025 城市×作物×年）。

统计公报是市政府的年度官方统计发布，其中「农业」章节含：
  粮食作物播种面积（总面积 + 分作物：水稻/玉米/大豆/…）
  粮食产量（总产 + 分作物）
  经济作物、油料、蔬菜及食用菌、果园面积、水果产量
  畜产品等

已确认可用：
  铁岭 https://www.tieling.gov.cn/tieling/zwgk/zfxxgk/fdzdgknr/tjxx/tjgb/  （2016—2025）
  朝阳 https://www.chaoyang.gov.cn/cyszf/zwgk/zfxxgkpt/fdzdgknr/tjxx/      （含2024）

原始 HTML 落盘 data/raw/production/{city}_bulletin/，解析结果写入 staging。
只做确定性正则提取，原文没有的数字绝不推算。
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "production"
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SOURCES = [
    ("铁岭", "https://www.tieling.gov.cn/tieling/zwgk/zfxxgk/fdzdgknr/tjxx/tjgb/"),
    ("朝阳", "https://www.chaoyang.gov.cn/cyszf/zwgk/zfxxgkpt/fdzdgknr/tjxx/"),
]

GB_RE = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>\s*(20\d\d)年[^<]*?统计公报', re.S)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def text_of(html: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    b = re.sub(r"<[^>]+>", "", b)
    b = re.sub(r"&nbsp;|&#160;", " ", b)
    return re.sub(r"\s+", "", b)      # 公报数字常被换行/空格打断，去空白便于匹配


def main() -> None:
    all_rows = []
    for city, list_url in SOURCES:
        RAW_C = RAW / f"{city}_bulletin"
        RAW_C.mkdir(parents=True, exist_ok=True)
        try:
            h = get(list_url)
        except Exception as exc:
            print(f"[{city}] 列表失败 {exc}")
            continue
        domain = "https://" + list_url.split("/")[2]
        links = {}
        for href, year in GB_RE.findall(h):
            # 政府站多为根相对路径（以 / 开头），必须拼到域名根而不是栏目路径下
            if href.startswith("http"):
                full = href
            elif href.startswith("/"):
                full = domain + href
            else:
                full = list_url.rstrip("/") + "/" + href
            links.setdefault(year, full)
        # 备用：title 属性
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*title="(20\d\d年[^"]*统计公报)"', h):
            href = m.group(1)
            full = (href if href.startswith("http")
                    else domain + href if href.startswith("/")
                    else list_url.rstrip("/") + "/" + href)
            links.setdefault(m.group(2)[:4], full)
        # 再备用：任何含「统计公报」的链接
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]*统计公报[^<]*)</a>', h):
            href = m.group(1)
            ym = re.search(r"(20\d\d)", m.group(2))
            if not ym:
                continue
            full = (href if href.startswith("http")
                    else domain + href if href.startswith("/")
                    else list_url.rstrip("/") + "/" + href)
            links.setdefault(ym.group(1), full)
        print(f"[{city}] 找到公报 {len(links)} 年: {sorted(links)}")

        for year, url in sorted(links.items()):
            if int(year) < 2020:
                continue
            aid = hashlib.md5(url.encode()).hexdigest()[:16]
            out = RAW_C / f"{year}_{aid}.html"
            if not out.exists():
                try:
                    out.write_text(get(url), encoding="utf-8")
                except Exception as exc:
                    print(f"  [{city} {year}] 下载失败 {exc}")
                    continue
                time.sleep(0.8)
            txt = text_of(out.read_text(encoding="utf-8"))
            rows = parse_agri(city, year, txt, url, str(out.relative_to(ROOT)))
            all_rows += rows
            print(f"  [{city} {year}] 提取 {len(rows)} 条农业指标")

    if not all_rows:
        print("[WARN] 未提取到公报农业数据")
        return
    df = pd.DataFrame(all_rows) if False else None
    import pandas as pd
    df = pd.DataFrame(all_rows)
    df.to_csv(STAGING / "city_bulletin_production.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] city_bulletin_production {len(df)} 条")
    print(df.groupby(["city", "year"]).size().to_string())


# ---------- 农业指标解析 ----------
CROP_LIST = ["粮食作物", "粮食", "水稻", "玉米", "大豆", "小麦", "薯类", "谷子", "高粱",
             "油料作物", "油料", "蔬菜及食用菌", "蔬菜", "花生"]

AREA_PAT = re.compile(r"([\u4e00-\u9fa5]{2,7}?)播种面积([\d.]+)千公顷")
PROD_PAT = re.compile(r"([\u4e00-\u9fa5]{2,7}?)产量([\d.]+)万吨")
ORCHARD_PAT = re.compile(r"果园面积([\d.]+)千公顷")


def parse_agri(city: str, year: str, txt: str, url: str, raw_file: str) -> list[dict]:
    out = []
    seen = set()
    for m in AREA_PAT.finditer(txt):
        crop, val = m.group(1), m.group(2)
        crop = crop.rstrip("全年")
        if crop not in CROP_LIST or ("crop", "area", crop) in seen:
            continue
        seen.add(("crop", "area", crop))
        out.append({"city": city, "year": int(year), "crop_raw": crop,
                    "metric": "planting_area", "value": float(val), "unit_raw": "千公顷",
                    "source": f"{city}市国民经济和社会发展统计公报", "source_url": url,
                    "raw_file": raw_file, "quality_grade": "A"})
    for m in PROD_PAT.finditer(txt):
        crop, val = m.group(1), m.group(2)
        # 排除「肉产量」等畜牧表述
        if re.search(r"肉$|禽|蛋|奶|水产品", crop):
            continue
        crop = crop.rstrip("全年")
        if crop not in CROP_LIST or ("crop", "prod", crop) in seen:
            continue
        seen.add(("crop", "prod", crop))
        out.append({"city": city, "year": int(year), "crop_raw": crop,
                    "metric": "production", "value": float(val), "unit_raw": "万吨",
                    "source": f"{city}市国民经济和社会发展统计公报", "source_url": url,
                    "raw_file": raw_file, "quality_grade": "A"})
    m = ORCHARD_PAT.search(txt)
    if m:
        out.append({"city": city, "year": int(year), "crop_raw": "果园",
                    "metric": "orchard_area", "value": float(m.group(1)), "unit_raw": "千公顷",
                    "source": f"{city}市国民经济和社会发展统计公报", "source_url": url,
                    "raw_file": raw_file, "quality_grade": "A"})
    return out


if __name__ == "__main__":
    main()
