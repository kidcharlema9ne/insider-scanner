"""Score scan (POST HOC, Michael's idea 8 Nov 2026): one point each for (R) no CEO and no CFO among the buyers [or no CFO alone],
(N) Nasdaq lagging SPY (lead63 lowest fifth), (D) a deep 12-month fall. Base rule (four or more distinct buyers) = 0 points.
Does the 21-session excess over same-window SPY rise with the score?

Development years only (entries <= 2020-12-31, D-068); the 2026 pilot is not used (no lead63 spread, Entry 37). No sealed return is read.
Returns = Entry 28 (run 42490748366); decline features = Entry 36 (run 42499472150); lead63 = Entry 37 (run 42501167019); buyer roles =
Entry 32 events (run 42493259014, `factor_roles.roles` patterns unchanged). No new features, returns or role parsing; this script joins and tabulates.

Flags (cut points recomputed on the joined cohort; the lead63 cut must reproduce Entry 41 when the cohort is n=1,273):
  R1  neither CEO nor CFO among the buyers (Entry 32 C3)            R2  no CFO among the buyers (Michael's alternative wording)
  N   lead63 <= its 20th percentile (Q1, Nasdaq lagging)            (Entries 37, 39, 41)
  D1  raw252 <= its 20th percentile (fell most over 12 months)      (Entry 36 fifth, fixed before any bucket scan)
  D2  raw252 <= -20 ATR (down 20+ ATR over 12 months)               (from the Entry 49 scan: chosen AFTER seeing it, so a post hoc flag)
Four score variants, equal weights (Michael has not set weights; unit points are a placeholder, not a decision):
  A = R1+N+D1   B = R2+N+D1   C = R1+N+D2   D = R2+N+D2        score 0..3

Tables per variant (all descriptive; the only inference is the quarter-block range, 10,000 resamples of whole calendar quarters):
  1. by score 0, 1, 2, 3: n, entry weeks, separate entry spells (gap > 42 days), excess, stock and SPY legs, median, share beating SPY, mean without
     2008Q4 / 2011Q3 / 2020Q1, means for 2006-2010 vs 2011-2020, quarter-block range of the mean.
  2. the 8 flag combinations (R, N, D) with n and excess.
  3. each flag's marginal: mean with the flag vs without it.
  4. score >= 2 vs score <= 1: means, difference, quarter-block range of the difference; score >= k trades per month (n / 180 months).
  5. regression excess = a + bR*R + bN*N + bD*D, each coefficient with a quarter-block range (does each flag add anything given the others?).
No new chance test is run: the lead63 chance needs a circular shift (Entries 37, 41), the role and decline chances are logged (Entries 32, 36), and a
combined chance would be a new design. Best-of-4 variants is therefore NOT quantified; read the ranges, not any single cell. Cells with n < 15 are marked thin.
Cautions written in advance: the score-3 group will be small (expected about 15-25 events in 15 years); R, N and D were each found after looking at data
(C3 in the pilot, lead63 and the 12-month fall in Entries 36-37, D2 in Entry 49), so a score built from them is a lead, not a rule, and weights must be
declared before any held-out test; the deepest falls carry survivorship exposure (Entries 38, 40, 44) and costs (Entry 45) not in any number here.

Usage:  python score_scan.py EVENTS.json YEAR_FOLDER DECLINE_FOLDER REGIME_FOLDER RETURNS_FOLDER   |   --selftest
"""
import statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, EPISODES, assert_allowed, quarter
import factor_decline as fd
import factor_regime as fg
import factor_roles as fr
from factor_regime import spells

SEED = 20261108
VARIANTS = {'A': ('R1', 'D1'), 'B': ('R2', 'D1'), 'C': ('R1', 'D2'), 'D': ('R2', 'D2')}
THIN = 15
MONTHS = 180            # 15 development years


def build(events_path, year_folder, decline_folder, regime_folder, returns_folder):
    import numpy as np
    roles = {(r['cik'], r['sym'], r['entry']): r for r in fr.load(events_path, year_folder, returns_folder)}
    rows = fd.load(decline_folder, returns_folder)
    fdate = fg.load_features(regime_folder)
    dev = []
    for r in rows:
        f = fdate.get(r['entry'])
        ro = roles.get((r['cik'], r['sym'], r['entry']))
        if r['entry'] <= DEV_END and f and 'lead63' in f and 'raw252' in r and ro:
            dev.append({**r, 'lead63': f['lead63'], 'ceo': ro['ceo'], 'cfo': ro['cfo']})
    dev.sort(key=lambda r: r['entry'])
    cut_n = float(np.quantile([r['lead63'] for r in dev], 0.2))
    cut_d = float(np.quantile([r['raw252'] for r in dev], 0.2))
    print(f'cohort (development, lead63 + raw252 + roles): n={len(dev)}; lead63 20th percentile {cut_n:+.4f} (Entry 41: -0.0195 at n=1,273); '
          f'raw252 20th percentile {cut_d:+.2f} ATR')
    for r in dev:
        r['R1'] = (not r['ceo']) and (not r['cfo'])
        r['R2'] = not r['cfo']
        r['N'] = r['lead63'] <= cut_n
        r['D1'] = r['raw252'] <= cut_d
        r['D2'] = r['raw252'] <= -20.0
    return dev


