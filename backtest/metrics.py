"""
Backtest performance metrics - same formulas the old (fake-LLM) engine.py used
for win rate / profit factor / drawdown, kept because the math itself was
always sound; only the signal-generation step it fed on was fake.
"""

from typing import Dict, List


def compute_metrics(trades: List[Dict]) -> Dict:
    if not trades:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
            "profit_factor": 0.0, "total_pnl": 0.0, "max_drawdown": 0.0,
            "expectancy": 0.0,
        }

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["pnl"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    total = len(trades)
    total_pnl = sum(t["pnl"] for t in trades)

    return {
        "total_trades": total,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / total,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        "total_pnl": total_pnl,
        "max_drawdown": max_dd,
        "expectancy": total_pnl / total,
    }


def compare_before_after(raw_trades: List[Dict], ai_filtered_trades: List[Dict]) -> Dict:
    return {
        "raw": compute_metrics(raw_trades),
        "ai_filtered": compute_metrics(ai_filtered_trades),
        "raw_trades": raw_trades,
        "ai_filtered_trades": ai_filtered_trades,
    }
