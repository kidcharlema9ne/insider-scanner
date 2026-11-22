"""Cross of two leads on the primary set: C16 lead63 (ONEQ minus SPY, 63 sessions; Entries 37 and 39) with the C8 12-month decline measures (Entry 36).

Question: is the Nasdaq-lagging result (lead63 lowest fifth, 'Q1') the same effect as the deep-decline result, or a separate one?
Development years only (entries <= 2020-12-31, D-068). The 2026 pilot is NOT used (79 of 80 pilot entries sit in one regime, Entry 37). Returns are the
Entry 28 results (run 42490748366); decline features are from run 42499472150 (Entry 36); lead63 is from run 42501167019 (Entry 37). This script
computes no new returns and no new features; it only joins them and tabulates. Exploratory: a lead, not a rule.

Declared before the run (nothing below was chosen after seeing a cross result):
  Bands.   lead63 band = lowest fifth (Q1, Nasdaq lagging), highest fifth (Q5), middle three fifths, cut points recomputed on the joined development rows
           (they must reproduce Entry 39: <= -0.0176 and >= +0.0391).  Decline group for a measure d = lowest fifth of d (fell most), highest fifth (fell
           least), middle three fifths.  Lower value of raw252 / rel252 / hi252 / raw126 = fell more.
  Primary decline measure: raw252 (the Entry 36 headline). Also reported, same layout: rel252, hi252, raw126.
  A. Overlap.    Spearman(lead63, d) for the four measures; share of lead63-Q1 events that fall in the 'fell most' group of d (20% if unrelated) and the
                 share of 'fell most' events that are lead63-Q1.  (4 + 8 descriptive numbers)
  B. 3x3 table.  decline group x lead63 band: n, entry weeks, separate entry spells (42-day rule), mean and median excess over SPY in ATR units.
                 Cells with n < 15 are marked and not interpreted.  (4 measures)
  C. Within-band decline relation.  Spearman(d, excess) inside lead63 Q1, middle, Q5 (n in each); and lead63 Q1 vs not-Q1 mean excess inside the
                 'fell most' group and inside the remaining events.  (descriptive)
  D. Regression, excess = a + b*fall [+ c*Q1 + e*Q5], fall = 1 - percentile rank of d (0 = fell least, 1 = fell most), so b is the excess gap between the
                 least and most fallen event.  Three models: decline alone, lead63 alone, both.  Ranges = quarter-block bootstrap (whole calendar quarters
                 resampled, 10,000 draws).  Key reading: does c (Q1) shrink toward zero once fall is in the model, and does b shrink once Q1 is in?
                 CHANCE TESTS (the only two): the Q1 coefficient c in the 'both' model for raw252, and the Q1 coefficient in the 'lead63 alone' model, each by
                 an exact circular shift of lead63 over the distinct entry dates (decline held fixed; keeps market persistence). Alone, not corrected.
  E. Without the three large episodes (2008Q4, 2011Q3, 2020Q1): table B and model D for raw252.
Not done on purpose: pilot cross (too small, one regime); any new cut point or window; any claim about Q5 beyond what is printed.
Questions on the tally: 12 overlap numbers, 4 3x3 tables (36 cells), within-band rho (12) and 8 group means, 3 models x 4 measures (coefficients), 2 chance tests.

Subset option (declared 8 Nov 2026 BEFORE the 2011-2020 run, Entry 40 option (b)): `--start 2011-01-01` keeps only development entries from that date, where the
share of events with no price series is 5-15% (Entry 38) instead of 22-42% in 2006-2010. Everything above is repeated unchanged on the subset (lead63 and decline cut
points are recomputed on the subset and will differ from Entry 39). Section F adds the Entry 36 decline result on the same subset: Spearman of excess with raw252,
rel252, hi252 and the within-week shuffle chance (10,000 draws, as Entry 36), plus the fell-most fifth vs fell-least fifth. Output now also prints the stock and SPY legs
(ATR) beside each excess (D-053). This is a survivorship-exposure check, not a new hypothesis; it adds no new statistics beyond F's 3 chance-tested correlations.

Usage:  python factor_cross.py cross DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER [--start YYYY-MM-DD]   |   --selftest
"""
import argparse, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, EPISODES, quarter
import factor_decline as fd
import factor_regime as fg

