"""Historical OHLC outcome calculations. Requires externally validated adjusted bars."""
from bisect import bisect_right
from calendar import monthrange
from datetime import date
from decimal import Decimal

HORIZONS=(11,21,43,64)

def d(x):return Decimal(str(x))

def true_range(bar,previous_close):
    high,low=d(bar["high"]),d(bar["low"])
    return max(high-low,abs(high-previous_close),abs(low-previous_close))

def atr14(bars,entry_index):
    """14 completed bars before entry; requires 15 earlier bars for first TR."""
    if entry_index<15: return None
    return sum((true_range(bars[i],d(bars[i-1]["close"])) for i in range(entry_index-14,entry_index)),Decimal(0))/14

def trading_entry_index(bars,filing_date):
    """First bar strictly after filing date (D-051)."""
    for i,bar in enumerate(bars):
        if str(bar["date"])>str(filing_date):return i
    return None

def six_month_anniversary(day):
    year, month = divmod(day.year * 12 + day.month - 1 + 6, 12)
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def compare_disclosure(bars, filing_date, *, sessions=None):
    """Measure price-only paths from the D-051 entry and D-052 reference.

    Supply an independent sorted exchange calendar for production. A missing
    security bar cannot move entry or compress the observation window.
    """
    filing_date = str(filing_date)
    by_day = {str(bar["date"]): bar for bar in bars}
    days = list(by_day) if sessions is None else sessions
    next_idx = bisect_right(days, filing_date)
    if next_idx == len(days) or days[next_idx] not in by_day:
        return {"status": "missing_entry_session"}
    history_days = days[max(0, next_idx - 15):next_idx]
    if len(history_days) < 15 or any(day not in by_day for day in history_days):
        return {"status": "missing_or_invalid_entry_atr"}
    atr = atr14([by_day[day] for day in history_days], 15)
    if atr is None or atr <= 0:
        return {"status": "missing_or_invalid_entry_atr"}
    entry_date = days[next_idx]
    next_open = d(by_day[entry_date]["open"])
    if next_open <= 0:
        return {"status": "invalid_reference_price"}
    filing_bar = by_day.get(filing_date)
    filing_close = d(filing_bar["close"]) if filing_bar else None
    result = {
        "status": "ok", "filing_date": filing_date, "next_open_date": entry_date,
        "next_open": str(next_open), "atr14": str(atr), "horizons": {},
        "filing_close_status": "ok" if filing_close and filing_close > 0 else "missing_or_invalid_filing_close",
    }
    if filing_close and filing_close > 0:
        result.update(
            filing_close=str(filing_close),
            entry_gap_percent=str((next_open / filing_close - 1) * 100),
            entry_gap_atr=str((next_open - filing_close) / atr),
        )
    anniversary = six_month_anniversary(date.fromisoformat(entry_date)).isoformat()
    ends = [(str(h), next_idx + h) for h in HORIZONS]
    ends.append(("6m", bisect_right(days, anniversary) if anniversary <= days[-1] else len(days) + 1))
    for label, end in ends:
        if end > len(days):
            result["horizons"][label] = {"status": "insufficient_forward_bars"}
            continue
        window_days = days[next_idx:end]
        if any(day not in by_day for day in window_days):
            result["horizons"][label] = {"status": "missing_forward_session"}
            continue
        window = [by_day[day] for day in window_days]
        high = max(d(bar["high"]) for bar in window)
        low = min(d(bar["low"]) for bar in window)
        close = d(window[-1]["close"])

        def stats(entry):
            return {
                "max_gain_atr": str((high - entry) / atr),
                "max_adverse_atr": str((low - entry) / atr),
                "end_return_atr": str((close - entry) / atr),
                "max_gain_percent": str((high / entry - 1) * 100),
                "max_adverse_percent": str((low / entry - 1) * 100),
                "end_return_percent": str((close / entry - 1) * 100),
            }

        outcome = {"status": "ok", "end_date": window_days[-1], "next_open": stats(next_open)}
        if filing_close and filing_close > 0:
            # Same forward sessions for both reference prices. The filing day's
            # intraday range preceded its close and cannot enter the extrema.
            outcome["filing_close_reference"] = stats(filing_close)
        result["horizons"][label] = outcome
    return result
