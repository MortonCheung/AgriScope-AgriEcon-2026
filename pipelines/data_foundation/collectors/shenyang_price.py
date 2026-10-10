"""沈阳市「菜篮子信息发布平台」价格采集（P0-1 六城市真实农产品价格）。

来源：沈阳市发展和改革委员会 价格监测局 官方发布
     https://fgw.shenyang.gov.cn/wjgz/clzxxfbpt/
数据接口：https://www.lnsyjgjc.com/api/showList（公开 GET，无鉴权、无验证码）
     marketType=1 → 批发价格(10种)  2 → 超市零售(33种)  3 → 集市零售(42种)
     dates=YYYY-MM-DD → 指定日期；周末/节假日无数据

字段：productName 商品名 / grade 规格 / price 价格 / unit 单位 / volume 成交量
     dayVolumeRatio 日成交量环比 / dayRriceRatio 日价格环比 / regionName 区域

原始 JSON 原样落盘到 data/raw/prices/shenyang_clz/，绝不修改。
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "shenyang_clz"
RAW.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
API = "https://www.lnsyjgjc.com/api/showList"
MARKET_TYPES = {"3": "集市零售", "2": "超市零售", "1": "批发价格"}
START = date(2020, 1, 1)


def fetch(d: str, mt: str, retries: int = 3):
    params = {"marketType": mt, "dates": d, "page": 1, "limit": 100}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.lnsyjgjc.com/api/daily"})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def main() -> None:
    end = date.today()
    d = START
    saved = skipped = empty = fail = 0
    t0 = time.time()
    while d <= end:
        if d.weekday() >= 5:      # 周末无数据，直接跳过（已验证）
            d += timedelta(days=1)
            continue
        ds = d.isoformat()
        for mt, label in MARKET_TYPES.items():
            out = RAW / f"{ds}_mt{mt}.json"
            if out.exists():
                skipped += 1
                continue
            try:
                r = fetch(ds, mt)
                out.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
                n = r.get("count", 0) or 0
                if n:
                    saved += 1
                else:
                    empty += 1
            except Exception as exc:
                fail += 1
                print(f"  [FAIL] {ds} mt{mt}: {exc}")
            time.sleep(0.45)
        if (d - START).days % 90 == 0:
            el = time.time() - t0
            print(f"  进度 {ds} | 成功{saved} 空{empty} 跳过{skipped} 失败{fail} | {el/60:.1f}min")
        d += timedelta(days=1)

    print(f"\n[OK] 沈阳价格采集完成：成功 {saved}，空 {empty}，跳过 {skipped}，失败 {fail}")
    print(f"     原始文件目录 {RAW}")


if __name__ == "__main__":
    main()
