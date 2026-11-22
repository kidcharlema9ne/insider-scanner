"""Expected published quarters for the current historical SEC snapshot."""

QUARTERS = frozenset(
    f"{year}q{quarter}_form345.zip"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 3)
)


def missing_quarters(names):
    return sorted(QUARTERS.difference(names))


SEC_CATALOG = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"


def catalog_links(html):
    """Read exact SEC-published ZIP links for this snapshot."""
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urlsplit

    links = {}

    class CatalogParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            href = dict(attrs).get("href")
            if tag != "a" or not href:
                return
            url = urljoin(SEC_CATALOG, href)
            parts = urlsplit(url)
            name = parts.path.rsplit("/", 1)[-1]
            if parts.scheme != "https" or parts.netloc != "www.sec.gov" or name not in QUARTERS:
                return
            if name in links and links[name] != url:
                raise ValueError(f"Multiple SEC catalog URLs for {name}")
            links[name] = url

    CatalogParser().feed(html)
    missing = missing_quarters(links)
    if missing:
        raise ValueError(f"SEC catalog missing {len(missing)} expected quarter links: {missing[:5]}")
    return links