DECL = ('raw252', 'rel252', 'hi252', 'raw126')
PRIMARY = 'raw252'
SEED = 20261108
ENTRY39_CUTS = (-0.0176, 0.0391)


def bands(x, lo, hi):
    return ['Q1' if v <= lo else 'Q5' if v >= hi else 'mid' for v in x]


def groups(x, q=(0.2, 0.8)):
    import numpy as np
    lo, hi = np.quantile(x, list(q))
    return ['most' if v <= lo else 'least' if v >= hi else 'mid' for v in x]


def design(rows, m, model):
    """Columns for the regression models. model: 'decl' | 'lead' | 'both'."""
    import numpy as np
    n = len(rows)
    cols = []
    if model in ('decl', 'both'):
        r = fd.rank_avg([r_[m] for r_ in rows])
        cols.append(1.0 - r / (n - 1))
    if model in ('lead', 'both'):
        cols.append(np.array([1.0 if r_['band'] == 'Q1' else 0.0 for r_ in rows]))
        cols.append(np.array([1.0 if r_['band'] == 'Q5' else 0.0 for r_ in rows]))
    return np.column_stack([np.ones(n)] + cols)


def names(model):
    return {'decl': ['const', 'fall'], 'lead': ['const', 'Q1', 'Q5'], 'both': ['const', 'fall', 'Q1', 'Q5']}[model]


def block_boot(X, y, qid, nq, draws=10000):
    """Quarter-block bootstrap of OLS coefficients via per-quarter sufficient statistics."""
    import numpy as np
    p = X.shape[1]
    XtX = np.zeros((nq, p, p))
    Xty = np.zeros((nq, p))
    for q in range(nq):
        m = qid == q
        XtX[q] = X[m].T @ X[m]
        Xty[q] = X[m].T @ y[m]
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, nq, size=(draws, nq))
    A = XtX[idx].sum(axis=1)
    b = Xty[idx].sum(axis=1)
    return np.einsum('dij,dj->di', np.linalg.pinv(A), b)


def fit_report(rows, m, model, label):
    import numpy as np
    X = design(rows, m, model)
    y = np.array([r['excess_atr'] for r in rows])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    qs = sorted({quarter(r['entry']) for r in rows})
    qi = {q: i for i, q in enumerate(qs)}
    qid = np.array([qi[quarter(r['entry'])] for r in rows])
    bb = block_boot(X, y, qid, len(qs))
    out = []
    for j, nm in enumerate(names(model)):
        lo, hi = np.percentile(bb[:, j], [2.5, 97.5])
        out.append(f'{nm} {beta[j]:+.3f} [{lo:+.3f}, {hi:+.3f}]')
    print(f'    {label} {model:5s} n={len(rows)}, {len(qs)} quarters:  ' + '   '.join(out))
    return dict(zip(names(model), beta))


def shift_chance(rows, fdate, m, model, lo, hi, draws=None):
    """Exact circular shift of lead63 over the distinct entry dates; decline held fixed. Returns observed Q1 coefficient and two-sided chance."""
    import numpy as np
    dates = sorted({r['entry'] for r in rows})
    nd = len(dates)
    pos = {d: k for k, d in enumerate(dates)}
    di = np.array([pos[r['entry']] for r in rows])
    lead = np.array([fdate[d] for d in dates])
    y = np.array([r['excess_atr'] for r in rows])
    n = len(rows)
    fall = 1.0 - fd.rank_avg([r[m] for r in rows]) / (n - 1)
    j = names(model).index('Q1')

    def coef(s):
        x = lead[(di + s) % nd]
        q1 = (x <= lo).astype(float)
        q5 = (x >= hi).astype(float)
        cols = [np.ones(n)] + ([fall] if model == 'both' else []) + [q1, q5]
        return np.linalg.lstsq(np.column_stack(cols), y, rcond=None)[0][j]
    obs = coef(0)
    sims = np.array([abs(coef(s)) for s in range(1, nd)])
    return obs, float(((sims >= abs(obs) - 1e-12).sum() + 1) / (nd)), nd


def cell_line(rs):
    if not rs:
        return 'n=0'
    ds = sorted(r['entry'] for r in rs)
    ex = [r['excess_atr'] for r in rs]
    flag = '  (n<15, not interpreted)' if len(rs) < 15 else ''
    return (f'n={len(rs):3d} {len({fd.week_of(r) for r in rs}):3d}w {len(fg.spells(ds)):2d}sp  mean {statistics.fmean(ex):+.3f}  '
            f'median {statistics.median(ex):+.3f}  [stock {statistics.fmean(r["stock_atr"] for r in rs):+.3f} SPY {statistics.fmean(r["spy_atr"] for r in rs):+.3f}]{flag}')


