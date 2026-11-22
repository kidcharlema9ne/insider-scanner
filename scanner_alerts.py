"""Prepare SEC filing alerts without depending on a fresh market-price feed.

The caller supplies a verified filing event and the latest completed daily bar.
No network request or Pushover delivery occurs in this module.
"""
from datetime import date

def build_alert(event, daily_bar=None):
    required=("accession","filing_datetime","issuer_name","ticker")
    missing=[k for k in required if not event.get(k)]
    if missing: raise ValueError("Missing required SEC filing fields: "+", ".join(missing))
    ticker=event["ticker"]
    lines=[f"SEC Form 4 purchase candidate: {ticker}",
           str(event["issuer_name"]),
           f"Filed: {event['filing_datetime']}",
           f"SEC accession: {event['accession']}"]
    if event.get("insider_name"):lines.append(f"Insider: {event['insider_name']}")
    if event.get("purchase_dollars") is not None:lines.append(f"Reported purchase: ${event['purchase_dollars']}")
    flags=event.get("review_flags") or []
    if flags:lines.append("Review flags: "+", ".join(flags))
    if daily_bar is None:
        lines.append("Price: unavailable (filing alert not delayed)")
    else:
        if not daily_bar.get("date") or daily_bar.get("close") is None:
            raise ValueError("Daily price requires an explicit session date and close")
        if str(daily_bar["date"])>str(date.today()):
            raise ValueError("Future daily-price date")
        lines.append(f"Last completed daily close ({daily_bar['date']}): ${daily_bar['close']}")
        lines.append("Historical daily close; NOT a live quote")
        if daily_bar.get("atr14") is not None:
            lines.append(f"Last calculated ATR(14): ${daily_bar['atr14']}")
    lines.append("Candidate only; discretionary status requires review.")
    return {"title":f"Insider P candidate: {ticker}",
            "message":"\n".join(lines),
            "priority":0,
            "dedupe_key":str(event["accession"])+":"+str(event.get("security_title","common"))}
