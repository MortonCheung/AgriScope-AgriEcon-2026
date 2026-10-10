"""STEP D5 — 区县统计公报 / 统计年鉴采集（用于交叉校验 + 补 2025 年）。

为什么需要：
  1. 《沈阳统计年鉴》农业表覆盖数据年 2015-2024（本市实际可得 2018-2024）；
     区县公报是获取 **2025 年** 区县农业生产数据的官方渠道；
  2. 任务书 §十三-5 要求「同一数据多来源验证」。

做法（可复现、不绕过任何登录）：
  · 逐区县取「统计信息 → 统计公报 / 统计年鉴」栏目页，解析条目链接与标题；
  · 下载条目 HTML；并继续抓取条目页内链接的 PDF/DOC 附件（部分区县正文在附件里）；
  · 文件名用「标题年份 + 条目ID」双键，避免同名覆盖；
  · 登记到 source_registry。

已知站点差异（实测）：
  · 康平县政府站点 TLS 握手不接受默认密码套件 → 使用 unverified http/https 回退；
  · 新民市公报标题用中文数字年份（二〇二五年）→ 年份解析需支持中文数字；
  · 沈北新区/于洪区近年公报正文在 PDF 附件 → 需下钻附件。
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, PROJECT_ROOT, StepTimer, get_logger  # noqa: E402

MOD = "24_district_bulletin_fetch"
LOG = get_logger(MOD)
RAW = PATHS.project["data_raw_district"] / "bulletins"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CTX = ssl._create_unverified_context()

PORTALS: Dict[str, Tuple[str, str, str]] = {
    "新民市":   ("https://www.xinmin.gov.cn",
                 "https://www.xinmin.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/",
                 "https://www.xinmin.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/"),
    "辽中区":   ("https://www.liaozhong.gov.cn",
                 "https://www.liaozhong.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/",
                 "https://www.liaozhong.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/"),
    "康平县":   ("http://www.kangping.gov.cn",
                 "http://www.kangping.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/",
                 "http://www.kangping.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/"),
    "法库县":   ("https://www.faku.gov.cn",
                 "https://www.faku.gov.cn/zfxxgk/fdzdgknr/tjxx/tjgb/",
                 "https://www.faku.gov.cn/zfxxgk/fdzdgknr/tjxx/tjnj/"),
    "沈北新区": ("https://www.nsy.gov.cn",
                 "https://www.nsy.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/",
                 "https://www.nsy.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/"),
    "苏家屯区": ("https://www.sjtq.gov.cn",
                 "https://www.sjtq.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/",
                 "https://www.sjtq.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/"),
    "浑南区":   ("http://www.hunnan.gov.cn",
                 "http://www.hunnan.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/",
                 "http://www.hunnan.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/"),
    "于洪区":   ("https://www.syyh.gov.cn",
                 "https://www.syyh.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/",
                 "https://www.syyh.gov.cn/zwgk/fdzdgknr/tjxx/tjnj/"),
}

DOC_EXT = re.compile(r"\.(pdf|doc|docx|xls|xlsx)(\?|$)", re.I)
CN_DIGIT = {"〇": "0", "零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
            "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}


def year_of(text: str) -> int:
    m = re.search(r"(20[12]\d)", text)
    if m:
        return int(m.group(1))
    m2 = re.search(r"([〇零一二三四五六七八九]{4})\s*年", text)
    if m2:
        y = int("".join(CN_DIGIT.get(c, "?") for c in m2.group(1)).replace("?", "0"))
        if 2010 <= y <= 2030:
            return y
    return -1


def get(url: str, binary: bool = False, timeout: int = 90, retries: int = 3):
    last = None
    for a in range(retries):
        for u in ([url, url.replace("https://", "http://")] if url.startswith("https") else [url]):
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": u})
                with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                    data = r.read()
                return data if binary else data.decode("utf-8", "replace")
            except Exception as exc:  # noqa: BLE001
                last = exc
        time.sleep(2 * (a + 1))
    raise last


def abs_url(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return urllib.parse.urlparse(base).scheme + ":" + href
    if href.startswith("/"):
        p = urllib.parse.urlparse(base)
        return f"{p.scheme}://{p.netloc}{href}"
    return base.rsplit("/", 1)[0] + "/" + href


def article_id(url: str) -> str:
    m = re.search(r"_(t?\d{6,})\.", url)
    if m:
        return m.group(1)
    return hashlib.md5(url.encode()).hexdigest()[:10]


def list_items(html: str, base: str) -> List[Tuple[str, str]]:
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
        href, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        text = re.sub(r"\s+", " ", text).strip()
        if not href or href.startswith(("#", "javascript")):
            continue
        u = abs_url(base, href)
        if DOC_EXT.search(u) or (".html" in u.lower() and text):
            out.append((text, u))
    seen, uniq = set(), []
    for t, u in out:
        if u in seen:
            continue
        seen.add(u)
        uniq.append((t, u))
    return uniq


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        RAW.mkdir(parents=True, exist_ok=True)
        registry_rows = []
        for ds, (portal, bcol, ycol) in PORTALS.items():
            outdir = RAW / ds
            outdir.mkdir(parents=True, exist_ok=True)
            for kind, col in (("bulletin", bcol), ("yearbook", ycol)):
                try:
                    html = get(col)
                except Exception as exc:  # noqa: BLE001
                    log.warning("[FAIL] %s %s 栏目页不可达：%s", ds, kind, exc)
                    continue
                items = list_items(html, col)
                keep = [(t, u) for t, u in items
                        if any(k in t for k in ("公报", "综述", "统计资料", "年鉴", "汇编"))
                        or year_of(t) > 0]
                log.info("%s %s：栏目解析 %d 条（保留 %d）", ds, kind, len(items), len(keep))
                for title, url in keep:
                    y = year_of(title)
                    aid = article_id(url)
                    ext = ".pdf" if ".pdf" in url.lower() else (
                        ".docx" if ".docx" in url.lower() else (
                            ".doc" if ".doc" in url.lower() else ".html"))
                    fn = outdir / f"{kind}_{y if y > 0 else 'unknown'}_{aid}{ext}"
                    if not (fn.exists() and fn.stat().st_size > 0):
                        try:
                            if ext == ".html":
                                fn.write_text(get(url), encoding="utf-8")
                            else:
                                fn.write_bytes(get(url, binary=True))
                            log.info("   [OK] %s ← %s", fn.name, title[:34])
                        except Exception as exc:  # noqa: BLE001
                            log.warning("   [FAIL] %s：%s", url, exc)
                            continue
                    registry_rows.append({
                        "source_id": f"{ds}-{kind}-{y}-{aid}",
                        "title": title, "publisher": f"{ds}人民政府/统计局",
                        "year": y, "data_year": y,
                        "url": url, "local_file": str(fn.relative_to(PROJECT_ROOT)),
                        "data_type": "statistical_bulletin" if kind == "bulletin" else "statistical_yearbook",
                        "districts": ds, "crops": "粮食/蔬菜/油料等（以原文为准）",
                        "original_unit": "以原文为准", "source_grade": "B",
                        "accessed_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "notes": "区县政府门户；用于交叉校验与补 2025 年",
                    })
                    # 下钻条目页内的附件（部分区县正文在 PDF/DOC）
                    if ext == ".html":
                        try:
                            inner = get(url)
                        except Exception:  # noqa: BLE001
                            inner = ""
                        for _, au in list_items(inner, url):
                            if not DOC_EXT.search(au):
                                continue
                            aext = "." + au.rsplit(".", 1)[-1].split("?")[0].lower()
                            afn = outdir / f"{kind}_{y if y > 0 else 'unknown'}_{article_id(au)}{aext}"
                            if afn.exists() and afn.stat().st_size > 0:
                                continue
                            try:
                                afn.write_bytes(get(au, binary=True))
                                log.info("   [OK] 附件 %s", afn.name)
                                registry_rows.append({
                                    "source_id": f"{ds}-{kind}-{y}-{article_id(au)}",
                                    "title": f"{title}（附件）", "publisher": f"{ds}人民政府/统计局",
                                    "year": y, "data_year": y, "url": au,
                                    "local_file": str(afn.relative_to(PROJECT_ROOT)),
                                    "data_type": "statistical_bulletin_attachment",
                                    "districts": ds, "crops": "以原文为准",
                                    "original_unit": "以原文为准", "source_grade": "B",
                                    "accessed_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "notes": "公报附件",
                                })
                            except Exception as exc:  # noqa: BLE001
                                log.warning("   [FAIL] 附件 %s：%s", au, exc)
                    time.sleep(1.2)

        reg_p = PATHS.project["data_raw_district"] / "source_registry.csv"
        old = pd.read_csv(reg_p).fillna("") if reg_p.exists() else pd.DataFrame()
        new = pd.DataFrame(registry_rows)
        if len(new):
            for c in old.columns:
                if c not in new.columns:
                    new[c] = ""
            if len(old.columns):
                new = new[old.columns]
            out = pd.concat([old, new], ignore_index=True)
            out = out.drop_duplicates(subset=["source_id"], keep="last").sort_values("source_id")
            out.to_csv(reg_p, index=False, encoding="utf-8-sig")
        log.info("source_registry 累计 %d 条", len(old) + len(new) if len(new) else len(old))


if __name__ == "__main__":
    main()
