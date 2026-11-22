#!/usr/bin/env python3
"""Continuous sizing weights from the logged marginal edges (arithmetic only).

Reads NO price data and computes NO return. Inputs are numbers already logged:
  - Entry 67 (run 42536840085): regression excess = a + R1 + N + P + F,
    estimate and quarter-block 95% range per term.
  - Entry 51 (run 42516534558): regression excess = a + R1 + N + D1.
  - Entry 67 threshold table: cumulative mean excess and n for raw252 <= -T ATR.

Method (declared before running):
  1. SE of each term ~ (range width) / (2 * 1.96)  (assumes a symmetric range).
  2. Noise reliability w = est^2 / (est^2 + SE^2)   (zero-mean prior; a noisy
     small term is pulled toward zero harder than a firm large one).
  3. Selection haircut s = 0.5 on every found-by-search term (Entry 64's
     judgment; NOT measured). It sets the overall scale only.
  4. Size add-on in units of U (U = 0.25% of equity per 1 ATR):
        add_U = (s * w * est) / K,  K = 0.25 ATR of shrunk edge per 1U
     so add_U = 2 * w * est with the defaults. The base cluster rule is NOT
     haircut: it is 1.0U by Michael's definition.
  5. Total = 1.0 + sum of add-ons for the flags that are on. Additive model.

Status: descriptive sizing arithmetic, post hoc inputs, PROVISIONAL. Run
locally (no workflow); there is no workflow run link for this file.
"""
import itertools

S = 0.5      # selection haircut (judgment)
K = 0.25     # ATR of shrunk marginal edge per 1U of size (judgment)
Z = 1.96

# (estimate, low, high) quarter-block 95% range, from the log
MODELS = {
    "Entry 67 (R1+N+P+F)": {
        "R1": (0.116, -0.128, 0.371),
        "N": (0.498, 0.112, 0.933),
        "P": (0.262, -0.120, 0.639),
        "F": (0.359, -0.078, 0.689),
    },
    "Entry 51 (R1+N+D1)": {
        "R1": (0.108, -0.137, 0.364),
        "N": (0.505, 0.113, 0.901),
        "D1": (0.496, 0.040, 0.858),
    },
}


def weights(terms):
    out = {}
    for k, (est, lo, hi) in terms.items():
        se = (hi - lo) / (2 * Z)
        w = est * est / (est * est + se * se)
        out[k] = dict(est=est, se=se, w=w, shrunk=S * w * est, add_U=S * w * est / K)
    return out


def main():
    for name, terms in MODELS.items():
        print("==", name)
        wt = weights(terms)
        for k, d in wt.items():
            print(f"  {k:3s} est {d['est']:+.3f}  SE {d['se']:.3f}  reliability {d['w']:.3f}"
                  f"  shrunk edge {d['shrunk']:+.3f} ATR  add {d['add_U']:+.2f}U")
        print("  totals (base 1.0U + flags on):")
        keys = list(wt)
        for r in range(len(keys) + 1):
            for combo in itertools.combinations(keys, r):
                tot = 1.0 + sum(wt[c]["add_U"] for c in combo)
                print(f"    {'+'.join(combo) or 'cluster only':14s} {tot:.2f}U  ({tot * 0.25:.3f}% per ATR)")

    # graded fall: increments between cumulative thresholds (derived from rows,
    # not a script output of the study); raw, not adjusted for N or R1.
    cum = [(-10, 0.467, 481), (-12, 0.513, 390), (-15, 0.599, 269), (-20, 0.673, 156), (-25, 0.565, 91)]
    print("== graded 12-month fall, increments from the cumulative table (raw excess, ATR over SPY)")
    for (t1, m1, n1), (t2, m2, n2) in zip(cum, cum[1:]):
        n = n1 - n2
        m = (m1 * n1 - m2 * n2) / n
        print(f"  fell {-t1}-{-t2} ATR: n={n:4d}  excess {m:+.3f}")
    print(f"  fell more than {-cum[-1][0]} ATR: n={cum[-1][2]}  excess {cum[-1][1]:+.3f}")


if __name__ == "__main__":
    main()