def score(r, v):
    a, b = VARIANTS[v]
    return int(r[a]) + int(r['N']) + int(r[b])


def mean_or_nan(rs):
    return statistics.fmean(r['excess_atr'] for r in rs) if rs else float('nan')


def line(rs):
    if not rs:
        return 'n=0'
    ex = [r['excess_atr'] for r in rs]
    ds = sorted(r['entry'] for r in rs)
    thin = ' THIN' if len(rs) < THIN else ''
    return (f'n={len(rs):4d} w={len({fd.week_of(r) for r in rs}):3d} sp={len(spells(ds)):2d}  excess {statistics.fmean(ex):+.3f} '
            f'(stock {statistics.fmean(r["stock_atr"] for r in rs):+.3f}, SPY {statistics.fmean(r["spy_atr"] for r in rs):+.3f})  '
            f'median {statistics.median(ex):+.3f}  beat SPY {sum(e > 0 for e in ex) / len(ex):.0%}{thin}')


class QBoot:
    """Quarter-block bootstrap on the cohort: resamples whole calendar quarters."""
    def __init__(self, dev, draws=10000):
        import numpy as np
        self.np = np
        qs = sorted({quarter(r['entry']) for r in dev})
        self.qi = {q: i for i, q in enumerate(qs)}
        self.nq = len(qs)
        rng = np.random.default_rng(SEED + 7)
        self.W = rng.multinomial(self.nq, [1 / self.nq] * self.nq, size=draws).astype(float)
        self.dev = dev

    def sums(self, rs):
        S, N = self.np.zeros(self.nq), self.np.zeros(self.nq)
        for r in rs:
            S[self.qi[quarter(r['entry'])]] += r['excess_atr']
            N[self.qi[quarter(r['entry'])]] += 1
        return S, N

    def mean_range(self, rs):
        S, N = self.sums(rs)
        num, den = self.W @ S, self.W @ N
        ok = den > 0
        m = num[ok] / den[ok]
        return float(self.np.quantile(m, 0.025)), float(self.np.quantile(m, 0.975))

    def diff_range(self, a, b):
        np = self.np
        Sa, Na = self.sums(a)
        Sb, Nb = self.sums(b)
        da, db = self.W @ Na, self.W @ Nb
        ok = (da > 0) & (db > 0)
        m = (self.W @ Sa)[ok] / da[ok] - (self.W @ Sb)[ok] / db[ok]
        return float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))

    def ols_ranges(self, X, y, qid):
        """X: n x k with intercept; returns point estimates and 95% quarter-block ranges per coefficient."""
        np = self.np
        k = X.shape[1]
        A, b = np.zeros((self.nq, k, k)), np.zeros((self.nq, k))
        for i in range(len(y)):
            A[qid[i]] += np.outer(X[i], X[i])
            b[qid[i]] += X[i] * y[i]
        beta = np.linalg.solve(A.sum(0), b.sum(0))
        Aw, bw = np.einsum('dq,qij->dij', self.W, A), np.einsum('dq,qi->di', self.W, b)
        out = []
        for d in range(len(self.W)):
            try:
                out.append(np.linalg.solve(Aw[d], bw[d]))
            except np.linalg.LinAlgError:
                pass
        out = np.array(out)
        return beta, np.quantile(out, 0.025, axis=0), np.quantile(out, 0.975, axis=0)


