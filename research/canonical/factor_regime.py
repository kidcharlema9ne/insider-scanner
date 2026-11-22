"""Candidates C14-C17 on the primary set: market regime at entry (SPY and the Nasdaq Composite proxy ONEQ), and the controller crossing.

Development years (entries <= 2020-12-31) plus the 2026 pilot only (D-068). Exploratory: a lead, not a rule. The 21-session returns are the
Entry 28 results (run 42490748366); this script only adds market features measured BEFORE entry, from sessions strictly earlier than the
entry session (the last completed session is entry index - 1). No price after an entry is used in a feature.

Features (L = last completed session before entry; sym = SPY or ONEQ; closes only):
  {sym}vol21   standard deviation of daily % close changes over the 21 sessions ending L, annualised (x sqrt 252)      [market stress]
  {sym}dd252   close(L) / highest close of the 252 sessions ending L, minus 1 (<= 0)                                  [distance below the 1-year high]
  {sym}t200    close(L) / mean close of the 200 sessions ending L, minus 1                                            [trend; > 0 = above its 200-session average]
  lead63       ONEQ 63-session % change minus SPY 63-session % change                                                 [Nasdaq leadership]
Measures (7), declared before the run:  spyvol21 spydd252 spyt200 | onvol21 ondd252 ont200 | lead63

Menu (the chance tests cover exactly these):
  Part 1 (C14-C16): each measure vs the trade's 21-session excess over SPY, two statistics: (a) Spearman rank correlation, (b) 'smile' = mean
    excess of the lowest and highest fifths minus the middle three fifths. 14 statistics.
    Chance test = exact CIRCULAR SHIFT over the distinct entry dates: each trade is paired with the market features of another entry date
    (date index + s mod number of dates, every s), which keeps the market's own persistence and the overlap of 21-session windows. The
    within-week shuffle of Entries 32-35 is NOT used here because a market-level feature is almost the same for every trade in a week.
    Best-of-menu chance by the min-p method over the 14 statistics.
  Part 2 (C17, controller crossing, Michael's idea that controllers buy in calm markets): for each of the 7 measures, mean percentile rank of the
    measure among development events, controller-among-buyers minus the rest. Calm-market prediction: lower vol (spyvol21, onvol21), smaller
    drawdown (dd closer to 0), higher trend. Chance test = controller label shuffled among events inside the same entry quarter (10,000
    shuffles); best of 7 by min-p.
Descriptive only (not in the chance menu): quintile tables with and without the three large episodes; share of controller events inside the
large episodes; forward SPY direction during the hold (NOT tradable; shows how much of the result depends on the market's move after entry);
the 2026 pilot split at the development median.

Usage:  python factor_regime.py year YEAR --primary FILE --out FILE   |   summary FEATURES_FOLDER RETURNS_FOLDER YEAR_FOLDER EVENTS.json   |   lead FEATURES_FOLDER RETURNS_FOLDER YEAR_FOLDER EVENTS.json   |   --selftest
"""
import argparse, json, math, statistics, sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refined_baseline import DEV_END, EPISODES, assert_allowed, load_span, quarter

MEASURES = ['spyvol21', 'spydd252', 'spyt200', 'onvol21', 'ondd252', 'ont200', 'lead63']
SEED = 20261108
EXPECT_DEV = 1372            # Entry 28
SYMS = ('SPY', 'ONEQ')


# ------------------------------------------------------------------ features (date-level; identical for every trade on that date)
def _closes(bars, dates, a, b):
    return [bars[dates[k]][3] for k in range(max(a, 0), b) if dates[k] in bars]


def _ref_close(bars, dates, idx, back=3):
    for k in range(back + 1):
        if idx - k < 0:
            return None
        b = bars.get(dates[idx - k])
        if b:
            return b[3]
    return None


