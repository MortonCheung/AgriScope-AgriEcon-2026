#!/usr/bin/env python3
"""构建源码+必需资产+已构建前端的部署包，明确排除secret/cache/raw全集。"""
import argparse
import json
import subprocess
import tarfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="rc3", help="发布标签，用于输出目录与包名，如 rc3")
    args = parser.parse_args()
    label = args.label.strip() or "rc3"
    out_dir = ROOT / f"output/{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    manifest = json.loads((ROOT / 'runtime/manifest.json').read_text())
    paths = set(p for p in tracked if p)
    paths.update(a['path'] for a in manifest['assets'] if a.get('required', True))
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'frontend/dist').rglob('*') if p.is_file())
    forbidden = [p for p in paths if Path(p).name == '.env' or any(x in p for x in ['node_modules/', 'llm/artifacts/'])]
    if forbidden:
        raise RuntimeError('Forbidden files in bundle: ' + str(forbidden))
    missing = [p for p in paths if not (ROOT / p).is_file()]
    if missing:
        raise RuntimeError('Missing bundle files: ' + str(missing[:10]))
    out = out_dir / f'agriscope-{label}-deploy.tar.gz'
    with tarfile.open(out, 'w:gz') as tf:
        for p in sorted(paths):
            tf.add(ROOT / p, arcname=p, recursive=False)
    print(json.dumps({'bundle': str(out), 'files': len(paths), 'bytes': out.stat().st_size}))


if __name__ == '__main__':
    main()
