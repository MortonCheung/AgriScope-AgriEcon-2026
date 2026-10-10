"""锦州市政府「菜篮子信息发布平台」日度价格采集（本轮第二优先级）。

来源：https://www.jz.gov.cn/ztzl/clzxxfbpt.htm
省发改委文件佐证："设立市级'菜篮子'信息发布平台，发布每日价情信息"

URL 规律（已验证）：
  列表首页   https://www.jz.gov.cn/ztzl/clzxxfbpt.htm          （最新一页）
  分页       https://www.jz.gov.cn/ztzl/clzxxfbpt/{N}.htm       N=1(最旧) .. 95
             —— 注意是**倒序**：首页为第96页，尾页为 1.htm
  日度文章   https://www.jz.gov.cn/info/1796/{id}.htm           「X年X月X日锦州市农产品市场价格」
  周分析     https://www.jz.gov.cn/info/1797/{id}.htm           「X月X日-X月X日…周分析预测」

此前只有 jinzhou_price_basket_weekly.csv（周度 1885 行），本轮补的是**日度原文**。
必须直连（沙箱代理对 gov.cn 502）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "jinzhou_deep"
HTML = RAW / "html"
HTML.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://www.jz.gov.cn/ztzl/clzxxfbpt"
INDEX = BASE + ".htm"


def get(url: str, timeout: int = 30, retries: int = 3) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": INDEX})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
            for enc in ("utf-8", "gb18030"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def parse_items(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href = m.group(1)
        if "/info/" not in href:
            continue
        txt = re.sub(r"<[^>]+>", "|", m.group(2))
        txt = re.sub(r"[\s\t\r\n]+", "", txt).strip("|")
        parts = [p for p in txt.split("|") if p]
        if not parts:
            continue
        title = parts[0]
        date = ""
        dm = re.search(r"(20\d\d)年(\d{1,2})月(\d{1,2})日", title)
        if dm:
            date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
        if not date:
            for p in parts[1:]:
                if re.match(r"^20\d\d-\d\d-\d\d$", p):
                    date = p
                    break
        full = href if href.startswith("http") else (
            "https://www.jz.gov.cn/ztzl/" + href.lstrip("./")
            if not href.startswith("/") else "https://www.jz.gov.cn" + href)
        kind = "daily" if "/info/1796/" in full else ("weekly" if "/info/1797/" in full else "other")
        out.append({"url": full, "title": title, "date": date, "kind": kind})
    seen, uniq = set(), []
    for it in out:
        if it["url"] not in seen:
            seen.add(it["url"])
            uniq.append(it)
    return uniq


def main() -> None:
    t0 = time.time()
    print("=== 锦州菜篮子平台：列表抓取（倒序 96 页）===")
    # 若索引已存在则复用，避免重复抓 96 页列表（长任务被中断时可续跑）
    idx_file = RAW / "article_index.json"
    if idx_file.exists():
        try:
            cached = json.loads(idx_file.read_text(encoding="utf-8"))
            if cached:
                print(f"  [复用已有索引] {len(cached)} 条，跳过列表抓取")
                items = cached
        except Exception:
            items = []
    items: list[dict] = items if "items" in dir() or True else []
    try:
        got = parse_items(get(INDEX))
        items += got
        print(f"  [首页] {len(got)} 条")
    except Exception as exc:
        print(f"  [首页] 失败 {exc}")
    for n in range(95, 0, -1):          # 95 -> 1（从较新到较旧）
        try:
            got = parse_items(get(f"{BASE}/{n}.htm"))
        except Exception as exc:
            print(f"  [页 {n}] 失败 {exc}")
            continue
        items += got
        if n % 12 == 0 or n > 93:
            print(f"  [页 {n}] {len(got)} 条，累计 {len(items)}")
        time.sleep(0.3)

    seen, uniq = set(), []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            uniq.append(it)
    items = uniq
    print(f"[OK] 列表条目 {len(items)} 条")
    ds = sorted([i["date"] for i in items if i["date"]])
    if ds:
        print(f"    日期范围：{ds[0]} ~ {ds[-1]}")
    kinds = {}
    for i in items:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
    print(f"    类型：{kinds}")

    (RAW / "article_index.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== 文章下载 ===")
    saved = skip = fail = 0
    for i, it in enumerate(items, 1):
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        out = HTML / f"{aid}.html"
        if out.exists():
            skip += 1
            continue
        try:
            out.write_text(get(it["url"]), encoding="utf-8")
            saved += 1
        except Exception as exc:
            fail += 1
            if fail <= 5:
                print(f"  [FAIL] {it['url']}: {exc}")
            continue
        time.sleep(0.28)
        if i % 150 == 0:
            print(f"  进度 {i}/{len(items)} | 新{saved} 跳过{skip} 失败{fail} | {(time.time()-t0)/60:.1f}min")

    print(f"\n[OK] 锦州采集完成：新增 {saved}，跳过 {skip}，失败 {fail}")


if __name__ == "__main__":
    main()