def table3(rows, m, label):
    print(f'  {label} {m}: decline group (rows) x lead63 band (columns); n, entry weeks, spells, excess over SPY (ATR)')
    for g, gname in (('most', 'fell most'), ('mid', 'middle   '), ('least', 'fell least')):
        for b in ('Q1', 'mid', 'Q5'):
            print(f'    {gname:10s} | lead63 {b:3s}: {cell_line([r for r in rows if r["g_" + m] == g and r["band"] == b])}')


def load_joined(decline_folder, regime_folder, returns_folder):
    rows = fd.load(decline_folder, returns_folder)
    fdate = fg.load_features(regime_folder)
    out = []
    for r in rows:
        f = fdate.get(r['entry'])
        if f and 'lead63' in f and r['entry'] <= DEV_END and all(m in r for m in DECL):
            out.append({**r, 'lead63': f['lead63']})
    return sorted(out, key=lambda r: r['entry']), {d: f['lead63'] for d, f in fdate.items() if 'lead63' in f}


def cross(decline_folder, regime_folder, returns_folder, start=None):
    import numpy as np
    dev, fdate = load_joined(decline_folder, regime_folder, returns_folder)
    if start:
        dev = [r for r in dev if r['entry'] >= start]
        print(f'SUBSET: entries from {start} to {DEV_END} only')
    x = np.array([r['lead63'] for r in dev])
    lo, hi = np.quantile(x, [0.2, 0.8])
    print(f'development events with lead63 and all four decline measures: {len(dev)}; lead63 cut points {lo:+.4f} / {hi:+.4f} (Entry 39: {ENTRY39_CUTS[0]:+.4f} / {ENTRY39_CUTS[1]:+.4f})')
    for r, b in zip(dev, bands(x, lo, hi)):
        r['band'] = b
    for m in DECL:
        for r, g in zip(dev, groups([r[m] for r in dev])):
            r['g_' + m] = g
    ex = np.array([r['excess_atr'] for r in dev])
    print(f'all development rows: excess {ex.mean():+.3f} (n={len(dev)}); Q1 {np.mean([r["excess_atr"] for r in dev if r["band"] == "Q1"]):+.3f}')
    print('\n=== A. Overlap: are Nasdaq-lagging entries the same entries as deep-decline entries? ===')
    q1 = [r for r in dev if r['band'] == 'Q1']
    for m in DECL:
        a, b = fd.rank_avg([r['lead63'] for r in dev]), fd.rank_avg([r[m] for r in dev])
        rho = float(np.corrcoef(a, b)[0, 1])
        most = [r for r in dev if r['g_' + m] == 'most']
        print(f'  {m}: Spearman(lead63, {m}) {rho:+.3f}; lead63-Q1 events in the fell-most fifth {sum(r["g_" + m] == "most" for r in q1)}/{len(q1)} = '
              f'{sum(r["g_" + m] == "most" for r in q1) / len(q1):.1%} (20% if unrelated); fell-most events that are lead63-Q1 {sum(r["band"] == "Q1" for r in most)}/{len(most)} = '
              f'{sum(r["band"] == "Q1" for r in most) / len(most):.1%}')
    print('\n=== B. Decline group x lead63 band ===')
    for m in DECL:
        table3(dev, m, 'all development')
    print('\n=== C. Within-band decline relation, and lead63 inside decline groups ===')
    for m in DECL:
        for b in ('Q1', 'mid', 'Q5'):
            sub = [r for r in dev if r['band'] == b]
            rho = float(np.corrcoef(fd.rank_avg([r[m] for r in sub]), fd.rank_avg([r['excess_atr'] for r in sub]))[0, 1])
            print(f'  {m} inside lead63 {b:3s}: Spearman(d, excess) {rho:+.3f}  (n={len(sub)}; negative = deeper fall, better excess)')
        most = [r for r in dev if r['g_' + m] == 'most']
        rest = [r for r in dev if r['g_' + m] != 'most']
        for nm, grp in (('fell-most fifth', most), ('all other events', rest)):
            a = [r for r in grp if r['band'] == 'Q1']
            c = [r for r in grp if r['band'] != 'Q1']
            print(f'  {m} {nm}: lead63 Q1 {cell_line(a)}   |   not Q1 {cell_line(c)}')
    print('\n=== D. Regression (excess in ATR); coefficient [quarter-block 95% range]. fall: 0 = fell least, 1 = fell most ===')
    fits = {}
    for m in DECL:
        print(f'  -- {m}')
        for model in ('decl', 'lead', 'both'):
            fits[(m, model)] = fit_report(dev, m, model, 'all')
    print('  chance (exact circular shift of lead63 over entry dates; decline fixed; alone, not corrected):')
    for model in ('lead', 'both'):
        obs, p, nd = shift_chance(dev, fdate, PRIMARY, model, lo, hi)
        print(f'    Q1 coefficient, model {model} ({PRIMARY}): {obs:+.3f}, chance {p:.1%} over {nd} entry dates')
    print('\n=== E. Without the three large episodes ===')
    d2 = [r for r in dev if quarter(r['entry']) not in EPISODES]
    table3(d2, PRIMARY, 'without episodes')
    for model in ('decl', 'lead', 'both'):
        fit_report(d2, PRIMARY, model, 'no-episodes')
    if start:
        print('\n=== F. Entry 36 decline result on the same subset (excess in ATR; chance = excess shuffled inside the same entry week, 10,000 draws) ===')
        for m in ('raw252', 'rel252', 'hi252'):
            obs, p, n = fd.perm_rho(dev, m, 'excess_atr')
            print(f'  {m}: Spearman {obs:+.3f}, chance {p:.2%} (n={n})')
        for m in ('raw252', 'rel252', 'hi252'):
            print(f'  {m} fell-most fifth: {cell_line([r for r in dev if r["g_" + m] == "most"])}')
            print(f'  {m} fell-least fifth: {cell_line([r for r in dev if r["g_" + m] == "least"])}')
        print(f'  all subset events: {cell_line(dev)}')
    print('\nQuestions asked on this cohort in this entry: see the docstring tally (cross of two registered leads; descriptive tables plus 2 chance tests).')


