"""Write charts (PNG), tables (CSV) and readable reports (Markdown) to the outputs folder."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed: works headless in Codespaces and CI
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .metrics import LABELS, daily  # noqa: E402

COLOURS = {"v2": "#FF6223", "v1": "#282D37", "always_short": "#8A8F99", "always_long": "#4F7CAC"}
STYLES = {"v2": "-", "v1": "-", "always_short": "--", "always_long": ":"}


def _style(ax, title: str, ylabel: str):
    ax.set_title(title, loc="left", fontsize=12)
    ax.set_ylabel(ylabel)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E8EAEE", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: "£0" if v == 0 else (f"-£{abs(v)/1e3:,.0f}k" if v < 0 else f"£{v/1e3:,.0f}k")))
    ax.axhline(0, color="#5E6573", linewidth=0.8)


def cumulative_chart(pnl: pd.DataFrame, path: Path, period: str | None, title: str, divider=None,
                     guard_days: pd.DataFrame | None = None, n_highlights: int = 2, guard_style: str = "lines"):
    """Cumulative daily P&L for every strategy, plus a dashed vertical line on each day the V2 guard
    stood aside from at least one V1 trade. guard_style="lines" draws them across the chart;
    "strip" draws them in a band underneath instead (an option for very long periods).
    The days where standing aside mattered most are labelled with what it was worth (V2 minus V1 that day)."""
    sub = pnl if period is None else pnl[pnl["period"] == period]
    if guard_style == "strip":
        fig, (ax, strip) = plt.subplots(2, 1, figsize=(12.5, 7.4), sharex=True,
                                        gridspec_kw={"height_ratios": [12, 1], "hspace": 0.05})
    else:
        fig, ax = plt.subplots(figsize=(12.5, 7))
        strip = None

    g = pd.DataFrame()
    if guard_days is not None:
        g = guard_days if period is None else guard_days[guard_days["period"] == period]
        g = g[g["blocked_halfhours"] > 0]
        target = strip if strip is not None else ax
        for i, d in enumerate(g.index):
            target.axvline(d, color="#9AA0AA", linestyle=(0, (3, 3)), linewidth=0.6,
                           alpha=0.9 if strip is not None else (0.6 if len(g) < 300 else 0.3), zorder=0,
                           label="V2 guard active: stood aside from some or all V1 trades" if i == 0 else None)
        if strip is not None:
            strip.set_yticks([])
            strip.set_ylabel("V2\nguard", rotation=0, ha="right", va="center", fontsize=9, color="#5E6573")
            strip.spines[["top", "right", "left"]].set_visible(False)

    first = daily(sub, "pnl_v2").index
    ends = {"do_nothing": 0.0}
    ax.plot([first.min(), first.max()], [0, 0], "-", color="#5E6573", linewidth=1.0, label=LABELS["do_nothing"])
    for s in ["always_long", "always_short", "v1", "v2"]:
        c = daily(sub, f"pnl_{s}").cumsum()
        ax.plot(c.index, c.values, STYLES[s], color=COLOURS[s], linewidth=2.4 if s == "v2" else 1.4, label=LABELS[s])
        ends[s] = c.iloc[-1]

    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + (hi - lo) * 0.15)            # headroom for the highlight labels
    lo, hi = ax.get_ylim()
    span = hi - lo
    ax.set_xlim(first.min(), first.max() + (first.max() - first.min()) * 0.12)

    # direct labels at the right-hand end of each line, nudged apart so they don't overlap
    placed = []
    for s, v in sorted(ends.items(), key=lambda kv: kv[1]):
        y = v
        while any(abs(y - p) < 0.035 * span for p in placed):
            y += 0.035 * span
        placed.append(y)
        colour = "#5E6573" if s == "do_nothing" else COLOURS[s]
        name = {"always_long": "Always long", "always_short": "Always short", "v1": "V1", "v2": "V2",
                "do_nothing": "Do nothing"}[s]
        money = "£0" if v == 0 else (f"-£{abs(v)/1e3:,.0f}k" if v < 0 else f"£{v/1e3:,.0f}k")
        ax.text(first.max() + (first.max() - first.min()) * 0.008, y, f"{name} {money}", va="center", fontsize=9,
                color=colour, fontweight="bold" if s == "v2" else "normal")

    if len(g) and n_highlights:
        x_mid = first.min() + (first.max() - first.min()) * 0.6
        for k, (d, r) in enumerate(g.sort_values("v2_minus_v1_gbp", ascending=False).head(n_highlights).iterrows()):
            ax.axvline(d, color="#FF6223", linestyle="--", linewidth=1.0, alpha=0.9, zorder=1)
            right = d > x_mid
            ax.text(d, hi - span * (0.03 + 0.05 * k),
                    (f"{d:%d %b %Y}: guard saved £{r['v2_minus_v1_gbp']:,.0f} " if right
                     else f" {d:%d %b %Y}: guard saved £{r['v2_minus_v1_gbp']:,.0f}"),
                    color="#B23F0F", fontsize=9, va="top", ha="right" if right else "left")

    if divider is not None:
        for a in [ax] + ([strip] if strip is not None else []):
            a.axvline(pd.Timestamp(divider), color="#282D37", linestyle="-.", linewidth=1.0)
        ax.text(pd.Timestamp(divider), lo + span * 0.03, "  validation starts", color="#282D37", fontsize=9)
    _style(ax, title, "Cumulative profit")
    handles, labels = ax.get_legend_handles_labels()
    if strip is not None and len(g):
        h2, l2 = strip.get_legend_handles_labels()
        handles, labels = h2 + handles, l2 + labels
    (strip if strip is not None else ax).legend(handles, labels, frameon=False, loc="upper center",
                                                bbox_to_anchor=(0.5, -0.6 if strip is not None else -0.08),
                                                ncol=3, fontsize=9)
    if strip is None:
        fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def gap_bucket_chart(model: pd.DataFrame, path: Path) -> pd.DataFrame:
    edges = [-np.inf, -50, -30, -20, -10, -5, 0, 5, 10, 20, 30, 50, np.inf]
    labels = ["<-50", "-50/-30", "-30/-20", "-20/-10", "-10/-5", "-5/0", "0/5", "5/10", "10/20", "20/30", "30/50", ">50"]
    m = model.assign(bucket=pd.cut(model["gap_pct"], edges, labels=labels),
                     fwd=model["cashout_price"] - model["hr_price"])
    m = m[m["period"].isin(["train", "validation"])]
    t = m.groupby(["bucket", "period"], observed=True)["fwd"].mean().unstack()
    fig, ax = plt.subplots(figsize=(11, 4.8))
    x = np.arange(len(t))
    ax.bar(x - 0.2, t.get("train"), 0.4, color="#282D37", label="2016–2022 (train)")
    ax.bar(x + 0.2, t.get("validation"), 0.4, color="#FF6223", label="2023 onwards (validation)")
    ax.set_xticks(x, [str(i) for i in t.index])
    ax.set_xlabel("Hourly auction price vs UK CCGT SRMC (% gap)")
    ax.set_title("Mean move from hourly auction to cashout, by SRMC gap (negative = price fell)", loc="left", fontsize=12)
    ax.set_ylabel("£/MWh")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E8EAEE", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.axhline(0, color="#5E6573", linewidth=0.8)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return t.round(2)


# ---------------------------------------------------------------- markdown helpers
def _fmt(v, col: str) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    if isinstance(v, (int, float, np.floating, np.integer)):
        if col.endswith("_gbp"):
            return f"-£{abs(v):,.0f}" if v < 0 else f"£{v:,.0f}"
        if col.endswith("_pct"):
            return f"{v:.1f}%"
        if "sharpe" in col or "share" in col:
            return f"{v:.2f}"
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
    return str(v)


def md_table(df: pd.DataFrame, cols: list[str] | None = None) -> str:
    cols = cols or list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df[cols].iterrows():
        lines.append("| " + " | ".join(_fmt(r[c], c) for c in cols) + " |")
    return "\n".join(lines)


def write_dq_report(issues: pd.DataFrame, nulls: pd.DataFrame, path: Path, engine_kind: str):
    nulls = nulls.copy()
    for c in ["first_value_utc", "last_value_utc"]:
        nulls[c] = nulls[c].apply(lambda t: "" if t is None or pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%d"))
    text = [
        "# Data quality report",
        "",
        f"Generated by `run.py` (SQL engine: {engine_kind}). Every cleaning decision below is applied in code;",
        "nothing is edited by hand. Counts refer to half-hourly rows unless stated.",
        "",
        "## Checks and actions",
        "",
        md_table(issues),
        "",
        "## Coverage of the columns used",
        "",
        "A column that only starts part-way through the history is a structural gap (the feed did not exist yet),",
        "not missing data, so it is never back-filled.",
        "",
        md_table(nulls),
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")


def write_results(path: Path, *, tables: dict[str, pd.DataFrame], robustness: pd.DataFrame,
                  kill: pd.DataFrame, threshold: float, guard_share: dict, buckets: pd.DataFrame, cfg):
    cols = ["strategy", "total_pnl_gbp", "net_of_always_short_gbp", "sharpe_annualised", "max_drawdown_gbp",
            "worst_day_gbp", "worst_day", "worst_week_gbp", "profitable_days_pct", "hit_rate_halfhours_pct",
            "time_in_market_pct"]
    text = [
        "# Results",
        "",
        "Generated by `run.py`. All figures are frictionless (no fees or slippage) at ±25MW, held from the 09:00",
        "hourly auction to cashout. P&L uses the brief's formula and is summed per UTC delivery day.",
        "",
        "## Parameters",
        "",
        f"- V1 entry: hourly price more than {cfg.entry_gap_pct:.0f}% above UK CCGT SRMC → short {cfg.position_mw:.0f}MW.",
        f"- V2 guard: stand aside when forecast demand minus forecast wind exceeds **{threshold:,.0f} MW** "
        f"(the {cfg.guard_percentile:.0%} percentile of V1-signal half-hours, fitted on {cfg.train_start}–{cfg.train_end} only).",
        f"- Guard blocks {guard_share['train']:.1f}% of V1 signal half-hours in train and {guard_share['validation']:.1f}% in validation.",
        "",
        "## Validation period (2023 onwards, untouched during fitting)",
        "",
        md_table(tables["validation"], cols),
        "",
        "## Training period (2016–2022)",
        "",
        md_table(tables["train"], cols),
        "",
        "## Full period",
        "",
        md_table(tables["full"], cols),
        "",
        "## Robustness checks (validation period)",
        "",
        md_table(robustness),
        "",
        "## Kill-condition monitor for V2 (see DECISION_MEMO.md)",
        "",
        "The limits are judgement calls, shown against both periods so their behaviour is visible. The 12-month window for K3 "
        "was chosen over 6 months because 6 months fired on 197 validation days, too often to act on.",
        "",
        md_table(kill),
        "",
        "## Evidence for the hypothesis: mean move from hourly auction to cashout (£/MWh) by SRMC gap",
        "",
        md_table(buckets.reset_index().rename(columns={"bucket": "gap_pct_bucket"})),
        "",
        "## Charts",
        "",
        "![Cumulative profit by strategy, training period 2016–2022](figures/cumulative_pnl_train.png)",
        "",
        "![Cumulative profit by strategy, validation period 2023 onwards](figures/cumulative_pnl_validation.png)",
        "",
        "![Mean move from hourly auction to cashout by SRMC gap](figures/move_by_srmc_gap.png)",
        "",
        "Interactive version: `interactive_charts.html` in this folder.",
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")


# ---------------------------------------------------------------- interactive page
INTERACTIVE_TEMPLATE = r"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>V1 and V2 strategy results: interactive charts</title>
<style>
:root{--bg:#FFFFFF;--ink:#282D37;--muted:#5E6573;--line:#DCDFE4;--grid:#E8EAEE;--guard:#9AA0AA;
  --v2:#FF6223;--v1:#282D37;--short:#8A8F99;--long:#4F7CAC;--zero:#5E6573;
  box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1E222A;--ink:#ECEEF1;--muted:#A5ACB8;--line:#3A404C;--grid:#323844;--v1:#D5D9E0;--zero:#A5ACB8;--guard:#6B7280}}
:root[data-theme="dark"]{--bg:#1E222A;--ink:#ECEEF1;--muted:#A5ACB8;--line:#3A404C;--grid:#323844;--v1:#D5D9E0;--zero:#A5ACB8;--guard:#6B7280}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Aptos,"Segoe UI",system-ui,-apple-system,Arial,sans-serif;line-height:1.5}
main{max-width:1180px;margin:0 auto;padding:28px 20px 48px}
h1{font-size:1.5rem;font-weight:600;margin:0 0 4px}
.lede{color:var(--muted);margin:0 0 20px;max-width:75ch}
.controls{display:flex;flex-wrap:wrap;gap:14px 28px;margin-bottom:14px;align-items:flex-end}
.group .l{display:block;font-size:.85rem;color:var(--muted);margin-bottom:6px}
.seg{display:flex;flex-wrap:wrap;gap:4px}
.seg button{font:inherit;font-size:.9rem;padding:6px 12px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:4px;cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.seg button:focus-visible{outline:2px solid var(--v2);outline-offset:2px}
.seg .sw{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:baseline}
.chart{position:relative;height:min(62vh,520px);min-height:320px;border:1px solid var(--line);border-radius:8px;padding:12px}
.note{font-size:.85rem;color:var(--muted);margin:8px 0 22px}
h2{font-size:1.05rem;font-weight:600;margin:0 0 8px}
.tablewrap{overflow-x:auto;margin-bottom:22px}
table{border-collapse:collapse;width:100%;min-width:640px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{font-weight:600;font-size:.85rem;color:var(--muted)}
</style>
</head>
<body>
<main>
  <h1>V1 and V2 strategy results</h1>
  <p class="lede">Cumulative profit at &plusmn;25MW from the 09:00 hourly auction to cashout. V1 sells when the hourly price clears more than 10% above UK CCGT SRMC. V2 does the same but stands aside when forecast demand minus wind is above __THRESHOLD__MW. Dashed lines mark days the V2 guard stood aside; hover for values, drag across the chart to zoom, double-click to reset.</p>
  <div class="controls">
    <div class="group"><span class="l" id="pl">Period</span>
      <div class="seg" id="period" role="group" aria-labelledby="pl">
        <button type="button" data-v="train" aria-pressed="false">Training, 2016–2022</button>
        <button type="button" data-v="validation" aria-pressed="true">Validation, 2023 onwards</button>
      </div></div>
    <div class="group"><span class="l" id="sl">Strategies (select one or more)</span>
      <div class="seg" id="series" role="group" aria-labelledby="sl"></div></div>
    <div class="group"><span class="l" id="gl">V2 guard days</span>
      <div class="seg" id="guard" role="group" aria-labelledby="gl">
        <button type="button" data-v="all" aria-pressed="true">All</button>
        <button type="button" data-v="top" aria-pressed="false">Biggest 5 only</button>
        <button type="button" data-v="none" aria-pressed="false">Hide</button>
      </div></div>
  </div>
  <div class="chart"><canvas id="c" aria-label="Cumulative profit by strategy"></canvas></div>
  <p class="note" id="note"></p>
  <h2>Headline metrics for the selected period</h2>
  <div class="tablewrap"><table><thead><tr><th>Strategy</th><th>Total profit</th><th>Net of always short</th><th>Sharpe</th><th>Max drawdown</th><th>Worst day</th><th>Time in market</th></tr></thead><tbody id="tb"></tbody></table></div>
  <h2>Days where the V2 guard mattered most</h2>
  <div class="tablewrap"><table><thead><tr><th>Date</th><th>Half-hours blocked</th><th>V2 minus V1 that day</th></tr></thead><tbody id="gd"></tbody></table></div>
  <p class="note">Generated by <code>python run.py</code> from the challenge dataset. Frictionless P&amp;L (no fees or slippage). See DECISION_MEMO.md for the recommendation and README.md for method and limitations.</p>
</main>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"></script>
<script>
const D = __DATA__;
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const gbp=v=>v==null||isNaN(v)?"–":(v<0?"−£":"£")+Math.abs(Math.round(v)).toLocaleString("en-GB");
const fmtDate=ms=>{const d=new Date(ms);return d.getUTCDate()+" "+["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()]+" "+d.getUTCFullYear();};
const S=[{k:"do_nothing",label:"Do nothing (0MW)",c:"--zero",w:1,dash:[]},
         {k:"always_long",label:"Always long (+25MW)",c:"--long",w:1.3,dash:[2,3]},
         {k:"always_short",label:"Always short (−25MW)",c:"--short",w:1.3,dash:[6,4]},
         {k:"v1",label:"V1: short above +10%",c:"--v1",w:1.5,dash:[]},
         {k:"v2",label:"V2: V1 + tight-system guard",c:"--v2",w:2.6,dash:[]}];
let state={period:"validation",show:new Set(S.map(s=>s.k)),guard:"all"};
let chart, zoom=null;

function idx(){const p=state.period;const out=[];D.period.forEach((q,i)=>{if(q===p)out.push(i);});return out;}
function cum(key,ix){let s=0;return ix.map(i=>({x:D.t[i],y:key==="do_nothing"?0:(s+=D.pnl[key][i])}));}
function guardDays(ix){const lo=D.t[ix[0]],hi=D.t[ix[ix.length-1]];
  let g=D.guard.filter(r=>r[0]>=lo&&r[0]<=hi);
  if(state.guard==="none")return[];
  if(state.guard==="top")g=g.slice().sort((a,b)=>b[2]-a[2]).slice(0,5);
  return g;}

const guardPlugin={id:"guardLines",beforeDatasetsDraw(c){const g=c.$guard||[];if(!g.length)return;
  const {ctx,chartArea:{top,bottom,left,right},scales:{x}}=c;ctx.save();ctx.setLineDash([3,3]);
  const top5=new Set((c.$top||[]).map(r=>r[0]));
  g.forEach(r=>{const px=x.getPixelForValue(r[0]);if(px<left||px>right)return;
    const big=top5.has(r[0]);ctx.strokeStyle=big?css("--v2"):css("--guard");ctx.globalAlpha=big?0.9:0.55;ctx.lineWidth=big?1.2:0.6;
    ctx.beginPath();ctx.moveTo(px,top);ctx.lineTo(px,bottom);ctx.stroke();});
  ctx.restore();}};

function render(){
  const ix=idx();
  const datasets=S.filter(s=>state.show.has(s.k)).map(s=>({label:s.label,data:cum(s.k,ix),borderColor:css(s.c),backgroundColor:css(s.c),
    borderWidth:s.w,borderDash:s.dash,pointRadius:0,tension:0}));
  const g=guardDays(ix);
  const top=D.guard.filter(r=>r[0]>=D.t[ix[0]]&&r[0]<=D.t[ix[ix.length-1]]).slice().sort((a,b)=>b[2]-a[2]).slice(0,5);
  if(chart)chart.destroy();
  chart=new Chart(document.getElementById("c"),{type:"line",data:{datasets},plugins:[guardPlugin],
    options:{responsive:true,maintainAspectRatio:false,animation:false,parsing:false,normalized:true,
      interaction:{mode:"nearest",axis:"x",intersect:false},
      plugins:{decimation:{enabled:true,algorithm:"min-max"},
        legend:{position:"bottom",labels:{color:css("--ink"),boxWidth:14,boxHeight:3}},
        tooltip:{callbacks:{title:i=>fmtDate(i[0].parsed.x),label:i=>` ${i.dataset.label}: ${gbp(i.parsed.y)}`,
          afterBody:i=>{const r=D.guard.find(q=>q[0]===i[0].parsed.x);return r?[`V2 guard stood aside: ${r[1]} half-hours, V2 minus V1 ${gbp(r[2])}`]:[];}}}},
      scales:{x:{type:"linear",min:zoom?zoom[0]:D.t[ix[0]],max:zoom?zoom[1]:D.t[ix[ix.length-1]],grid:{color:css("--grid")},
          ticks:{color:css("--muted"),maxRotation:0,callback:v=>{const d=new Date(v);return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()]+" "+d.getUTCFullYear();}}},
        y:{grid:{color:c=>c.tick.value===0?css("--muted"):css("--grid")},ticks:{color:css("--muted"),callback:v=>gbp(v)},
          title:{display:true,text:"Cumulative profit",color:css("--muted")}}}}});
  chart.$guard=g; chart.$top=top; chart.update();
  const nGuard=D.guard.filter(r=>r[0]>=D.t[ix[0]]&&r[0]<=D.t[ix[ix.length-1]]).length;
  document.getElementById("note").textContent=`${fmtDate(D.t[ix[0]])} to ${fmtDate(D.t[ix[ix.length-1]])}. The V2 guard stood aside on ${nGuard.toLocaleString("en-GB")} days in this period`+
    (state.guard==="top"?"; showing the 5 where it mattered most (orange).":state.guard==="none"?" (lines hidden).":"; the 5 where it mattered most are orange.");
  const tb=document.getElementById("tb");tb.innerHTML="";
  D.metrics[state.period].forEach(r=>{const tr=document.createElement("tr");
    tr.innerHTML=`<td>${r.strategy}</td><td>${gbp(r.total)}</td><td>${gbp(r.net)}</td><td>${r.sharpe==null?"–":r.sharpe.toFixed(2)}</td><td>${gbp(r.dd)}</td><td>${gbp(r.worst)}</td><td>${r.tim.toFixed(1)}%</td>`;tb.appendChild(tr);});
  const gd=document.getElementById("gd");gd.innerHTML="";
  top.forEach(r=>{const tr=document.createElement("tr");tr.innerHTML=`<td>${fmtDate(r[0])}</td><td>${r[1]}</td><td>${gbp(r[2])}</td>`;gd.appendChild(tr);});
}

function wireSeg(id,fn){const el=document.getElementById(id);el.addEventListener("click",e=>{const b=e.target.closest("button");if(!b)return;fn(b,el);render();});}
const sEl=document.getElementById("series");
S.forEach(s=>{const b=document.createElement("button");b.type="button";b.dataset.v=s.k;b.setAttribute("aria-pressed","true");
  b.innerHTML=`<span class="sw" style="background:${css(s.c)}"></span>${s.label}`;sEl.appendChild(b);});
wireSeg("series",(b)=>{const k=b.dataset.v;if(state.show.has(k)){if(state.show.size===1)return;state.show.delete(k);}else state.show.add(k);b.setAttribute("aria-pressed",String(state.show.has(k)));});
wireSeg("period",(b,el)=>{state.period=b.dataset.v;zoom=null;el.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));});
wireSeg("guard",(b,el)=>{state.guard=b.dataset.v;el.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));});

// drag to zoom, double-click to reset (no plugin needed)
(function(){const cv=document.getElementById("c");let x0=null;
  cv.addEventListener("mousedown",e=>{x0=e.offsetX;});
  cv.addEventListener("mouseup",e=>{if(x0===null||!chart)return;const a=Math.min(x0,e.offsetX),b=Math.max(x0,e.offsetX);x0=null;
    if(b-a<10)return;zoom=[chart.scales.x.getValueForPixel(a),chart.scales.x.getValueForPixel(b)];render();});
  cv.addEventListener("dblclick",()=>{zoom=null;render();});})();

if(typeof Chart==="undefined"){document.getElementById("note").textContent="The chart library didn't load: this page needs an internet connection to fetch Chart.js. The static charts are in outputs/figures/.";}
else{render();const mq=matchMedia("(prefers-color-scheme: dark)");mq.addEventListener&&mq.addEventListener("change",render);}
</script>
</body>
</html>
"""