def sym_features(bars, dates, i):
    """Features for one symbol at entry index i (sessions strictly before i)."""
    out = {}
    L = dates[i - 1]
    if L not in bars:
        return out
    last = bars[L][3]
    cl = _closes(bars, dates, i - 22, i)
    rets = [cl[k] / cl[k - 1] - 1 for k in range(1, len(cl))]
    if len(rets) >= 17:
        out['vol21'] = statistics.pstdev(rets) * math.sqrt(252)
    c252 = _closes(bars, dates, i - 252, i)
    if len(c252) >= 200:
        out['dd252'] = last / max(c252) - 1
    c200 = _closes(bars, dates, i - 200, i)
    if len(c200) >= 160:
        out['t200'] = last / (sum(c200) / len(c200)) - 1
    ref = _ref_close(bars, dates, i - 1 - 63)
    if ref:
        out['pct63'] = last / ref - 1
    return out


def date_features(dates, spy, oneq, entry):
    assert_allowed(entry)
    i = bisect_left(dates, entry)
    if i >= len(dates) or dates[i] != entry or i < 253:
        return {'status': 'not_available'}
    s, o = sym_features(spy, dates, i), sym_features(oneq, dates, i)
    out = {'status': 'ok'}
    for k, v in s.items():
        if k != 'pct63':
            out['spy' + k] = v
    for k, v in o.items():
        if k != 'pct63':
            out['on' + k] = v
    if 'pct63' in s and 'pct63' in o:
        out['lead63'] = o['pct63'] - s['pct63']
    return out


def year_job(year, primary_path, out):
    from r2_storage import client
    s3 = client()
    entries = [e for e in json.loads(Path(primary_path).read_text()) if e['entry'].startswith(str(year))]
    for e in entries:
        assert_allowed(e['entry'])
    feats = {}
    if entries:
        bars, dates = load_span(s3, 'etf', [year - 1, year], set(SYMS), 30, 0)
        spy, oneq = bars.get('SPY', {}), bars.get('ONEQ', {})
        print(f'{year}: {len(entries)} entries, {len(dates)} sessions loaded, SPY bars {len(spy)}, ONEQ bars {len(oneq)}')
        for d in sorted({e['entry'] for e in entries}):
            feats[d] = date_features(dates, spy, oneq, d)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({'year': year, 'dates': feats}))
    print(f'{year}: {len(feats)} entry dates; ' + str(dict(Counter(f["status"] for f in feats.values()))) + '; coverage ' +
          ', '.join(f'{m} {sum(m in f for f in feats.values())}' for m in MEASURES))


# ------------------------------------------------------------------ statistics (numpy)
def rank_avg(x):
    import numpy as np
    x = np.asarray(x, dtype=float)
    order = x.argsort(kind='mergesort')
    r = np.empty(len(x))
    r[order] = np.arange(len(x), dtype=float)
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    return (np.bincount(inv, weights=r) / counts)[inv]


def rho_smile(x, e):
    """x: measure values (no NaN); e: excess. Returns (Spearman rho, smile)."""
    import numpy as np
    if len(x) < 50:
        return 0.0, 0.0
    rx, re_ = rank_avg(x), rank_avg(e)
    rx, re_ = rx - rx.mean(), re_ - re_.mean()
    den = float(np.sqrt((rx ** 2).sum() * (re_ ** 2).sum()))
    rho = float((rx @ re_) / den) if den > 0 else 0.0
    cuts = np.quantile(x, [0.2, 0.4, 0.6, 0.8])
    lab = np.searchsorted(cuts, x, side='right')
    ext = (lab == 0) | (lab == 4)
    smile = float(e[ext].mean() - e[~ext].mean()) if ext.any() and (~ext).any() else 0.0
    return rho, smile


