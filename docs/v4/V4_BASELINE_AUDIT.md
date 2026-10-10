# V4 基线审计（Phase 0）

日期：2026-10-10。产品仓库基线：feat/frontend-v3-phase3-rc，5035668bab21785d392900f155ad548d2ece06ce；工作区干净。施工分支：feat/frontend-v4-spatial-experience。外层旧仓库有用户未提交删除与 README 改动，本轮不操作。

## 已实际运行
- 使用现有 Vite 5173 与正式 FastAPI 8787；ready 确认绑定 runtime 快照，沈阳/朝阳数据集可读、32 个模型资产、Daily 2026-10-06。
- 1440×900 浏览器从 `/` 点击进入，实际 URL 自动成为 `/liaoning?city=shenyang&horizon=14`。Opening 有讲解浮窗；全省页默认沈阳、四块研究正文侵占地图空间。
- 直接进入丹东决策：只有数据待接入状态，仍给出短期与长期入口；研究页代码和 DOM 存在双层 main/paper/header/close。
- 证据：output/playwright/v4-baseline/opening.png、province.png、dandong-decision.png、interaction.webm。基线朝阳截图首次超过默认 5 秒 screenshot 超时，重试处理，不将超时写为成功。

## 基线实测门禁
- npm run typecheck：通过。
- npm run test:unit：43 files / 391 tests 通过，属于基线，不作为 V4 最终结果。
- python3 -m pytest backend/tests -q：74 passed。
- python3 scripts/verify_assets.py：20/20、ASSETS_VERIFY_OK。README 提到 PUBLISHED 状态失败已经过时：当前校验器支持该状态。

## 根因
具体源码、基线行号见 V4_SPATIAL_SOURCE_AUDIT.md；决策来源见 CITY_DECISION_CAPABILITY_MATRIX.md。
- 空间观察与决策上下文共用强制沈阳；sessionStorage 和 URL 双 Effect 又补齐默认值。
- Hover 直接更换完整 Inspector，列表离开不清 Hover；Canvas 与列表各自 setCity。
- 相机 focus 只来自城市路径，省域点击没有微调。
- Opening 实际方位角 118°；一个 Canvas、实体几何与 RAF 清理已有可复用基础。
- 非沈阳模块页在完整城市页内嵌另一完整页面，产生两个关闭控件。
- supported 仅代表价格模型能力，被误作整个城市决策价值开关，且朝阳触发仅沈阳支持的长期接口。

## 与旧规则冲突
frontend/AGENTS.md 中“其他城市只保留元数据”与真实六城正式研究及本次用户需求不符。本轮以用户 V4 手册与正式运行数据为准，保留科学边界、复用优先和逐阶段 build 要求。不改变研究结论、训练权重、数据统计口径。
