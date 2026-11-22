import unittest
from sec_amendments_and_identity import amendment_groups,resolve_security

class AmendmentIdentityTests(unittest.TestCase):
    def test_amendment_never_erases_original(self):
        original={"accession":"a","form":"4","filing_date":"2026-01-05","issuer_cik":"1",
                  "security_title":"Common Stock","owners":[{"cik":"10"}]}
        amended={**original,"accession":"b","form":"4/A","filing_date":"2026-01-07"}
        r=amendment_groups([amended,original])
        self.assertEqual(r[0]["possible_original_accessions"],["a"])
        self.assertFalse(r[0]["automatically_suppressed"])
        self.assertEqual(r[0]["status"],"requires_explicit_link")
    def test_unmatched_amendment(self):
        r=amendment_groups([{"accession":"b","form":"4/A","filing_date":"2026-01-07",
          "issuer_cik":"1","security_title":"Common Stock","owners":[]}])
        self.assertEqual(r[0]["status"],"unmatched_amendment")
    def test_point_in_time_security(self):
        old={"issuer_cik":"1","ticker":"ABC","security_title":"Common Stock",
             "start_date":"2006-01-01","end_date":"2010-12-31","security_id":"old"}
        new={**old,"start_date":"2011-01-01","end_date":None,"security_id":"new"}
        self.assertEqual(resolve_security("1","ABC","Common Stock","2008-01-02",[old,new])["security_id"],"old")
        self.assertEqual(resolve_security("1","ABC","Common Stock","2018-01-02",[old,new])["security_id"],"new")
        self.assertEqual(resolve_security("2","ABC","Common Stock","2008-01-02",[old,new])["status"],"unmatched")
        self.assertEqual(resolve_security("1","ABC","Common Stock","2008-01-02",[old,old|{"security_id":"other"}])["status"],"ambiguous")
if __name__=="__main__":unittest.main()
