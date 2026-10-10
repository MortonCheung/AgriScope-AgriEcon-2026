# experiments/code/FIXES.md — P0 修复清单（逐条 diff 级说明）

> 所有修复**仅作用于 `experiments/code/`（独立副本）**。
> 原始工程 `/Users/morton_cheung/Desktop/比赛/大数据分析` 与
> 只读快照 `农业建模/source_snapshot/` **均未被修改**（见 `../REPORT.md` 第 2 节零改动证明）。
>
> 代码指纹（.py 内容树哈希，`environment/env_fingerprint.json`）：
> - 未修复副本 `code_original/src`：`2e42c7e6c5615cdb`
> - 已修复副本 `code/src`：`a8a3dc725098bbf2`
>
> 复现要求："修复前测试失败 → 修复后测试通过"逐项证据见
> `../results/p0_regression_BEFORE.csv` / `../results/p0_regression_AFTER.csv`
> （未修复 **0/7 通过**，修复后 **7/7 通过**）。

---

## P0-1 HRI 全样本排名前视　→ 文件 `decision_engine/final/risk.py`

**问题**：`hri_components()` 中 `c_consecutive_rise` 用 `s.rank(pct=True)` 对**整段作物序列**排名，
同一历史切点的取值会随未来观测加入而改变（前视）。HRI 又进入回测策略，污染策略结论。

```diff
- d["c_consecutive_rise"] = d.groupby("crop", sort=False)["consecutive_rise"].transform(
-     lambda s: (s.rank(pct=True))) * 100
+ # [P0-1 FIX] 改为 past-only expanding rank（与其余组件 _exp_pct 口径一致）
+ d["c_consecutive_rise"] = d.groupby("crop", sort=False)["consecutive_rise"].transform(
+     lambda s: s.expanding(min_periods=MIN_WEEKS).rank(pct=True)) * 100
```

**验收（P0-1 测试）**：对 cutoff ∈ {2023W30, 2024W26, 2025W26}，用 `history<=cutoff` 独立计算 HRI，
与全量历史的 cutoff 行逐值比对。
- 修复前：`max|Δ(c_consecutive_rise)| = 5.83`，`max|Δ(HRI)| = 5.83`（1336–1814 行受影响）→ **FAIL**
- 修复后：三个 cutoff 全部 `max|Δ| = 0`（3010 行）→ **PASS**

**副作用（正向）**：原实现使 HRI 在**不足 40 周历史**的 warm-up 期也被填上非空值。
修复后 warm-up 期（每作物前 39 周 × 10 作物 = 390 行）HRI 记为缺失（缺失不进加权），
HRI 有效行 3010 → 2620。这正是"用未来数据填充早期值"被消除的直接体现。

---

## P0-2 前瞻标签未右删失　→ 文件 `decision_engine/final/risk.py`

**问题**：`_fwd()` 用 `hi = min(j+h+1, len(sub))`，对离样本终点不足 h 步的行仍以**较短窗口**
计算收益并写成 `fwd_{h}w`，等于把未成熟标签当完整 h 窗口标签使用。

```diff
- for j in range(len(sub)):
-     lo = j + 1; hi = min(j + h + 1, len(sub))
-     if hi <= lo:
-         continue
-     w = p[lo:hi]
+ for j in range(n):
+     if j + h >= n:          # 未来 h 步未完整可观察 → 右删失
+         continue
+     w = p[j + 1:j + h + 1]
      fwd[idx[j]] = w[-1] / p[j] - 1
      worst[idx[j]] = w.min() / p[j] - 1
+     matured[idx[j]] = True
+ ...
+ d[f"label_matured_{h}w"] = matured
+ d[f"label_status_{h}w"] = np.where(matured, "MATURED", "LABEL_NOT_MATURED")
```

**验收（P0-2 测试）**：检查每作物尾部 h−1 行的 `fwd_{h}w` 是否必为 NaN，且存在成熟度标记。
- 修复前：土豆 h=4/8/12 尾部各有 2/6/10 行"有值" → **FAIL**
- 修复后：尾部 `fwd_*` 全为 NaN，`label_matured_*` 存在 → **PASS**

