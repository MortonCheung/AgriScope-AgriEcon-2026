"""按需抓取大仓库的目标文件（GitHub API）。

背景：本机 git 直连 github.com 失败，但 `gh api` 可用；且磁盘有限，
故对大仓库（scientific-agent-skills / AI-Scientist / zotero）只抓取
「研究所需的目标路径」，不做全量解压。

用法：
  python _fetch_selected.py            # 抓取全部目标
  python _fetch_selected.py --list     # 只列出匹配到的文件
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (owner/repo, 本地目录, 目标路径正则列表)
TARGETS = [
    ("K-Dense-AI/scientific-agent-skills", "scientific-agent-skills", [
        r"^skills/(statistical-analysis|scientific-writing|scientific-critical-thinking|"
        r"peer-review|scholar-evaluation|research-lookup|literature-review)/.*$",
        r"^README\.md$", r"^LICENSE.*$", r"^AGENTS\.md$",
    ]),
    ("SakanaAI/AI-Scientist", "AI-Scientist", [
        r"^ai_scientist/.*$", r"^docs/.*$", r"^templates/.*\.md$",
        r"^README\.md$", r"^launch_scientist.*\.py$", r"^SECURITY\.md$",
        r"^LICENSE.*$", r"^pyproject\.toml$", r"^setup\.py$",
    ]),
    ("zotero/zotero", "zotero", [
        r"^chrome/content/zotero/xpcom/data/item\.js$",
        r"^chrome/content/zotero/xpcom/data/itemFields\.js$",
        r"^chrome/content/zotero/xpcom/data/creator\.js$",
        r"^chrome/content/zotero/xpcom/data/collection\.js$",
        r"^chrome/content/zotero/xpcom/data/attachment\.js$",
        r"^chrome/content/zotero/xpcom/data/dataObjects\.js$",
        r"^chrome/content/zotero/xpcom/data/cachedTypes\.js$",
        r"^chrome/content/zotero/xpcom/data/dataObjectUtilities\.js$",
        r"^chrome/content/zotero/xpcom/translation/.*$",
        r"^chrome/locale/en-US/zotero/zotero\.properties$",
        r"^chrome/content/zotero/xpcom/utilities_item\.js$",
        r"^README\.md$", r"^LICENSE.*$",
    ]),
]


def gh(args: list) -> str:
    r = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} -> {r.returncode}: {r.stderr[:200]}")
    return r.stdout


def tree(repo: str, branch: str = "main") -> list:
    out = gh(["api", f"repos/{repo}/git/trees/{branch}?recursive=1",
              "--jq", r'.tree[]|select(.type=="blob")|.path'])
    return [p for p in out.splitlines() if p]


def fetch_file(repo: str, path: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        b64 = gh(["api", f"repos/{repo}/contents/{path}", "--jq", ".content"]).strip()
        data = base64.b64decode(b64.replace("\n", ""))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"   [FAIL] {path}: {exc}")
        return False


def main() -> None:
    list_only = "--list" in sys.argv
    total = 0
    for repo, name, pats in TARGETS:
        print(f"\n=== {name} ({repo}) ===")
        try:
            paths = tree(repo)
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] 无法获取树：{exc}")
            continue
        import re
        sel = [p for p in paths if any(re.match(pat, p) for pat in pats)]
        print(f"  树内 {len(paths)} 文件 → 命中 {len(sel)}")
        if list_only:
            for p in sel[:80]:
                print("   ", p)
            continue
        ok = 0
        for p in sel:
            dest = HERE / name / p
            if fetch_file(repo, p, dest):
                ok += 1
        print(f"  已抓取 {ok}/{len(sel)}")
        total += ok
    print(f"\n合计抓取 {total} 个文件")
    for _, name, _ in TARGETS:
        d = HERE / name
        if d.exists():
            n = sum(1 for _ in d.rglob("*") if _.is_file())
            print(f"  {name}: {n} 文件")


if __name__ == "__main__":
    main()
