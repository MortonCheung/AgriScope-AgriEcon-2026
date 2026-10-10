# AgriScope RC3 部署报告

生成时间：2026-10-08（Asia/Shanghai）
**当前状态：`NOT_DEPLOYED`（未部署，且不得声称为已部署）**

## 1. 结论

本机侧部署准备**已全部完成并产出可一键执行的部署包**；服务器侧**未执行任何变更**，
原因是 SSH 公钥认证被外部阻塞（见第 2 节）。该阻塞按规范 §40 属合法阻塞项。

## 2. 外部阻塞（已实测确证，非推测）

| 项目 | 实测结果 |
|---|---|
| 目标主机 | `root@39.105.27.85`（阿里云），网络可达 |
| 认证 | `Server accepts key` 之后返回 `Permission denied (publickey)` |
| 私钥 | `~/.ssh/morton_aliyun_ed25519` **受 passphrase 保护**：`ssh-keygen -y -P "" -f <key>` → `incorrect passphrase supplied to decrypt private key` |
| ssh-agent | `ssh-add -l` → `The agent has no identities` |
| 其他密钥 | `~/.ssh` 仅此一对密钥，无 `config`；`ubuntu@` 与备用密钥同样被拒 |

因此**无法在非交互自动化中完成认证**。服务器可达但无法登录，故未执行只读审计
（`docker ps` 等），也未部署、未改动任何服务。

**解阻条件（人工，二选一）**：
1. 本机执行 `ssh-add ~/.ssh/morton_aliyun_ed25519`（输入口令）；或
2. 在服务器 `~/.ssh/authorized_keys` 追加 `~/.ssh/morton_aliyun_ed25519.pub`。

## 3. 已交付的部署产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 一键部署包 | `output/rc3/agriscope-rc3-deploy.tar.gz` | **1379 文件，263,656,399 bytes（≈264 MB）** |
| 构建脚本 | [build_deploy_bundle.py](file:///Users/morton_cheung/Desktop/比赛/大数据分析/AgriScope/scripts/build_deploy_bundle.py) | 支持 `--label rc3`，默认输出 `output/<label>/agriscope-<label>-deploy.tar.gz` |
| 操作手册 | [deploy/README.md](file:///Users/morton_cheung/Desktop/比赛/大数据分析/AgriScope/deploy/README.md) | RC3 化：部署步骤、环境变量加载语义、运行约定、验收清单、恢复流程 |
| systemd 单元 | `deploy/agriscope-api.service`、`agriscope-daily-chain.{service,timer}`、`agriscope-api-refresh.{service,path}` | API、20:30/23:30 Daily+长期链、快照刷新 |
| nginx 模板 | `deploy/nginx.conf.example` | 反代与静态资源 |
| 运行时环境模板 | `deploy/runtime.env.example` | 路径/端口/域名/允许来源（不含 Secret） |

**部署包内容与排除项**：包含 Git 源码、`runtime/manifest.json` 必需资产、`frontend/dist`；
**排除**真实 `.env`、`node_modules/`、`llm/artifacts/`（LLM 缓存与响应）。
构建脚本对禁止项做硬校验，命中即抛错。

## 4. 服务器侧验收清单（登录后逐项执行）

见 `deploy/README.md` §4，关键项：

- [ ] `systemctl status agriscope-api` active；`curl -s http://127.0.0.1:8787/health/ready` 返回 ready
- [ ] `python3 scripts/smoke_rc2.py --base-url http://127.0.0.1:8787` 通过
- [ ] `./scripts/acceptance.sh` 19/19；`pytest backend/tests/test_e2e.py` 通过
- [ ] `systemctl list-timers | grep agriscope` 显示 daily-chain 与 api-refresh 已排程
- [ ] `journalctl -u agriscope-daily-chain` 无 FAILED；`chain_status.json` 正常
- [ ] Daily 与长期 `latest_data_date` 均前进；无 `LONG_HORIZON_STALE`
- [ ] nginx 反代可达、静态资源 200、`ALLOWED_ORIGINS` 已收紧
- [ ] `llm/artifacts`、runtime snapshots 仅 `agriscope` 用户可写

## 5. 部署安全约束

- 服务器若已运行既有容器/服务（如 `astrbot`、`napcat` 等），**一律不得中断或改端口**；
  部署前先 `docker ps`、`systemctl list-units` 只读核对。
- 后端为**单 worker + 启动时绑定快照 + 推理锁**；每日数据更新后需重启后端以重绑快照。
- 环境变量加载由根级 `agriscope_env.py` 统一负责：**系统环境变量优先**，
  `backend/.env` 仅作兜底；`.env` 中的过期 `AGRISCOPE_ROOT`/`PROJECT_ROOT` 会被拒绝注入。
- 禁止提交或打包任何 Secret。

## 6. 诚实性边界

- **未部署**：本机联调不等于服务器上线；本文档不构成上线声明。
- 独立最终评估证据未达门槛，部署仅提供**情景参考**，不给生产点预测或强推荐。
- LLM / Hybrid 数值若未通过校准与门禁，停留在 `RESEARCH_ONLY`，不进入生产 Registry。