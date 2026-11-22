"""Stock conditions known at the hypothetical entry open."""

from bisect import bisect_left
from decimal import Decimal
from math import log
from statistics import stdev

from price_outcomes import d


def stock_entry_features(bars, sessions, entry_date, atr):
    """Use contiguous completed sessions and never inspect the entry bar."""
    index = bisect_left(sessions, entry_date)
    if index == len(sessions) or sessions[index] != entry_date:
        raise ValueError("Entry date is outside the exchange calendar")
    earlier = sessions[max(0, index - 253):index]
    wanted = set(earlier)
    by_day = {str(bar["date"]): bar for bar in bars if str(bar["date"]) in wanted}
    history = []
    for day in reversed(earlier):
        if day not in by_day:
            break
        history.append(by_day[day])
    result = {"completed_session_count": len(history), "prior_returns": {}}
    if not history:
        return result

    close = d(history[0]["close"])
    result["prior_close"] = str(close)
    if close <= 0:
        return result
    result["atr_percent_of_prior_close"] = str(d(atr) / close * 100)
    for window in (5, 21, 63, 126, 252):
        if len(history) > window and (base := d(history[window]["close"])) > 0:
            result["prior_returns"][str(window)] = {
                "percent": str((close / base - 1) * 100),
                "atr": str((close - base) / d(atr)),
            }

    if len(history) >= 21:
        closes = [float(bar["close"]) for bar in history[:21]]
        if min(closes) > 0:
            result["daily_log_return_std_20"] = stdev(log(a / b) for a, b in zip(closes, closes[1:]))
    if len(history) >= 252:
        high = max(d(bar["high"]) for bar in history[:252])
        low = min(d(bar["low"]) for bar in history[:252])
        if high > low > Decimal(0):
            result["range_52w"] = {
                "distance_from_high_percent": str((close / high - 1) * 100),
                "distance_from_low_percent": str((close / low - 1) * 100),
                "position": str((close - low) / (high - low)),
            }
    return result
