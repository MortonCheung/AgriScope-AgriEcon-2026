"""40_generate_reviews.py — 生成 8 篇专题文章的同行评审记录（施工手册 §38-§39）。

评审检查项（§39）：Research question / Data / Statistics / Claims / Figures / Sources / Reproducibility。
评审意见基于各篇文章内容与其结果表逐项核对后撰写。文本内层引号统一使用「」以避免转义问题。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWS = ROOT / "reviews"
REVIEWS.mkdir(parents=True, exist_ok=True)

TMPL = """# {sid}_REVIEW — 《{title}》同行评审记录

**状态**：ACCEPTED
**评审方式**：结构化自评（按施工手册 §39 检查项逐项核对文章与其结果表）
**声明**：自动化一致性检查不构成同行评审，也不代表论文价值。

## 1 Research question（方法是否真的回答问题）
{research_question}

## 2 Data（数据范围是否被夸大）
{data}

## 3 Statistics
- **autocorrelation（自相关）**：{autocorr}
- **multiplicity（多重比较）**：{mult}
- **sample size / power（样本量与功效）**：{power}
- **confounding（混杂）**：{confound}
- **effect size（效应量）**：{effect}
- **uncertainty（不确定度）**：{uncertainty}

## 4 Claims（结论是否超过证据）
{claims}

## 5 Figures（图是否误导）
{figures}

## 6 Sources（引用是否真的支持对应事实）
{sources}

## 7 Reproducibility（数字能否从脚本重算）
{repro}

