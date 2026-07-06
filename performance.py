from collections import defaultdict
from typing import Dict, Iterable, List

from db import closed_signal_rows


def _metrics(rows: Iterable[Dict]) -> Dict:
    rows = list(rows)
    results = [float(row["r_result"]) for row in rows if row.get("r_result") is not None]
    if not results:
        return {
            "trades": 0, "wins": 0, "losses": 0, "breakeven": 0,
            "win_rate_pct": None, "expectancy_r": None, "avg_r": None,
            "avg_win_r": None, "avg_loss_r": None, "profit_factor_r": None,
            "max_drawdown_r": None, "net_r": 0.0,
        }

    wins = [r for r in results if r > 0]
    losses = [r for r in results if r < 0]
    breakeven = [r for r in results if r == 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for result in results:
        equity += result
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return {
        "trades": len(results),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate_pct": round(100 * len(wins) / len(results), 2),
        "expectancy_r": round(sum(results) / len(results), 3),
        "avg_r": round(sum(results) / len(results), 3),
        "avg_win_r": round(sum(wins) / len(wins), 3) if wins else None,
        "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else None,
        "profit_factor_r": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "max_drawdown_r": round(max_dd, 3),
        "net_r": round(sum(results), 3),
    }


def _group(rows: List[Dict], key: str) -> Dict:
    groups = defaultdict(list)
    for row in rows:
        groups[str(row.get(key) or "UNKNOWN")].append(row)
    return {name: _metrics(items) for name, items in sorted(groups.items())}


def _score_bucket(score: int) -> str:
    if score < 70:
        return "<70"
    if score < 80:
        return "70-79"
    if score < 90:
        return "80-89"
    return "90-100"


def performance_report() -> Dict:
    rows = closed_signal_rows()
    for row in rows:
        row["score_bucket"] = _score_bucket(int(row.get("score") or 0))
    return {
        "note": "Statystyki dotyczą tylko zarejestrowanych sygnałów. Score nie jest prawdopodobieństwem.",
        "overall": _metrics(rows),
        "by_side": _group(rows, "side"),
        "by_setup": _group(rows, "setup_type"),
        "by_regime": _group(rows, "regime"),
        "by_score_bucket": _group(rows, "score_bucket"),
    }
