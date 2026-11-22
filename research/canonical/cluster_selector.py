"""CANONICAL cluster selector for the insider-buying study (D-057 / D-058).

Every later test imports this module. It does NOT re-implement the selector. It runs ChatGPT's recovered
code (research/recovered_20261107/{matrix_warm,wider,liquidity_tiers}.py, byte-identical to branch
recovery/nov7-cohort-provenance tip c4fb693) and exposes the result. The workflow that calls it first checks
the recovered files are unchanged.

Unapproved choices that live inside the recovered selector (Michael has NOT approved these; see SHARED_LOG Entry 7):
  1. sole-owner filings only (joint filings dropped)
  2. entity-like owner names excluded by the regex `entity`
  3. one representative filing per cluster (prefers outcome_status ok, then earliest filing date, accession)

Usage (inputs are the saved Actions artifacts, laid out as zips in `workdir`: matrix.zip, 1.zip, zero.zip,
and `current_zip` with the 15-session dollar-volume feature):
    from cluster_selector import load_cohort
    c = load_cohort('/tmp/run_x', 'current.zip')
    c.all_trades   # 137 completed four-plus trades (dicts)
    c.liquid       # the 91 with average daily dollar volume >= $3M
"""
import contextlib, io, os, sys
from types import SimpleNamespace

RECOVERED = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'recovered_20261107')
FLOOR = 3_000_000


def load_cohort(workdir, current_zip='current.zip'):
    workdir = os.path.abspath(workdir)
    sys.path.insert(0, os.path.abspath(RECOVERED))
    cwd, argv = os.getcwd(), sys.argv
    os.chdir(workdir)
    sys.argv = ['liquidity_tiers.py', current_zip]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import liquidity_tiers as lt          # runs ChatGPT's code; its own assertions must pass
    finally:
        os.chdir(cwd); sys.argv = argv
    D = lt.D
    trades = []
    for tier, adv, opening, entry, ticker, row in lt.sample:
        i = lt.days.index(entry)
        regime = (D(lt.spy[lt.days[i-1]]['close']) - D(lt.spy[lt.days[i-16]]['close'])) / lt.mean(
            lt.true_range(k) for k in range(i-14, i))
        stock, spy_atr, excess = lt.returns(row)
        trades.append(dict(
            entry=entry, ticker=ticker, issuer_cik=row['issuer_cik'], tier=tier, cfo=tier >= 2,
            adv=float(adv), spy_regime_15=float(regime),
            decline_15_atr=float(-D(row['entry_features']['prior_returns']['15']['atr'])),
            entry_open=float(opening), atr14=float(row['atr14']),
            stock_atr=float(stock), spy_atr=float(spy_atr), excess_atr=float(excess), row=row))
    liquid = [t for t in trades if t['adv'] >= FLOOR]
    return SimpleNamespace(all_trades=trades, liquid=liquid, lt=lt)


def add_roles(c):
    """Add buyer-role fields to every trade (new code; reads the recovered selector's own data).
    t['ceo'], t['n_buyers'], t['n_pure_directors'] (Director and not Officer). Self-checks against the selector's
    buyer count and CFO flag on all trades."""
    import re
    lt = c.lt
    CFO_RE = re.compile(r'\b(?:CFO|chief financial officer)\b', re.I)      # same pattern as wider.py
    CEO_RE = re.compile(r'\b(?:CEO|chief executive officer)\b', re.I)
    where = {id(row): (key, i, n, cfo) for (key, i), (row, cfo, n) in lt.short.items()}
    bad = 0
    for t in c.all_trades:
        key, i, n, cfo = where[id(t['row'])]
        start, entry = lt.calendar[max(0, i-15)], lt.calendar[i]
        bs = [r for j, rs in lt.by_security[key].items() if j <= i for r in rs
              if any(start <= d < entry for d in r['transaction_dates'])]
        owners = {}
        for r in bs:
            o = r['owners'][0]; owners.setdefault(o['cik'], o)
        rel = lambda o: o['relationship'].split(',')
        t['n_buyers'] = len(owners)
        t['ceo'] = any('Officer' in rel(o) and CEO_RE.search(o['title'] or '') for o in owners.values())
        t['n_pure_directors'] = sum('Director' in rel(o) and 'Officer' not in rel(o) for o in owners.values())
        cfo2 = any('Officer' in r['owners'][0]['relationship'].split(',') and CFO_RE.search(r['owners'][0]['title'] or '') for r in bs)
        bad += (len(owners) != n) or (cfo2 != cfo)
    assert bad == 0, f'{bad} trades where rebuilt buyer sets disagree with the selector'
    return c
