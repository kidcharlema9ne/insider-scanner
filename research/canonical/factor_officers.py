"""Candidates C11-C13 on the primary set: treasurer, controller / accounting officer, and other (non-C-suite) officers among the buyers.

Development years (entries <= 2020-12-31) plus the 2026 pilot only (D-068). Exploratory: a lead, not a rule.
Same inputs, same return data and same chance test as factor_roles.py / factor_tenpct.py (they are imported, not rewritten).

Role classes, written down BEFORE the run. A buyer counts only if his filing ticks Officer (a title on a director-only filing
is ignored, as in factor_roles.py). One buyer can carry several flags ("CFO & Treasurer" is both CFO and treasurer).
  CEO / CFO      as in factor_roles.py
  treasurer      title matches \\btreasurer\\b and not \\bassistant\\b      (an Assistant Treasurer is NOT a treasurer here)
  controller     title matches controller | comptroller | chief accounting officer | principal accounting officer | CAO
                 (the accounting-function officer; the "Assistant" exclusion applies here too)
  C-suite other  chief ... officer | COO | CTO | CIO | CMO | CLO | CRO | president (not vice president) | chairman  (not CEO/CFO/treasurer/controller)
  other officer  an Officer-box buyer with a NON-blank title that matches none of the classes above
                 (VPs, SVPs, EVPs, general counsel, secretary, division heads, ...)
  untitled       an Officer-box buyer with a blank title (cannot be classified; kept apart, never counted as "other officer")

Menu declared before the run (the chance test covers exactly these):
  O1  treasurer among the buyers                       vs not
  O2  controller / accounting officer among the buyers vs not
  O3  any other (non-C-suite) officer among the buyers vs none
  O4  treasurer or controller among the buyers (finance-function officer besides the CFO)   vs not
  O5  Spearman rank correlation of excess with the number of distinct other-officer buyers
Descriptive only (not in the chance menu): title census, bucket table by number of other officers, O3 crossed with the
Entry 32 CEO/CFO split, with and without the three large episodes, the 2026 pilot.

Usage: python factor_officers.py EVENTS.json YEAR_FOLDER RETURNS_FOLDER      |      --selftest
"""
import re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factor_roles as fr
from factor_roles import CEO_RE, CFO_RE, DEV_END, EPISODES, SEED, indep, quarter, stats_line, week_boot, week_of
from factor_tenpct import rank

TREAS_RE = re.compile(r'\btreasurer\b', re.I)
CTRL_RE = re.compile(r'\b(?:controller|comptroller|chief accounting officer|principal accounting officer|CAO)\b', re.I)
ASSIST_RE = re.compile(r'\bassistant\b|\basst\b', re.I)
CSUITE_RE = re.compile(r'\bchief\b.*\bofficer\b|\b(?:COO|CTO|CIO|CMO|CLO|CRO)\b|\bchairman\b', re.I)
PRES_RE = re.compile(r'\bpresident\b', re.I)
VICE_RE = re.compile(r'\bvice\b|\bvp\b|\bv\.p\.|\bsvp\b|\bevp\b', re.I)


def classify(title):
    """Flags for ONE officer-buyer's title."""
    t = title or ''
    ceo, cfo = bool(CEO_RE.search(t)), bool(CFO_RE.search(t))
    tre = bool(TREAS_RE.search(t)) and not ASSIST_RE.search(t)
    ctl = bool(CTRL_RE.search(t)) and not ASSIST_RE.search(t)
    cs = bool(CSUITE_RE.search(t)) or (bool(PRES_RE.search(t)) and not VICE_RE.search(t))   # a Vice President is NOT 'president'
    named = bool(t.strip())
    other = named and not (ceo or cfo or tre or ctl or cs)
    return {'ceo': ceo, 'cfo': cfo, 'treasurer': tre, 'controller': ctl, 'csuite': cs, 'other': other, 'untitled': not named}


def roles3(owners):
    """owners: [cik, relationship, title] triples -> event-level flags (distinct people counted once per flag)."""
    people = {}
    for cik, relationship, title in owners:
        if 'Officer' not in [x.strip() for x in relationship.split(',')]:
            continue
        p = people.setdefault(cik, {k: False for k in ('ceo', 'cfo', 'treasurer', 'controller', 'csuite', 'other', 'untitled')})
        for k, v in classify(title).items():
            p[k] = p[k] or v
    # a person with several lines may have one blank and one named line; he is untitled only if no line named him
    for p in people.values():
        if p['untitled'] and any(p[k] for k in ('ceo', 'cfo', 'treasurer', 'controller', 'csuite', 'other')):
            p['untitled'] = False
    cnt = lambda k: sum(p[k] for p in people.values())
    return {'ceo': cnt('ceo') > 0, 'cfo': cnt('cfo') > 0, 'untitled_officer': cnt('untitled') > 0,
            'n_officers': len(people), 'n_buyers': len({o[0] for o in owners}),
            'treasurer': cnt('treasurer') > 0, 'controller': cnt('controller') > 0, 'n_other': cnt('other'),
            'n_csuite_other': sum(p['csuite'] and not (p['ceo'] or p['cfo']) for p in people.values())}


