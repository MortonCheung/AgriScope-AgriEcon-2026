# -*- coding: utf-8 -*-
"""Final Model 阶段（基于 data/model_ready/ 的最终审计、重训、校准、回测与冻结）。

与旧 v1/v2 结果严格隔离：
  - 旧产物保留在 models/evaluation/ 与 models/data/snapshots/v1, v2；
  - 本包所有新增产物写入 models/reports/final/ 与 models/data/snapshots/final_v1/。
"""