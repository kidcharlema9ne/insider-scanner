"""Point-in-time research statistics for insider purchase outcomes.

Inputs are disclosure-level observations, one per eligible investor entry.
Never count individual transaction lines as separate stock-performance observations.
ATR returns are primary. No composite score.
"""
from collections import defaultdict
from decimal import Decimal
from math import sqrt

def _decimal(x):
    if x is None or x=="": return None
    try: return Decimal(str(x))
    except (ValueError,ArithmeticError): return None

def summarize(observations, group_keys=("role",), horizon="21", metric="end_return_atr"):
    """Summarize disclosed investor opportunities with explicit denominators.

    Each observation must contain opportunity_id, episode_id, horizons, and group fields.
    The optional horizon record is the existing price_outcomes shape, whose executable
    baseline is horizons[horizon]['next_open']. Only successful, finite numeric outcomes
    contribute to statistics. All exclusions remain counted and visible.
    """
    groups=defaultdict(list)
    seen=set()
    for r in observations:
        oid=r.get("opportunity_id")
        if not oid: raise ValueError("Each observation needs a stable opportunity_id")
        if oid in seen: raise ValueError("Duplicate opportunity_id: "+str(oid))
        seen.add(oid)
        key=tuple(str(r.get(k,"unknown") or "unknown") for k in group_keys)
        groups[key].append(r)
    output=[]
    for key,rows in sorted(groups.items()):
        values=[]
        episodes=defaultdict(list)
        excluded=defaultdict(int)
        ungrouped = 0
        for r in rows:
            h=r.get("horizons",{}).get(str(horizon),{})
            if h.get("status")!="ok":
                excluded[h.get("status") or (r.get("outcome_status") if r.get("outcome_status") != "ok" else None) or "missing_horizon"]+=1
                continue
            v=_decimal(h.get("next_open",{}).get(metric))
            if v is None or not v.is_finite():
                excluded["invalid_metric"]+=1
                continue
            values.append(v)
            memberships = r.get("episode_ids")
            if memberships is None:
                memberships = [r["episode_id"]] if r.get("episode_id") else []
            if not memberships:
                ungrouped += 1
            for episode_id in set(memberships):
                episodes[episode_id].append(v)
        n=len(values)
        mean=sum(values)/n if n else None
        wins=sum(v>0 for v in values)
        ep_wins=sum(any(v>0 for v in vs) for vs in episodes.values())
        sorted_values=sorted(values)
        median=(sorted_values[(n-1)//2]+sorted_values[n//2])/2 if n else None
        sd=(sum((float(v-mean))**2 for v in values)/(n-1))**0.5 if n>1 else None
        se=sd/sqrt(n) if sd is not None else None
        output.append({
            "group":dict(zip(group_keys,key)),"horizon":str(horizon),"metric":metric,
            "total_opportunities":len(rows),"valid_opportunities":n,
            "excluded_opportunities":len(rows)-n,"exclusion_reasons":dict(sorted(excluded.items())),
            "distinct_valid_episodes":len(episodes),"valid_opportunities_without_episode":ungrouped,"winning_opportunities":wins,
            "winning_episodes":ep_wins,"opportunity_win_rate":str(Decimal(wins)/n) if n else None,
            "episode_win_rate":str(Decimal(ep_wins)/len(episodes)) if episodes else None,
            "mean_atr":str(mean) if mean is not None else None,
            "median_atr":str(median) if median is not None else None,
            "sample_standard_deviation_atr":sd,"standard_error_atr":se,
            "interpretation":"Descriptive; non-independent observations and selection bias may invalidate naive confidence intervals."
        })
    return output


def chronological_samples(observations, validation_start):
    """Separate cohorts and purge development labels that reach validation."""
    from datetime import date

    boundary = date.fromisoformat(validation_start)
    result = {"development": [], "validation": [], "purged": [], "undated": []}
    for row in observations:
        entry = row.get("next_open_date")
        if not entry:
            result["undated"].append(row)
            continue
        if date.fromisoformat(entry) >= boundary:
            result["validation"].append(row)
            continue
        ends = [date.fromisoformat(h["end_date"]) for h in row.get("horizons", {}).values()
                if h.get("status") == "ok"]
        cohort = "purged" if any(end >= boundary for end in ends) else "development"
        result[cohort].append(row)
    return result


def adjust_false_discovery_rate(p_values):
    """Benjamini–Hochberg adjusted p-values for one prespecified family."""
    ordered = []
    for i, value in enumerate(p_values):
        p = _decimal(value)
        if p is None or not p.is_finite() or not 0 <= p <= 1:
            raise ValueError("FDR adjustment requires finite p-values between zero and one")
        ordered.append((p, i))
    ordered.sort()
    adjusted = [None] * len(ordered)
    running_min = Decimal(1)
    for rank in range(len(ordered), 0, -1):
        p, index = ordered[rank - 1]
        running_min = min(running_min, p * len(ordered) / rank)
        adjusted[index] = running_min
    return adjusted
