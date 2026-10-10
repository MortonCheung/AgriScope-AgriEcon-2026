"""05_add_frontend_summary.py — 为每篇文章插入显式 FRONTEND_SUMMARY 块（§32）。

要求：`abstract` 与 `frontend_summary` 必须是**两个独立字段**，且 frontend_summary
**不得由字符串截断生成**。故此处将逐篇撰写的简短摘要以显式标记块写入文章文件本身。

块格式：
  <!-- FRONTEND_SUMMARY -->
  正文（人工/模型基于该篇文章撰写，非 substring）
  <!-- /FRONTEND_SUMMARY -->
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPORTS = Path("/Users/morton_cheung/Desktop/比赛/大数据分析/shenyang/reports/v2")

SUMMARIES = {
    "A01": "沈阳 10 种蔬菜批发价格季节波动明显（季节指数极差中位 0.775），成交量季节波动很小（0.084）。"
           "20 项趋势检验中 8 项 FDR 显著：价格仅土豆下降 3.07%/年，成交量 7 项方向不一。",
    "A02": "在含自回归的日度模型中，100 项核心检验仅 6 项 FDR 显著且效应量 ≤0.06 个标准差，94 项无证据。"
           "序列持续性极强（AR(1) 中位 0.930），不控制自回归会把慢变趋势误认为天气作用。",
    "A03": "预定义滞后窗 11/160、累积降水 10/80 项 FDR 显著。非线性在控制 AR(1) 后 7/80 显著；"
           "若不控制 AR(1)，同一检验会虚假地达到 69/80 显著。",
    "A04": "10 个清洁事件簇的安慰剂 p 在 0.59–0.77，与随机日期不可分辨。2026 年 7 月降雨 173.9mm "
           "为样本第 1/2,083，但市场响应落在普通日期波动范围内。",
    "A05": "4 项品种×气象交互检验中 3 项 FDR 显著，说明品种响应斜率存在可检出的差异（探索性）。"
           "恢复观察右删失率价格 51%、成交量 46%，不给出韧性排序。",
    "A06": "控制价格自身滞后后，成交量对价格的同期效应中位仅 +0.0007（FDR 0/10）。供应传导两步规则未同时满足。"
           "Rolling Origin 下加入天气使 RMSE 相对变化中位数为 −0.66%，未带来预测增量。",
    "A07": "8 个农业区县粮食播种面积中位相差约 8.5 倍（18,934–160,585 公顷）。9 个核心作物类别均具备 "
           "7 年 × 8 区县完整数据；康平、法库、新民数据完整度最高。",
    "A08": "54 项区县面板检验中 4 项 FDR 显著，均为强降水日数与对数单产正相关（β 0.036–0.090）；"
           "但 wild cluster bootstrap 下 p=0.057，判定为部分支持但不确定。",
    "A09": "综合结论：2026 年 7 月降雨为观测期最强（173.9mm），但现有数据未提供气象显著驱动市场量价、"
           "或天气显著影响区县单产的稳健证据；生产端与市场端因缺少货源地数据无法连接。",
}


def main() -> int:
    n = 0
    for p in sorted(REPORTS.glob("0[1-9]_*.md")):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r"<!-- ARTICLE_END:(A\d\d) -->", txt)
        if not m:
            print(f"[SKIP] {p.name}：无 ARTICLE_END 标记")
            continue
        sid = m.group(1)
        if "<!-- FRONTEND_SUMMARY -->" in txt:
            print(f"[skip] {p.name} 已有 FRONTEND_SUMMARY")
            continue
        block = (f"<!-- FRONTEND_SUMMARY -->\n{SUMMARIES[sid]}\n<!-- /FRONTEND_SUMMARY -->\n\n")
        txt = txt.replace(m.group(0), block + m.group(0))
        p.write_text(txt, encoding="utf-8")
        n += 1
        print(f"[OK] {p.name} ← {sid}")
    print(f"共更新 {n} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
