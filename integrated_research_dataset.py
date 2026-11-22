"""Join SEC disclosure opportunities to validated daily bars, without look-ahead.

Security identity is explicit. Unmatched and incomplete observations remain in output.
"""
from collections import defaultdict
from entry_features import stock_entry_features
from sec_amendments_and_identity import resolve_security
from price_outcomes import compare_disclosure
from research_benchmarks import benchmark_outcomes
from sec_episode_research import build_episodes, build_purchase_groups, prior_disclosure_counts

def _role(owners):
    titles=" ".join(str(o.get("title","")) for o in owners).lower()
    relationships=" ".join(str(o.get("relationship","")) for o in owners).lower()
    if "chief financial" in titles or "cfo" in titles:return "CFO"
    if "chief executive" in titles or "ceo" in titles:return "CEO"
    if "director" in relationships:return "Director"
    if "officer" in relationships:return "Officer"
    return "Unclassified"

def integrate(disclosures, bars_by_security, security_mappings=None, *, sessions=None, dated_mappings=None, classifications=None, benchmark_bars=None):
    """Return disclosure-level records, episode summary and quality accounting.

    bars_by_security maps stable security_id to chronological validated daily OHLCV.
    security_mappings maps (issuer_cik,ticker_at_filing,security_title) to stable IDs,
    or supply explicit security_id on a disclosure. Never guess by ticker alone.
    classifications maps (security_id, entry_date) to verified entry-time exchange,
    index membership, and optional sector or industry benchmark symbols.
    """
    disclosures=list(disclosures)
    security_mappings=security_mappings or {}
    if dated_mappings is not None and security_mappings:
        raise ValueError("Supply either dated mappings or the legacy static mapping")
    mapping_index = defaultdict(list)
    if dated_mappings is not None:
        for mapping in dated_mappings:
            if not mapping.get("start_date") or not mapping.get("security_id"):
                raise ValueError("Dated mapping requires start_date and security_id")
            mapping_index[str(mapping.get("issuer_cik", ""))].append(mapping)
    episodes=build_episodes(disclosures)
    episode_for={}
    for i,e in enumerate(episodes):
        for accession in e["accessions"]:
            episode_for.setdefault((accession,e["owner_cik"]),f"episode-{i+1}")
    history=prior_disclosure_counts(disclosures)
    result=[]
    seen=set()
    for r in disclosures:
        oid="|".join(str(r.get(k,"")) for k in ("accession","issuer_cik","security_title"))
        if oid in seen:raise ValueError("Duplicate disclosure/security opportunity: "+oid)
        seen.add(oid)
        owners=r.get("owners") or []
        owner_ids=sorted({str(o.get("cik")) for o in owners if o.get("cik")})
        key=(str(r.get("issuer_cik") or ""),str(r.get("ticker_at_filing") or ""),str(r.get("security_title") or ""))
        if dated_mappings is not None:
            match = (resolve_security(*key, r["filing_date"], mapping_index[key[0]])
                     if r.get("filing_date") else {"status": "missing_filing_date"})
            sid = match.get("security_id")
        else:
            sid = r.get("security_id") or security_mappings.get(key)
            match = {"status": "provided" if sid else "unmatched"}
        item={"opportunity_id":oid,"accession":r.get("accession"),"issuer_cik":r.get("issuer_cik"),
              "ticker_at_filing":r.get("ticker_at_filing"),"security_title":r.get("security_title"),
              "filing_date":r.get("filing_date"),"security_id":sid,"role":_role(owners),
              "transaction_dates":r.get("transaction_dates", []), "owners":owners,"owner_ciks":owner_ids,"review_flags":r.get("review_flags",[]),
              "aggregate_dollars":r.get("aggregate_dollars"),
              "insider_weighted_price":r.get("insider_weighted_price"),
              "prior_disclosures_by_owner":{o:history.get((str(r.get("issuer_cik") or ""),o,r.get("accession")),0) for o in owner_ids},
              "episode_ids":[episode_for[(r["accession"],o)] for o in owner_ids if (r["accession"],o) in episode_for],
              "episode_id":episode_for.get((r["accession"],owner_ids[0])) if len(owner_ids)==1 else None,
              "security_match":match, "outcome_status":"not_computed","horizons":{}}
        if not sid:
            item["outcome_status"]="unmatched_security"
        elif sid not in bars_by_security:
            item["outcome_status"]="missing_price_series"
        elif not r.get("filing_date"):
            item["outcome_status"]="missing_filing_date"
        else:
            outcome=compare_disclosure(bars_by_security[sid],r["filing_date"], sessions=sessions)
            item["outcome_status"]=outcome["status"]
            if outcome["status"] == "ok" and classifications is not None:
                classification = classifications.get((sid, outcome["next_open_date"]), {})
                item["benchmarks"] = benchmark_outcomes(outcome, classification, benchmark_bars or {})
            item["horizons"]=outcome.get("horizons",{})
            if outcome["status"] == "ok" and sessions is not None:
                item["entry_features"] = stock_entry_features(
                    bars_by_security[sid], sessions, outcome["next_open_date"], outcome["atr14"]
                )
            for k in ("next_open","next_open_date","atr14","entry_gap_atr","entry_gap_percent","filing_close","filing_close_status"):
                if k in outcome:item[k]=outcome[k]
        result.append(item)
    campaigns = build_purchase_groups(result, sessions, campaign=True)
    if sessions is not None:
        episodes = build_purchase_groups(result, sessions)
        for groups, field in ((episodes, "episode_ids"), (campaigns, "campaign_ids")):
            memberships = defaultdict(list)
            for group in groups:
                for oid in group["opportunity_ids"]:
                    memberships[oid].append(group["group_id"])
            for item in result:
                item[field] = memberships[item["opportunity_id"]]
        for item in result:
            item["episode_id"] = item["episode_ids"][0] if len(item["episode_ids"]) == 1 else None
    return {"schema_version":1,"entry_rule":"D-051: next regular session open after SEC filing date",
            "opportunities":result,"episodes":episodes,"campaigns":campaigns,
            "counts":{"disclosures":len(result),"episodes":len(episodes),
                      "priced":sum(r["outcome_status"]=="ok" for r in result),
                      "unpriced":sum(r["outcome_status"]!="ok" for r in result)}}
