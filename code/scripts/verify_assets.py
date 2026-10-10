#!/usr/bin/env python3
"""运行时资产清单校验（适配 publishing 生成的新 manifest 结构）。

manifest 由 `AgriScope/pipelines/publishing/publish_runtime.py` 生成，结构：
    {"generated_at", "publisher", "note", "assets": [{"source","destination","description","status"}]}
本脚本校验：每个 asset 的 status 为**成功态**且 destination 在 AgriScope 内实际存在且非空。

成功态词表（与 publishing 的返回值一致）：
    `OK`                        —— copy_item 直接复制成功
    `PUBLISHED(<asset_type>)`   —— 由另一条发布脚本（如 publish_research.py）落地的产品件
失败态（`SKIP(...)` 等）一律计为问题。
不写入、不改动任何资产（--refresh 仅保留兼容参数位，当前无副作用）。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'runtime/manifest.json'

# 成功态前缀；SKIP(missing-src) 等不在其中，仍然会失败。
OK_STATUS_PREFIXES = ('OK', 'PUBLISHED')


def _is_ok_status(status) -> bool:
    return isinstance(status, str) and status.startswith(OK_STATUS_PREFIXES)


def _nonempty(p: Path) -> bool:
    if p.is_file():
        return p.stat().st_size > 0
    if p.is_dir():
        return any(p.iterdir())
    return False


def verify(man, root=ROOT, refresh=False):
    problems, ok = [], 0
    assets = man.get('assets', [])
    if not assets:
        problems.append('manifest has no assets')
    seen = set()
    for asset in assets:
        dest = asset.get('destination', '')
        status = asset.get('status')
        if not dest or dest in seen:
            problems.append(f'invalid/duplicate destination: {dest}')
            continue
        seen.add(dest)
        p = (root / dest).resolve()
        if not p.is_relative_to(root.resolve()):
            problems.append(f'destination escapes AgriScope: {dest}')
            continue
        if not _is_ok_status(status):
            problems.append(f'source unavailable -> {dest} (status={status!r}, source={asset.get("source")})')
            continue
        if not _nonempty(p):
            problems.append(f'missing/empty destination: {dest}')
            continue
        ok += 1
    return {'ok': ok, 'total': len(assets), 'problems': problems,
            'generated_at': man.get('generated_at'), 'publisher': man.get('publisher')}


def main(argv=None):
    refresh = '--refresh' in (sys.argv[1:] if argv is None else argv)
    man = json.loads(MANIFEST.read_text())
    result = verify(man, refresh=refresh)
    print(json.dumps(result, ensure_ascii=False))
    print('ASSETS_VERIFY_FAILED' if result['problems'] else 'ASSETS_VERIFY_OK')
    return 1 if result['problems'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