---

## P0-3 季节基线名不副实　→ 文件 `decision_engine/final/backtest.py`

**问题**：`_seasonal_pick()` 先算了同月历史均价 `best`，随后遍历 `g.sort_values("crop")`
返回**第一个匹配作物**，从未调用 `best.idxmax()` → 季节基线实际退化为"字典序第一个有历史的作物"。

```diff
- best = hh.groupby("crop")["price_per_kg"].mean()
- for c in g.sort_values("crop")["crop"]:
-     if c in best.index:
-         return g.index[g["crop"] == c][0]
- return g["forecast"].idxmax()
+ # 同月、严格早于 t、前瞻窗口已成熟（rel_ret 非缺失）的历史样本上，
+ # 按作物求「未来 H 天窗口相对收益」均值，取最高者
+ hh = hh[hh["rel_ret"].notna()]
+ best = hh.groupby("crop")["rel_ret"].mean()
+ sel = best.reindex(list(g["crop"].values)).dropna()
+ winner = sel.idxmax()
+ return g.index[g["crop"] == winner][0]
```
配套新增 `_seasonal_hist()`：从冻结数据集构造 `rel_ret = target_mean_price_next_30d / price - 1`
（该目标仅在窗口完整可观察时非空，天然满足成熟条件）。

**验收（P0-3 测试）**：构造"字典序陷阱"（最优=西红柿，字典序第一=土豆）。
- 修复前：选到「土豆」→ **FAIL**
- 修复后：选到「西红柿」→ **PASS**

---

## P0-4 策略收益分量用跨作物绝对价格　→ 文件 `decision_engine/final/backtest.py`

**问题**：`strategy_scores()` 中 `s_profit = forecast`、`s_chase = anchor_price`。
不同蔬菜计价水平与量纲不同，**选绝对价格最高者 ≠ 选相对涨幅最高/亏损最小者**；
`Profit_only` 命名尤其不准确（既非利润、也非机会最优）。

```diff
+ d["predicted_return"]     = d["forecast"] / d["anchor_price"] - 1
+ d["predicted_low_return"] = d["fc_low"].fillna(d["forecast"]) / d["anchor_price"] - 1
+ d["ret_n"]  = _pool_pct(d["predicted_return"])
+ d["lret_n"] = _pool_pct(d["predicted_low_return"])
- d["s_profit"] = d["forecast"]
- d["s_chase"]  = d["anchor_price"]
+ d["s_profit"]      = d["predicted_return"]              # 最高预测相对收益
+ d["s_price_level"] = d["anchor_price"]                  # 绝对价格最高（语义单列）
+ d["s_chase"]       = run_up_4w.fillna(predicted_return) # 追涨：近 4 周相对涨幅最高
+ d["s_robust"]      = d["predicted_low_return"] - 0.5*d["hri_n"]*d["predicted_return"]
+ d["s_balanced_fix_v2"] = 0.30*ret_n + 0.20*lret_n - 0.20*mr_n - 0.30*hri_n
```
策略集合重命名：`Profit_only` → **`Highest_forecast_return`**；新增 **`Highest_price_level`**；
`Chase_price` → **`Chase_price_momentum`**。原 `Balanced_old`、`Balanced_fix_v1` 保留以便归因。

**验收（P0-4 测试）**：构造"绝对价最高=A，相对收益最高=B"的池。
- 修复前：Profit/Chase 均选 A → **FAIL**
- 修复后：均选 B → **PASS**

---

## P0-5 重叠窗口 / 切点步长 / 随机基线　→ 文件 `backtest.py`、`hri_stats.py`

### P0-5a `cutoff_step_days` 形同虚设
```diff
- step = pd.Timedelta(days=cutoff_step_days)   # 定义了但从未使用
- for t in dates:                              # 遍历全部交易日
+ def _select_cutoffs(dates, step_days=7):     # 真正按自然日步长抽稀
+     ...
+ dates = _select_cutoffs(sorted(panel["date"].unique()), cutoff_step_days)
```
效果：切点数 **667 → 140（step7）**；新增 **step30 非重叠口径 = 33 个切点**（相邻切点的
未来 30 天窗口不再重叠）。
- 修复前：`_select_cutoffs` 不存在 → **FAIL**
- 修复后：`step7=140 > step30=33`，且原始实现两者都等于全部交易日 → **PASS**

