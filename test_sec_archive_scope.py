import unittest

from sec_archive_scope import QUARTERS, catalog_links


class CatalogTests(unittest.TestCase):
    def test_uses_exact_official_links_and_requires_complete_scope(self):
        paths = {
            name: f"/files/{'datastandardsinnovation' if name == '2026q3_form345.zip' else 'structureddata'}/data/insider-transactions-data-sets/{name}"
            for name in QUARTERS
        }
        html = "".join(f'<a href="{path}">{name}</a>' for name, path in paths.items())
        links = catalog_links(html)
        self.assertEqual(len(links), 83)
        self.assertEqual(links["2006q1_form345.zip"], "https://www.sec.gov" + paths["2006q1_form345.zip"])
        self.assertEqual(links["2026q3_form345.zip"], "https://www.sec.gov" + paths["2026q3_form345.zip"])
        with self.assertRaisesRegex(ValueError, "missing"):
            catalog_links(html.replace(paths["2006q1_form345.zip"], "https://example.com/2006q1_form345.zip"))
