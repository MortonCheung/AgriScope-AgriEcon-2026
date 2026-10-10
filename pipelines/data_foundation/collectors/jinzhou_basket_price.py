"""锦州市菜篮子信息发布平台采集（城市级价格源）。

来源：
  价格信息（每日） https://www.jz.gov.cn/ztzl/clzxxfbpt/jgxx.htm   （正文为图片，需 OCR）
  分析预测（每周） https://www.jz.gov.cn/ztzl/clzxxfbpt/fxyc.htm   （正文为文本，可解析）

输出：
  data/raw/prices/jinzhou/basket_weekly/html/*.html       分析预测原文
  data/raw/prices/jinzhou/basket_weekly/list_meta.json   文章清单
  data/raw/prices/jinzhou/basket_daily/*.html            每日价格正文（小样）
  data/raw/prices/jinzhou/basket_daily/img/*.png         每日价格图片（小样）
  city_data/reference/staging/jinzhou_price_basket_weekly.csv           解析后的周价格观测

只做确定性正则提取，原文没有的数字绝不推算。
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "jinzhou"
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

BASE = "https://www.jz.gov.cn"
WEEKLY_LIST = "https://www.jz.gov.cn/ztzl/clzxxfbpt/fxyc.htm"
DAILY_LIST = "https://www.jz.gov.cn/ztzl/clzxxfbpt/jgxx.htm"

# 列表页链接形如 ../../info/1797/xxx.htm 或 ../../../info/1797/xxx.htm（深层分页）
LINK_RE = re.compile(r'<a href="((?:\.\./)+info/\d+/\d+\.htm)"[^>]*title="([^"]+)"')
DATE_RE = re.compile(r'<label>(\d{4}-\d{2}-\d{2})</label>')
# 正文「发布时间」字段（比列表页 label 准确）
PUB_RE = re.compile(r'发布时间[：:]\s*(\d{4}-\d{2}-\d{2})')
# 「下页」按钮（p_next class），href 为相对路径，需按当前页目录解析
NEXT_RE = re.compile(r'<span class="p_next[^"]*"><a href="([^"]+)"')


def get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def get_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def collect_list(list_url: str, max_pages: int = 200) -> list[dict]:
    """遍历列表分页，返回 [{url, title, date, page}]"""
    from urllib.parse import urljoin
    items: dict[str, dict] = {}
    cur = list_url
    for _ in range(max_pages):
        h = get(cur)
        for rel, title in LINK_RE.findall(h):
            full = urljoin(cur, rel)
            d = DATE_RE.search(h)
            items.setdefault(full, {"url": full, "title": title,
                                    "date": d.group(1) if d else ""})
        # 下页
        m = NEXT_RE.search(h)
        nxt = urljoin(cur, m.group(1)) if m else None
        if not nxt or nxt == cur:
            break
        cur = nxt
        time.sleep(0.6)
    return list(items.values())


def parse_weekly(text: str, title: str, pub_date: str) -> list[dict]:
    """解析周分析预测正文中的价格观测。
    典型格式：五花猪肉零售均价13.1元/斤 / 鸡蛋零售均价5.69元/斤 / 牛奶零售均价2.5元/250g
    周区间从标题提取（如 9月7日-9月13日），年份用发布日期推断。
    """
    obs = []
    # 标题周区间：X月X日-X月X日
    m = re.search(r"(\d{1,2})月(\d{1,2})日[—-](\d{1,2})月(\d{1,2})日", title)
    if not m:
        m = re.search(r"(\d{1,2})月(\d{1,2})日", title)
    year = int(pub_date[:4]) if pub_date else None
    week_label = ""
    if m and len(m.groups()) == 4:
        sm, sd, em, ed = m.groups()
        # 跨年（12月底~1月初）时周结束日可能早于开始日 → 结束年=开始年+1
        if int(em) < int(sm) or (int(em) == int(sm) and int(ed) < int(sd)):
            week_label = f"{year}-{int(sm):02d}-{int(sd):02d}~{year + 1}-{int(em):02d}-{int(ed):02d}"
        else:
            week_label = f"{year}-{int(sm):02d}-{int(sd):02d}~{year}-{int(em):02d}-{int(ed):02d}"
    elif m and len(m.groups()) == 2:
        sm, sd = m.groups()
        week_label = f"{year}-{int(sm):02d}-{int(sd):02d}~"
    else:
        week_label = title

    # 通用模式：名称 + 零售均价/批发均价 + 数字 + 单位
    # 名称组排除「零售/批发」字，允许括号顿号（如「奶制品（酸奶、奶粉）零售均价」）
    pat = re.compile(
        r"((?:(?!零售|批发)[\u4e00-\u9fa5（）()、，,·]){2,12}?)(?:零售|批发)?均价"
        r"([\d.]+)\s*元/(斤|500克|500g|公斤|千克|250g|250克|升|瓶|盒|头|只|个|箱)")
    for mm in pat.finditer(text):
        name = re.sub(r"[（）()、，,·]", "", mm.group(1))
        val, unit = mm.group(2), mm.group(3)
        obs.append({
            "week_label": week_label, "pub_date": pub_date, "title": title,
            "product_raw": name, "price_raw": val, "unit_raw": f"元/{unit}",
        })

    # 蔬菜平均价格：本周X种蔬菜……蔬菜平均价格为X.XX元/斤
    m2 = re.search(r"(\d{1,2})种蔬菜[^。；]*?平均价格为?\s*([\d.]+)\s*元/斤", text)
    if m2:
        obs.append({
            "week_label": week_label, "pub_date": pub_date, "title": title,
            "product_raw": f"{m2.group(1)}种蔬菜均价", "price_raw": m2.group(2),
            "unit_raw": "元/斤",
        })
    return obs


def main(limit_weekly: int = 0, daily_samples: int = 3) -> None:
    weekly_html = RAW / "basket_weekly" / "html"
    weekly_html.mkdir(parents=True, exist_ok=True)
    daily_dir = RAW / "basket_daily"
    (daily_dir / "html").mkdir(parents=True, exist_ok=True)
    (daily_dir / "img").mkdir(parents=True, exist_ok=True)

    # ---------- 1. 周分析预测（文本价格主源） ----------
    print("[周分析预测] 收集列表 …")
    weekly = collect_list(WEEKLY_LIST)
    print(f"  共 {len(weekly)} 篇")
    if limit_weekly:
        weekly = weekly[:limit_weekly]
    meta, all_obs = [], []
    for i, it in enumerate(weekly):
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:12]
        f = weekly_html / f"{aid}.html"
        if not f.exists():
            try:
                f.write_text(get(it["url"]), encoding="utf-8")
            except Exception as exc:
                print(f"  [FAIL] {it['date']} {it['title'][:24]}: {exc}")
                continue
            time.sleep(0.6)
        text = re.sub(r"<[^>]+>", " ", f.read_text(encoding="utf-8"))
        text = re.sub(r"\s+", " ", text)
        # 正文发布时间优先（列表页 label 为整页第一个日期，不可靠）
        m_pub = PUB_RE.search(f.read_text(encoding="utf-8"))
        pub_date = m_pub.group(1) if m_pub else it["date"]
        obs = parse_weekly(text, it["title"], pub_date)
        meta.append({**it, "file": f.name, "obs": len(obs), "pub_date": pub_date})
        all_obs += obs
        if (i + 1) % 50 == 0:
            print(f"  已处理 {i + 1}/{len(weekly)}")

    (RAW / "basket_weekly" / "list_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[周分析预测] 下载 {len(meta)} 篇，解析 {len(all_obs)} 条观测")

    if all_obs:
        df = pd.DataFrame(all_obs)
        df["city"] = "锦州"
        df["source_id"] = "SRC-JZ-BASKET-WEEKLY"
        df["source_name"] = "锦州市菜篮子信息发布平台·农产品市场价格周分析预测"
        df["source_url"] = "https://www.jz.gov.cn/ztzl/clzxxfbpt/fxyc.htm"
        df["fetch_time"] = datetime.now().isoformat(timespec="seconds")
        df["parser_version"] = "jinzhou_basket_price_v1"
        df["quality_grade"] = "B"
        out = STAGING / "jinzhou_price_basket_weekly.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[OK] → {out}")
        print(df.groupby(["product_raw", "unit_raw"]).size().sort_values(ascending=False).head(25).to_string())

    # ---------- 2. 每日价格（图片，仅小样） ----------
    daily = collect_list(DAILY_LIST)
    print(f"[每日价格] 共 {len(daily)} 篇，取前 {daily_samples} 篇做小样")
    for it in daily[:daily_samples]:
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:12]
        f = daily_dir / "html" / f"{aid}.html"
        if not f.exists():
            f.write_text(get(it["url"]), encoding="utf-8")
            time.sleep(0.6)
        h = f.read_text(encoding="utf-8")
        imgs = re.findall(r'<img[^>]*src="(/__local/[^"]+\.png)"', h)
        for img_url in imgs:
            if not img_url.strip():
                continue
            full = BASE + img_url
            png = daily_dir / "img" / f"{aid}.png"
            if not png.exists():
                try:
                    png.write_bytes(get_bytes(full))
                    print(f"  [IMG-OK] {it['date']} {full} → {png.name}")
                except Exception as exc:
                    print(f"  [IMG-FAIL] {it['date']}: {exc}")
                time.sleep(0.6)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-weekly", type=int, default=0, help="仅抓前 N 篇周报（0=全部）")
    ap.add_argument("--daily-samples", type=int, default=3)
    args = ap.parse_args()
    main(args.limit_weekly, args.daily_samples)