SPLITS = {
    'O1 treasurer among the buyers': lambda r: r['treasurer'],
    'O2 controller / accounting officer among the buyers': lambda r: r['controller'],
    'O3 any other (non-C-suite) officer among the buyers': lambda r: r['n_other'] >= 1,
    'O4 treasurer or controller among the buyers': lambda r: r['treasurer'] or r['controller'],
}
SPEAR = 'O5 Spearman (number of other officers vs excess)'


def perm_test(dev, draws=10000):
    """Same method as factor_tenpct.perm_test: excess shuffled inside the same entry week, every statistic recomputed,
    best-of-menu chance by the min-p method."""
    import numpy as np
    dev = sorted(dev, key=week_of)
    ex = np.array([r['excess_atr'] for r in dev])
    wk = {w: i for i, w in enumerate(sorted({week_of(r) for r in dev}))}
    wi = np.array([wk[week_of(r)] for r in dev])
    lab = {g: np.array([bool(f(r)) for r in dev], dtype=bool) for g, f in SPLITS.items()}
    rno = rank(np.array([r['n_other'] for r in dev], dtype=float))

    def stats(e):
        d = {g: ((e[l].mean() - e[~l].mean()) if l.any() and (~l).any() else 0.0) for g, l in lab.items()}
        re_ = rank(e)
        d[SPEAR] = float(np.corrcoef(rno, re_)[0, 1]) if rno.std() > 0 and re_.std() > 0 else 0.0
        return d
    obs = stats(ex)
    keys = list(obs)
    rng = np.random.default_rng(SEED)
    sim = {g: np.empty(draws) for g in keys}
    for k in range(draws):
        order = np.lexsort((rng.random(len(dev)), wi))
        d = stats(ex[order])
        for g in keys:
            sim[g][k] = abs(d[g])
    srt = {g: np.sort(sim[g]) for g in keys}
    p1 = {g: float(1.0 - np.searchsorted(srt[g], abs(obs[g]) - 1e-12, side='left') / draws) for g in keys}
    obs_min = min(p1.values())
    per_min = np.min(np.vstack([1.0 - np.searchsorted(srt[g], sim[g] - 1e-12, side='left') / draws for g in keys]), axis=0)
    return obs, p1, float((per_min <= obs_min + 1e-12).mean()), obs_min


def show(title, rs, dev=False):
    print(f'\n--- {title} ---')
    print(f'all: {stats_line(rs)}')
    for name, f in SPLITS.items():
        a, b = [r for r in rs if f(r)], [r for r in rs if not f(r)]
        extra = ''
        if dev and len(a) > 30 and len(b) > 30:
            lo, hi = week_boot(a)
            extra = f'  | mean 95% range {lo:+.3f} to {hi:+.3f}; {indep(a)}'
        print(f'{name}:\n    yes {stats_line(a)}{extra}\n    no  {stats_line(b)}')
    print('by number of other (non-C-suite) officers among the buyers:')
    for v in range(4):
        sub = [r for r in rs if min(r['n_other'], 3) == v]
        print(f'    {v}{"+" if v == 3 else ""}: {stats_line(sub)}')
    print('other officers crossed with the Entry 32 split (neither CEO nor CFO identified vs CEO and/or CFO):')
    for lab, f in (('neither CEO nor CFO', lambda r: not r['ceo'] and not r['cfo']), ('CEO and/or CFO', lambda r: r['ceo'] or r['cfo'])):
        for olab, o in (('other officer present', lambda r: r['n_other'] >= 1), ('no other officer', lambda r: r['n_other'] == 0)):
            print(f'    {lab} | {olab}: {stats_line([r for r in rs if f(r) and o(r)])}')


def census(rows):
    """Title census so the classes can be audited: officer-buyer titles by event count, per class."""
    c, per = Counter(), Counter()
    for r in rows:
        seen = set()
        for cik, relationship, title in r['owners']:
            if 'Officer' not in [x.strip() for x in relationship.split(',')] or not title.strip():
                continue
            k = re.sub(r'\s+', ' ', title.strip().lower())
            if (cik, k) in seen:
                continue
            seen.add((cik, k))
            c[k] += 1
    for k, n in c.items():
        f = classify(k)
        cls = ('treasurer' if f['treasurer'] else '') + ('controller' if f['controller'] else '') + ('CEO' if f['ceo'] else '') + ('CFO' if f['cfo'] else '')
        per['other' if f['other'] else (cls or 'c-suite other' if f['csuite'] else cls or 'assistant-excluded / unmatched')] += n
    return c, per


