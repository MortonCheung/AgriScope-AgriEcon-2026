"""辽宁省统计局年鉴与年度数据下载（数据源 C：农业生产数据）。

仅使用统计局官方公开资料，保存原始 ZIP/Excel 到 data/raw/statistical_yearbooks/。
"""
from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "statistical_yearbooks"
RAW.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://tjj.ln.gov.cn"

FILES = {
    "yearbook_2020.zip": "/tjj/tjsj/tjnj/njsjxz/2023110210085021756/2025010614482229551.zip",
    "yearbook_2019.zip": "/tjj/tjsj/tjnj/njsjxz/2023110210084851581/2024042816145835780.zip",
    "yearbook_2018.zip": "/tjj/tjsj/tjnj/njsjxz/2023110210084851581/2024042816144622966.zip",
}


def download(name: str, path: str) -> bool:
    out = RAW / name
    if out.exists() and out.stat().st_size > 1024:
        print(f"[SKIP] {name} 已存在 ({out.stat().st_size} bytes)")
        return True
    url = BASE + path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300, context=CTX) as r:
            data = r.read()
        out.write_bytes(data)
        print(f"[OK] {name} {len(data)} bytes")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> None:
    results = {}
    for name, path in FILES.items():
        ok = download(name, path)
        results[name] = {
            "status": "success" if ok else "network_failed",
            "source_url": BASE + path,
            "file": f"data/raw/statistical_yearbooks/{name}",
        }
    (RAW / "manifest.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[OK] manifest 写入")


if __name__ == "__main__":
    main()
