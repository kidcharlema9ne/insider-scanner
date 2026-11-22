import unittest
from form4_parser import parse_form4

XML = """<ownershipDocument>
<documentType>4</documentType>
<issuer><issuerCik>12345</issuerCik><issuerName>Example Inc</issuerName><issuerTradingSymbol>EXM</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>789</rptOwnerCik><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId></reportingOwner>
<nonDerivativeTable>
<nonDerivativeTransaction>
<securityTitle><value>Common Stock</value></securityTitle>
<transactionDate><value>2026-11-02</value></transactionDate>
<transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>12.50</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
<footnoteId id="F1"/>
</nonDerivativeTransaction>
<nonDerivativeTransaction><transactionCoding><transactionCode>S</transactionCode></transactionCoding></nonDerivativeTransaction>
</nonDerivativeTable>
<footnotes><footnote id="F1">Purchase pursuant to Rule 10b5-1 plan.</footnote></footnotes>
</ownershipDocument>"""


class ParserTests(unittest.TestCase):
    def test_candidate_not_automatic_qualification(self):
        result = parse_form4("<ACCEPTANCE-DATETIME>20261103170512\n<XML>" + XML + "</XML>")
        self.assertEqual(result["candidate_purchase_count"], 1)
        purchase = result["candidate_purchases"][0]
        self.assertEqual(purchase["transaction_value"], "1250.00")
        self.assertEqual(purchase["acceptance_datetime"], "2026-11-03T17:05:12")
        self.assertIn("possible_10b5_1", purchase["review_flags"])
        self.assertEqual(result["status"], "candidate_only_requires_eligibility_review")

    def test_raw_xml_and_missing_timestamp(self):
        result = parse_form4(XML)
        self.assertIsNone(result["acceptance_datetime"])
        self.assertIn("missing_acceptance_timestamp", result["candidate_purchases"][0]["review_flags"])

    def test_reject_invalid(self):
        with self.assertRaises(ValueError):
            parse_form4("not a Form 4")


if __name__ == "__main__":
    unittest.main()
