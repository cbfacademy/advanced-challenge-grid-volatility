"""Performance metrics on daily P&L (UTC delivery days), plus the kill-condition monitor."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config

STRATEGIES = ["always_long", "always_short", "v1", "v2"]
LABELS = {"always_long": "Always long (+25MW)", "always_short": "Always short (-25MW)",
          "v1": "V1: short above +10%", "v2": "V2: V1 + tight-system guard", "do_nothing": "Do nothing (0MW)"}


def daily(pnl: pd.DataFrame, col: str) -> pd.Series:
    s = pnl.groupby("date_utc")[col].sum()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def summarise(pnl: pd.DataFrame, name: str, pnl_col: str | None = None, pos_col: str | None = None) -> dict:
    pnl_col = pnl_col or f"pnl_{name}"
    pos_col = pos_col or f"pos_{name}"
    d = daily(pnl, pnl_col)
    cum = d.cumsum()
    weekly = d.groupby(d.index.to_period("W-SUN")).sum()
    active = pnl[pos_col] != 0 if pos_col in pnl else pnl[pnl_col] != 0
    active_days = pnl.loc[active, "date_utc"].unique()
    d_active = d[d.index.isin(pd.to_datetime(active_days))]
    traded = pnl.loc[active, pnl_col]
    std = d.std()
    return {
        "strategy": LABELS.get(name, name),
        "total_pnl_gbp": d.sum(),
        "pnl_per_year_gbp": d.sum() / max(len(d), 1) * 365,
        "sharpe_annualised": d.mean() / std * np.sqrt(365) if std > 0 else np.nan,
        "max_drawdown_gbp": (cum - cum.cummax()).min() if len(cum) else 0.0,
        "worst_day_gbp": d.min(),
        "worst_day": d.idxmin().date().isoformat() if len(d) and d.min() < 0 else "",
        "worst_week_gbp": weekly.min() if len(weekly) else 0.0,
        "profitable_days_pct": 100 * (d_active > 0).mean() if len(d_active) else np.nan,
        "hit_rate_halfhours_pct": 100 * (traded > 0).mean() if len(traded) else np.nan,
        "time_in_market_pct": 100 * active.mean(),
        "days": len(d),
    }


def summary_table(pnl: pd.DataFrame, period: str | None) -> pd.DataFrame:
    sub = pnl if period is None else pnl[pnl["period"] == period]
    rows = [summarise(sub, s) for s in STRATEGIES]
    rows.insert(0, {"strategy": LABELS["do_nothing"], "total_pnl_gbp": 0.0, "pnl_per_year_gbp": 0.0,
                    "max_drawdown_gbp": 0.0, "worst_day_gbp": 0.0, "time_in_market_pct": 0.0,
                    "days": sub["date_utc"].nunique()})
    t = pd.DataFrame(rows)
    short_total = t.loc[t["strategy"] == LABELS["always_short"], "total_pnl_gbp"].iloc[0]
    t["net_of_always_short_gbp"] = t["total_pnl_gbp"] - short_total
    t.insert(0, "period", period or "full")
    return t


def kill_monitor(pnl: pd.DataFrame, cfg: Config, col: str = "pnl_v2", period: str = "validation") -> pd.DataFrame:
    """Day-by-day check of the kill conditions over a period. Each K column is True on a breach day.
    K1 and K2 are stop conditions; K3 and K4 trigger a review."""
    d = daily(pnl[pnl["period"] == period], col)
    cum = d.cumsum()
    w = cfg.kill_rolling_days
    out = pd.DataFrame({
        "daily_pnl_gbp": d,
        "drawdown_gbp": cum - cum.cummax(),
        f"rolling_{w}d_pnl_gbp": d.rolling(w, min_periods=w).sum(),
    })
    out["K1_daily_loss"] = out["daily_pnl_gbp"] < cfg.kill_daily_loss_gbp
    out["K2_drawdown"] = out["drawdown_gbp"] < cfg.kill_drawdown_gbp
    out["K3_rolling_pnl_negative"] = out[f"rolling_{w}d_pnl_gbp"] < 0
    out["K4_guard_miss"] = out["daily_pnl_gbp"] < cfg.kill_guard_miss_gbp
    out.index.name = "date_utc"
    return out


def kill_summary(mon: pd.DataFrame, cfg: Config, period: str) -> pd.DataFrame:
    desc = {"K1_daily_loss": f"Stop: single-day loss worse than -£{abs(cfg.kill_daily_loss_gbp):,.0f}",
            "K2_drawdown": f"Stop: drawdown from peak worse than -£{abs(cfg.kill_drawdown_gbp):,.0f}",
            "K3_rolling_pnl_negative": f"Review: rolling {cfg.kill_rolling_days}-day P&L below zero",
            "K4_guard_miss": f"Review: day worse than -£{abs(cfg.kill_guard_miss_gbp):,.0f} that the guard let through"}
    rows = []
    for k, text in desc.items():
        hits = mon.index[mon[k]]
        rows.append({"period": period, "condition": k, "description": text, "days_breached": len(hits),
                     "first_breach": hits.min().date().isoformat() if len(hits) else "",
                     "last_breach": hits.max().date().isoformat() if len(hits) else ""})
    return pd.DataFrame(rows)