def report(dev):
    import numpy as np
    qb = QBoot(dev)
    qid = np.array([qb.qi[quarter(r['entry'])] for r in dev])
    y = np.array([r['excess_atr'] for r in dev])
    print(f'\nALL cohort events: {line(dev)}')
    for v, (ra, db) in VARIANTS.items():
        for r in dev:
            r['s'] = score(r, v)
        print(f'\n################ Variant {v}: score = {ra} + N + {db} ################')
        print('--- 1. By score ---')
        for s in range(4):
            g = [r for r in dev if r['s'] == s]
            ne = [r for r in g if quarter(r['entry']) not in EPISODES]
            e1 = [r for r in g if r['entry'] < '2011-01-01']
            e2 = [r for r in g if r['entry'] >= '2011-01-01']
            rng = f'quarter-block [{qb.mean_range(g)[0]:+.3f}, {qb.mean_range(g)[1]:+.3f}]' if len(g) >= THIN else 'range not shown (thin)'
            print(f'  score {s}: {line(g)}\n           no-episodes {mean_or_nan(ne):+.3f} (n={len(ne)}) | 2006-10 {mean_or_nan(e1):+.3f} (n={len(e1)}) | 2011-20 {mean_or_nan(e2):+.3f} (n={len(e2)}) | {rng}')
        print('--- 2. The 8 flag combinations (R, N, D) ---')
        for combo in [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]:
            g = [r for r in dev if (int(r[ra]), int(r['N']), int(r[db])) == combo]
            print(f'  {ra}={combo[0]} N={combo[1]} {db}={combo[2]}: {line(g)}')
        print('--- 3. Each flag with vs without ---')
        for f in (ra, 'N', db):
            w, wo = [r for r in dev if r[f]], [r for r in dev if not r[f]]
            print(f'  {f}: with {line(w)}\n      without {line(wo)}')
        print('--- 4. Score >= 2 vs <= 1; trades per month ---')
        hi, lo = [r for r in dev if r['s'] >= 2], [r for r in dev if r['s'] <= 1]
        if hi and lo:
            d = mean_or_nan(hi) - mean_or_nan(lo)
            rg = qb.diff_range(hi, lo)
            print(f'  score >= 2: {line(hi)}\n  score <= 1: {line(lo)}\n  difference {d:+.3f}, quarter-block range [{rg[0]:+.3f}, {rg[1]:+.3f}]')
        for k in (1, 2, 3):
            n = sum(r['s'] >= k for r in dev)
            print(f'  score >= {k}: {n} trades in 15 years = {n / MONTHS:.2f} per month')
        print('--- 5. Regression: excess = a + bR*R + bN*N + bD*D (quarter-block ranges) ---')
        X = np.array([[1.0, float(r[ra]), float(r['N']), float(r[db])] for r in dev])
        beta, lo_, hi_ = qb.ols_ranges(X, y, qid)
        for i, nm in enumerate(('intercept', ra, 'N', db)):
            print(f'  {nm:9s} {beta[i]:+.3f}  [{lo_[i]:+.3f}, {hi_[i]:+.3f}]')
    print('\nQuestions asked on this cohort in this entry: 4 score variants x (4 score levels + 8 combinations + 3 flag splits + 1 high/low difference + 4 coefficients), '
          'descriptive with quarter-block ranges; no chance test. POST HOC.')


def main(events_path, year_folder, decline_folder, regime_folder, returns_folder):
    dev = build(events_path, year_folder, decline_folder, regime_folder, returns_folder)
    m = mean_or_nan(dev)
    print(f'all cohort mean excess {m:+.3f}')
    report(dev)


def selftest():
    import random
    rng = random.Random(3)
    dev = []
    for k in range(900):
        d = f'20{10 + k % 8}-{1 + k % 12:02d}-{1 + k % 27:02d}'
        r = {'entry': d, 'cik': str(k), 'sym': 'X', 'ceo': rng.random() < 0.6, 'cfo': rng.random() < 0.4, 'lead63': rng.gauss(0, 0.03),
             'raw252': rng.gauss(-8, 6), 'stock_atr': 0.0, 'spy_atr': 0.0}
        dev.append(r)
    dev.sort(key=lambda r: r['entry'])
    import numpy as np
    cn, cd = float(np.quantile([r['lead63'] for r in dev], 0.2)), float(np.quantile([r['raw252'] for r in dev], 0.2))
    for r in dev:
        r['R1'] = not r['ceo'] and not r['cfo']
        r['R2'] = not r['cfo']
        r['N'] = r['lead63'] <= cn
        r['D1'] = r['raw252'] <= cd
        r['D2'] = r['raw252'] <= -20.0
        s = int(r['R1']) + int(r['N']) + int(r['D1'])
        r['excess_atr'] = 0.5 * s + rng.gauss(0, 1)
    assert score(dev[0], 'A') == int(dev[0]['R1']) + int(dev[0]['N']) + int(dev[0]['D1'])
    assert score(dev[0], 'D') == int(dev[0]['R2']) + int(dev[0]['N']) + int(dev[0]['D2'])
    qb = QBoot(dev, 500)
    hi, lo = [r for r in dev if score(r, 'A') >= 2], [r for r in dev if score(r, 'A') <= 1]
    lo_r, hi_r = qb.diff_range(hi, lo)
    assert lo_r > 0.3, (lo_r, hi_r)
    X = np.array([[1.0, float(r['R1']), float(r['N']), float(r['D1'])] for r in dev])
    qid = np.array([qb.qi[quarter(r['entry'])] for r in dev])
    beta, l, h = qb.ols_ranges(X, np.array([r['excess_atr'] for r in dev]), qid)
    assert all(abs(b - 0.5) < 0.25 for b in beta[1:]) and (l[1:] > 0).all(), (beta, l)
    try:
        assert_allowed('2023-05-01')
        raise SystemExit('guard did not fire')
    except RuntimeError:
        pass
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        report(dev)
    assert 'Variant D' in buf.getvalue() and 'per month' in buf.getvalue()
    print('score_scan self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
        raise SystemExit(0)
    if len(sys.argv) != 6:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
