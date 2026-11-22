"""D-009/D-025 benchmark selection and entry-aligned price comparisons."""

from decimal import Decimal

from price_outcomes import d


def select_market_benchmark(classification):
    """Use only a verified effective-dated classification supplied by caller."""
    exchange = classification.get("exchange")
    if exchange == "XNYS":
        return "SPY"
    if exchange == "XASE":
        return "IWM"
    if exchange == "XNAS":
        member = classification.get("sp500_member")
        if member is True:
            return "SPY"
        if member is False:
            return "ONEQ"
    return None


def benchmark_outcomes(outcome, classification, benchmark_bars):
    """Compare open-to-close price returns on the stock's exact horizon dates."""
    market = select_market_benchmark(classification)
    benchmarks = {
        "market": market,
        "sector": classification.get("sector_benchmark"),
        "industry": classification.get("industry_benchmark"),
    }
    result = {}
    for kind, symbol in benchmarks.items():
        if not symbol:
            result[kind] = {"status": "missing_point_in_time_classification"}
            continue
        bars = benchmark_bars.get(symbol, {})
        entry = bars.get(outcome.get("next_open_date"))
        if not entry or (price := d(entry["open"])) <= 0:
            result[kind] = {"status": "missing_or_invalid_benchmark_entry", "symbol": symbol}
            continue
        metrics = {}
        for horizon, observation in outcome.get("horizons", {}).items():
            if observation["status"] != "ok":
                metrics[horizon] = {"status": "missing_stock_outcome"}
                continue
            end = bars.get(observation["end_date"])
            if not end or (close := d(end["close"])) <= 0:
                metrics[horizon] = {"status": "missing_or_invalid_benchmark_end"}
                continue
            percent = (close / price - 1) * Decimal(100)
            stock = d(observation["next_open"]["end_return_percent"])
            metrics[horizon] = {
                "status": "ok", "benchmark_return_percent": str(percent),
                "stock_excess_percentage_points": str(stock - percent),
            }
        result[kind] = {"status": "ok", "symbol": symbol, "horizons": metrics}
    return result
