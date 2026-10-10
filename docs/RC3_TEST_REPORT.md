# AgriScope RC3 测试报告

生成时间：2026-10-08（Asia/Shanghai）
执行命令：`./scripts/test_all.sh`（不训练、不部署）
环境：`PROJECT_ROOT=$PWD`，`PYTHONPATH=$PWD/models/src:$PWD/models:$PWD/models/tests:$PWD`

## 1. 结论

**代码级测试全绿**；唯一失败项是**资产哈希门禁**，原因是本轮 RC3 修改了 11 个源码文件，
而 `runtime/manifest.json` 仍记录 RC2 冻结哈希。该门禁在发布前需重冻结一次，**不是代码缺陷**。

| 层 | 结果 |
|---|---|
| 前端 typecheck | PASS |
| 前端单测 | **322 passed / 32 files** |
| 前端构建 | PASS（`vite build`，产物写入 `frontend/dist`） |
| 前端生产边界检查 | `Production boundary PASS (formal API / unavailable)` |
| Backend 验收 | **19/19 通过**，状态 `BACKEND_FROZEN` |
| Backend 契约 pytest | 52 passed |
| Final Model 冻结 | `FINAL_FREEZE_UNCHANGED`，173 文件，指纹 `b19b187268ee92db` |
| Final 验收 | **38/38 passed** |
| Daily 验收 | PASS（`dry_run=False`，`n_evaluated=10`，`fallback=False`） |
| Daily 测试 | 84 passed |
| Long-Horizon 一致性门禁 | `LONG_HORIZON_V2_ENGINEERING_ACCEPTANCE_PASS`，registry 120 行 |
| 全层 Python 回归 | **168 passed**（104.03s，4 个 pandas 弃用告警，无失败） |
| 独立指标重算 | `INDEPENDENT_RECALCULATION_PASS`，586,000 行 / 3,840 组，最大偏差 ≈2.8e-14 |
| 资产校验 | **`ASSETS_VERIFY_FAILED`**（707/722 ok，见第 2 节） |

## 2. 唯一失败项：资产哈希门禁

`scripts/verify_assets.py` 报告：

```
ok=707 / total=722
problems（hash/size mismatch）:
  backend/app/main.py, deploy/README.md, llm/common.py, llm/context/leakage.py,
  llm/context/packet.py, llm/evaluation/harness.py, llm/evaluation/v2.py,
  llm/providers/openai_compat.py, llm/run_real_pilot.py,
  llm/tests/test_hardening_v2.py, scripts/build_deploy_bundle.py
generated_drift（生成数据的正常漂移）:
  data/processed/daily/logs/run_2026-10-06.log,
  data/processed/daily/monitor/status.json,
  data/processed/daily/normalize_report.json,
  data/processed/daily/snapshots/daily/2026-10-06.json
optional_missing: []
```

**判定**：11 个 mismatch 与 RC3 实际改动文件**一一对应**，属预期变更；
`generated_drift` 是 Daily 每日运行的生成物，属正常时序漂移。

**处置（发布步骤，未执行）**：运行 `scripts/freeze_runtime_manifest.py` 重冻结
`runtime/manifest.json`。RC2 的历史哈希与结论保留在 `RC2_FREEZE_GATE.md`，**不会被改写**。

## 3. 本轮 RC3 新增/变更的测试覆盖

- `llm/tests`：21 passed（含并发改造后的回归）。
- 串行 vs 并发等价性：以 fake provider 对同一 config 分别跑 `concurrency=1` 与 `concurrency=3`，
  行数、顺序、anchor、`api_called` 归因完全一致（无 API 调用）。
- 泄漏审计边界：对 3 个 pilot 作物 × 4 phase × 6 anchor × 2 mode 共 **78 个 packet** 全量审计，**0 失败**。
- Secret 扫描：`scripts/secret_scan.py` → `SECRET_SCAN_CLEAN`（工作区 0 命中、全历史 0 命中）。

## 4. 未覆盖 / 未执行

- 阿里云服务器侧验收：SSH 公钥认证被外部阻塞，未执行（见 `RC3_DEPLOYMENT_REPORT.md`）。
- 资产重冻结与 Git 提交/合并/tag：未执行，待确认。
- 前端浏览器端 E2E 真机联调：本轮沿用既有 `RC2_BROWSER_E2E_REPORT.md` 证据，未重跑。