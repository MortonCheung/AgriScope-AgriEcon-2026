#!/usr/bin/env python3
"""扫描当前Git发布候选文件；只输出文件位置，绝不打印疑似凭据值。"""
import json
import re
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    patterns=[re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
              re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}'),
              re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
              re.compile(rb'\bAKIA[0-9A-Z]{16}\b')]
    suspect,large,forbidden=[],[],[]
    for name in sorted(set(paths)):
        if not name:continue
        p=ROOT/name
        if not p.is_file():continue
        if p.name in ['.env','.netrc','credentials.json'] or p.name.endswith(('.pem','.key')):
            forbidden.append(name)
        if p.stat().st_size>10*1024*1024:large.append({'path':name,'size':p.stat().st_size})
        blob=p.read_bytes()
        if any(pattern.search(blob) for pattern in patterns):suspect.append(name)
    report={'status':'RELEASE_FILE_AUDIT_PASS' if not (suspect or large or forbidden) else 'FAIL',
            'files_checked':len(set(paths)-{''}),'secret_suspect_files':suspect,'forbidden_files':forbidden,
            'large_files_over_10MiB':large,'values_printed':False,
            'scope':'Git tracked and nonignored new files; pattern-based scan, not a proof no unknown secret exists'}
    (ROOT/'RC2_RELEASE_FILE_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
    return int(report['status']=='FAIL')


if __name__=='__main__':raise SystemExit(main())