def shift_test(dev, fdate):
    """Exact circular-shift test. dev: rows with 'entry' and 'excess_atr'; fdate: {entry: {measure: value}}.
    Returns observed stats, single-question chances, best-of-menu chance, smallest observed chance, number of dates."""
    import numpy as np
    dates = sorted({r['entry'] for r in dev})
    nd = len(dates)
    pos = {d: k for k, d in enumerate(dates)}
    di = np.array([pos[r['entry']] for r in dev])
    ex = np.array([r['excess_atr'] for r in dev])
    F = {m: np.array([fdate.get(d, {}).get(m, np.nan) for d in dates], dtype=float) for m in MEASURES}
    keys = [(m, s) for m in MEASURES for s in ('rho', 'smile')]

    def stats_at(s):
        out = {}
        for m in MEASURES:
            x = F[m][(di + s) % nd]
            ok = ~np.isnan(x)
            r, sm = rho_smile(x[ok], ex[ok])
            out[(m, 'rho')], out[(m, 'smile')] = r, sm
        return out
    obs = stats_at(0)
    sims = {k: np.empty(nd - 1) for k in keys}
    for s in range(1, nd):
        d = stats_at(s)
        for k in keys:
            sims[k][s - 1] = abs(d[k])
    srt = {k: np.sort(sims[k]) for k in keys}
    n = nd - 1
    p1 = {k: float((n - np.searchsorted(srt[k], abs(obs[k]) - 1e-12, side='left') + 1) / (n + 1)) for k in keys}
    obs_min = min(p1.values())
    perm = np.min(np.vstack([(n - np.searchsorted(srt[k], sims[k] - 1e-12, side='left') + 1) / (n + 1) for k in keys]), axis=0)
    best = float(((perm <= obs_min + 1e-12).sum() + 1) / (n + 1))
    return obs, p1, best, obs_min, nd


def controller_test(events, draws=10000):
    """events: dev rows with 'controller', measures and 'entry'. Mean percentile rank difference (controller minus rest) per measure;
    controller label shuffled inside the same entry quarter."""
    import numpy as np
    out, pr = {}, {}
    for m in MEASURES:
        idx = np.array([k for k, r in enumerate(events) if m in r], dtype=int)
        x = np.array([events[k][m] for k in idx])
        pr[m] = (idx, (rank_avg(x) + 0.5) / len(x))
    lab = np.array([bool(r['controller']) for r in events])
    byq = defaultdict(list)
    for k, r in enumerate(events):
        byq[quarter(r['entry'])].append(k)
    groups = [np.array(v) for v in byq.values()]

    def diffs(l):
        d = {}
        for m, (idx, p) in pr.items():
            a, b = l[idx], ~l[idx]
            d[m] = float(p[a].mean() - p[b].mean()) if a.any() and b.any() else 0.0
        return d
    obs = diffs(lab)
    rng = np.random.default_rng(SEED)
    sim = {m: np.empty(draws) for m in pr}
    for k in range(draws):
        sl = lab.copy()
        for g in groups:
            sl[g] = lab[rng.permutation(g)]          # labels shuffled among events of the same entry quarter
        d = diffs(sl)
        for m in pr:
            sim[m][k] = abs(d[m])
    srt = {m: np.sort(sim[m]) for m in pr}
    p1 = {m: float(1.0 - np.searchsorted(srt[m], abs(obs[m]) - 1e-12, side='left') / draws) for m in pr}
    obs_min = min(p1.values())
    per = np.min(np.vstack([1.0 - np.searchsorted(srt[m], sim[m] - 1e-12, side='left') / draws for m in pr]), axis=0)
    return obs, p1, float((per <= obs_min + 1e-12).mean()), obs_min


# ------------------------------------------------------------------ summary
def stats_line(rows):
    if not rows:
        return 'n=0'
    ex = [r['excess_atr'] for r in rows]
    return (f'n={len(rows)}  stock {statistics.fmean(r["stock_atr"] for r in rows):+.3f}  SPY {statistics.fmean(r["spy_atr"] for r in rows):+.3f}  '
            f'excess {statistics.fmean(ex):+.3f}  median {statistics.median(ex):+.3f}')


def week_of(r):
    return date.fromisoformat(r['entry']).isocalendar()[:2]


