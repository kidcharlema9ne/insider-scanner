"""Archive probe (Entry 39): for symbols that events call 'no_price', what is actually in the archive?
Prints, per probe symbol and year, exact matches, near matches (symbol contains the probe) and number of sampled
sessions on which the exact symbol appears.  Declared before running: probes C, MI, ALD, CVH, LEE, CTT, STKR, AII,
EGR, MBP, PRM, MIG, ILI, AFT, PABK, NSBC; years 2008 and 2012.  Diagnostic only, no returns."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
PROBES = 'C MI ALD CVH LEE CTT STKR AII EGR MBP PRM MIG ILI AFT PABK NSBC'.split()


def scan(s3, year, every=10):
    from archive_coverage_audit import list_dates, read_file
    keys = list_dates(s3, 'stock', year)
    keys = keys[::every] + keys[-1:]
    per = []
    with ThreadPoolExecutor(8) as pool:
        for _, _, t in pool.map(lambda k: read_file(s3, k), keys):
            per.append(set(t['symbol']))
    return per


def report(per, probes):
    allsyms = set().union(*per)
    for p in probes:
        exact = sum(p in s for s in per)
        near = sorted(x for x in allsyms if p in x and x != p)[:8]
        print(f'  {p:5s} exact on {exact}/{len(per)} sampled sessions; near matches: {near}')


def selftest():
    import io, contextlib
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        report([{'C', 'C-DELISTED'}, {'AB'}], ['C', 'AB', 'ZZ'])
    assert 'exact on 1/2' in b.getvalue() and 'exact on 0/2' in b.getvalue()
    print('selftest ok')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        selftest()
    else:
        from r2_storage import client
        s3 = client()
        for y in (2008, 2012):
            per = scan(s3, y)
            print(f'{y}: {len(per)} sampled sessions, {len(set().union(*per))} symbols')
            report(per, PROBES)
