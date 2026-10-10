# M3_MODEL_CANDIDATES.md（R08 / §三十五~四十）
> 本文件为 **PREBUILD**：只设计结构，**不输出沈北实际减产**。

## M3-A 简单分阶段剂量响应
```
Damage = clip( f(duration | growth_stage), 0, 0.95 )
```
- 结构：每阶段分段线性（锚点来自文献区间），**强制单调不减**
- 输入：`waterlogging_duration` + `growth_stage`
- 输出：`yield_loss_fraction`
- 硬约束：同阶段下 duration ↑ ⇒ 期望损伤**不得系统性下降**

## M3-B 分层贝叶斯 Meta-regression
```
lnRR_i ~ Normal( mu_i, sigma_i )
mu_i   = a_study[i] + b_stage[i] * f(duration_i) + c * depth_i
a_study ~ Normal(a0, tau_a)     # study random effect
```
- 用于融合不同论文；`depth` 若可得
- **前提**：需要方差信息以正确加权 → 当前 **variance_available=NO** → **暂不能正式拟合**

## M3-C 保守区间模型（partial identification）
```
(stage, duration) → [loss_low, loss_high]
```
- 当文献异质、无法拟合光滑函数时使用；输出**区间**而非点估计

## 选择原则（§三十九）
按 ① 文献数量 ② 研究设计 ③ 效应可比性 ④ 方差信息 决定，**不预设 M3-B 最好**。
当前（含 §八十九 新增文献）：文献 4 篇**夏玉米** + 1 篇**全球 meta 分析**（多作物）+ 1 篇**水稻方法学**；**均无逐研究方差**。
→ **修正后：M3-B（先验级，用全球 meta 的分组效应作弱信息先验）+ M3-C（保守区间）并行**；M3-A 作透明基准。
**严格加权 meta-analysis 仍待方差补齐**（§三十四）。
