"""锦州价格图片批量 OCR —— **按图片 URL 去重**。

【为什么必须去重】
锦州菜篮子栏目每天发布一篇「锦州市农产品市场价格」文章，但**价格表图并非每日更新**。
对全量 1590 篇日度文章做 URL 归并后：
    唯一图片 598 张 / (图,日期) 对 1586 个 → 平均复用 2.65 天
    2020 年为真日度（1.00x），2021 年起约 3 天更新一次（3.42x ~ 3.56x）
若按 1586 篇各 OCR 一次入库，会把同一张价格表的价格**复制到连续 2~5 天**，
制造大量「价格未变」的伪日度观测，导致下游波动率被严重低估。
因此本脚本只对**唯一图**执行一次 OCR。

【输出】
  data/raw/prices/jinzhou_deep/ocr/{image_id}.txt        每张唯一图的 OCR 文本
  data/raw/prices/jinzhou_deep/image_groups.json         图 → 引用日期映射（含跨度异常标记）

【加速】优先用 swiftc 预编译 ocr_image.swift 为二进制，避免每张图重复编译。

质量等级：OCR 为机器转录 → quality_grade = B；原图全部保留，不删除。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from pathlib import Path

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "jinzhou_deep"
HTML = RAW / "html"
IMG = RAW / "images"
OCR = RAW / "ocr"
OCR.mkdir(parents=True, exist_ok=True)
SWIFT_SRC = ROOT / "collectors" / "ocr_image.swift"
SWIFT_BIN = ROOT / "collectors" / ".ocr_image_bin"

IMG_RE = re.compile(r'<img[^>]*src="([^"]+\.(?:png|jpg|jpeg))"[^>]*>', re.I)
WORKERS = int(os.environ.get("JZ_OCR_WORKERS", "4"))


def build_tool() -> str:
    """编译 Vision OCR 二进制；失败则回退到 swift 解释执行。"""
    if SWIFT_BIN.exists() and SWIFT_BIN.stat().st_mtime > SWIFT_SRC.stat().st_mtime:
        return str(SWIFT_BIN)
    try:
        r = subprocess.run(["swiftc", "-O", str(SWIFT_SRC), "-o", str(SWIFT_BIN)],
                           capture_output=True, timeout=300)
        if r.returncode == 0 and SWIFT_BIN.exists():
            print(f"[OK] 已编译 OCR 二进制 {SWIFT_BIN.name}")
            return str(SWIFT_BIN)
        print("[WARN] swiftc 编译失败，回退 swift 解释执行:", r.stderr.decode()[:200])
    except Exception as exc:
        print("[WARN] swiftc 不可用，回退 swift 解释执行:", exc)
    return "swift"


def abs_url(src: str) -> str:
    if src.startswith("http"):
        return src
    return "https://www.jz.gov.cn" + (src if src.startswith("/") else "/" + src)


def collect_groups() -> dict[str, set[str]]:
    """扫描全部已下载 HTML，建立 image_id → {日期} 映射。"""
    idx = json.loads((RAW / "article_index.json").read_text(encoding="utf-8"))
    daily = [x for x in idx if x["kind"] == "daily"]
    groups: dict[str, set[str]] = defaultdict(set)
    scanned = 0
    for it in daily:
        d = it.get("date")
        if not d:
            continue
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        hf = HTML / f"{aid}.html"
        if not hf.exists():
            continue
        try:
            t = hf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        scanned += 1
        for s in IMG_RE.findall(t):
            if not ("__local" in s or "_vsl" in s or "upload" in s.lower()):
                continue
            iid = hashlib.md5(abs_url(s).encode()).hexdigest()[:16]
            groups[iid].add(d)
    print(f"扫描 HTML {scanned} 篇 → 唯一图片 {len(groups)} 张")
    return groups


def pick_image(iid: str, dates: set[str]) -> Path | None:
    """在 images/ 里找一个该图的副本作为代表（不复制、不改名）。"""
    for d in sorted(dates):
        f = IMG / f"{d}_{iid}.png"
        if f.exists():
            return f
    hits = sorted(IMG.glob(f"*_{iid}.png"))
    return hits[0] if hits else None


def do_ocr(iid: str, img: Path, tool: str) -> tuple[str, bool, str]:
    txt = OCR / f"{iid}.txt"
    if txt.exists() and txt.stat().st_size > 0:
        return iid, True, "skip"
    if tool == "swift":
        cmd = ["swift", str(SWIFT_SRC), str(img), str(txt)]
    else:
        cmd = [tool, str(img), str(txt)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        ok = r.returncode == 0 and txt.exists() and txt.stat().st_size > 0
        return iid, ok, "" if ok else r.stderr.decode()[:120]
    except Exception as exc:
        return iid, False, str(exc)[:120]


def main() -> None:
    t0 = time.time()
    groups = collect_groups()

    # 已下载图 vs 尚未下载
    todo: list[tuple[str, Path, set[str]]] = []
    missing = 0
    for iid, dates in groups.items():
        img = pick_image(iid, dates)
        if img is None:
            missing += 1
            continue
        todo.append((iid, img, dates))
    print(f"已有原图 {len(todo)} 张；尚未下载 {missing} 张")

    tool = build_tool()
    done = fail = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(do_ocr, i, p, tool) for i, p, _ in todo]
        for n, f in enumerate(futs, 1):
            iid, ok, err = f.result()
            if ok:
                done += 1
            else:
                fail += 1
                print(f"  [FAIL] {iid}: {err}")
            if n % 50 == 0:
                print(f"  OCR {n}/{len(todo)} | 成功 {done} 失败 {fail} | "
                      f"{(time.time()-t0)/60:.1f}min")

    # 写映射表（图 → 日期），含跨度异常标记
    out = []
    suspect = 0
    for iid, dates in sorted(groups.items()):
        ds = sorted(dates)
        span = None
        try:
            span = (_date(*map(int, ds[-1].split("-"))) - _date(*map(int, ds[0].split("-")))).days
        except Exception:
            pass
        susp = bool(span is not None and span > 30)
        if susp:
            suspect += 1
        has_txt = (OCR / f"{iid}.txt").exists()
        out.append({
            "image_id": iid,
            "date_first": ds[0], "date_last": ds[-1],
            "n_days_referenced": len(ds),
            "span_days": span,
            "suspect_span": susp,          # 同一 URL 出现在相隔 >30 天 → 需人工核对
            "dates": ds,
            "ocr_ready": has_txt,
            "ocr_text": f"data/raw/prices/jinzhou_deep/ocr/{iid}.txt" if has_txt else None,
        })
    (RAW / "image_groups.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n[OK] OCR 完成：成功 {done}，失败 {fail}，跳过(已存在) 计入成功")
    print(f"     唯一图 {len(groups)} 张；未下载 {missing} 张；跨度异常 {suspect} 张")
    print(f"     映射表 {RAW/'image_groups.json'}")
    print(f"     用时 {(time.time()-t0)/60:.1f} 分钟")


if __name__ == "__main__":
    main()
