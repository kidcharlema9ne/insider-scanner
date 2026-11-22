"""Conservative, auditable Form 4 amendment and point-in-time security resolution.

Never merge an amendment with its original merely because issuer/owner/date match.
Never infer a historical ticker from a present-day ticker.
"""
from collections import defaultdict
from datetime import date

def amendment_groups(disclosures):
    """Flag possible amendment families without deleting original public opportunities."""
    by_key=defaultdict(list)
    for r in disclosures:
        owners=tuple(sorted(str(o.get("cik","")) for o in r.get("owners",[]) if o.get("cik")))
        key=(str(r.get("issuer_cik","")),owners,str(r.get("security_title","")))
        by_key[key].append(r)
    results=[]
    for key,items in by_key.items():
        items.sort(key=lambda x:(str(x.get("filing_date","")),str(x.get("accession",""))))
        for r in items:
            if str(r.get("form","")).upper()=="4/A":
                prior=[p["accession"] for p in items if str(p.get("filing_date",""))<=str(r.get("filing_date",""))
                       and p["accession"]!=r["accession"] and str(p.get("form","")).upper()=="4"]
                results.append({"amendment_accession":r["accession"],"possible_original_accessions":prior,
                                "status":"requires_explicit_link" if prior else "unmatched_amendment",
                                "automatically_suppressed":False})
    return results

def resolve_security(issuer_cik, ticker_at_filing, security_title, filing_date, mappings):
    """Require unique point-in-time issuer/security match; otherwise flag unresolved.

    mappings: iterable of dicts {issuer_cik,ticker,security_title,start_date,end_date,security_id}.
    End date inclusive. No fuzzy or present-day mapping is silently accepted.
    """
    matches=[]
    for m in mappings:
        if str(m.get("issuer_cik",""))!=str(issuer_cik):continue
        if str(m.get("ticker","")).upper()!=str(ticker_at_filing or "").upper():continue
        if str(m.get("security_title","")).casefold()!=str(security_title or "").casefold():continue
        if m.get("start_date") and filing_date<m["start_date"]:continue
        if m.get("end_date") and filing_date>m["end_date"]:continue
        if m.get("security_id"):matches.append(m["security_id"])
    ids=sorted(set(matches))
    if len(ids)==1:return {"status":"matched","security_id":ids[0]}
    return {"status":"ambiguous" if ids else "unmatched","candidate_security_ids":ids}
