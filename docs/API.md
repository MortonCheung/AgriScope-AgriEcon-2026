# AgriScope API

唯一后端：`backend/`（FastAPI）。本地端口 **8787**，单 worker，`/api` 前缀由前端 Vite 代理。
路径与实现见 `backend/app/routes/*.py`；响应模型见 `backend/app/schemas.py`；错误码见 `backend/app/errors.py`。
交互式文档：`GET /docs`（Swagger）。

## 通用约定

- **Request-ID**：每个请求回带 `X-Request-ID`（请求头传入则沿用，否则服务端生成），用于跨层追踪。
- **请求体上限**：JSON 请求体上限 64 KB，超限返回 `BAD_REQUEST`。
- **错误信封**（统一）：
  ```json
  { "error_code": "UNSUPPORTED_CITY", "message": "…", "request_id": "…", "details": {} }
  ```
  错误码：`BAD_REQUEST`、`VALIDATION_ERROR`、`UNSUPPORTED_CITY`、`NOT_FOUND`、`MODEL_UNAVAILABLE`、
  `DAILY_UNAVAILABLE`、`FORECAST_UNAVAILABLE`、`RESEARCH_UNAVAILABLE`、`LLM_UNAVAILABLE`、
  `INFERENCE_ERROR`、`INTERNAL_ERROR`。

## health

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 存活探针，返回 `{"status":"ok", …}` |
| GET | `/health/ready` | 就绪探针（真检查）：绑定快照、数据集、模型产物、meta 文件、Daily latest。未就绪前不声明 ready |

## meta 与能力

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/api/meta` | — | 版本矩阵：backend / final_model（`model_version`、`data_version`、`code_fingerprint`）/ runtime（`snapshot_dir`、`runtime_data_status`、`runtime_data_version`） |
| GET | `/api/decision/capabilities` | `city`（slug，如 `shenyang`） | 城市决策能力。响应 `CapabilityResponse`：`city_id`、`tier`、`supported`、`crops[{id,label,horizons[{days,mode}]}]`、`market_as_of`、`model_version`、`data_version`、`code_fingerprint`、`limitation` |
| GET | `/api/capabilities` | 同上 | 上者的兼容别名（不在 OpenAPI schema 中） |

## decision（短期 Final，契约 v1）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/decision` | 主入口（前端 `HttpDecisionProvider` 默认） |
| POST | `/api/decision/evaluate` | 别名 |
| POST | `/api/decision/rank` | 别名（不在 OpenAPI schema 中） |
| POST | `/api/decision/stress` | 压力情景（价格 / 亩产 / 成本 / 延迟），响应 `StressResponse` |

- 请求体为 `FinalDecisionRequest`（`contract_version:'1'`），**原样回显**，不绑定 `response_model`。
- 响应含 `data_status`，取值仅 `model` / `mock` / `legacy_model_fixture`（见
  `frontend/src/domain/decision/types.ts` 与 `validation.ts`）。正式 HTTP 通道**拒绝**把 `mock`
  或 `legacy_model_fixture` 当作模型结果返回。
- `StressResponse`：`candidate_id`、`changes{price_pct,yield_pct,cost_pct,delay_days}`、`available`、
  `profit_base`、`delta_cny`、`roi`、`note`、`model_version`、`data_version`。

## daily

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/api/daily/latest` | `city`（默认 `shenyang`，目前仅 shenyang） | Daily 市场脉搏最新快照（schema 1.1.0）。含 `schema_version`、`daily_pipeline_version`、`data_version`、`model_version`、`generated_at`、`timezone`（固定 `Asia/Shanghai`）、`latest_data_date`、`status`、`freshness`、`recommendation`、`monitor` |

## forecast（长期，只读预生成快照）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/forecast/capabilities` | 长期可用跨度与生产状态（`crop` 查询参数） |
| POST | `/api/forecast/long-horizon` | 长期预测主契约。请求 `LongHorizonForecastRequest`；双目标 `harvest_market_price`（默认）与 `cycle_market_average` |
| POST | `/api/decision/long-horizon` | 上市窗口种植决策（结构化契约 v2） |

`LongHorizonForecastRequest`（`extra="forbid"`, `strict`）：

```json
{ "contract_version": "1|2", "city_id": "shenyang", "crop": "土豆",
  "horizon_days": 90, "target_type": "harvest_market_price" }
```

`LongHorizonDecisionRequest`（`contract_version` 必须为 `"2"`）：

```json
{ "contract_version": "2",
  "user_context": {
    "city_id": "shenyang", "area_mu": 60, "budget_cny": 300000,
    "risk_preference": "conservative|balanced|aggressive",
    "crop_preferences": ["西红柿"],
    "actual_inputs": { "西红柿": { "cost_per_mu": null, "yield_kg_per_mu": null } },
    "market_context": { "as_of": null, "expected_harvest_horizon_days": 90, "expected_harvest_date": null }
  },
  "input_source": { "kind": "structured" } }
```

- 上市日期必须精确对应已登记跨度，**不静默选取最近档位**。
- 响应显式携带 `actual_method`、`fallback_used`、生产状态（如 `SCENARIO_ONLY` / `PRODUCTION_POINT` /
  `EXPLORATORY_SCENARIO_ONLY`）与 `LONG_HORIZON_STALE`。长期失败**不会**影响短期与 Daily。

## research（研究中心，只读）

只读暴露前端研究契约（`runtime/research/product/**`），**路径白名单**（服务端正则约束城市、文章 id 与
文件名，解析后必须落在研究产品目录内），不做研究计算、不改写结论。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/research/catalog` | 研究总索引（轻量，不含正文） |
| GET | `/api/research/cities` | 已发布研究城市与模块概况 |
| GET | `/api/research/llm-evaluation` | LLM 回溯评估证据（由真实产物派生，只读） |
| GET | `/api/research/{city}/manifest.json` | 城市研究清单 |
| GET | `/api/research/{city}/sources.json` | 城市数据来源清单 |
| GET | `/api/research/{city}/sync-report.json` | 城市研究同步报告 |
| GET | `/api/research/{city}/articles/{article_id}.json` | 研究模块正文 |
| GET | `/api/research/{city}/references.md` | 来源清单（纯文本） |
| GET | `/api/research/{city}/tables/{file}` | 研究数据表（CSV，按需加载） |
| GET | `/api/research/{city}/figures/{file}` | 研究插图（按需加载） |

## 边界

LLM / Hybrid 数值一律 `RESEARCH_ONLY`，后端不把它们作为生产模型；`/api/research/llm-evaluation` 只复述
已发布证据。若证据产物缺失，该端点按契约返回 `LLM_UNAVAILABLE`（不伪造）。科学边界总览见根 `README.md`。