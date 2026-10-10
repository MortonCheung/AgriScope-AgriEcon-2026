"""大连市农业农村局「12316 金农热线」农产品周报采集器（col4139 + col4141）。

=========================================================================
【站点与接口（已实测）】
  列表页（静态，仅含最新 15 条）：
      https://agri.dl.gov.cn/col/col4139/index.html   「农产品价格监测分析」
      https://agri.dl.gov.cn/col/col4141/index.html   「大连市主要农产品产地价格」
  分页接口（汉网 jpage dataproxy，页面 JS 实际调用的就是它）：
      /module/web/jpage/dataproxy.jsp?page=N&webid=26&path=https://agri.dl.gov.cn/
          &columnid={4139|4141}&unitid=29776&webname=大连市农业农村局&permissiontype=0
  注意：该接口的 page 参数**不是**常规「第 N 页」语义，单次会返回一个很大的重叠窗口
      （实测 col4139：page1~6 各返回 301/301/301/254/154/54 条，累计 1365 条，
       去重后恰为站点声明的 totalrecord=554）。
      → 因此本采集器**逐页取其并集并按文章 ID 去重**，直到某页返回 0 条；
        并校验去重结果 == 站点声明的 totalrecord，作为完整性的硬证据。

【数据载体（关键，决定解析方式）】
  col4139「一周价格涨跌」：正文为**叙述文本**（类别均价 + 增减较明显的个别品种价），
      内嵌图片均为**走势图**（每篇 13~14 张，无数据表）。
      → 批发价 / 零售价 / 产地价 的**类别均价与个别品种价**取自正文文本。
  col4141「产地价格表」：正文**为空**，价格表**整张以 PNG 图片发布**（每篇 1~2 张）。
      → 产地价**逐品种明细**必须靠图片 + OCR（见 parsers/dalian_12316_parser.py）。
  极少数 col4141 文章（2022 年前后）图片 src 为编辑器遗留的 `blob:` 伪地址，静态 HTML
      中不存在真实图片地址 → 该期无可用图片，**如实记 missing，不编造**。

【落盘】data/raw/prices/dalian_12316/
      html/{col}_{artid}.html        原始文章 HTML（原封不动）
      images/{md5}.{ext}             col4141 价格表原图（col4139 走势图不下载，见下）
      ocr/{md5}.txt                  col4141 原图的 macOS Vision OCR 文本
      article_index.json             文章索引 + 每篇图片清单/下载状态

【为什么不下载 col4139 的图片】
  col4139 内嵌图片经全量抽样确认为 Chart 走势图（粮油/肉畜/蔬菜/水产/水果 × 批发/零售/产地），
  不含表格数据，无结构化价值；若下载则约 554×13≈7200 张。仅登记其 URL 备查。

【限速】默认每请求 sleep 0.6s（0.5~2s 区间内），单线程，避免对政府站点造成压力。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "dalian_12316"
HTML_DIR = RAW / "html"
IMG_DIR = RAW / "images"
OCR_DIR = RAW / "ocr"
for _d in (HTML_DIR, IMG_DIR, OCR_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SWIFT_SRC = ROOT / "collectors" / "ocr_image.swift"
SWIFT_BIN = ROOT / "collectors" / ".ocr_image_bin"

BASE = "https://agri.dl.gov.cn"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SLEEP = float(os.environ.get("DL12316_SLEEP", "0.6"))
COLUMNS = {"4139": "农产品价格监测分析", "4141": "大连市主要农产品产地价格"}
IMAGE_COLUMNS = {"4141"}   # 仅此栏目的图片含表格数据，需下载并 OCR

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Referer": BASE + "/"})

RE_RECORD = re.compile(r"<record><!\[CDATA\[(.*?)\]\]></record>", re.S)
RE_HREF = re.compile(r'href="([^"]*art_(\d+)_(\d+)\.html)"', re.I)
RE_TITLE = re.compile(r'title="([^"]*)"', re.I)
RE_DATE = re.compile(r"\[(\d{4}-\d{2}-\d{2})\]")
RE_IMG = re.compile(r'<img[^>]*?src="([^"]+\.(?:png|jpg|jpeg|gif))"', re.I)
RE_TOTAL = re.compile(r"<totalrecord>(\d+)</totalrecord>", re.I)


def http_get(url: str, tries: int = 3, timeout: int = 40) -> str | None:
    """复用 Session 的连接（实测比每次新建连接快 10 倍以上）。"""
    for a in range(tries):
        try:
            r = SESSION.get(url, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r.content.decode("utf-8", "replace")
        except Exception:
            time.sleep(1.2 * (a + 1))
    return None


def http_get_bytes(url: str, tries: int = 3, timeout: int = 60) -> bytes | None:
    for a in range(tries):
        try:
            r = SESSION.get(url, timeout=timeout, verify=False)
            if r.status_code == 200:
                return r.content
        except Exception:
            time.sleep(1.2 * (a + 1))
    return None


def dataproxy_url(col: str, page: int) -> str:
    q = urllib.parse.urlencode({
        "page": page, "webid": "26", "path": BASE + "/", "columnid": col,
        "unitid": "29776", "webname": "大连市农业农村局", "permissiontype": "0",
    })
    return f"{BASE}/module/web/jpage/dataproxy.jsp?{q}"


def harvest(col: str) -> tuple[list[dict], int]:
    """翻页取并集并按文章 ID 去重。返回 (文章列表, 站点声明总数)。"""
    seen: dict[str, dict] = {}
    declared = 0
    for page in range(1, 41):
        t = http_get(dataproxy_url(col, page))
        if not t:
            print(f"  [WARN] col{col} page={page} 拉取失败")
            break
        if not declared:
            m = RE_TOTAL.search(t)
            declared = int(m.group(1)) if m else 0
        recs = RE_RECORD.findall(t)
        if not recs:
            break
        for rec in recs:
            h = RE_HREF.search(rec)
            if not h:
                continue
            url, artid = h.group(1), h.group(3)
            if not url.startswith("http"):
                url = BASE + url
            tm = RE_TITLE.search(rec)
            dm = RE_DATE.search(rec)
            seen[artid] = {
                "column": col,
                "article_id": artid,
                "date": dm.group(1) if dm else "",
                "title": (tm.group(1).strip() if tm else ""),
                "url": url,
            }
        time.sleep(SLEEP)
    arts = sorted(seen.values(), key=lambda r: r["date"])
    return arts, declared


def content_html(t: str) -> str:
    m = re.search(r"ContentStart(.*?)ContentEnd", t, re.S)
    return m.group(1) if m else ""


def abs_img(src: str) -> str | None:
    if src.startswith("blob:"):
        return None
    if src.startswith("http"):
        return src
    if src.startswith("/"):
        return BASE + src
    return BASE + "/" + src


def build_ocr_tool() -> str:
    if SWIFT_BIN.exists() and SWIFT_BIN.stat().st_mtime > SWIFT_SRC.stat().st_mtime:
        return str(SWIFT_BIN)
    try:
        r = subprocess.run(["swiftc", "-O", str(SWIFT_SRC), "-o", str(SWIFT_BIN)],
                           capture_output=True, timeout=300)
        if r.returncode == 0 and SWIFT_BIN.exists():
            return str(SWIFT_BIN)
    except Exception:
        pass
    return "swift"


def _ocr_one(src: Path, dst: Path, tool: str) -> bool:
    cmd = ["swift", str(SWIFT_SRC), str(src), str(dst)] if tool == "swift" else [tool, str(src), str(dst)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False


def ocr(img: Path, out: Path, tool: str) -> bool:
    """OCR 单张图。

    重要：col4141 早期（约 2018-2022）的价格表是**很窄很长的明细库表**
    （如 942×8544px，含「序号/产品名称/价格/价格单位/价格类型/价格区域/价格时间」）。
    直接整图 OCR 时 macOS Vision 只会识别出 1~2 个文本块（实测失败）。
    因此对高度 > 2000px 的图**纵向切片（1200px 步长 + 150px 重叠）后再逐片 OCR 拼接**，
    实测每片均能正常识别（且重叠可避免跨片行被截断丢失）。
    """
    if out.exists() and out.stat().st_size > 0:
        n_lines = len([x for x in out.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()])
        tall = False
        try:
            from PIL import Image
            with Image.open(img) as im:
                tall = im.size[1] > 2000
        except Exception:
            pass
        if not tall or n_lines >= 3:      # 长图若只识别出 1~2 行，视为失败需重做
            return True
    try:
        from PIL import Image
        with Image.open(img) as im:
            w, h = im.size
            if h > 2000:
                tmp = Path(tempfile.mkdtemp(prefix="dl12316_slice_"))
                parts, step, ov = [], 1200, 150
                y = 0
                idx = 0
                while y < h and idx < 60:
                    im.crop((0, y, w, min(h, y + step + ov))).save(tmp / f"s{idx}.png")
                    o = tmp / f"s{idx}.txt"
                    if _ocr_one(tmp / f"s{idx}.png", o, tool):
                        parts.append(o.read_text(encoding="utf-8", errors="replace"))
                    y += step
                    idx += 1
                out.write_text("\n".join(parts), encoding="utf-8")
                shutil.rmtree(tmp, ignore_errors=True)
                return out.exists() and out.stat().st_size > 0
    except Exception:
        pass
    return _ocr_one(img, out, tool)


def main() -> None:
    t0 = time.time()
    index: dict[str, dict] = {}
    idx_file = RAW / "article_index.json"
    if idx_file.exists():
        for r in json.loads(idx_file.read_text(encoding="utf-8")):
            index[r["url"]] = r

    for col, colname in COLUMNS.items():
        print(f"\n=== col{col} {colname} ===")
        arts, declared = harvest(col)
        print(f"  去重文章 {len(arts)} 篇；站点声明 totalrecord={declared}"
              f"{'  [完整]' if declared and len(arts) == declared else '  [不一致]'}")
        for n, a in enumerate(arts, 1):
            key = a["url"]
            rec = index.get(key, {})
            rec.update(a)
            rec["column_name"] = colname
            hf = HTML_DIR / f"{col}_{a['article_id']}.html"
            if not hf.exists():
                t = http_get(a["url"])
                if t is None:
                    rec["html"] = None
                    rec["html_error"] = "fetch_failed"
                    index[key] = rec
                    continue
                hf.write_text(t, encoding="utf-8")
                time.sleep(SLEEP)
            rec["html"] = str(hf.relative_to(ROOT))
            t = hf.read_text(encoding="utf-8", errors="replace")
            rec["content_chars"] = len(re.sub(r"<[^>]+>", "", content_html(t)))

            imgs = []
            for src in RE_IMG.findall(content_html(t)):
                u = abs_img(src)
                if u is None:
                    imgs.append({"src": src, "file": None, "status": "missing_blob_src"})
                    continue
                ext = u.rsplit(".", 1)[-1].lower()
                iid = hashlib.md5(u.encode()).hexdigest()[:16]
                f = IMG_DIR / f"{iid}.{ext}"
                item = {"src": u, "image_id": iid}
                if col in IMAGE_COLUMNS:
                    if not f.exists():
                        b = http_get_bytes(u)
                        if b is None:
                            item["status"] = "download_failed"
                            imgs.append(item)
                            continue
                        f.write_bytes(b)
                        time.sleep(SLEEP)
                    item["file"] = str(f.relative_to(ROOT))
                    item["status"] = "ok"
                else:
                    item["status"] = "skipped_chart"
                imgs.append(item)
            rec["images"] = imgs
            index[key] = rec
            if n % 40 == 0:
                print(f"  进度 {n}/{len(arts)} | {(time.time()-t0)/60:.1f}min")

    # ---- OCR col4141 图片 ----
    tool = build_ocr_tool()
    todo = [(im["image_id"], ROOT / im["file"]) for r in index.values()
            for im in r.get("images", []) if im.get("file")]
    seen_iid, uniq = set(), []
    for iid, f in todo:
        if iid in seen_iid:
            continue
        seen_iid.add(iid)
        uniq.append((iid, f))
    print(f"\n=== OCR col4141 唯一图 {len(uniq)} 张（工具 {Path(tool).name}）===")
    ok = fail = 0
    # OCR 为本地计算（非网络请求），用线程池并行；网络限速不受影响。
    workers = int(os.environ.get("DL12316_OCR_WORKERS", "4"))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(ocr, f, OCR_DIR / f"{iid}.txt", tool): iid for iid, f in uniq}
        for n, fut in enumerate(as_completed(futs), 1):
            iid = futs[fut]
            if fut.result():
                ok += 1
            else:
                fail += 1
                print(f"  [OCR FAIL] {iid}")
            if n % 100 == 0:
                print(f"  OCR {n}/{len(uniq)} 成功 {ok} 失败 {fail} | {(time.time()-t0)/60:.1f}min")

    idx_file.write_text(json.dumps(sorted(index.values(), key=lambda r: (r["column"], r["date"])),
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    n_html = sum(1 for r in index.values() if r.get("html"))
    n_img = sum(1 for r in index.values() for im in r.get("images", []) if im.get("file"))
    print(f"\n[OK] 文章 {len(index)} 篇（已落盘 HTML {n_html}）")
    print(f"     col4141 图片 {n_img} 张；OCR 成功 {ok} 失败 {fail}")
    print(f"     索引 {idx_file.relative_to(ROOT)}")
    print(f"     用时 {(time.time()-t0)/60:.1f} 分钟")


if __name__ == "__main__":
    main()
