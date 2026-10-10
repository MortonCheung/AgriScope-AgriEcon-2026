from pathlib import Path
import pandas as pd
from decision_engine.common import de_path

P = de_path("evaluation", "recommendation", "recommender_backtest.parquet")


def test_backtest_artifacts():
    if not Path(P).exists():
        return                      # 回测未运行则跳过（不失败）
    bt = pd.read_parquet(P)
    assert len(bt) > 0
    assert {"cutoff", "policy", "rank", "realized_profit_mean", "regret"} <= set(bt.columns)
    # regret 定义：同 cutoff 内 top1 最佳实现利润 − 本方案（top3 平均可能高于 top1，故只对 top1 校验非负）
    t1 = bt[bt["rank"] == "top1"]
    assert (t1["regret"] >= -1e-6).all()
    assert set(bt["rank"]) <= {"top1", "top3"}
    for pol in ["C_agriscope_balanced", "A_profit_only", "B_risk_only"]:
        assert pol in set(bt["policy"])