def main(events_path, year_folder, returns_folder):
    fr.roles = roles3
    rows = fr.load(events_path, year_folder, returns_folder)
    dev = [r for r in rows if r['entry'] <= DEV_END]
    pil = [r for r in rows if r['entry'] > DEV_END]
    c, per = census(rows)
    print(f'\nTitle census (all {len(rows)} analysed events; distinct officer-buyer title strings: {len(c)}). Most common 45:')
    for k, n in c.most_common(45):
        f = classify(k)
        tag = 'TREAS' if f['treasurer'] else 'CTRL' if f['controller'] else 'CEO' if f['ceo'] else 'CFO' if f['cfo'] else 'csuite' if f['csuite'] else 'OTHER'
        print(f'    {n:4d}  {tag:6s} {k}')
    print(f'buyer-title entries by class (a title can sit in two): {dict(per)}')
    print(f'Events (all analysed): treasurer {sum(r["treasurer"] for r in rows)}, controller {sum(r["controller"] for r in rows)}, '
          f'other officer {sum(r["n_other"] >= 1 for r in rows)}, untitled officer {sum(r["untitled_officer"] for r in rows)}; '
          f'other-officer count {sorted(Counter(min(r["n_other"], 4) for r in rows).items())}')
    assistants = sum(1 for r in rows for cik, rel, t in r['owners'] if 'Officer' in rel and ASSIST_RE.search(t) and (TREAS_RE.search(t) or CTRL_RE.search(t)))
    print(f'Assistant treasurers / assistant controllers excluded from O1/O2 (buyer entries): {assistants}')
    show('A. DEVELOPMENT 2006-2020 (entries <= 2020-12-31): excess over same-window SPY, ATR, price only', dev, dev=True)
    show('B. 2026 PILOT (in-sample, small)', pil)
    show('C. Development without the three large episodes (2008Q4, 2011Q3, 2020Q1)', [r for r in dev if quarter(r['entry']) not in EPISODES])
    print('\n--- D. Chance test: excess shuffled among trades inside the same entry week (10,000 shuffles, development only) ---')
    obs, p1, best, obs_min = perm_test(dev)
    for g in obs:
        print(f'  {g}: observed {obs[g]:+.3f}, chance of one this large (this question alone) {p1[g]:.1%}')
    print(f'Best of this menu of 5: smallest single-question chance {obs_min:.1%}; chance the best of 5 is at least that small by luck {best:.1%}')
    print('Questions asked on this cohort in this entry: 4 binary splits + 1 rank correlation (menu), plus 1 bucket table and 4 crossed cells (descriptive).')


def selftest():
    c = classify('Chief Financial Officer and Treasurer')
    assert c['cfo'] and c['treasurer'] and c['csuite'] and not c['other']
    assert not classify('Assistant Treasurer')['treasurer'] and classify('Assistant Treasurer')['other']
    assert classify('VP, Controller')['controller'] and not classify('VP, Controller')['other']
    assert classify('Chief Accounting Officer')['controller']
    assert classify('Corporate Comptroller')['controller']
    assert classify('Senior Vice President')['other'] and classify('EVP & General Counsel')['other']
    assert not classify('President')['other'] and classify('President')['csuite'] and not classify('President')['ceo']
    assert classify('')['untitled'] and not classify('')['other']
    r = roles3([['1', 'Officer', 'Treasurer'], ['2', 'Officer', 'VP Sales'], ['2', 'Officer', ''], ['3', 'Director', 'Controller'], ['4', 'Director', '']])
    assert r['treasurer'] and not r['controller'] and r['n_other'] == 1 and not r['untitled_officer'] and r['n_buyers'] == 4, r
    r = roles3([['1', 'Officer', ''], ['2', 'Director', ''], ['3', 'Director', ''], ['4', 'Director', '']])
    assert r['untitled_officer'] and r['n_other'] == 0
    rows = [{'entry': f'2010-0{1 + k % 9}-{1 + k % 27:02d}', 'excess_atr': float(k % 5) - 1.0, 'stock_atr': 0.0, 'spy_atr': 0.0, 'cik': str(k),
             'owners': [[str(k), 'Officer', 'Treasurer' if k % 3 == 0 else 'VP'], [str(k) + 'b', 'Officer', 'Controller' if k % 4 == 0 else 'SVP'],
                        [str(k) + 'c', 'Director', ''], [str(k) + 'd', 'Officer', '']]} for k in range(120)]
    for r in rows:
        r.update(roles3(r['owners']))
    a, b = perm_test(rows, 100), perm_test(rows, 100)
    assert a == b
    print('factor_officers self-test passed')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
    else:
        main(*sys.argv[1:4])
