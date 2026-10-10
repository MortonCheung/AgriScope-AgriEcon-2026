#!/usr/bin/env bash
# AgriScope v1.0 · 一键全量测试（不训练、不部署）
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"       # AgriScope（产品仓）
PROJECT="$(cd "$ROOT/.." && pwd)"             # monorepo 根（研发态 data/ 与 models/）
cd "$ROOT"
export PYTHONPATH="$ROOT/pipelines/modeling/src:$ROOT/pipelines/modeling:$ROOT/pipelines/modeling/tests:$ROOT/pipelines:$ROOT"
FAIL=0
step() { echo; echo "===== $1 ====="; }

step "1/6 Frontend (typecheck + tests + build + verify)"
( cd frontend && npm run typecheck && npm test && npm run build ) || FAIL=1

step "2/6 Backend (acceptance + E2E)"
python3 backend/scripts/acceptance.py || FAIL=1

step "3/6 Final Model"
python3 scripts/check_final_freeze.py || FAIL=1
PROJECT_ROOT="$PROJECT" python3 pipelines/modeling/scripts/check_acceptance_final.py || FAIL=1

step "4/6 Daily"
PROJECT_ROOT="$PROJECT" python3 pipelines/daily/acceptance.py || FAIL=1

step "5/6 Long-Horizon（一致性门禁，不训练）"
python3 scripts/verify_long_horizon.py || FAIL=1

step "6/6 全层 Python 回归 + 独立指标重算（不训练）"
# Backend 单独进程：产品只读 runtime/models/src；避免与 pipelines/modeling/src 同名包互相污染。
python3 -m pytest backend/tests -q || FAIL=1
PROJECT_ROOT="$PROJECT" python3 -m pytest pipelines/long_horizon/tests tests --import-mode=importlib -q || FAIL=1
PROJECT_ROOT="$ROOT/runtime" python3 -m pytest pipelines/modeling/tests --import-mode=importlib -q || FAIL=1
PROJECT_ROOT="$PROJECT" python3 -m pytest llm/tests -q || FAIL=1
PROJECT_ROOT="$PROJECT" python3 -m pytest pipelines/daily/tests -q || FAIL=1
python3 scripts/independent_recalculate_v2.py || FAIL=1
python3 scripts/verify_assets.py || FAIL=1

echo
if [ "$FAIL" -eq 0 ]; then echo "ALL_TESTS_PASS"; else echo "TESTS_FAILED"; fi
exit "$FAIL"
