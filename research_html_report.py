"""Self-contained, escaped HTML research findings report; ATR metrics first."""
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal, InvalidOperation
from research_statistics import summarize

def esc(x):return html.escape(str(x if x is not None else "—"),quote=True)
def cell(x):return "<td>"+esc(x)+"</td>"
def table(headers,rows):
    return "<table><thead><tr>"+"".join("<th>"+esc(h)+"</th>" for h in headers)+"</tr></thead><tbody>"+ "".join("<tr>"+"".join(cell(v) for v in row)+"</tr>" for row in rows)+"</tbody></table>"

def display_number(value, *, scale=1, prefix="", suffix=""):
    if value is None:
        return None
    try:
        number = Decimal(str(value)) * scale
    except InvalidOperation:
        return None
    return f"{prefix}{number:,.2f}{suffix}" if number.is_finite() else None


def render(dataset, title="Insider Buying Research — Findings", *, detail_limit=None, scope_note=None):
    observations=dataset["opportunities"]
    status=Counter(r.get("outcome_status","unknown") for r in observations)
    horizons=("11","21","43","64","6m")
    metrics=(("max_gain_atr","Maximum appreciation (ATR)"),("max_adverse_atr","Maximum adverse excursion (ATR)"),("end_return_atr","Ending return (ATR)"))
    sections=[]
    groups = ((), ("role",)) if len({row.get("role") for row in observations}) > 1 else ((),)
    for horizon in horizons:
        rows=[]
        for metric,label in metrics:
            for group in groups:
                summaries=summarize(observations,group_keys=group,horizon=horizon,metric=metric)
                for s in summaries:
                    rows.append((label,"All" if not group else s["group"]["role"],s["total_opportunities"],
                                 s["valid_opportunities"],s["distinct_valid_episodes"],
                                 display_number(s["mean_atr"]),display_number(s["median_atr"]),
                                 display_number(s["opportunity_win_rate"], scale=100, suffix="%"),
                                 display_number(s["episode_win_rate"], scale=100, suffix="%"),s["excluded_opportunities"]))
        sections.append("<section><h2>"+esc("Six calendar months" if horizon == "6m" else horizon + " trading sessions")+"</h2>"+
                        table(("Metric","Group","Total","Valid","Episodes","Mean ATR","Median ATR","Opportunity >0 rate","Episode >0 rate","Missing"),rows)+"</section>")
    details=[]
    for r in observations[:detail_limit]:
        h=r.get("horizons",{}).get("21",{})
        stats=h.get("next_open",{}) if h.get("status")=="ok" else {}
        details.append((r["accession"],r.get("ticker_at_filing"),r.get("filing_date"),r.get("role"),
                        display_number(r.get("aggregate_dollars"), prefix="$"), r.get("next_open_date"),
                        display_number(r.get("next_open"), prefix="$"), display_number(r.get("atr14"), prefix="$"),
                        display_number(stats.get("max_gain_atr")),display_number(stats.get("max_adverse_atr")),display_number(stats.get("end_return_atr")),
                        r.get("outcome_status")))
    summary=table(("Status","Count"),sorted(status.items()))
    detail_table=table(("SEC accession","Ticker at filing","Filing date","Role","Insider $","Entry date","Entry open","Fixed ATR(14)",
                        "Max gain ATR (21)","MAE ATR (21)","End ATR (21)","Data status"),details)
    css="""body{font:15px system-ui,sans-serif;max-width:1040px;margin:auto;padding:clamp(12px,3vw,26px);color:#18212d;background:#f7f9fc}
    h1,h2{color:#10294a}section{background:white;padding:20px;margin:18px 0;border:1px solid #dde6f0;border-radius:12px;overflow:auto}
    table{border-collapse:collapse;width:max-content;max-width:100%;font-size:13px}th,td{padding:6px 9px;border-bottom:1px solid #dce4ed;text-align:left;font-variant-numeric:tabular-nums}td{white-space:nowrap}td:nth-child(n+3){text-align:right}tbody tr:nth-child(even){background:#f7f9fc}
    th{background:#e8eef6;position:sticky;top:0}p{line-height:1.6}.warning{border-left:4px solid #ba781a;padding:12px;background:#fff7e8}"""
    note=("Research output, not investment advice. Entry is the next regular trading session open after SEC filing date (D-051). "
          "ATR(14) is fixed using completed pre-entry sessions. Each filing/security is one investor opportunity; "
          "episodes are descriptive, not synthetic trades. Missing outcomes are excluded from metric denominators, not treated as losses. "
          "Benchmark, sector, dividend, delisting and corporate-action completeness must be independently verified. "
          "Six months ends on the last regular session on or before the entry anniversary. "
          "No causal inference or cluster-aware confidence intervals are claimed.")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+esc(title)+'</title><style>'+css+'</style></head><body><h1>'+esc(title)+'</h1>'+
            ('<p class="warning">'+esc(scope_note)+'</p>' if scope_note else '')
            + '<p>Generated '+esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))+'</p><p class="warning">'+esc(note)+'</p>'
            '<section><h2>Coverage and exclusions</h2><p>Opportunities: '+esc(len(observations))+
            ' | Episodes: '+esc(len(dataset.get("episodes",[])))+'</p>'+summary+'</section>'+
            ''.join(sections)+'<section><h2>Disclosure-level observations (21-session snapshot)</h2>'+
            ('<p>Showing '+esc(len(details))+' of '+esc(len(observations))+' disclosures.</p>' if detail_limit is not None else '')+
            detail_table+'</section></body></html>')

def write_report(dataset,output_path, **render_options):
    path=Path(output_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(render(dataset, **render_options),encoding="utf-8")
    return path

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("dataset_json")
    p.add_argument("output_html")
    args=p.parse_args()
    write_report(json.loads(Path(args.dataset_json).read_text()),args.output_html)
