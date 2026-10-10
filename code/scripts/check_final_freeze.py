#!/usr/bin/env python3
"""核对施工前 173 个 Final 源码、报告、模型资产，以及实时计算的代码指纹。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_final_freeze(root=ROOT):
    baseline = json.loads((root / 'runtime/final_frozen_baseline.json').read_text())
    changed = [p for p, expected in baseline['files'].items()
               if not (root / p).is_file() or hashlib.sha256((root / p).read_bytes()).hexdigest() != expected]
    fingerprint = hashlib.sha256()
    for path in sorted((root / 'runtime/models/src').rglob('*.py')):
        fingerprint.update(path.name.encode())
        fingerprint.update(path.read_bytes())
    live = fingerprint.hexdigest()[:16]
    meta = json.loads((root / 'runtime/models/reports/final/FINAL_RUN_META.json').read_text())
    if changed or live != baseline['code_fingerprint'] or live != meta['code_fingerprint']:
        raise RuntimeError('Final frozen drift: ' + json.dumps({'changed': changed, 'live_fingerprint': live}))
    result = {'status': 'FINAL_FREEZE_UNCHANGED', 'files_checked': len(baseline['files']), 'code_fingerprint': live}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    check_final_freeze()
