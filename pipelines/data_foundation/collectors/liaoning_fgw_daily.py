"""辽宁省发改委「每日价格」采集（省级每日农产品价格）。

来源：辽宁省发展和改革委员会 价格监测
      https://fgw.ln.gov.cn/fgw/xxgk/jgjc/mrjg/index.shtml
实际数据页（iframe）：https://fgw.ln.gov.cn/wjweb/price/MRJQ.aspx
     ASP.NET WebForms，用 __doPostBack('btncxjq') + tnxtime=YYYY-MM-DD 查询历史日期。
     页面 GBK 编码。

内容（原文注明「全省十四个市平均价」→ 省级，不是城市级）：
     辽宁主要农副产品市场价格（14 种：大米/面粉/玉米/大豆/鲜猪肉/牛肉/羊肉/鸡肉/鸡蛋/
     豆油/鲜奶/仔猪/生猪/水稻）
     辽宁主要蔬菜品种市场价格（16 种）

原始 HTML 原样落盘到 data/raw/prices/liaoning_fgw_daily/，不做修改。
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "liaoning_fgw_daily"
RAW.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
URL = "https://fgw.ln.gov.cn/wjweb/price/MRJQ.aspx"
REFERER = "https://fgw.ln.gov.cn/fgw/xxgk/jgjc/mrjg/index.shtml"
START = date(2020, 3, 1)


def http(data=None, timeout=40):
    req = urllib.request.Request(
        URL, data=data.encode() if data else None,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
                 "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode("gbk", "replace")


def hidden(html):
    out = {}
    for n in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        m = re.search(r'name="' + n + r'"[^>]*value="([^"]*)"', html)
        out[n] = m.group(1) if m else ""
    return out


def main() -> None:
    h0 = http()
    hid = hidden(h0)
    print(f"[OK] 取得 ViewState (len={len(hid['__VIEWSTATE'])})")
    (RAW / "_init.html").write_text(h0, encoding="utf-8")

    end = date.today()
    d = START
    ok = empty = skip = fail = 0
    t0 = time.time()
    while d <= end:
        ds = d.isoformat()
        out = RAW / f"{ds}.html"
        if out.exists():
            skip += 1
            d += timedelta(days=1)
            continue
        form = dict(hid)
        form.update({"__EVENTTARGET": "btncxjq", "__EVENTARGUMENT": "", "tnxtime": ds})
        try:
            h = http(urllib.parse.urlencode(form))
            out.write_text(h, encoding="utf-8")
            if re.search(r"元/500", h):
                ok += 1
            else:
                empty += 1
        except Exception as exc:
            fail += 1
            print(f"  [FAIL] {ds}: {exc}")
            time.sleep(3)
        time.sleep(0.8)
        if (d - START).days % 180 == 0:
            print(f"  进度 {ds} | 成功{ok} 空{empty} 跳过{skip} 失败{fail} | {(time.time()-t0)/60:.1f}min")
        d += timedelta(days=1)

    print(f"\n[OK] 省发改委每日价格采集完成：成功 {ok}，空 {empty}，跳过 {skip}，失败 {fail}")
    (RAW / "_collect_log.json").write_text(json.dumps(
        {"ok": ok, "empty": empty, "skip": skip, "fail": fail,
         "start": START.isoformat(), "end": end.isoformat()}, ensure_ascii=False, indent=1),
        encoding="utf-8")


if __name__ == "__main__":
    main()
