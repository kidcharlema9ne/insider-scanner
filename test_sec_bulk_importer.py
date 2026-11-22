import io, sqlite3, unittest, zipfile
from sec_bulk_importer import import_zip, disclosure_opportunities, sec_date

def fixture():
    tables={
    "SUBMISSION.tsv":"ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\tAFF10B5ONE\tREMARKS\nA\t2026-08-04\t4\t100\tAcme\tACME\t0\t\n",
    "REPORTINGOWNER.tsv":"ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\nA\t200\tJane Doe\tDirector\t\n",
    "FOOTNOTES.tsv":"ACCESSION_NUMBER\tFOOTNOTE_ID\tFOOTNOTE_TXT\nA\tF1\tPurchased under Rule 10b5-1 trading plan\n",
    "NONDERIV_TRANS.tsv":"ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tTRANS_CODE\tTRANS_DATE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\tSECURITY_TITLE\tSECURITY_TITLE_FN\tDIRECT_INDIRECT_OWNERSHIP\tNATURE_OF_OWNERSHIP\tSHRS_OWND_FOLWNG_TRANS\nA\t1\tP\t2026-08-01\t100\t50\tA\tCommon Stock\tF1\tD\t\t500\nA\t2\tP\t2026-08-02\t200\t55\tA\tCommon Stock\t\tD\t\t700\nA\t3\tS\t2026-08-02\t100\t60\tD\tCommon Stock\t\tD\t\t600\n"}
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w") as z:
        for n,s in tables.items():z.writestr(n,s)
    return out.getvalue()

class TestBulk(unittest.TestCase):
    def test_sec_source_dates(self):
        self.assertEqual(sec_date("06-NOV-2026"), "2026-11-06")
        self.assertIsNone(sec_date("31-FEB-2026"))

    def test_import_aggregate_and_idempotence(self):
        db=sqlite3.connect(":memory:")
        self.assertEqual(import_zip(fixture(),db),2)
        self.assertEqual(import_zip(fixture(),db),2)
        self.assertEqual(db.execute("select count(*) from purchase_candidates").fetchone()[0],2)
        records=list(disclosure_opportunities(db))
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]["form"], "4")
        self.assertEqual(records[0]["transaction_dates"], ["2026-08-01", "2026-08-02"])
        self.assertEqual(records[0]["aggregate_dollars"],"16000")
        self.assertEqual(records[0]["insider_weighted_price"],str(__import__("decimal").Decimal(16000)/__import__("decimal").Decimal(300)))
        self.assertIn("possible_10b5_1",records[0]["review_flags"])
if __name__=="__main__":unittest.main()