def load_features(folder):
    fd = {}
    for p in sorted(Path(folder).glob('regime_*.json')):
        for d, f in json.loads(p.read_text())['dates'].items():
            assert_allowed(d)
            fd[d] = f if f.get('status') == 'ok' else {}
    return fd


def quint_table(rs, m):
    import numpy as np
    sub = [r for r in rs if m in r]
    if len(sub) < 50:
        return f'  {m}: too few ({len(sub)})'
    x = np.array([r[m] for r in sub])
    cuts = np.quantile(x, [0.2, 0.4, 0.6, 0.8])
    lab = np.searchsorted(cuts, x, side='right')
    lines = [f'  {m} (n={len(sub)}; cut points {", ".join(f"{c:+.3f}" for c in cuts)}):']
    for q in range(5):
        lines.append(f'    Q{q + 1}{" (lowest)" if q == 0 else " (highest)" if q == 4 else ""}: {stats_line([r for r, l in zip(sub, lab) if l == q])}')
    return '\n'.join(lines)


def summary(feat_folder, ret_folder, year_folder, events_path):
    import factor_roles as fr
    import factor_officers as fo
    fr.roles = fo.roles3
    rows = fr.load(events_path, year_folder, ret_folder)
    fdate = load_features(feat_folder)
    miss = 0
    for r in rows:
        f = fdate.get(r['entry'])
        if f:
            r.update({k: v for k, v in f.items() if k in MEASURES})
        else:
            miss += 1
    dev = sorted([r for r in rows if r['entry'] <= DEV_END], key=lambda r: r['entry'])
    pil = [r for r in rows if r['entry'] > DEV_END]
    print(f'analysed {len(rows)} (development {len(dev)}, pilot {len(pil)}); entries with no market features {miss}')
    print('coverage (development): ' + ', '.join(f'{m} {sum(m in r for r in dev)}' for m in MEASURES))
    print(f'independent observations (development): {len({r["entry"] for r in dev})} entry dates, {len({week_of(r) for r in dev})} weeks, {len({r["cik"] for r in dev})} issuers')
    print('\n=== A. Quintile tables, development 2006-2020 (excess over same-window SPY, ATR; Q1 = lowest value of the measure) ===')
    for m in MEASURES:
        print(quint_table(dev, m))
    d2 = [r for r in dev if quarter(r['entry']) not in EPISODES]
    print('\n=== B. Same, without the three large episodes (2008Q4, 2011Q3, 2020Q1) ===')
    for m in MEASURES:
        print(quint_table(d2, m))
    print('\n=== C. Trend split (above vs below the 200-session average), development | without episodes ===')
    for m, name in (('spyt200', 'SPY'), ('ont200', 'ONEQ')):
        for tag, rs in (('all', dev), ('no episodes', d2)):
            up, dn = [r for r in rs if m in r and r[m] > 0], [r for r in rs if m in r and r[m] <= 0]
            print(f'{name} above 200: {tag}: {stats_line(up)}\n{name} at/below 200: {tag}: {stats_line(dn)}')
    print('\n=== D. Chance test, Part 1: circular shift over entry dates (development only) ===')
    obs, p1, best, obs_min, nd = shift_test(dev, fdate)
    print(f'{nd} distinct entry dates = {nd - 1} shifts + the real alignment. Single-question chance = share of alignments with |statistic| at least as large.')
    for (m, s), v in obs.items():
        print(f'  {m} {s}: observed {v:+.3f}, chance {p1[(m, s)]:.1%}')
    print(f'Best of this menu of 14: smallest single-question chance {obs_min:.1%}; chance the best of 14 is at least that small by luck {best:.1%}')
    print('\n=== E. Controller crossing (Part 2): mean percentile rank of the market measure, controller events minus the rest ===')
    ev = [r for r in dev]
    n_c = sum(r['controller'] for r in ev)
    print(f'controller events {n_c} of {len(ev)}; entry dates {len({r["entry"] for r in ev if r["controller"]})}; weeks {len({week_of(r) for r in ev if r["controller"]})}')
    c_obs, c_p1, c_best, c_min = controller_test(ev)
    for m in MEASURES:
        a = [r[m] for r in ev if r['controller'] and m in r]
        b = [r[m] for r in ev if not r['controller'] and m in r]
        print(f'  {m}: controller mean {statistics.fmean(a):+.4f} (median {statistics.median(a):+.4f}) vs rest {statistics.fmean(b):+.4f} (median {statistics.median(b):+.4f}); '
              f'percentile-rank gap {c_obs[m]:+.3f}, chance {c_p1[m]:.1%}')
    print(f'  Calm-market prediction: lower spyvol21/onvol21, dd252 nearer 0 (higher), higher t200. Best of 7: smallest chance {c_min:.1%}; best-of-7 by luck {c_best:.1%}')
    ep_c = sum(quarter(r['entry']) in EPISODES for r in ev if r['controller'])
    ep_o = sum(quarter(r['entry']) in EPISODES for r in ev if not r['controller'])
    print(f'  Share of events inside the three large episodes: controller {ep_c}/{n_c} ({ep_c / n_c:.1%}); rest {ep_o}/{len(ev) - n_c} ({ep_o / (len(ev) - n_c):.1%})')
    med = statistics.median(r['spyvol21'] for r in ev if 'spyvol21' in r)
    for tag, f in (('calmer half (SPY 21-session vol below median)', lambda r: r['spyvol21'] < med), ('stressed half', lambda r: r['spyvol21'] >= med)):
        grp = [r for r in ev if 'spyvol21' in r and f(r)]
        c = [r for r in grp if r['controller']]
        o = [r for r in grp if not r['controller']]
        print(f'  {tag}: controller {stats_line(c)} | rest {stats_line(o)}')
    print('\n=== F. DESCRIPTIVE ONLY, not tradable: direction of SPY during the 21-session hold (development) ===')
    for tag, rs in (('all', dev), ('no episodes', d2)):
        up, dn = [r for r in rs if r['spy_atr'] > 0], [r for r in rs if r['spy_atr'] <= 0]
        print(f'{tag}: SPY up during hold: {stats_line(up)}\n{tag}: SPY down/flat during hold: {stats_line(dn)}')
    print('\n=== G. 2026 PILOT (in-sample, small): split at the development median of each measure ===')
    for m in MEASURES:
        vals = [r[m] for r in dev if m in r]
        if not vals or not any(m in r for r in pil):
            continue
        cut = statistics.median(vals)
        lo, hi = [r for r in pil if m in r and r[m] < cut], [r for r in pil if m in r and r[m] >= cut]
        print(f'  {m} (dev median {cut:+.4f}): below {stats_line(lo)} | at/above {stats_line(hi)}')
    print('Questions asked on this cohort in this entry: 14 statistics (Part 1) + 7 controller gaps (Part 2), plus descriptive quintile tables, trend splits, hold-direction split, pilot split.')