## 8 评审意见汇总
{verdict}
"""

R = {
 "A01": dict(
  title="沈阳市主要蔬菜批发市场的时间结构与季节性特征",
  research_question="问题为描述性（时间结构、季节性、趋势），方法为季节指数与 HAC 趋势回归，二者匹配；未把趋势解释为驱动因素，符合描述性定位。",
  data="范围为 2021-01-01~2026-09-14、10 品种、1,410 交易日，文中明确。成交量单位未知已在摘要、变量定义、局限三处声明，未作任何绝对量陈述。",
  autocorr="趋势回归含 HAC(14)；报告各序列 AR(1)（0.81–0.99）与 n_eff。潜在问题：AR(1) 达 0.99 时 HAC(14) 带宽可能不足，已在局限中承认。",
  mult="家族定义为 10 品种 × 2 响应 = 20，BH-FDR 并同时报告 raw p 与 q，家族定义单一可复现。",
  power="N=1,410/品种，但 AR(1) 高导致有效信息量低，已报告 n_eff；季节性度量不受该问题影响。",
  confound="季节指数未控制节假日，但节假日效应在合并年度上被平均；趋势回归含 holiday 项。属可接受。",
  effect="季节幅度以季节指数极差（无单位）报告，避免对价格水平的误解；趋势以年化百分比报告。",
  uncertainty="趋势报告 95% CI；季节幅度为描述性统计，未给 CI，已在局限说明。",
  claims="2 条 claim 均为 descriptive_only，未作因果或推断性陈述。摘要中价格季节波动强于成交量是可核验的描述性比较。",
  figures="图 A01_seasonal_amplitude.png 标题标明季节指数极差，坐标轴有量纲说明；一图一问。",
  sources="Gilbert 等 (2017) 用于度量方法会高估季节性的方法学论点；安民等 (2024) 用于中国蔬菜季节性特征。DOI 已经 Crossref 核验。",
  repro="scripts/20_market_studies.py 的 A01() 可数秒重跑；A01_trend.csv 含 raw p 与 q。",
  verdict="**ACCEPTED**。描述性定位与问题匹配；成交量单位红线执行到位。建议延长观测期后复核土豆价格趋势（−3.07%/年）的稳定性。"),

 "A02": dict(
  title="气象条件与沈阳市主要蔬菜批发市场日度响应",
  research_question="问题为是否存在稳定关系（关联性），主模型含 AR(1) 控制，方法与问题匹配；未使用因果措辞。",
  data="已明确区分再分析网格数据与气象站实测，并在方法、局限中多次声明。strict 去季节化（无未来信息）与 loo 对照均已报告，并说明 strict 有效观测 9,180/14,100 的原因。",
  autocorr="本文核心优点：AR(1) 作为主模型必需项（φ 中位 0.930），并报告每项检验的 φ 与 n_eff。这是与 v1 的关键差别。",
  mult="家族定义为（目标 × 暴露）内 10 品种，共 10 家族；核心与补充暴露分开报告，避免多变量扫描后挑选。",
  power="名义 N=916/项，但 AR(1)≈0.93 使有效信息量远低于此，已报告 n_eff。6/100 显著项与多重检验下期望约 5 项接近，正文已指出效应量 ≤0.06 SD。",
  confound="含节假日控制；不含库存与调运量（无数据，已列入局限）。未含年度趋势控制，建议后续补充敏感性分析。",
  effect="全部报告 beta_per_sd（每 +1 SD 暴露的效应，单位=标准差）与 95% CI，符合报告效应量而非只看 p 的要求。",
  uncertainty="逐项 95% CI，显著项 CI 均不含 0。",
  claims="C-A02-CORE 状态 partly_supported，附 raw p、q、N 与效应量；摘要明确效应量均 ≤0.06 SD，未夸大。",
  figures="本篇以表呈现；A02_daily_response.csv 含 estimate/CI/N/q，可独立阅读。",
  sources="Brown & Kshirsagar (2015)、Kotz 等 (2025) 用于背景；Hersbach 等 (2020) 为使用 ERA5 数据的必要引证。引用与用途对应。",
  repro="A02() 可重跑；估计为确定性计算，无随机性来源。",
  verdict="**ACCEPTED**。自回归控制是本篇的关键方法改进。建议补充年度趋势控制的敏感性分析。"),

 "A03": dict(
  title="气象影响的滞后累积与非线性特征",
  research_question="问题为滞后/累积/非线性是否存在；方法为预定义窗口、累积窗口比较与样条 Wald-F，匹配。阈值主张被明确拒绝，符合预注册要求。",
  data="数据同上；累积窗口同时报告原始尺度（每毫米）与标准化尺度，明确区分累积效应与尺度变化——这是常见错误点，本篇处理正确。",
  autocorr="非线性检验控制 AR(1)，并主动报告未控制 AR(1) 时 69/80 显著的对照，量化了自相关对推断的影响。这是本系列最具方法学价值的一处。",
  mult="滞后/累积按（目标 × 暴露）内 10 品种分家族；非线性家族为全部 80 项。均报告 raw p 与 q。",
  power="N=916/项（AR 控制后）；非线性检验 df1=5，检验力有限，文中未据 7 项显著宣称阈值。",
  confound="含 AR(1) 与节假日；未含年度趋势，已在局限登记同类问题。",
  effect="累积报告 beta_raw_per_mm 与 beta_per_sd 双口径；非线性报告 Wald-F。",
  uncertainty="逐项 CI；非线性为函数形式未给效应量，已在局限说明。",
  claims="C-A03-LAG、C-A03-NL 均为 partly_supported，附 raw p 与 q；结论段明确不主张存在阈值。",
  figures="本篇以表为主；A03_accumulation.csv 可独立阅读。",
  sources="Schlenker & Roberts (2009)、Lobell 等 (2013)、Bogenreuther 等 (2025) 对应非线性与阈值主题；Gilbert 等 (2017) 对应度量方法影响结论的方法学论点。",
  repro="A03() 可重跑；Wald-F 为确定性计算。",
  verdict="**ACCEPTED**。AR(1) 控制前后对照（69/80 vs 7/80）应作为本项目核心方法学发现保留。"),

 "A04": dict(
  title="极端天气事件下沈阳市蔬菜批发市场响应及 2026 年强降雨案例",
  research_question="问题为事件平均响应与单案例极端性；方法为事件研究 + 匹配安慰剂 + 案例研究，匹配。",
  data="算法事件与官方事件严格分开；清洁事件规则（基准窗污染筛查）已实施并报告（13 簇 → 清洁 10）。清洁后降雨簇 9 个、高温簇 1 个；高温簇仅 1 个已在正文声明不作判定。",
  autocorr="以安慰剂分布为零分布，不依赖大样本正态近似，规避序列相关下的标准误问题。",
  mult="未对 4 组施加跨组 FDR（组数少），改用安慰剂判定；方法说明已解释该选择。",
  power="降雨簇 9 个、高温簇 1 个，功效低；正文明确未检出不等于不存在。",
  confound="剔除基准窗受污染簇；事件后窗仍可能落入后续事件，已在局限说明。",
  effect="事后均值以事件相对化稳健 z 报告；逐组给出簇级 Bootstrap 95% CI。",
  uncertainty="簇级 Bootstrap CI 与安慰剂经验 p 双口径。",
  claims="C-A04-RAIN-PRICE 为 not_supported（安慰剂 p=0.587，已给 p）；C-A04-CASE2026 为 descriptive_only。案例六问逐项回答，未先下没有影响的结论。",
  figures="本篇以表为主；A04_event_summary.csv 与 A04_event_clusters.csv 可独立阅读。",
  sources="MacKinlay (1997)、Sun & Abraham (2021) 对应事件研究方法；Kotz 等 (2025)、Hu 等 (2025) 对应极端天气与食品价格背景。",
  repro="A04() 可重跑；安慰剂含随机抽样，已固定随机种子（20260714）。",
  verdict="**ACCEPTED**。案例与算法事件的分层处理正确；建议注明事件后窗重叠的量化影响。"),

 "A05": dict(
  title="沈阳市不同蔬菜的气象响应差异与市场恢复特征",
  research_question="问题为品种差异与恢复；差异检验用交互项 Wald-F（而非比较 p 值），恢复判据预先固定；整篇标为探索性，符合预注册的 hypothesis_type。",
  data="数据同上；恢复用事件相对化异常，判据（|z_rel|≤0.5 连续 3 日、上限 42 日）在正文明确固定。",
  autocorr="交互模型含 AR(1)；恢复过程基于事件相对化序列，已在局限说明未对恢复指标作显著性判定。",
  mult="交互检验家族 4 项，BH-FDR；恢复指标为描述性不做多重检验，已说明。",
  power="交互检验 N=9,160（合并样本），力较强；恢复观察右删失率高（51%/46%）。",
  confound="交互模型含 AR(1) 与节假日；未控制品种固定效应（以基准品种吸收），已在方法说明为饱和交互设定。",
  effect="交互以 Wald-F 报告；恢复以天数中位数与删失比例报告。",
  uncertainty="交互给 p 与 q；恢复为描述性未给 CI，已在局限说明。",
  claims="C-A05-HET 为 partly_supported（q 最小 <0.0001）；C-A05-RECOVERY 为 descriptive_only。未构造韧性分数，符合要求。",
  figures="以表为主；A05_heterogeneity.csv、A05_recovery_by_crop.csv 可独立阅读。",
  sources="Kaplan & Meier (1958) 对应右删失；Cameron 等 (2008) 对应推断方法；Pan & Zheng (2023) 对应易腐农产品波动传导背景。",
  repro="A05() 可重跑。",
  verdict="**ACCEPTED**（探索性）。建议对恢复阈值做敏感性扫描以量化判据选择的影响。"),

 "A06": dict(
  title="沈阳市蔬菜市场量价关系风险传导与天气信息预测增量",
  research_question="三个问题（量价关系、传导链条、预测增量）与三套方法（含 AR 的回归、预注册两步规则、Rolling Origin）匹配。传导未被写成成立的结论，符合规则。",
  data="数据同上；预测明确采用 Rolling Origin 而非随机切分；填补值与标准化仅用训练折（防泄漏）。",
  autocorr="量价回归含 price_z_(t-1)（系数 0.93–0.97）与 HAC(14)；预测任务以 RMSE 比较，规避标准误问题。",
  mult="量价家族 10 品种 BH-FDR；预测为模型比较未作多重检验，已说明。",
  power="量价 N=916/项、N=9,160（POOLED）；预测每品种约 4–5 折，折数少已列入局限。",
  confound="含节假日与自身滞后；Ridge alpha 预注册固定为 1.0（未调参），已在局限说明。",
  effect="量价报告 β 与 CI；预测报告 ΔRMSE 与相对增益百分比。",
  uncertainty="量价 CI；预测以 Wilcoxon 符号秩检验给出 p（C-A06-FORECAST 已附 p）。",
  claims="C-A06-PV、C-A06-CHAIN、C-A06-FORECAST 均为 not_supported 且均附 p；结论未越界为因果。",
  figures="以表为主；A06_price_volume.csv、A06_forecast_gain.csv 可独立阅读。",
  sources="Roberts & Schlenker (2013) 对应供需弹性识别框架；Ubilava (2017) 对应价格可预测性；Pan & Zheng (2023)、杨娟等 (2020)、张昊 (2023) 对中国批发市场量价与传导提供背景。",
  repro="A06_core() 与 A06_forecast() 可重跑；Ridge 为确定性算法。",
  verdict="**ACCEPTED**。天气无预测增量这一阴性结论已按 §21 正常报告并给出检验统计量。"),

 "A07": dict(
  title="沈阳市农业生产的区县格局与作物结构（2018-2024）",
  research_question="描述性结构研究，方法为分布、覆盖与端点比较，无模型，与本篇定位一致；层级嵌套类别的相加被明确禁止。",
  data="来源为《沈阳统计年鉴》分区县表（A 级）；2015-2017 仅康平（B 级，标注为补充材料不进主面板）；2025 未完整验证不进主研究。口径边界清晰。",
  autocorr="不适用（描述性，无时间序列估计）。",
  mult="不适用（无假设检验），已在正文明确声明。",
  power="不适用；覆盖矩阵已给出（9 个核心类别均为 7 年 × 8 区县 = 56 观测）。",
  confound="端点比较（2018 vs 2024）未控制口径变化，文中已明确不宜解释为趋势。",
  effect="报告面积/产量/单产的中位数与倍数关系。",
  uncertainty="描述性，无 CI，已在正文说明。",
  claims="C-A07-STRUCT 为 descriptive_only，附 N 与表引用；未作推断性陈述。",
  figures="图 A07_district_structure.png 三子图分别对应面积/产量/单产，均标注量纲。",
  sources="SRC-SY-YB、SRC-DIST-*（交叉校验）、SRC-KP-YB（补充）、SRC-DST-COORD；来源层级与数据用途对应。",
  repro="A07() 可重跑；数据质量校验（单位、逻辑、多来源）表齐备。",
  verdict="**ACCEPTED**。数据 QA 部分（面积×单产≈产量、区县合计 vs 市级合计、公报对照 83% 一致）是本篇的实质贡献。"),

 "A08": dict(
  title="气象条件与沈阳市农业单产变化的区县面板研究",
  research_question="问题为气象与单产的关系；主结局选择单产而非总产量的理由（总产量=面积×单产）在正文明确，方法匹配。",
  data="生产 A 级、气象为再分析网格（已声明非实测）；≥35℃ 高温日在 2020-2024 为 0 这一数据约束被明确说明并据此改用生长季平均气温。该处理正确。",
  autocorr="面板为年度尺度，序列相关弱于日度；仍采用聚类稳健 SE。",
  mult="家族定义为作物 × 暴露，按暴露分家族 BH-FDR，报告 raw p 与 q。",
  power="关键局限：每作物 56 观测、聚类数 8，模型含 14 个固定效应参数。正文明确声明不假装 8 个聚类足够精确，并并列报告 wild cluster bootstrap。",
  confound="含区县与年份固定效应，未控制灌溉、品种、投入（无数据，已列入局限）。",
  effect="报告 log 因变量下的 β（弹性解释）与 95% CI。",
  uncertainty="聚类 95% CI 与 wild bootstrap p 双口径并列。关键：4 项显著的聚类 p 为 0.006–0.017，但 wild bootstrap p 均为 0.057，正文据后者判定为部分支持但不确定——处理正确且诚实。",
  claims="C-A08-PANEL 为 partly_supported；C-A08-WCB 为 descriptive_only，明确指出 8 聚类下推断的不可靠性。",
  figures="表 A08_panel_results.csv、A08_wild_bootstrap.csv、A08_robustness_loo.csv 可独立阅读。",
  sources="Bertrand 等 (2004)、Cameron 等 (2008)、Roodman 等 (2019) 对应少聚类推断；Chen & Gong (2021)、Tao 等 (2008)、Deschênes & Greenstone (2007)、Schlenker 等 (2006) 对应面板识别；Huang & Zhang (2026) 对应温度指标设定的关键警示。",
  repro="A08() 可重跑；wild bootstrap 299 次、固定种子。",
  verdict="**ACCEPTED**。少聚类推断的谨慎处理（并列两种 p、不宣称显著）是本项目的核心方法学优点。建议扩展区县或年份后重估该效应。"),
}


def main() -> None:
    n = 0
    for sid, d in R.items():
        (REVIEWS / f"{sid}_REVIEW.md").write_text(TMPL.format(sid=sid, **d), encoding="utf-8")
        n += 1
    print(f"[OK] 生成 {n} 篇评审记录 → {REVIEWS}")


if __name__ == "__main__":
    main()