def write_interactive(pnl: pd.DataFrame, guard_days: pd.DataFrame, tables: dict, threshold: float, path: Path):
    """Self-contained interactive page (data embedded; Chart.js loaded from a CDN when opened)."""
    import json
    days = pnl.groupby("date_utc").agg(period=("period", "first"),
                                       **{s: (f"pnl_{s}", "sum") for s in ["always_long", "always_short", "v1", "v2"]})
    days.index = pd.to_datetime(days.index)
    t_ms = [int(d.value // 10**6) for d in days.index]
    g = guard_days[guard_days["blocked_halfhours"] > 0]
    metrics_out = {}
    for per, key in [("train", "train"), ("validation", "validation")]:
        rows = []
        for _, r in tables[key].iterrows():
            sh = r.get("sharpe_annualised")
            rows.append({"strategy": r["strategy"], "total": float(r["total_pnl_gbp"]),
                         "net": float(r["net_of_always_short_gbp"]),
                         "sharpe": None if sh is None or pd.isna(sh) else round(float(sh), 2),
                         "dd": float(r["max_drawdown_gbp"]), "worst": float(r["worst_day_gbp"]),
                         "tim": float(r["time_in_market_pct"])})
        metrics_out[per] = rows
    data = {
        "t": t_ms,
        "period": days["period"].tolist(),
        "pnl": {s: [round(float(v), 2) for v in days[s]] for s in ["always_long", "always_short", "v1", "v2"]},
        "guard": [[int(d.value // 10**6), int(r["blocked_halfhours"]), round(float(r["v2_minus_v1_gbp"]), 2)]
                  for d, r in g.iterrows()],
        "metrics": metrics_out,
    }
    html = (INTERACTIVE_TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__THRESHOLD__", f"{threshold:,.0f}"))
    path.write_text(html, encoding="utf-8")