# ------------------------------------------------------------------ lead63 follow-up (Entry 37 lead): is the U-shape a few episodes or many?
def spells(dates, gap=42):
    """dates: sorted ISO dates of extreme-fifth entries. A spell is a maximal run with no gap larger than `gap` calendar days.
    Returns lists of indices into `dates`."""
    out, cur = [], []
    prev = None
    for k, d in enumerate(dates):
        dd = date.fromisoformat(d)
        if prev is not None and (dd - prev).days > gap:
            out.append(cur)
            cur = []
        cur.append(k)
        prev = dd
    if cur:
        out.append(cur)
    return out


def smile_of(ext_sum, ext_n, all_sum, all_n):
    mid_n = all_n - ext_n
    return (ext_sum / ext_n - (all_sum - ext_sum) / mid_n) if ext_n > 0 and mid_n > 0 else float('nan')


def lead_followup(feat_folder, ret_folder, year_folder, events_path):
    import numpy as np
    import factor_roles as fr
    import factor_officers as fo
    fr.roles = fo.roles3
    rows = fr.load(events_path, year_folder, ret_folder)
    fdate = load_features(feat_folder)
    for r in rows:
        f = fdate.get(r['entry'])
        if f and 'lead63' in f:
            r['lead63'] = f['lead63']
    dev = sorted([r for r in rows if r['entry'] <= DEV_END and 'lead63' in r], key=lambda r: r['entry'])
    x = np.array([r['lead63'] for r in dev])
    lo, hi = np.quantile(x, [0.2, 0.8])
    for r in dev:
        r['band'] = 'Q1' if r['lead63'] <= lo else 'Q5' if r['lead63'] >= hi else 'mid'
    ex = np.array([r['excess_atr'] for r in dev])
    ext = np.array([r['band'] != 'mid' for r in dev])
    print(f'development events with lead63: {len(dev)}; cut points: lowest fifth <= {lo:+.4f}, highest fifth >= {hi:+.4f} (as in Entry 37)')
    print(f'Entry 37 statistic reproduced: smile = mean excess of Q1+Q5 {ex[ext].mean():+.3f} (n={ext.sum()}) minus middle three fifths {ex[~ext].mean():+.3f} (n={(~ext).sum()}) = {ex[ext].mean() - ex[~ext].mean():+.3f}')
    for b in ('Q1', 'mid', 'Q5'):
        print(f'  {b}: {stats_line([r for r in dev if r["band"] == b])}')
    print('\n=== A. By entry year (development): events in the lowest fifth / highest fifth / middle, and mean excess of each ===')
    print('year | Q1 n, excess | Q5 n, excess | middle n, excess')
    for y in sorted({r['entry'][:4] for r in dev}):
        cell = lambda b: (lambda s: f'{len(s):3d}, {statistics.fmean(r["excess_atr"] for r in s):+.2f}' if s else '  0,   -  ')([r for r in dev if r['entry'][:4] == y and r['band'] == b])
        print(f'{y} | {cell("Q1")} | {cell("Q5")} | {cell("mid")}')
    print('\n=== B. Separate market periods ("spells": consecutive extreme-fifth entry dates with no gap over 42 calendar days) ===')
    spell_rows = {}
    for b in ('Q1', 'Q5'):
        sub = [r for r in dev if r['band'] == b]
        ds = [r['entry'] for r in sub]
        sp = spells(ds)
        spell_rows[b] = [[sub[k] for k in g] for g in sp]
        sizes = sorted(((len(g), g) for g in spell_rows[b]), key=lambda t: -t[0])
        tot = len(sub)
        print(f'{b}: {tot} events in {len(sp)} spells; largest 8 spells (events, first to last entry date, mean excess):')
        for n, g in sizes[:8]:
            print(f'    {n:3d}  {g[0]["entry"]} to {g[-1]["entry"]}  {statistics.fmean(r["excess_atr"] for r in g):+.3f}')
        top3 = [r for _, g in sizes[:3] for r in g]
        rest = [r for _, g in sizes[3:] for r in g]
        print(f'    top 3 spells hold {len(top3)} of {tot} events ({len(top3) / tot:.0%}); mean excess in them {statistics.fmean(r["excess_atr"] for r in top3):+.3f}; '
              f'in all other spells {statistics.fmean(r["excess_atr"] for r in rest):+.3f} (n={len(rest)}, {len(sp) - 3} spells)')
        sm = [statistics.fmean(r['excess_atr'] for r in g) for g in spell_rows[b]]
        print(f'    spells with positive mean excess: {sum(m > 0 for m in sm)} of {len(sm)}; mean of spell means (each spell counts once) {statistics.fmean(sm):+.3f}, median {statistics.median(sm):+.3f}')
    mid_ds = [r['entry'] for r in dev if r['band'] == 'mid']
    mid_sp = spells(mid_ds)
    print(f'middle three fifths for reference: {len(mid_ds)} events in {len(mid_sp)} spells (same 42-day rule)')
    print('\n=== C. Leave-out checks on the smile statistic (extreme fifths minus middle three fifths; Entry 37 value above) ===')
    tot_s, tot_n = ex.sum(), len(ex)
    for y in sorted({r['entry'][:4] for r in dev}):
        keep = np.array([r['entry'][:4] != y for r in dev])
        print(f'  leave out {y}: {smile_of(ex[keep & ext].sum(), (keep & ext).sum(), ex[keep].sum(), keep.sum()):+.3f}  (n={keep.sum()})')
    ep = np.array([quarter(r['entry']) in EPISODES for r in dev])
    k = ~ep
    print(f'  leave out the three large episodes: {smile_of(ex[k & ext].sum(), (k & ext).sum(), ex[k].sum(), k.sum()):+.3f}  (n={k.sum()})')
    for b in ('Q1', 'Q5'):
        sizes = sorted(spell_rows[b], key=lambda g: -len(g))[:3]
        drop = {id(r) for g in sizes for r in g}
        keep = np.array([id(r) not in drop for r in dev])
        print(f'  leave out the 3 largest {b} spells: {smile_of(ex[keep & ext].sum(), (keep & ext).sum(), ex[keep].sum(), keep.sum()):+.3f}  (n={keep.sum()})')
    drop = {id(r) for b in ('Q1', 'Q5') for g in sorted(spell_rows[b], key=lambda g: -len(g))[:3] for r in g}
    keep = np.array([id(r) not in drop for r in dev])
    print(f'  leave out the 3 largest spells of both extremes: {smile_of(ex[keep & ext].sum(), (keep & ext).sum(), ex[keep].sum(), keep.sum()):+.3f}  (n={keep.sum()})')
    print('\n=== D. Quarter-block bootstrap (10,000 resamples of whole calendar quarters; keeps regime persistence) ===')
    qs = sorted({quarter(r['entry']) for r in dev})
    qi = {q: i for i, q in enumerate(qs)}
    ids = np.array([qi[quarter(r['entry'])] for r in dev])
    isq1 = np.array([r['band'] == 'Q1' for r in dev])
    isq5 = np.array([r['band'] == 'Q5' for r in dev])
    nq = len(qs)
    agg = lambda mask: (np.bincount(ids, weights=ex * mask, minlength=nq), np.bincount(ids, weights=mask.astype(float), minlength=nq))
    (e_s, e_n), (q1_s, q1_n), (q5_s, q5_n), (a_s, a_n) = agg(ext), agg(isq1), agg(isq5), agg(np.ones(len(ex), dtype=bool))
    rng = np.random.default_rng(SEED)
    draw = rng.integers(0, nq, size=(10000, nq))
    S = lambda arr: arr[draw].sum(axis=1)
    es, en, qs1, qn1, qs5, qn5, as_, an = S(e_s), S(e_n), S(q1_s), S(q1_n), S(q5_s), S(q5_n), S(a_s), S(a_n)
    with np.errstate(divide='ignore', invalid='ignore'):
        smile = es / en - (as_ - es) / (an - en)
        q1m, q5m, midm = qs1 / qn1, qs5 / qn5, (as_ - qs1 - qs5) / (an - qn1 - qn5)
    pct = lambda v: f'{np.nanpercentile(v, 2.5):+.3f} to {np.nanpercentile(v, 97.5):+.3f}'
    print(f'{nq} quarters. Smile {ex[ext].mean() - ex[~ext].mean():+.3f}: 95% range {pct(smile)}; share of resamples with smile <= 0: {np.nanmean(smile <= 0):.1%}')
    print(f'Q1 mean {ex[isq1].mean():+.3f}: range {pct(q1m)}; Q5 mean {ex[isq5].mean():+.3f}: range {pct(q5m)}; middle three mean {ex[~ext].mean():+.3f}: range {pct(midm)}')
    print(f'Q1 minus middle: share of resamples <= 0: {np.nanmean(q1m - midm <= 0):.1%}; Q5 minus middle: share <= 0: {np.nanmean(q5m - midm <= 0):.1%}')
    print('Questions asked on this cohort in this entry: follow-up on one already-registered lead (descriptive; reproduction of the Entry 37 statistic, by-year table, spell counts, 14 leave-out values, 5 bootstrap ranges).')