### P0-5b 随机基线不可复现且只抽一次
```diff
- rng = np.random.RandomState(abs(hash(str(t))) % (10 ** 6))   # 受 PYTHONHASHSEED 影响
- ridx = g.index[rng.permutation(len(g))[0]]
+ def _cutoff_seed(t):   # 仅由日期 ordinal + 固定盐派生，跨进程可复现
+     return int((_RANDOM_SALT * 1000003 + pd.Timestamp(t).toordinal()) % (2 ** 31 - 1))
+ rows.append(_rec(t, "Random_seeded", ...))        # 确定性单次抽取（留作参照）
+ rows.append(_expectation_rec(t, g))               # Random_expectation：均匀随机选择的解析期望
```
显著性检验一律以 `Random_expectation`（池内均值，无抽样噪声）为基准。
- 修复前：存在 `abs(hash(str(t)))` → **FAIL**
- 修复后：`_cutoff_seed` 在 PYTHONHASHSEED=0/12345 下输出一致（`1710796674`）→ **PASS**

### P0-5c HRI 时序稳健检验
`hri_stats.py`：
```diff
- stride = max(2, w // 2)      # w=12 时 stride=6，相邻样本前瞻窗口仍重叠 50%
+ stride = int(w)              # 真·非重叠：每 w 周抽 1 个
```
```diff
- # 旧：拼接两组→块重采样→shuffle→按固定位置切分（实为普通置换检验，破坏块结构）
- pooled = np.concatenate([x_hi, x_lo]); ...; rng.shuffle(samp)
- diffs[b] = mean(samp[:len(x_hi)]) - mean(samp[len(x_hi):])
+ # 新：两组**中心化序列**上分别做循环块 bootstrap（H0 下两组均值相等的零分布）
+ ch = x_hi - mean(x_hi); cl = x_lo - mean(x_lo)
+ bh = _circ_block_sample(ch, n_hi, block, rng); bl = _circ_block_sample(cl, n_lo, block, rng)
+ diffs[b] = mean(bh) - mean(bl)
```

---

## P0-6 报告与表数值不一致　→ 交付层面的对齐（不覆写旧报告）

- 旧 `RECOMMENDATION_REPORT.md` 的 `after=0.0870` 与同报告嵌入的生产路径 `profit_only_after=0.130434`
  不一致；`OPTIMIZATION_REPORT.md` 出现"单作物 HHI=1.0"与"茄子+甘蓝组合"并存；
  `cross_city/report.md` 与 `synthesis/report.md` 对事件后异常的表述不一致。
- **处理方式**：本次**不修改、不覆写**任何旧报告（硬约束），而是在
  `../REPORT.md` 中给出**以表与代码为唯一权威**的口径，并把上表数值差异作为"已知不一致"如实登记。
- 修复后 `high_hri_rate` 等关键指标一律取 `strategy_benchmark_step7.csv` / `_step30.csv` 的
  同一行同一列，消除"文字自我修正"的空间。
- 修复前 STRATS 仍含 `Profit_only` → **FAIL**；修复后策略集合口径明确 → **PASS**

---

## 附：本次**未**修改、但需在论文中如实声明的问题

1. **模型选择使用同一 OOT 折**：`models.select_per_horizon()` 用 test 折的 `mean_WAPE + 0.5·std_WAPE`
   选出"最终模型"，随后又在该折上评估策略 → 存在**选择偏差**（review P0-5"多重调参"）。
   本次未重做嵌套交叉验证，仅声明该限制。
2. **`data/processed/daily/final_input/extended_snapshot` 的冻结时间**为 2026-10-07，
   数据末端至 2026-10-06；与旧报告"至 2026-09-14"略有差异，故切点数与原报告（652）不同（旧口径复现为 667）。
3. **市场机会收益 ≠ 农户利润**：`realized_return` 不含成本/亩产，不能解释为经营利润。
