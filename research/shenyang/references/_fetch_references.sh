#!/usr/bin/env bash
# 参考项目获取（research_v2 第一阶段）
#
# 施工手册 §2 要求使用 `gh repo clone ... --depth 1 --filter=blob:none`。
# 本机实测：git 直连 github.com 失败（Empty reply from server，沙箱网络限制），
# 但 `gh api`（api.github.com，已认证）可用。
#
# 因此采用等价替代：`gh api repos/OWNER/REPO/tarball/BRANCH` 下载工作树 tarball，
# 再选择性解压。与 --depth 1 --filter=blob:none 同效：**只取最新工作树，不含历史**，
# 且对大仓库选择性解压以节省磁盘（本机剩余空间有限）。
#
# 不安装、不运行任何参考项目；仅阅读其代码与文档。

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="${TMPDIR:-/tmp}/refproj_tarballs"
mkdir -p "$TMP" "$HERE"

fetch() {  # $1=owner/repo  $2=local name  $3=branch
  local repo="$1" name="$2" br="${3:-main}"
  local tgz="$TMP/${name}.tar.gz"
  if [ -f "$tgz" ] && [ -s "$tgz" ]; then
    echo "[SKIP] $name tarball 已存在"
  else
    echo "[GET ] $repo@$br"
    gh api "repos/$repo/tarball/$br" > "$tgz" || { echo "[FAIL] $repo"; return 1; }
  fi
  echo "       $(du -h "$tgz" | cut -f1)"
}

# 1) 全量解压（体积小）
fetch stanford-oval/storm storm main
fetch assafelovic/gpt-researcher gpt-researcher main
fetch Future-House/paper-qa paper-qa main

# 2) 选择性解压（体积大）
fetch K-Dense-AI/scientific-agent-skills scientific-agent-skills main
fetch SakanaAI/AI-Scientist AI-Scientist main
fetch zotero/zotero zotero main

extract_all() { # $1=name
  local name="$1" tgz="$TMP/$1.tar.gz"
  [ -d "$HERE/$name" ] && { echo "[skip] $name 已解压"; return; }
  mkdir -p "$HERE/$name"
  tar xzf "$tgz" -C "$HERE/$name" --strip-components=1 && echo "[OK  ] $name 全量解压"
}

extract_sel() { # $1=name  其余=相对路径模式
  local name="$1"; shift
  local tgz="$TMP/$name.tar.gz"
  [ -d "$HERE/$name" ] && { echo "[skip] $name 已解压"; return; }
  mkdir -p "$HERE/$name"
  local first
  first="$(tar tzf "$tgz" | head -n1 | cut -d/ -f1)"
  tar xzf "$tgz" -C "$HERE/$name" --strip-components=1 --wildcards "$@" 2>/dev/null \
    && echo "[OK  ] $name 选择性解压：$*"
}

extract_all storm
extract_all gpt-researcher
extract_all paper-qa

# scientific-agent-skills：只取 skills/ 与顶层说明
extract_sel scientific-agent-skills "*/skills/*" "*/README.md" "*/LICENSE*"

# AI-Scientist：取源码与文档，跳过 notebook / 大数据
extract_sel AI-Scientist "*/ai_scientist/*" "*/templates/*" "*/docs/*" "*/README.md" \
  "*/pyproject.toml" "*/setup.py" "*/SECURITY.md" "*/LICENSE*" "*/launch_scientist*.py" \
  "*/run.sh" "*/experimental/*"

# zotero：只取「条目元数据 / 字段 schema / 导出格式」相关源码
extract_sel zotero \
  "*/chrome/content/zotero/xpcom/data/*" \
  "*/chrome/content/zotero/xpcom/*.js" \
  "*/chrome/locale/en-US/zotero/zotero.properties" \
  "*/chrome/content/zotero/xpcom/translation/*" \
  "*/README.md" "*/LICENSE*"

echo
echo "=== 结果 ==="
du -sh "$HERE"/* 2>/dev/null
echo "=== 磁盘 ==="
df -h /Users/morton_cheung | tail -n 1
