"""Parse original SEC Form 4 submissions into auditable purchase records.

Pure standard-library module. Parsing is intentionally conservative: code P is
a candidate, not proof of discretionary buying. Preserve flags for review.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
import xml.etree.ElementTree as ET

ACCEPTED_RE = re.compile(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", re.I)
XML_RE = re.compile(r"<XML>(.*?)</XML>", re.I | re.S)


def value(element, path):
    node = element.find(path) if element is not None else None
    return (node.text or "").strip() if node is not None else ""


def decimal(text):
    try:
        return str(Decimal(text)) if text else None
    except InvalidOperation:
        return None


@dataclass
class Purchase:
    issuer_cik: str
    issuer_name: str
    issuer_ticker: str
    owner_ciks: list[str]
    owner_names: list[str]
    acceptance_datetime: str | None
    transaction_date: str
    security_title: str
    shares: str | None
    price_per_share: str | None
    transaction_value: str | None
    acquired_disposed: str
    direct_indirect: str
    ownership_nature: str
    footnote_ids: list[str]
    review_flags: list[str]


def parse_form4(raw: str) -> dict:
    """Return raw candidate code-P rows, never assert discretionary eligibility."""
    match = ACCEPTED_RE.search(raw)
    accepted = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").isoformat() if match else None
    blocks = XML_RE.findall(raw)
    if not blocks and "<ownershipDocument" in raw:
        blocks = [raw]
    root = None
    for block in blocks:
        try:
            candidate = ET.fromstring(block.strip())
        except ET.ParseError:
            continue
        if candidate.tag.split("}")[-1] == "ownershipDocument":
            root = candidate
            break
    if root is None:
        raise ValueError("No valid ownershipDocument XML found in SEC submission")
    def nodes(tag):
        return [e for e in root.iter() if e.tag.split("}")[-1] == tag]
    issuer = nodes("issuer")
    issuer = issuer[0] if issuer else None
    owners = nodes("reportingOwner")
    owner_ciks = [value(o, "reportingOwnerId/rptOwnerCik") for o in owners]
    owner_names = [value(o, "reportingOwnerId/rptOwnerName") for o in owners]
    relationships = {"isDirector": "Director", "isOfficer": "Officer",
                     "isTenPercentOwner": "10% Owner", "isOther": "Other"}
    reporting_owners = [
        {"cik": cik, "name": name, "title": value(owner, "reportingOwnerRelationship/officerTitle"),
         "relationship": ", ".join(label for field, label in relationships.items()
                                   if value(owner, f"reportingOwnerRelationship/{field}").lower() in {"1", "true"})}
        for owner, cik, name in zip(owners, owner_ciks, owner_names)
    ]
    footnotes = {e.get("id"): (e.text or "").strip() for e in nodes("footnote")}
    purchases = []
    for tx in nodes("nonDerivativeTransaction"):
        if value(tx, "transactionCoding/transactionCode").upper() != "P":
            continue
        shares = decimal(value(tx, "transactionAmounts/transactionShares/value"))
        price = decimal(value(tx, "transactionAmounts/transactionPricePerShare/value"))
        amount = str(Decimal(shares) * Decimal(price)) if shares is not None and price is not None else None
        refs = [e.get("id") for e in tx.iter() if e.tag.split("}")[-1] == "footnoteId" and e.get("id")]
        note = " ".join(footnotes.get(fid, "") for fid in refs).lower()
        flags = []
        if "10b5-1" in note or "10b5" in note:
            flags.append("possible_10b5_1")
        if any(x in note for x in ("automatic", "dividend reinvest", "directed share", "underwriter", "ipo")):
            flags.append("possible_non_discretionary")
        if not accepted:
            flags.append("missing_acceptance_timestamp")
        if shares is None or price is None:
            flags.append("missing_numeric_amount")
        if value(tx, "transactionAmounts/transactionAcquiredDisposedCode/value").upper() != "A":
            flags.append("not_acquisition")
        if not owner_ciks or not all(owner_ciks):
            flags.append("missing_owner_identity")
        purchases.append(Purchase(
            issuer_cik=value(issuer, "issuerCik"),
            issuer_name=value(issuer, "issuerName"),
            issuer_ticker=value(issuer, "issuerTradingSymbol"),
            owner_ciks=owner_ciks, owner_names=owner_names,
            acceptance_datetime=accepted,
            transaction_date=value(tx, "transactionDate/value"),
            security_title=value(tx, "securityTitle/value"),
            shares=shares, price_per_share=price, transaction_value=amount,
            acquired_disposed=value(tx, "transactionAmounts/transactionAcquiredDisposedCode/value"),
            direct_indirect=value(tx, "ownershipNature/directOrIndirectOwnership/value"),
            ownership_nature=value(tx, "ownershipNature/natureOfOwnership/value"),
            footnote_ids=refs, review_flags=flags,
        ))
    return {
        "owners": reporting_owners,
        "document_type": value(root, "documentType"),
        "acceptance_datetime": accepted,
        "issuer_cik": value(issuer, "issuerCik"),
        "candidate_purchase_count": len(purchases),
        "candidate_purchases": [asdict(p) for p in purchases],
        "footnotes": footnotes,
        "status": "candidate_only_requires_eligibility_review",
    }
