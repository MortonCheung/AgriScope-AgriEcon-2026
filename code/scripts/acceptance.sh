#!/usr/bin/env bash
# AgriScope v1.0 · 一键正式验收（只读校验 + 各层验收；禁止训练）
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"       # AgriScope（产品仓）
PROJECT="$(cd "$ROOT/.." && pwd)"             # monorepo 根（研发态 data/ 与 models/）
cd "$ROOT"
export PYTHONPATH="$ROOT/pipelines/modeling/src:$ROOT/pipelines/modeling:$ROOT/pipelines/modeling/tests:$ROOT/pipelines:$ROOT"
FAIL=0

echo "===== 0. 运行时资产清单校验 ====="
python3 scripts/verify_assets.py || FAIL=1

echo; echo "===== 1. Backend 正式验收 ====="
python3 backend/scripts/acceptance.py || FAIL=1

echo; echo "===== 2. Final Model 验收 ====="
python3 scripts/check_final_freeze.py || FAIL=1
PROJECT_ROOT="$PROJECT" python3 pipelines/modeling/scripts/check_acceptance_final.py || FAIL=1

echo; echo "===== 3. Daily 验收 ====="
PROJECT_ROOT="$PROJECT" python3 pipelines/daily/acceptance.py || FAIL=1

echo; echo "===== 4. Long-Horizon 一致性门禁 ====="
python3 scripts/verify_long_horizon.py || FAIL=1

echo "===== 5. 长期/LLM/运行时/契约边界测试 ====="
# Backend 单独进程：产品只读 runtime/models/src；避免与 pipelines/modeling/src 同名包互相污染。
python3 -m pytest backend/tests -q || FAIL=1
PROJECT_ROOT="$PROJECT" python3 -m pytest pipelines/long_horizon/tests tests --import-mode=importlib -q || FAIL=1
PROJECT_ROOT="$ROOT/runtime" python3 -m pytest pipelines/modeling/tests --import-mode=importlib -q || FAIL=1
PROJECT_ROOT="$PROJECT" python3 -m pytest llm/tests -q || FAIL=1
python3 scripts/independent_recalculate_v2.py || FAIL=1

echo
if [ "$FAIL" -eq 0 ]; then echo "ACCEPTANCE_PASS"; else echo "ACCEPTANCE_FAILED"; fi
exit "$FAIL"
