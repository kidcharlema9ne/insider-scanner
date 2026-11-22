"""SEC Form 3/4/5 quarterly ZIP importer. Standard library; preserves raw rows."""
import csv, io, json, re, sqlite3, zipfile
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

def rows(z, filename):
    with z.open(filename) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace", newline=""), delimiter="\t")

def sec_date(value):
    """Normalize source dates while retaining original values in the raw tables."""
    if not value:
        return None
    value = value.strip()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        try:
            return datetime.strptime(value, "%d-%b-%Y").date().isoformat()
        except ValueError:
            return None


def number(x):
    try:
        return str(Decimal(x)) if x not in ("", None) else None
    except (InvalidOperation, TypeError):
        return None

def flag_text(s):
    s=(s or "").lower()
    flags=[]
    if re.search(r"10b5[ -]?1|trading plan|rule 10b5",s): flags.append("possible_10b5_1")
    if re.search(r"automatic|dividend reinvest|employee stock purchase|directed share|ipo allocation|underwrit",s):
        flags.append("possible_non_discretionary")
    return flags

def extract(z):
    """Yield transaction-level candidates, never preemptively label discretionary."""
    submission={r["ACCESSION_NUMBER"]:r for r in rows(z,"SUBMISSION.tsv")}
    owners=defaultdict(list)
    for r in rows(z,"REPORTINGOWNER.tsv"):
        owners[r["ACCESSION_NUMBER"]].append({"cik":r.get("RPTOWNERCIK",""),"name":r.get("RPTOWNERNAME",""),"relationship":r.get("RPTOWNER_RELATIONSHIP",""),"title":r.get("RPTOWNER_TITLE","")})
    notes=defaultdict(dict)
    for r in rows(z,"FOOTNOTES.tsv"):
        notes[r["ACCESSION_NUMBER"]][r["FOOTNOTE_ID"]]=r.get("FOOTNOTE_TXT","")
    for r in rows(z,"NONDERIV_TRANS.tsv"):
        if r.get("TRANS_CODE","").upper()!="P": continue
        acc=r["ACCESSION_NUMBER"]
        sub=submission.get(acc)
        if sub is None: continue
        if sub.get("DOCUMENT_TYPE","").upper() not in ("4","4/A"): continue
        ids=set()
        for k,v in r.items():
            if k.endswith("_FN") and v:
                ids.update(re.findall(r"F\d+|\w+",v))
        texts=[notes[acc][i] for i in sorted(ids) if i in notes[acc]]
        combined=" ".join([sub.get("REMARKS",""),*texts,r.get("NATURE_OF_OWNERSHIP","")])
        flags=flag_text(combined)
        if sub.get("AFF10B5ONE","").strip().upper() in ("1","Y","YES","TRUE"):
            flags.append("filing_affirms_10b5_1")
        if r.get("TRANS_ACQUIRED_DISP_CD","").upper()!="A": flags.append("not_acquisition")
        if not owners[acc]: flags.append("missing_owner")
        shares=number(r.get("TRANS_SHARES"))
        price=number(r.get("TRANS_PRICEPERSHARE"))
        if shares is None or price is None: flags.append("missing_numeric_amount")
        amount=str(Decimal(shares)*Decimal(price)) if shares is not None and price is not None else None
        filing_date = sec_date(sub.get("FILING_DATE"))
        transaction_date = sec_date(r.get("TRANS_DATE"))
        if filing_date is None: flags.append("missing_or_invalid_filing_date")
        if transaction_date is None: flags.append("missing_or_invalid_transaction_date")
        yield {
            "accession":acc,"transaction_row_key":r.get("NONDERIV_TRANS_SK",""),
            "form":sub.get("DOCUMENT_TYPE"),"filing_date":filing_date,
            "transaction_date":transaction_date,"issuer_cik":sub.get("ISSUERCIK"),
            "issuer_name":sub.get("ISSUERNAME"),"ticker_at_filing":sub.get("ISSUERTRADINGSYMBOL"),
            "security_title":r.get("SECURITY_TITLE"),"shares":shares,"price_per_share":price,
            "dollar_value":amount,"acquired_disposed":r.get("TRANS_ACQUIRED_DISP_CD"),
            "direct_indirect":r.get("DIRECT_INDIRECT_OWNERSHIP"),
            "nature_of_ownership":r.get("NATURE_OF_OWNERSHIP"),
            "shares_after":r.get("SHRS_OWND_FOLWNG_TRANS"),
            "owners":owners[acc],"footnote_ids":sorted(ids),"footnote_texts":texts,
            "filing_10b5_1_flag":sub.get("AFF10B5ONE"),
            "review_flags":sorted(set(flags)),
            "raw_transaction":r,"raw_submission":sub
        }

def init_db(db):
    db.execute("""CREATE TABLE IF NOT EXISTS purchase_candidates (
        accession TEXT NOT NULL, transaction_row_key TEXT NOT NULL,
        filing_date TEXT, transaction_date TEXT, issuer_cik TEXT, ticker TEXT,
        dollar_value TEXT, review_flags TEXT, payload TEXT NOT NULL,
        PRIMARY KEY (accession,transaction_row_key))""")
    db.execute("CREATE INDEX IF NOT EXISTS purchase_by_issuer_date ON purchase_candidates(issuer_cik,filing_date)")

def import_zip(payload, db):
    init_db(db)
    count=0
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        for record in extract(z):
            db.execute("""INSERT OR REPLACE INTO purchase_candidates
                (accession,transaction_row_key,filing_date,transaction_date,issuer_cik,ticker,dollar_value,review_flags,payload)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (record["accession"],record["transaction_row_key"],record["filing_date"],record["transaction_date"],
                 record["issuer_cik"],record["ticker_at_filing"],record["dollar_value"],
                 json.dumps(record["review_flags"]),json.dumps(record)))
            count+=1
    db.commit()
    return count

def disclosure_opportunities(db, start=None, end=None):
    """Group multiple transaction rows within a filing by issuer/security, preserving underlying rows."""
    grouped=defaultdict(list)
    query = "SELECT payload FROM purchase_candidates"
    if start is not None and end is not None:
        records = db.execute(query + " WHERE filing_date BETWEEN ? AND ?", (start, end))
    else:
        records = db.execute(query)
    for (payload,) in records:
        r=json.loads(payload)
        grouped[(r["accession"],r["issuer_cik"],r["security_title"])].append(r)
    for (accession,cik,security),group in grouped.items():
        amounts=[Decimal(r["dollar_value"]) for r in group if r["dollar_value"] is not None]
        shares=[Decimal(r["shares"]) for r in group if r["shares"] is not None]
        total_shares=sum(shares)
        total_amount=sum(amounts)
        yield {"accession":accession,"issuer_cik":cik,"security_title":security,
               "form":group[0]["form"],
               "filing_date":sec_date(group[0]["filing_date"]),
               "transaction_dates":sorted({day for r in group if (day := sec_date(r["transaction_date"]))}),
               "original_submission_date":sec_date(group[0].get("raw_submission", {}).get("DATE_OF_ORIG_SUB")),"ticker_at_filing":group[0]["ticker_at_filing"],
               "transaction_count":len(group),"aggregate_shares":str(total_shares) if len(shares)==len(group) else None,
               "aggregate_dollars":str(total_amount) if len(amounts)==len(group) else None,
               "insider_weighted_price":str(total_amount/total_shares) if len(amounts)==len(group) and len(shares)==len(group) and total_shares else None,
               "owners":group[0]["owners"],"review_flags":sorted(set(f for r in group for f in r["review_flags"])),
               "transaction_row_keys":[r["transaction_row_key"] for r in group]}
