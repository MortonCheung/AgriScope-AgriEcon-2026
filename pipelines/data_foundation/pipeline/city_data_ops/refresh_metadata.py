"""刷新元数据：各城 data_snapshot.json / MANIFEST.csv，并新建 city_data/SOURCE_REGISTRY.csv。"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
NOW = datetime.now().isoformat(timespec="seconds")
CITIES = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
          "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def refresh_city(code: str) -> None:
    d = ROOT / code / "data"
    inter = d / "interim"
    if not inter.exists():
        return
    # --- data_snapshot.json ---
    snap_p = d / "data_snapshot.json"
    snap = json.loads(snap_p.read_text(encoding="utf-8")) if snap_p.exists() else {"city": CITIES[code], "city_code": code}
    ds = snap.setdefault("datasets", {})
    for f in sorted(inter.glob("*.csv")):
        try:
            df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
        except Exception:
            continue
        dc = next((x for x in ("observation_date", "date", "year", "publish_date", "policy_date", "start_date")
                   if x in df.columns), None)
        ds[f.stem] = {
            "status": "AVAILABLE" if len(df) else "EMPTY",
            "rows": len(df),
            "unique_dates": int(df[dc].astype(str).nunique()) if dc else 0,
            "crop_count": int(df["crop_standard"].nunique()) if "crop_standard" in df.columns
                          else (int(df["crop"].nunique()) if "crop" in df.columns else 0),
            "source_count": int(df["source_id"].nunique()) if "source_id" in df.columns else 0,
        }
    snap["generated_at"] = NOW
    snap_p.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- MANIFEST.csv：刷新 interim 行 + 追加缺失 ---
    man_p = d / "MANIFEST.csv"
    fields = ["city", "layer", "dataset_type", "target_path", "original_path",
              "rows", "file_size", "sha256", "copy_method", "created_at", "notes"]
    rows = []
    if man_p.exists():
        with man_p.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    listed = {r.get("target_path") for r in rows}
    for r in rows:
        tp = r.get("target_path", "")
        fp = ROOT.parent / tp if tp.startswith("city_data/") else (ROOT / tp)
        if r.get("layer") == "interim" and fp.exists():
            r["rows"] = str(sum(1 for _ in fp.open(encoding="utf-8-sig")) - 1)
            r["file_size"] = str(fp.stat().st_size)
            r["sha256"] = sha(fp)
    for f in sorted(inter.glob("*.csv")):
        tp = f"city_data/{code}/data/{f.name}"
        if tp in listed:
            continue
        rows.append({"city": CITIES[code], "layer": "interim", "dataset_type": f.stem,
                     "target_path": tp, "original_path": "",
                     "rows": str(sum(1 for _ in f.open(encoding="utf-8-sig")) - 1),
                     "file_size": str(f.stat().st_size), "sha256": sha(f),
                     "copy_method": "manual", "created_at": NOW, "notes": "本轮缺口补齐新增"})
    with man_p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"  [OK] {CITIES[code]}: snapshot {len(ds)} 数据集, MANIFEST {len(rows)} 行")


def build_source_registry() -> None:
    fields = ["source_id", "publisher", "source_url", "retrieval_date", "raw_file",
              "dataset_type", "city", "county", "geo_level", "quality_grade", "notes"]
    new = [
        ["SRC-DL-SWJ-VOLUME", "大连市商务局", "https://boc.dl.gov.cn/", "2026-09-22",
         "data/raw/web_captures/dalian/volume/", "volume", "大连", "", "market/city", "A",
         "生活必需品市场监测数据(日/周,2020-2022);+230行;13市场/112日"],
        ["SRC-CNHNB-HANGQING", "惠农网", "https://www.cnhnb.com/hangqing/", "2026-09-22",
         "data/raw/web_captures/tieling/price/cnhnb/", "price", "铁岭/丹东/大连/锦州/朝阳", "多县", "county", "C",
         "县域产地行情(areaId);连续请求触发503风控,未绕过"],
        ["SRC-YMT-CHANDI", "一亩田", "https://m_hangqing.ymt.com/", "2026-09-22",
         "data/raw/web_captures/dandong/price/ymt/", "price", "丹东", "东港/凤城/宽甸/元宝/振兴/振安", "county", "C",
         "区县产地行情;仅近5日窗口,历史不可回溯"],
        ["SRC-DBS-FGJ", "调兵山市发改局", "https://www.dbs.gov.cn/", "2026-09-22",
         "data/raw/web_captures/tieling/price/diaobingshan_fgj/", "price", "铁岭", "调兵山市", "county", "B",
         "月度价格监测 2023-2024"],
        ["SRC-KY-FGJ", "开原市发改局", "https://www.kaiyuan.gov.cn/", "2026-09-22",
         "data/raw/web_captures/tieling/price/kaiyuan_fgj/", "price", "铁岭", "开原市", "county", "B",
         "价格报告 PDF"],
        ["SRC-CY-JPZAIQING", "朝阳市建平县/北票市政府", "https://www.chaoyang.gov.cn/", "2026-09-22",
         "data/raw/web_captures/chaoyang/disaster/", "disaster", "朝阳", "建平县/北票市", "county", "A",
         "灾情核定信息(受灾/成灾/绝收面积+损失)"],
        ["SRC-LNNYNC-LIANBO", "辽宁省农业农村厅", "https://nync.ln.gov.cn/", "2026-09-22",
         "data/raw/web_captures/*/{phenology,disaster,policy}/",
         "phenology/disaster/policy", "六城", "", "city/county", "B", "农业信息联播深分页(城市标签)"],
        ["SRC-ASKCI-PRICE", "中商情报网", "https://www.askci.com/news/data/price/", "2026-09-22",
         "data/raw/web_captures/*/price/", "price", "辽宁", "", "market", "C",
         "市场级日价(辽宁仅3市场)"],
        ["SRC-MOA-PFSC-SPOT", "农业农村部", "https://pfsc.agri.cn/", "2026-09-22",
         "data/raw/prices/moa_wholesale/", "price", "辽宁", "", "market", "B",
         "仅当日快照无历史;成交量字段全null;ncpscxx 502"],
        ["SRC-ECOM-JD", "京东(第三方)", "https://item.m.jd.com/", "2026-09-22",
         "data/raw/prices/ecommerce/", "price", "", "", "national", "D",
         "商品+规格可得;价格需登录(未绕过)"],
        ["SRC-ECOM-INSTANT", "美团/多多/盒马/七鲜等", "-", "2026-09-22", "-", "price", "", "", "store", "D",
         "ACCESS_RESTRICTED:价格需登录/APP/自提点"],
    ]
    p = ROOT / "reference" / "registries" / "SOURCE_REGISTRY.csv"
    existing = []
    if p.exists():
        with p.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
    have = {r["source_id"] for r in existing}
    for row in new:
        if row[0] in have:
            continue
        existing.append(dict(zip(fields, row)))
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in existing:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"[OK] SOURCE_REGISTRY.csv {len(existing)} 源")


if __name__ == "__main__":
    print("=== 刷新各城元数据 ===")
    for c in CITIES:
        try:
            refresh_city(c)
        except Exception as e:
            print(f"  [warn] {c}: {e}")
    build_source_registry()
