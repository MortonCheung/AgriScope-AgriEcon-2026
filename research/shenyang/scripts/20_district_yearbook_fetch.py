"""STEP D1 — 沈阳区县农业生产数据：年鉴原始件采集（Phase 「数据补充」）。

任务范围（严格）：
  只补齐 **沈阳市各区县农业生产数据 + 可对应的区县天气数据**。
  不做前端、不做市场分析重跑、不做新研究方向。

本脚本职责（仅采集，不解析）：
  1. 从沈阳市统计局「年度数据」栏目下载《沈阳统计年鉴》各卷 PDF；
     年鉴农业章含 3-4 农作物播种面积 / 3-5 农作物总产量 / 3-6 农作物单产量，
     三张表均为「行=作物、列=地区（沈阳市+8 个农业区县）」结构——本项目的区县生产主源。
  2. 原始 PDF 落盘 data/raw/district_production/yearbooks/；
  3. 写出 source_registry（可追溯：每个数字能查回哪一卷哪一表）。

红线：
  - 只下载官方（沈阳市统计局 tjj.shenyang.gov.cn）公开文件；
  - 不绕过任何登录/验证；失败就记录 FAIL，不伪造；
  - 原始文件不改写；文件名统一 SY_yearbook_{卷年}_data{数据年}.pdf。

产出：
  data/raw/district_production/yearbooks/SY_yearbook_*.pdf
  data/raw/district_production/source_registry.csv
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, PROJECT_ROOT, StepTimer, get_logger  # noqa: E402

MOD = "20_district_yearbook_fetch"
LOG = get_logger(MOD)

RAW_DIR = PATHS.project["data_raw_district"]      # data/raw/district_production
YB_DIR = RAW_DIR / "yearbooks"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 沈阳市统计局「年度数据」各卷落地页（卷年 → (数据年, 落地页)）
# 来源：https://tjj.shenyang.gov.cn/sjfb/ndsj/（2026-09 实测）
YB_INDEX = "https://tjj.shenyang.gov.cn/sjfb/ndsj/"
YB_PAGES = {
    2025: (2024, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202512/P020260119354584380580.pdf"),
    2024: (2023, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202412/t20241205_4771796.html"),
    2023: (2022, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202412/t20241205_4771795.html"),
    2022: (2021, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202412/t20241205_4771793.html"),
    2021: (2020, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202412/t20241205_4771792.html"),
    2020: (2019, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202412/t20241205_4771790.html"),
    2019: (2018, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202412/t20241205_4771788.html"),
    2018: (2017, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202207/t20220711_3408703.html"),
    2017: (2016, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202207/t20220711_3410812.html"),
    2016: (2015, "https://tjj.shenyang.gov.cn/sjfb/ndsj/202207/t20220711_3410887.html"),
}


def get(url: str, binary: bool = False, timeout: int = 180, retries: int = 3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (attempt + 1))
    raise last


def find_pdf_links(html: str, base: str) -> list:
    """从落地页 HTML 中提取 PDF 直链。"""
    links = re.findall(r'href="([^"]+\.pdf)"', html, flags=re.I)
    out = []
    for l in links:
        if l.startswith("http"):
            out.append(l)
        elif l.startswith("/"):
            m = re.match(r"(https?://[^/]+)", base)
            out.append(m.group(1) + l)
        else:
            out.append(base.rsplit("/", 1)[0] + "/" + l)
    return out


def title_of(pdf: Path) -> str:
    import fitz
    try:
        d = fitz.open(str(pdf))
        t = d[0].get_text().replace("\n", " ").strip()
        return t[:80]
    except Exception:  # noqa: BLE001
        return ""


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        YB_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        registry = []
        for vol, (dyear, page) in sorted(YB_PAGES.items(), reverse=True):
            out = YB_DIR / f"SY_yearbook_{vol}_data{dyear}.pdf"
            src_url = page
            if out.exists():
                log.info("[SKIP] 已存在 %s", out.name)
            else:
                try:
                    if page.lower().endswith(".pdf"):
                        pdf_url = page
                    else:
                        html = get(page)
                        pdfs = find_pdf_links(html, page)
                        if not pdfs:
                            log.warning("[FAIL] 卷 %d 落地页无 PDF 直链：%s", vol, page)
                            continue
                        pdf_url = pdfs[0]
                    blob = get(pdf_url, binary=True)
                    out.write_bytes(blob)
                    src_url = pdf_url
                    log.info("[OK] 年鉴 %d 卷（数据年 %d）→ %s（%.1f MB）",
                             vol, dyear, out.name, len(blob) / 1e6)
                except Exception as exc:  # noqa: BLE001
                    log.warning("[FAIL] 年鉴 %d 卷下载失败：%s", vol, exc)
                    continue
            registry.append({
                "source_id": f"SY-YB-{vol}",
                "title": f"《沈阳统计年鉴》{vol}（数据年份 {dyear}）",
                "publisher": "沈阳市统计局 / 国家统计局沈阳调查队",
                "year": vol,
                "data_year": dyear,
                "url": src_url,
                "local_file": str(out.relative_to(PROJECT_ROOT)),
                "data_type": "statistical_yearbook",
                "districts": "沈阳市+苏家屯区/浑南区/沈北新区/于洪区/辽中区/康平县/法库县/新民市",
                "crops": "粮食/谷物/稻谷/小麦/玉米/豆类/大豆/薯类/油料/花生/蔬菜及食用菌/瓜果等",
                "original_unit": "面积=公顷；产量=吨；单产=公斤/公顷",
                "source_grade": "A",
                "accessed_at": pd_Timestamp(),
                "notes": f"农业章 3-4/3-5/3-6 三表含分区县明细；卷首页={title_of(out)}",
            })

        reg = _load_registry()
        for r in registry:
            reg[r["source_id"]] = r
        _save_registry(reg)
        log.info("source_registry 累计 %d 条", len(reg))


def pd_Timestamp() -> str:
    import pandas as pd
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_registry() -> dict:
    p = RAW_DIR / "source_registry.csv"
    if not p.exists():
        return {}
    import pandas as pd
    d = pd.read_csv(p).fillna("")
    return {r["source_id"]: r.to_dict() for _, r in d.iterrows()}


def _save_registry(reg: dict) -> None:
    import pandas as pd
    cols = ["source_id", "title", "publisher", "year", "data_year", "url", "local_file",
            "data_type", "districts", "crops", "original_unit", "source_grade",
            "accessed_at", "notes"]
    d = pd.DataFrame(list(reg.values()))
    for c in cols:
        if c not in d.columns:
            d[c] = ""
    d = d[cols].sort_values("source_id")
    d.to_csv(RAW_DIR / "source_registry.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