def selftest():
    import numpy as np
    rng = np.random.default_rng(3)
    n = 1200
    dates = [f'{2008 + k // 100}-{1 + (k % 100) // 9:02d}-{1 + (k % 100) % 9 + 1:02d}' for k in range(n)]
    # no signal: coefficients near zero; planted decline-only effect recovered; Q1 label ignored
    lead = rng.normal(size=n)
    d = rng.normal(size=n)
    for case in ('decline', 'lead'):
        if case == 'decline':
            y = -0.8 * d + rng.normal(size=n)
        else:
            y = np.where(lead <= np.quantile(lead, 0.2), 0.8, 0.0) + rng.normal(size=n)
        rows = [{'entry': dates[k], 'excess_atr': float(y[k]), 'raw252': float(d[k]), 'band': b} for k, b in enumerate(bands(lead, *np.quantile(lead, [0.2, 0.8])))]
        X = design(rows, 'raw252', 'both')
        beta = np.linalg.lstsq(X, np.array([r['excess_atr'] for r in rows]), rcond=None)[0]
        if case == 'decline':
            assert beta[1] > 0.8 and abs(beta[2]) < 0.35, beta     # fall coefficient ~ 0.8 * (2 * 0.29 * 3.46 / ...) positive, Q1 near zero
        else:
            assert beta[2] > 0.6 and abs(beta[1]) < 0.35, beta
    g = groups(list(range(100)))
    assert g.count('most') == 20 and g.count('least') == 20 and g[0] == 'most' and g[-1] == 'least'
    assert bands([0, 5, 10], 1, 9) == ['Q1', 'mid', 'Q5']
    a = block_boot(np.column_stack([np.ones(40), np.arange(40.0)]), np.arange(40.0) * 2 + 1, np.repeat(np.arange(8), 5), 8, draws=50)
    assert np.allclose(a[:, 1], 2.0, atol=1e-6) and np.allclose(a[:, 0], 1.0, atol=1e-6)
    print('factor_cross self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
        raise SystemExit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('decline')
    ap.add_argument('regime')
    ap.add_argument('returns')
    ap.add_argument('--start')
    a = ap.parse_args()
    if a.cmd == 'cross':
        cross(a.decline, a.regime, a.returns, a.start)
    else:
        raise SystemExit(__doc__)
