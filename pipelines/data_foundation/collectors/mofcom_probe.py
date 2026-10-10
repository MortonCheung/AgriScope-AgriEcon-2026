"""探测商务部市场运行系统 cif.mofcom.gov.cn：
  1) listPage 接口的 size / current 上限（分页究竟能否恢复历史）
  2) 各 city 子站首页暴露的 blockid
  3) 枚举辽宁五城子站是否存在

只做探测，输出 JSON 摘要到 data/raw/prices/mofcom/probe_*.json
"""
from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.request
from pathlib import Path

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data/raw" / "prices" / "mofcom"
OUT.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
try:
    CTX.set_ciphers("DEFAULT@SECLEVEL=1")
except Exception:
    try:
        CTX.set_ciphers("ALL:@SECLEVEL=1")
    except Exception:
        pass
try:
    CTX.minimum_version = ssl.TLSVersion.TLSv1
except Exception:
    pass
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://cif.mofcom.gov.cn"


def get_bytes(url: str, timeout: int = 30, retries: int = 3, referer: str | None = None):
    last = None
    for a in range(retries):
        try:
            hdr = {"User-Agent": UA, "Accept": "*/*"}
            if referer:
                hdr["Referer"] = referer
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read(), dict(r.headers), r.status
        except Exception as exc:
            last = exc
            time.sleep(1.2 * (a + 1))
    raise last


def dec(raw: bytes) -> str:
    for e in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(e)
        except Exception:
            continue
    return raw.decode("gbk", "replace")


def probe_list(blockid: int, size: int, current: int = 1) -> dict:
    url = (f"{BASE}/newsite/content/content/front/listPage"
           f"?current={current}&size={size}&blockid={blockid}")
    try:
        raw, hdr, st = get_bytes(url, referer=f"{BASE}/newsite/html/dalian/index.html")
    except Exception as exc:
        return {"url": url, "error": str(exc)}
    txt = dec(raw)
    info = {"url": url, "status": st, "content_type": hdr.get("Content-Type"),
            "bytes": len(raw), "head": txt[:400]}
    try:
        j = json.loads(txt)
        info["json_keys"] = list(j.keys()) if isinstance(j, dict) else f"list[{len(j)}]"
        if isinstance(j, dict):
            for k, v in j.items():
                if isinstance(v, list):
                    info[f"len_{k}"] = len(v)
                elif isinstance(v, (int, str)):
                    info[k] = v
        elif isinstance(j, list):
            info["len_list"] = len(j)
    except Exception:
        info["json_ok"] = False
        ids = re.findall(r'/newsite/html/[a-z]+/html/\d+/\d{4}/\d{1,2}/\d{1,2}/\d+\.html', txt)
        info["href_count"] = len(ids)
    return info


def probe_index(city: str) -> dict:
    url = f"{BASE}/newsite/html/{city}/index.html"
    try:
        raw, hdr, st = get_bytes(url)
    except Exception as exc:
        return {"city": city, "url": url, "error": str(exc)}
    txt = dec(raw)
    blocks = sorted(set(re.findall(r"blockid=(\d+)", txt)))
    blocks2 = sorted(set(re.findall(r"['\"](\d{8})['\"]", txt)))
    arts = re.findall(rf'/newsite/html/{city}/html/\d+/\d{{4}}/\d{{1,2}}/\d{{1,2}}/\d+\.html', txt)
    title = re.search(r"<title>(.*?)</title>", txt, re.S)
    return {"city": city, "url": url, "status": st, "bytes": len(raw),
            "title": (title.group(1).strip() if title else "")[:60],
            "blockids": blocks, "blockids_8": blocks2,
            "article_links": len(set(arts))}


def main():
    report = {"list_probes": [], "index_probes": []}

    # 1) size 上限探测（大连生活必需品动态）
    for size in (10, 20, 50, 100, 200, 500, 1000):
        r = probe_list(24511242, size)
        r["size"] = size
        report["list_probes"].append(r)
        got = r.get("len_list") or r.get("len_records") or r.get("len_rows") or r.get("len_data")
        print(f"  size={size:5d} -> {r.get('content_type')} len={got} bytes={r.get('bytes')} err={r.get('error','')}")
        time.sleep(0.4)

    # 2) current 深分页探测（size=10, current 大）
    for cur in (1, 2, 5, 20, 50):
        r = probe_list(24511242, 10, cur)
        r["current"] = cur
        report["list_probes"].append(r)
        got = r.get("len_list") or r.get("len_records") or r.get("len_rows") or r.get("len_data")
        print(f"  current={cur:3d} -> len={got} err={r.get('error','')}")
        time.sleep(0.4)

    # 3) 附近 blockid 枚举
    for bid in (24511239, 24511240, 24511241, 24511242, 24511243, 24511244):
        r = probe_list(bid, 5)
        r["blockid"] = bid
        report["list_probes"].append(r)
        got = r.get("len_list") or r.get("len_records") or r.get("len_rows") or r.get("len_data")
        print(f"  blockid={bid} -> len={got} err={r.get('error','')}")
        time.sleep(0.4)

    # 4) 各市子站探测
    cities = ["dalian", "dandong", "tieling", "jinzhou", "chaoyang", "shenyang",
              "anshan", "fushun", "benxi", "yingkou", "fuxin", "liaoyang",
              "panjin", "huludao"]
    for c in cities:
        r = probe_index(c)
        report["index_probes"].append(r)
        print(f"  [{c}] {r.get('status','ERR')} blocks={r.get('blockids')} arts={r.get('article_links')} {r.get('error','')}")
        time.sleep(0.4)

    (OUT / "probe_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] -> {OUT / 'probe_report.json'}")


if __name__ == "__main__":
    main()
