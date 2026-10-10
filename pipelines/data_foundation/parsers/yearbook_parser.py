"""解析辽宁统计年鉴 Excel，抽取农业生产数据（数据源 C）。

流程：
  1. 解压 ZIP（修复 GBK 文件名编码）
  2. 扫描每个 Excel 的首行标题，定位「农作物播种面积」「主要农产品产量」等表
  3. 抽取地区（市）维度数据，输出 staging CSV，人工可核对

只读取官方年鉴，不做任何推算或补全；找不到就留空。
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import xlrd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "statistical_yearbooks"
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
# 年鉴中农业相关表名关键词
TABLE_KEYWORDS = re.compile(r"农作物播种面积|主要农产品产量|农作物总播种面积|粮食作物|"
                            r"水果生产|水果产量|园林水果|蔬菜|油料|农业生产条件|"
                            r"各地区.*播种面积|各地区.*产量|单位面积产量")


def fix_name(name: str) -> str:
    """ZIP 文件名以 cp437 解码，需还原为 GBK。"""
    try:
        return name.encode("cp437").decode("gbk", errors="replace")
    except Exception:
        return name


def extract_all() -> dict[str, Path]:
    out = {}
    for zf in RAW.glob("*.zip"):
        dest = RAW / zf.stem
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zf) as z:
            for info in z.infolist():
                fixed = fix_name(info.filename)
                if fixed.endswith("/"):
                    continue
                target = dest / Path(fixed).name
                # 同名文件（不同章节目录）加序号区分
                if target.exists():
                    target = dest / (Path(fixed).parent.name + "_" + Path(fixed).name)
                target.write_bytes(z.read(info))
                out[str(target)] = target
    return out


def scan_tables(files: dict[str, Path]) -> list[dict]:
    """扫描 Excel，返回命中的表（含 sheet 名、标题、行列预览）。"""
    hits = []
    for path in files.values():
        if not path.suffix.lower().endswith((".xls", ".xlsx")):
            continue
        try:
            book = xlrd.open_workbook(str(path))
        except Exception:
            continue
        for sh in book.sheets():
            if sh.nrows < 3:
                continue
            head = []
            for r in range(min(4, sh.nrows)):
                row = [str(sh.cell_value(r, c)).strip() for c in range(min(8, sh.ncols))]
                head.append(" ".join([x for x in row if x]))
            title = " | ".join([x for x in head if x])
            if TABLE_KEYWORDS.search(title):
                hits.append({
                    "file": str(path.relative_to(ROOT)),
                    "sheet": sh.name,
                    "title": title[:200],
                    "nrows": sh.nrows,
                    "ncols": sh.ncols,
                })
    return hits


def main() -> None:
    files = extract_all()
    print(f"解压文件 {len(files)} 个")
    hits = scan_tables(files)
    print(f"命中农业相关表 {len(hits)} 个")
    (STAGING / "yearbook_table_index.json").write_text(
        json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
    for h in hits[:25]:
        print(f"  {h['file'][-40:]} [{h['sheet']}] {h['title'][:90]}")


if __name__ == "__main__":
    main()