# ------------------------------------------------------------------ self-test
def selftest():
    import numpy as np
    dates = [f'{2005 + k // 252}-{1 + (k % 252) // 21:02d}-{1 + k % 21:02d}' for k in range(600)]
    rng = np.random.default_rng(1)
    px = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, 600))
    spy = {d: (p, p, p, p) for d, p in zip(dates, px)}
    on = {d: (p * 1.1, p * 1.1, p * 1.1, p * 1.1) for d, p in zip(dates, px)}
    i = 400
    f = date_features(dates, spy, on, dates[i])
    assert f['status'] == 'ok' and all(m in f for m in MEASURES), f
    assert abs(f['spyvol21'] - f['onvol21']) < 1e-9 and abs(f['lead63']) < 1e-9, 'identical series must give identical features and zero leadership'
    cl = px[i - 252:i]
    assert abs(f['spydd252'] - (px[i - 1] / cl.max() - 1)) < 1e-9
    assert abs(f['spyt200'] - (px[i - 1] / px[i - 200:i].mean() - 1)) < 1e-9
    assert f['spydd252'] <= 0
    r = np.diff(px[i - 22:i]) / px[i - 22:i - 1]
    assert abs(f['spyvol21'] - r.std() * math.sqrt(252)) < 1e-9
    bad = date_features(dates, spy, on, dates[100])
    assert bad['status'] == 'not_available'
    # no look-ahead: changing the entry-day close and later closes must not change a feature
    spy2 = dict(spy)
    for d in dates[i:]:
        spy2[d] = (1.0, 1.0, 1.0, 1.0)
    assert date_features(dates, spy2, on, dates[i]) ['spyvol21'] == f['spyvol21']
    rows = [{'entry': dates[300 + k], 'excess_atr': float(rng.normal()), 'cik': str(k), 'controller': k % 5 == 0} for k in range(120)]
    fd = {r['entry']: {m: float(rng.normal()) for m in MEASURES} for r in rows}
    a = shift_test(rows, fd)
    b = shift_test(rows, fd)
    assert a == b
    for r in rows:
        r.update(fd[r['entry']])
    c1, c2 = controller_test(rows, 200), controller_test(rows, 200)
    assert c1 == c2
    sp = spells(['2010-01-01', '2010-01-20', '2010-03-30', '2010-04-02', '2011-01-01'])
    assert sp == [[0, 1], [2, 3], [4]], sp
    assert math.isnan(smile_of(1.0, 0, 5.0, 10)) and abs(smile_of(6.0, 2, 10.0, 6) - (3.0 - 1.0)) < 1e-12
    print('factor_regime self-test passed')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', nargs='?')
    ap.add_argument('a', nargs='?')
    ap.add_argument('b', nargs='?')
    ap.add_argument('c', nargs='?')
    ap.add_argument('d', nargs='?')
    ap.add_argument('--primary')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    ns = ap.parse_args()
    if ns.selftest or ns.cmd == '--selftest':
        selftest()
    elif ns.cmd == 'year':
        year_job(int(ns.a), ns.primary, ns.out)
    elif ns.cmd == 'summary':
        summary(ns.a, ns.b, ns.c, ns.d)
    elif ns.cmd == 'lead':
        lead_followup(ns.a, ns.b, ns.c, ns.d)
    else:
        ap.error('use: year YEAR --primary F --out F | summary FEAT RET YEARS EVENTS | --selftest')
