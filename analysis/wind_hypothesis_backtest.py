from __future__ import annotations

import argparse
import html
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "analysis" / "wind_hypothesis_backtest.html"
TZ = "Europe/London"
ELEXON_START = pd.Timestamp("2023-01-01").date()
WIND_THRESHOLD = 0.30
POSITION_MW = 25.0


def load_market(end_date: pd.Timestamp) -> pd.DataFrame:
    market = pd.read_parquet(DATA / "market_prices.parquet")
    for column in ("da_hr_epex_price", "da_hh_epex_price", "cashout_price"):
        market[column] = pd.to_numeric(market[column], errors="coerce")

    local_time = market["delivery_start_utc"].dt.tz_convert(TZ)
    market["date"] = local_time.dt.date
    market["hour_start"] = market["delivery_start_utc"].dt.floor("h")
    market = market.loc[market["date"] <= end_date].copy()
    market["auction_move"] = (
        market["da_hh_epex_price"] - market["da_hr_epex_price"]
    )
    market["cashout_move"] = (
        market["cashout_price"] - market["da_hh_epex_price"]
    )
    return market


def load_generation_forecasts() -> pd.DataFrame:
    forecast = pd.read_parquet(
        DATA / "3rd Party Forecasts" / "generation_forecasts.parquet"
    )
    for column in (
        "wind_forecast",
        "solar_forecast",
        "nuclear_forecast",
        "demand",
    ):
        forecast[column] = pd.to_numeric(forecast[column], errors="coerce")

    forecast["hour_start"] = forecast["delivery_start_utc"].dt.floor("h")
    for fuel in ("wind", "solar", "nuclear"):
        forecast[f"{fuel}_share"] = (
            forecast[f"{fuel}_forecast"] / forecast["demand"]
        )
    forecast["renewable_share"] = (
        forecast["wind_forecast"] + forecast["solar_forecast"]
    ) / forecast["demand"]
    forecast["non_gas_share"] = (
        forecast["wind_forecast"]
        + forecast["solar_forecast"]
        + forecast["nuclear_forecast"]
    ) / forecast["demand"]

    features = (
        "wind_share",
        "solar_share",
        "nuclear_share",
        "renewable_share",
        "non_gas_share",
    )
    return (
        forecast.groupby("hour_start", as_index=False)
        .agg(**{feature: (feature, "mean") for feature in features})
    )


def load_fuel_prices() -> pd.DataFrame:
    raw = pd.read_excel(DATA / "fuel_prices.xlsx", header=None)
    fuel = raw.iloc[2:].copy()
    fuel.columns = raw.iloc[1].tolist()
    fuel = fuel.rename(columns={fuel.columns[0]: "date"})
    fuel["date"] = pd.to_datetime(fuel["date"], errors="coerce").dt.date
    column = "UK CCGT SRMC (£/MWh)"
    fuel[column] = pd.to_numeric(fuel[column], errors="coerce")
    return fuel[["date", column]].dropna()


def elexon_vintages(end_date: pd.Timestamp) -> pd.DataFrame:
    wind = pd.read_parquet(
        DATA
        / "3rd Party Forecasts"
        / "Elexon Forecasts"
        / "elexon_wind_fc.parquet"
    )
    wind["generation"] = pd.to_numeric(wind["generation"], errors="coerce")
    local_date = wind["startTime"].dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")
    wind["delivery_date"] = pd.to_datetime(local_date).dt.date
    wind = wind.loc[wind["delivery_date"] <= end_date].copy()
    decision_date = (
        pd.to_datetime(local_date.loc[wind.index]) - pd.Timedelta(days=1)
    ).dt.strftime("%Y-%m-%d")
    vintages = []

    for hour, name in ((9, "forecast_9am"), (15, "forecast_3pm")):
        local_cutoff = pd.to_datetime(
            decision_date + f" {hour:02d}:00"
        ).dt.tz_localize(TZ)
        eligible = wind.loc[
            wind["publishTime"] < local_cutoff.dt.tz_convert("UTC"),
            ["startTime", "publishTime", "generation"],
        ]
        latest = (
            eligible.sort_values(["startTime", "publishTime"])
            .drop_duplicates("startTime", keep="last")
            .rename(
                columns={"startTime": "hour_start", "generation": name}
            )
            [["hour_start", name]]
        )
        vintages.append(latest)

    result = vintages[0].merge(vintages[1], on="hour_start", how="inner")
    result["wind_revision_mw"] = (
        result["forecast_3pm"] - result["forecast_9am"]
    )
    return result


def add_positions(market: pd.DataFrame) -> pd.DataFrame:
    market["position_9am_mw"] = np.where(
        market["wind_share"] >= WIND_THRESHOLD, -POSITION_MW, 0.0
    )
    market["position_solar_mw"] = np.where(
        market["solar_share"] >= 0.005, -POSITION_MW, 0.0
    )
    market["position_nuclear_mw"] = np.where(
        market["nuclear_share"] >= 0.20, -POSITION_MW, 0.0
    )
    market["position_renewable_mw"] = np.where(
        market["renewable_share"] >= 0.30, -POSITION_MW, 0.0
    )
    market["position_non_gas_mw"] = np.where(
        market["non_gas_share"] >= 0.45, -POSITION_MW, 0.0
    )
    market["revision_mw"] = market["wind_revision_mw"]
    market["position_revision_mw"] = np.select(
        [
            market["revision_mw"] > 0,
            market["revision_mw"] < 0,
        ],
        [-POSITION_MW, POSITION_MW],
        default=0.0,
    )
    market["position_combined_mw"] = np.where(
        market["revision_mw"] > 0,
        -POSITION_MW,
        np.where(
            market["revision_mw"] < 0,
            POSITION_MW,
            market["position_9am_mw"],
        ),
    )
    return market


def daily_pnl(
    frame: pd.DataFrame, position_9am: np.ndarray, position_3pm: np.ndarray
) -> pd.Series:
    pnl = 0.5 * (
        position_9am * frame["auction_move"].to_numpy()
        + position_3pm * frame["cashout_move"].to_numpy()
    )
    return pd.DataFrame({"date": frame["date"].to_numpy(), "pnl": pnl}).groupby(
        "date"
    )["pnl"].sum()


def performance(
    frame: pd.DataFrame,
    position_9am: np.ndarray,
    position_3pm: np.ndarray,
    name: str,
) -> dict[str, float | int | str]:
    daily = daily_pnl(frame, position_9am, position_3pm)
    equity = daily.cumsum()
    peaks = pd.concat(
        [pd.Series([0.0]), equity.reset_index(drop=True)], ignore_index=True
    ).cummax().iloc[1:]
    drawdown = equity.reset_index(drop=True) - peaks.reset_index(drop=True)
    active = (np.abs(position_9am) + np.abs(position_3pm)) > 0
    active_dates = frame.loc[active, "date"].nunique()
    daily_std = daily.std(ddof=1)
    sharpe = (
        daily.mean() / daily_std * math.sqrt(252)
        if pd.notna(daily_std) and daily_std > 0
        else float("nan")
    )
    active_daily = daily.loc[
        daily.index.isin(frame.loc[active, "date"].unique())
    ]
    return {
        "strategy": name,
        "periods": len(frame),
        "days": len(daily),
        "active_days": int(active_dates),
        "active_half_hours": int(active.sum()),
        "total_pnl": float(daily.sum()),
        "mean_daily_pnl": float(daily.mean()),
        "daily_sd": float(daily_std),
        "daily_sharpe_252": float(sharpe),
        "profitable_days_pct": float((daily > 0).mean() * 100),
        "profitable_active_days_pct": (
            float((active_daily > 0).mean() * 100) if len(active_daily) else 0.0
        ),
        "best_day": float(daily.max()),
        "worst_day": float(daily.min()),
        "max_drawdown": float(drawdown.min()),
    }


def monthly_cumulative(daily: pd.Series) -> pd.Series:
    series = daily.copy()
    series.index = pd.to_datetime(series.index.astype(str))
    return series.resample("ME").sum().cumsum()


def svg_chart(
    title: str,
    subtitle: str,
    series: list[tuple[str, list[tuple[str, float]], str]],
    y_label: str,
    width: int = 900,
    height: int = 370,
) -> str:
    left, right, top, bottom = 88, 24, 55, 82
    chart_w, chart_h = width - left - right, height - top - bottom
    all_values = [point[1] for _, values, _ in series for point in values]
    if not all_values:
        return "<p>No observations available for this chart.</p>"
    low, high = min(all_values), max(all_values)
    spread = high - low or 1.0
    low -= spread * 0.08
    high += spread * 0.08

    def x_at(index: int, length: int) -> float:
        return left + (index / max(length - 1, 1)) * chart_w

    def y_at(value: float) -> float:
        return top + (high - value) / (high - low) * chart_h

    output = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(title)}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="{left}" y="25" class="chart-title">{html.escape(title)}</text>',
        f'<text x="{left}" y="43" class="chart-subtitle">{html.escape(subtitle)}</text>',
    ]
    for tick in range(5):
        value = low + (high - low) * tick / 4
        y = y_at(value)
        output.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" '
            'class="grid"/>'
        )
        output.append(
            f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" '
            f'class="axis">{value:,.0f}</text>'
        )
    if low <= 0 <= high:
        y = y_at(0)
        output.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" '
            'class="zero"/>'
        )
    output.extend(
        [
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" '
            'class="axis-line"/>',
            f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" '
            f'y2="{height-bottom}" class="axis-line"/>',
            f'<text transform="translate(18 {top + chart_h / 2:.1f}) rotate(-90)" '
            f'text-anchor="middle" class="axis-title">{html.escape(y_label)}</text>',
        ]
    )

    legend_columns = min(3, len(series))
    legend_width = chart_w / max(legend_columns, 1)
    for index, (name, values, color) in enumerate(series):
        if len(values) == 1:
            x, y = x_at(0, 1), y_at(values[0][1])
            output.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>'
            )
        else:
            points = " ".join(
                f"{x_at(i, len(values)):.1f},{y_at(value):.1f}"
                for i, (_, value) in enumerate(values)
            )
            output.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" '
                'stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round"/>'
            )
            for i, (label, value) in enumerate(values):
                x, y = x_at(i, len(values)), y_at(value)
                output.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}">'
                    f'<title>{html.escape(str(label))}: {value:,.2f}</title></circle>'
                )
        column = index % legend_columns
        row = index // legend_columns
        legend_x = left + column * legend_width
        legend_y = height - 35 + row * 18
        output.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x+20}" '
            f'y2="{legend_y}" stroke="{color}" stroke-width="3"/>'
        )
        output.append(
            f'<text x="{legend_x+26}" y="{legend_y+4}" class="legend">'
            f'{html.escape(name)}</text>'
        )

    if series and series[0][1] and len(series[0][1]) > 1:
        values = series[0][1]
        for i in np.linspace(0, len(values) - 1, min(6, len(values))).astype(int):
            label, _ = values[i]
            x = x_at(i, len(values))
            output.append(
                f'<text x="{x:.1f}" y="{height-bottom+20}" text-anchor="middle" '
                f'class="axis">{html.escape(str(label)[:7])}</text>'
            )
    output.append("</svg>")
    return "\n".join(output)


def money(value: float) -> str:
    return f"-£{abs(value):,.0f}" if value < 0 else f"£{value:,.0f}"


def number(value: float, places: int = 2) -> str:
    return f"{value:.{places}f}" if math.isfinite(value) else "—"


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{item}</td>" for item in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_report(end_date: pd.Timestamp) -> tuple[str, pd.DataFrame]:
    market = load_market(end_date)
    generation = load_generation_forecasts()
    fuel = load_fuel_prices()
    vintages = elexon_vintages(end_date)

    market = market.merge(generation, on="hour_start", how="left")
    market = market.merge(vintages, on="hour_start", how="left")
    market = add_positions(market)
    valid = market.dropna(
        subset=[
            "auction_move",
            "cashout_move",
            "wind_share",
            "solar_share",
            "nuclear_share",
            "renewable_share",
            "non_gas_share",
        ]
    ).copy()
    elexon = valid.loc[
        (valid["date"] >= ELEXON_START)
        & valid["wind_revision_mw"].notna()
    ].copy()
    if valid.empty or elexon.empty:
        raise ValueError("No complete market, forecast, and Elexon observations found.")

    daily_market = (
        valid.groupby("date", as_index=False)
        .agg(
            wind_share=("wind_share", "mean"),
            solar_share=("solar_share", "mean"),
            nuclear_share=("nuclear_share", "mean"),
            renewable_share=("renewable_share", "mean"),
            non_gas_share=("non_gas_share", "mean"),
            da_hr=("da_hr_epex_price", "mean"),
            da_hh=("da_hh_epex_price", "mean"),
            auction_move=("auction_move", "mean"),
        )
        .merge(fuel, on="date", how="left")
        .dropna(subset=["UK CCGT SRMC (£/MWh)"])
    )
    daily_market["srmc_gap"] = (
        daily_market["da_hh"] - daily_market["UK CCGT SRMC (£/MWh)"]
    )
    feature_bins: dict[str, pd.DataFrame] = {}
    for feature in (
        "wind_share",
        "nuclear_share",
        "renewable_share",
        "non_gas_share",
    ):
        binned = daily_market.copy()
        binned["bin"] = pd.qcut(
            binned[feature], 5, labels=False, duplicates="drop"
        )
        feature_bins[feature] = (
            binned.groupby("bin", observed=True)
            .agg(
                days=("date", "size"),
                mean_share=(feature, "mean"),
                srmc_gap=("srmc_gap", "mean"),
                below_srmc=(
                    "srmc_gap",
                    lambda values: (values < 0).mean() * 100,
                ),
                auction_move=("auction_move", "mean"),
            )
            .reset_index()
        )
    solar_cutoff = 0.005
    solar_data = daily_market.copy()
    solar_data["bin"] = np.where(
        solar_data["solar_share"] >= solar_cutoff,
        f"≥{solar_cutoff:.1%}",
        f"<{solar_cutoff:.1%}",
    )
    feature_bins["solar_share"] = (
        solar_data.groupby("bin", observed=True)
        .agg(
            days=("date", "size"),
            mean_share=("solar_share", "mean"),
            srmc_gap=("srmc_gap", "mean"),
            below_srmc=("srmc_gap", lambda values: (values < 0).mean() * 100),
            auction_move=("auction_move", "mean"),
        )
        .reset_index()
    )

    full_strategies: list[tuple[str, np.ndarray, np.ndarray]] = [
        (
            "Wind ≥30%, short and hold",
            valid["position_9am_mw"].to_numpy(),
            valid["position_9am_mw"].to_numpy(),
        ),
        (
            "Solar ≥0.5%, short and hold",
            valid["position_solar_mw"].to_numpy(),
            valid["position_solar_mw"].to_numpy(),
        ),
        (
            "Nuclear ≥20%, short and hold",
            valid["position_nuclear_mw"].to_numpy(),
            valid["position_nuclear_mw"].to_numpy(),
        ),
        (
            "Wind + solar ≥30%, short and hold",
            valid["position_renewable_mw"].to_numpy(),
            valid["position_renewable_mw"].to_numpy(),
        ),
        (
            "Wind + solar + nuclear ≥45%, short and hold",
            valid["position_non_gas_mw"].to_numpy(),
            valid["position_non_gas_mw"].to_numpy(),
        ),
        (
            "Gas benchmark: always long (+25 MW)",
            np.full(len(valid), POSITION_MW),
            np.full(len(valid), POSITION_MW),
        ),
        (
            "Gas benchmark: always short (−25 MW)",
            np.full(len(valid), -POSITION_MW),
            np.full(len(valid), -POSITION_MW),
        ),
        ("No action (flat)", np.zeros(len(valid)), np.zeros(len(valid))),
    ]
    directional_features = (
        ("Wind ≥30%", "position_9am_mw"),
        ("Solar ≥0.5%", "position_solar_mw"),
        ("Nuclear ≥20%", "position_nuclear_mw"),
    )
    directional_strategies: list[tuple[str, np.ndarray, np.ndarray]] = []
    directional_daily: dict[str, pd.Series] = {}
    for label, column in directional_features:
        short_position = valid[column].to_numpy()
        long_position = -short_position
        for direction, position in (("Long", long_position), ("Short", short_position)):
            name = f"{direction} when {label}"
            directional_strategies.append((name, position, position))
            directional_daily[name] = daily_pnl(valid, position, position)
    directional_stats = [
        performance(valid, x, y, name)
        for name, x, y in directional_strategies
    ]
    full_stats = [
        performance(valid, x, y, name) for name, x, y in full_strategies
    ]
    full_daily = {
        name: daily_pnl(valid, x, y)
        for name, x, y in full_strategies
    }
    full_daily.update(directional_daily)

    revision = elexon["wind_revision_mw"].to_numpy()
    x_wind = elexon["position_9am_mw"].to_numpy()
    x_renewable = elexon["position_renewable_mw"].to_numpy()
    matched_strategies: list[tuple[str, np.ndarray, np.ndarray]] = [
        (
            "Elexon revision only",
            np.zeros(len(elexon)),
            elexon["position_revision_mw"].to_numpy(),
        ),
        ("Wind 9am signal held", x_wind, x_wind),
        (
            "Wind + solar 9am signal held",
            x_renewable,
            x_renewable,
        ),
        (
            "Combined: wind 9am + revision",
            x_wind,
            elexon["position_combined_mw"].to_numpy(),
        ),
        (
            "Combined: wind + solar 9am + revision",
            x_renewable,
            np.where(
                revision > 0,
                -POSITION_MW,
                np.where(revision < 0, POSITION_MW, x_renewable),
            ),
        ),
        (
            "Gas benchmark: always short (−25 MW)",
            np.full(len(elexon), -POSITION_MW),
            np.full(len(elexon), -POSITION_MW),
        ),
        (
            "No action (flat)",
            np.zeros(len(elexon)),
            np.zeros(len(elexon)),
        ),
    ]
    matched_stats = [
        performance(elexon, x, y, name) for name, x, y in matched_strategies
    ]
    matched_daily = {
        name: daily_pnl(elexon, x, y)
        for name, x, y in matched_strategies
    }

    revision_market = elexon.loc[
        elexon["delivery_start_utc"].dt.tz_convert(TZ).dt.minute == 0
    ].copy()
    revision_market["revision_quintile"] = pd.qcut(
        revision_market["wind_revision_mw"],
        5,
        labels=False,
        duplicates="drop",
    )
    revision_bins = (
        revision_market.groupby("revision_quintile", observed=True)
        .agg(
            periods=("auction_move", "size"),
            revision=("wind_revision_mw", "mean"),
            auction_move=("auction_move", "mean"),
            cashout_move=("cashout_move", "mean"),
        )
        .reset_index()
    )

    wind_sensitivity = []
    for threshold in (0.20, 0.30, 0.40):
        position = np.where(
            valid["wind_share"].to_numpy() >= threshold, -POSITION_MW, 0.0
        )
        wind_sensitivity.append(
            performance(
                valid,
                position,
                position,
                f"Wind ≥{threshold:.0%}, held",
            )
        )
    generation_sensitivity = []
    for feature, position, threshold in (
        ("Solar share ≥0.5%", "position_solar_mw", 0.005),
        ("Nuclear share ≥20%", "position_nuclear_mw", 0.20),
        ("Wind + solar ≥30%", "position_renewable_mw", 0.30),
        ("Wind + solar + nuclear ≥45%", "position_non_gas_mw", 0.45),
    ):
        positions = valid[position].to_numpy()
        generation_sensitivity.append(
            performance(valid, positions, positions, feature)
        )
    revision_sensitivity = []
    for threshold in (0, 250, 500, 1000):
        y = np.where(
            revision > threshold,
            -POSITION_MW,
            np.where(revision < -threshold, POSITION_MW, x_wind),
        )
        revision_sensitivity.append(
            performance(
                elexon,
                x_wind,
                y,
                f"Combined, |revision| > {threshold:,} MW",
            )
        )

    annual_rows = []
    full_year = valid["date"].map(lambda value: value.year)
    for year in sorted(full_year.unique()):
        subset = valid.loc[full_year == year]
        positions = {
            "wind_30pct_pnl": subset["position_9am_mw"].to_numpy(),
            "solar_05pct_pnl": subset["position_solar_mw"].to_numpy(),
            "nuclear_20pct_pnl": subset["position_nuclear_mw"].to_numpy(),
            "renewable_30pct_pnl": subset["position_renewable_mw"].to_numpy(),
            "non_gas_45pct_pnl": subset["position_non_gas_mw"].to_numpy(),
        }
        annual_rows.append(
            {
                "year": year,
                "scope": "Full data",
                **{
                    key: daily_pnl(subset, position, position).sum()
                    for key, position in positions.items()
                },
                **{
                    f"{feature}_{direction}_pnl": daily_pnl(
                        subset,
                        (
                            subset[column].to_numpy()
                            if direction == "short"
                            else -subset[column].to_numpy()
                        ),
                        (
                            subset[column].to_numpy()
                            if direction == "short"
                            else -subset[column].to_numpy()
                        ),
                    ).sum()
                    for feature, column in directional_features
                    for direction in ("long", "short")
                },
                "gas_always_long_pnl": daily_pnl(
                    subset,
                    np.full(len(subset), POSITION_MW),
                    np.full(len(subset), POSITION_MW),
                ).sum(),
                "always_short_pnl": daily_pnl(
                    subset,
                    np.full(len(subset), -POSITION_MW),
                    np.full(len(subset), -POSITION_MW),
                ).sum(),
                "no_action_pnl": 0.0,
            }
        )
    for year in sorted(elexon["date"].map(lambda value: value.year).unique()):
        subset = elexon.loc[elexon["date"].map(lambda value: value.year) == year]
        x = subset["position_9am_mw"].to_numpy()
        r = subset["wind_revision_mw"].to_numpy()
        y_revision = np.where(
            r > 0, -POSITION_MW, np.where(r < 0, POSITION_MW, 0.0)
        )
        y_combined = np.where(
            r > 0, -POSITION_MW, np.where(r < 0, POSITION_MW, x)
        )
        annual_rows.append(
            {
                "year": year,
                "scope": "Elexon overlap",
                "wind_30pct_pnl": daily_pnl(subset, x, x).sum(),
                "solar_05pct_pnl": daily_pnl(
                    subset,
                    subset["position_solar_mw"].to_numpy(),
                    subset["position_solar_mw"].to_numpy(),
                ).sum(),
                "nuclear_20pct_pnl": daily_pnl(
                    subset,
                    subset["position_nuclear_mw"].to_numpy(),
                    subset["position_nuclear_mw"].to_numpy(),
                ).sum(),
                "renewable_30pct_pnl": daily_pnl(
                    subset,
                    subset["position_renewable_mw"].to_numpy(),
                    subset["position_renewable_mw"].to_numpy(),
                ).sum(),
                "non_gas_45pct_pnl": daily_pnl(
                    subset,
                    subset["position_non_gas_mw"].to_numpy(),
                    subset["position_non_gas_mw"].to_numpy(),
                ).sum(),
                "revision_only_pnl": daily_pnl(
                    subset, np.zeros(len(subset)), y_revision
                ).sum(),
                "combined_pnl": daily_pnl(subset, x, y_combined).sum(),
                "gas_always_long_pnl": daily_pnl(
                    subset,
                    np.full(len(subset), POSITION_MW),
                    np.full(len(subset), POSITION_MW),
                ).sum(),
                "always_short_pnl": daily_pnl(
                    subset,
                    np.full(len(subset), -POSITION_MW),
                    np.full(len(subset), -POSITION_MW),
                ).sum(),
                "no_action_pnl": 0.0,
            }
        )
    annual = pd.DataFrame(annual_rows)
    annual.to_csv(ROOT / "analysis" / "wind_hypothesis_annual_pnl.csv", index=False)

    gap_colors = {
        "wind_share": "#2563eb",
        "solar_share": "#f59e0b",
        "nuclear_share": "#7c3aed",
        "renewable_share": "#059669",
        "non_gas_share": "#dc2626",
    }
    feature_names = {
        "wind_share": "Wind",
        "solar_share": "Solar",
        "nuclear_share": "Nuclear",
        "renewable_share": "Wind + solar",
        "non_gas_share": "Wind + solar + nuclear",
    }
    generation_gap_chart = svg_chart(
        "Forecast generation mix vs DA-HH price minus CCGT SRMC",
        "Daily quintiles for wind, nuclear, and combined shares; solar is shown separately.",
        [
            (
                feature_names[feature],
                [
                    (
                        str(row["bin"])
                        if feature == "solar_share"
                        else f"Q{i + 1}",
                        float(row["srmc_gap"]),
                    )
                    for i, row in feature_bins[feature].iterrows()
                ],
                gap_colors[feature],
            )
            for feature in (
                "wind_share",
                "nuclear_share",
                "renewable_share",
                "non_gas_share",
            )
        ],
        "DA-HH less SRMC (£/MWh)",
        height=440,
    )
    wind_spread_chart = svg_chart(
        "Generation mix does not sort the 9am→3pm auction spread",
        "Mean DA-HH minus DA-HR price by daily wind-share quintile.",
        [
            (
                "Wind share",
                [
                    (f"Q{i + 1}", float(row["auction_move"]))
                    for i, row in feature_bins["wind_share"].iterrows()
                ],
                "#2563eb",
            ),
            (
                "Wind + solar",
                [
                    (f"Q{i + 1}", float(row["auction_move"]))
                    for i, row in feature_bins["renewable_share"].iterrows()
                ],
                "#059669",
            ),
            (
                "Wind + solar + nuclear",
                [
                    (f"Q{i + 1}", float(row["auction_move"]))
                    for i, row in feature_bins["non_gas_share"].iterrows()
                ],
                "#dc2626",
            ),
        ],
        "DA-HH less DA-HR (£/MWh)",
        height=410,
    )
    solar_gap_chart = svg_chart(
        "Solar threshold and the fair-value gap",
        "Daily forecast solar generation below / above 0.5% of demand.",
        [
            (
                "DA-HH less SRMC",
                [
                    (str(row["bin"]), float(row["srmc_gap"]))
                    for _, row in feature_bins["solar_share"].iterrows()
                ],
                "#f59e0b",
            )
        ],
        "DA-HH less SRMC (£/MWh)",
    )
    full_chart = svg_chart(
        "Cumulative gross P/L by generation-mix signal",
        "Daily P/L accumulated through 2 October 2026; 9am positions held to cashout.",
        [
            (name, list(monthly_cumulative(series).items()), color)
            for name, series, color in (
                (
                    "Wind ≥30%",
                    full_daily["Wind ≥30%, short and hold"],
                    "#2563eb",
                ),
                (
                    "Solar ≥0.5%",
                    full_daily["Solar ≥0.5%, short and hold"],
                    "#f59e0b",
                ),
                (
                    "Nuclear ≥20%",
                    full_daily["Nuclear ≥20%, short and hold"],
                    "#7c3aed",
                ),
                (
                    "Wind + solar ≥30%",
                    full_daily["Wind + solar ≥30%, short and hold"],
                    "#059669",
                ),
                (
                    "Wind + solar + nuclear ≥45%",
                    full_daily[
                        "Wind + solar + nuclear ≥45%, short and hold"
                    ],
                    "#dc2626",
                ),
                (
                    "Gas benchmark: always long",
                    full_daily["Gas benchmark: always long (+25 MW)"],
                    "#0891b2",
                ),
                (
                    "Gas benchmark: always short",
                    full_daily["Gas benchmark: always short (−25 MW)"],
                    "#475569",
                ),
                (
                    "No action",
                    full_daily["No action (flat)"],
                    "#94a3b8",
                ),
            )
        ],
        "Cumulative gross P/L (£)",
        height=500,
    )
    long_chart = svg_chart(
        "Cumulative gross P/L: go long when the generation signal is active",
        "Long 25 MW only when the specified forecast share threshold is met; otherwise flat.",
        [
            (
                label,
                list(monthly_cumulative(full_daily[name]).items()),
                color,
            )
            for label, name, color in (
                (
                    "Wind ≥30%",
                    "Long when Wind ≥30%",
                    "#2563eb",
                ),
                (
                    "Solar ≥0.5%",
                    "Long when Solar ≥0.5%",
                    "#f59e0b",
                ),
                (
                    "Nuclear ≥20%",
                    "Long when Nuclear ≥20%",
                    "#7c3aed",
                ),
                (
                    "Gas benchmark: always long",
                    "Gas benchmark: always long (+25 MW)",
                    "#0891b2",
                ),
                (
                    "Gas benchmark: always short",
                    "Gas benchmark: always short (−25 MW)",
                    "#475569",
                ),
                (
                    "No action",
                    "No action (flat)",
                    "#94a3b8",
                ),
            )
        ],
        "Cumulative gross P/L (£)",
        height=460,
    )
    short_chart = svg_chart(
        "Cumulative gross P/L: go short when the generation signal is active",
        "Short 25 MW only when the specified forecast share threshold is met; otherwise flat.",
        [
            (
                label,
                list(monthly_cumulative(full_daily[name]).items()),
                color,
            )
            for label, name, color in (
                (
                    "Wind ≥30%",
                    "Short when Wind ≥30%",
                    "#2563eb",
                ),
                (
                    "Solar ≥0.5%",
                    "Short when Solar ≥0.5%",
                    "#f59e0b",
                ),
                (
                    "Nuclear ≥20%",
                    "Short when Nuclear ≥20%",
                    "#7c3aed",
                ),
                (
                    "Gas benchmark: always long",
                    "Gas benchmark: always long (+25 MW)",
                    "#0891b2",
                ),
                (
                    "Gas benchmark: always short",
                    "Gas benchmark: always short (−25 MW)",
                    "#475569",
                ),
                (
                    "No action",
                    "No action (flat)",
                    "#94a3b8",
                ),
            )
        ],
        "Cumulative gross P/L (£)",
        height=460,
    )
    matched_chart = svg_chart(
        "Cumulative P/L on the Elexon overlap",
        "1,367 delivery days from 2 January 2023 to 2 October 2026; hourly wind revisions applied to both half-hours.",
        [
            (name, list(monthly_cumulative(series).items()), color)
            for name, series, color in (
                (
                    "Revision-only",
                    matched_daily["Elexon revision only"],
                    "#7c3aed",
                ),
                (
                    "Wind held",
                    matched_daily["Wind 9am signal held"],
                    "#2563eb",
                ),
                (
                    "Wind + solar held",
                    matched_daily["Wind + solar 9am signal held"],
                    "#059669",
                ),
                (
                    "Combined wind/revision",
                    matched_daily["Combined: wind 9am + revision"],
                    "#d97706",
                ),
                (
                    "Combined renewables/revision",
                    matched_daily[
                        "Combined: wind + solar 9am + revision"
                    ],
                    "#dc2626",
                ),
                (
                    "Gas benchmark: always long",
                    matched_daily["Gas benchmark: always long (+25 MW)"],
                    "#0891b2",
                ),
                (
                    "Gas benchmark: always short",
                    matched_daily["Gas benchmark: always short (−25 MW)"],
                    "#475569",
                ),
                (
                    "No action",
                    matched_daily["No action (flat)"],
                    "#94a3b8",
                ),
            )
        ],
        "Cumulative gross P/L (£)",
        height=500,
    )
    revision_chart = svg_chart(
        "Elexon revision bins vs auction repricing",
        "Hourly delivery periods only; forecasts are the latest versions published before 9am and 3pm UK time.",
        [
            (
                "DA-HH less DA-HR",
                [
                    (f"Q{i + 1}", float(row["auction_move"]))
                    for i, row in revision_bins.iterrows()
                ],
                "#7c3aed",
            )
        ],
        "DA-HH less DA-HR (£/MWh)",
    )

    full_rows = [
        [
            html.escape(str(item["strategy"])),
            f"{int(item['days']):,}",
            f"{int(item['active_days']):,}",
            money(float(item["total_pnl"])),
            f"{item['profitable_days_pct']:.1f}%",
            number(float(item["daily_sharpe_252"])),
            money(float(item["max_drawdown"])),
        ]
        for item in full_stats
    ]
    directional_rows = [
        [
            html.escape(str(item["strategy"])),
            f"{int(item['active_days']):,}",
            f"{int(item['active_half_hours']):,}",
            money(float(item["total_pnl"])),
            f"{item['profitable_days_pct']:.1f}%",
            number(float(item["daily_sharpe_252"])),
            money(float(item["max_drawdown"])),
        ]
        for item in directional_stats
    ]
    matched_rows = [
        [
            html.escape(str(item["strategy"])),
            f"{int(item['active_days']):,}",
            money(float(item["total_pnl"])),
            f"{item['profitable_days_pct']:.1f}%",
            number(float(item["daily_sharpe_252"])),
            money(float(item["max_drawdown"])),
        ]
        for item in matched_stats
    ]
    generation_rows = []
    for feature in (
        "wind_share",
        "solar_share",
        "nuclear_share",
        "renewable_share",
        "non_gas_share",
    ):
        bins = feature_bins[feature]
        bins = bins.sort_values("mean_share")
        for i, (_, row) in enumerate(bins.iterrows()):
            bin_label = (
                str(row["bin"])
                if feature == "solar_share"
                else f"Q{i + 1}"
            )
            generation_rows.append(
                [
                    html.escape(feature_names[feature]),
                    html.escape(bin_label),
                    f"{row['days']:,.0f}",
                    f"{row['mean_share']:.1%}",
                    f"{row['srmc_gap']:+.2f}",
                    f"{row['below_srmc']:.1f}%",
                    f"{row['auction_move']:+.2f}",
                ]
            )
    revision_rows = [
        [
            f"Q{int(row['revision_quintile']) + 1}",
            f"{row['periods']:,.0f}",
            f"{row['revision']:+,.0f}",
            f"{row['auction_move']:+.2f}",
            f"{row['cashout_move']:+.2f}",
        ]
        for _, row in revision_bins.iterrows()
    ]
    sensitivity_rows = [
        [
            html.escape(str(row["strategy"])),
            money(float(row["total_pnl"])),
            f"{row['profitable_days_pct']:.1f}%",
            money(float(row["max_drawdown"])),
        ]
        for row in [
            *wind_sensitivity,
            *generation_sensitivity,
            *revision_sensitivity,
        ]
    ]
    annual_table_rows = []
    for _, row in annual.iterrows():
        annual_table_rows.append(
            [
                str(row["year"]),
                html.escape(str(row["scope"])),
                money(float(row["wind_30pct_pnl"])),
                (
                    money(float(row["solar_05pct_pnl"]))
                    if pd.notna(row.get("solar_05pct_pnl"))
                    else "—"
                ),
                (
                    money(float(row["nuclear_20pct_pnl"]))
                    if pd.notna(row.get("nuclear_20pct_pnl"))
                    else "—"
                ),
                (
                    money(float(row["renewable_30pct_pnl"]))
                    if pd.notna(row.get("renewable_30pct_pnl"))
                    else "—"
                ),
                (
                    money(float(row["non_gas_45pct_pnl"]))
                    if pd.notna(row.get("non_gas_45pct_pnl"))
                    else "—"
                ),
                money(float(row["gas_always_long_pnl"])),
                money(float(row["always_short_pnl"])),
                money(float(row["no_action_pnl"])),
                (
                    money(float(row["revision_only_pnl"]))
                    if pd.notna(row.get("revision_only_pnl"))
                    else "—"
                ),
                (
                    money(float(row["combined_pnl"]))
                    if pd.notna(row.get("combined_pnl"))
                    else "—"
                ),
            ]
        )

    complete_dates = valid["date"].nunique()
    wind_active_periods = int((valid["position_9am_mw"] != 0).sum())
    html_report = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Generation mix backtest</title>
<style>
body{{font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;color:#172033;max-width:1100px;margin:2rem auto;padding:0 1.25rem}}
h1,h2{{line-height:1.2}}h1{{margin-bottom:.25rem}}h2{{margin-top:2rem}}
.lede,.note{{color:#475569}}.callout{{background:#eff6ff;border-left:4px solid #2563eb;padding:1rem 1.2rem;margin:1.5rem 0}}
.chart{{margin:1.25rem 0 2rem;border:1px solid #e2e8f0;border-radius:8px;padding:.5rem;overflow-x:auto}}
svg{{width:100%;height:auto;min-width:640px}}.chart-title{{font:600 16px system-ui;fill:#172033}}.chart-subtitle{{font:12px system-ui;fill:#64748b}}
.grid{{stroke:#e2e8f0;stroke-width:1}}.zero{{stroke:#64748b;stroke-width:1.2;stroke-dasharray:5 4}}.axis-line{{stroke:#64748b;stroke-width:1}}
.axis{{font:11px system-ui;fill:#475569}}.axis-title{{font:12px system-ui;fill:#334155}}.legend{{font:12px system-ui;fill:#334155}}
table{{width:100%;border-collapse:collapse;margin:1rem 0 1.75rem;font-variant-numeric:tabular-nums}}th,td{{border-bottom:1px solid #e2e8f0;padding:.55rem .65rem;text-align:right}}
th:first-child,td:first-child{{text-align:left}}thead{{background:#f8fafc}}.small{{font-size:.9rem;color:#64748b}}
</style>
</head>
<body>
<h1>Wind, solar &amp; nuclear: historical visualisation &amp; gross backtest</h1>
<p class="lede">GB market history through <strong>{end_date:%Y-%m-%d}</strong>. Positions are capped at ±25 MW; P/L follows the challenge formula and is before trading costs.</p>
<div class="callout"><strong>Bottom line:</strong> high wind and wind-plus-solar shares show the clearest association with lower DA-HH prices versus CCGT SRMC. Solar by itself is sparse, and nuclear share is not monotonic with that price gap. The specified threshold rules made {money(full_stats[0]["total_pnl"])} (wind), {money(full_stats[1]["total_pnl"])} (solar), {money(full_stats[2]["total_pnl"])} (nuclear), {money(full_stats[3]["total_pnl"])} (wind + solar), and {money(full_stats[4]["total_pnl"])} (wind + solar + nuclear). Gas-referenced always short made {money(full_stats[6]["total_pnl"])} over the same full sample. These are illustrative gross backtests, not evidence of deployable alpha.</div>

<h2>What was tested</h2>
<ul>
<li><strong>9am wind rule:</strong> short 25 MW for a delivery hour when mean forecast wind generation / demand across that hour is at least 30%; otherwise flat. The hourly position is applied to both half-hours and held through cashout (Y = X).</li>
<li><strong>Solar rule:</strong> short when solar forecast is at least 0.5% of demand; otherwise flat. <strong>Nuclear rule:</strong> short when nuclear forecast is at least 20% of demand. Separate checks use wind + solar ≥30% and wind + solar + nuclear ≥45% of demand.</li>
<li><strong>3pm revision rule:</strong> using the latest Elexon wind forecast published strictly before each UK-local 9am and 3pm cutoff, short 25 MW if the forecast rises, long 25 MW if it falls, and hold the 9am position if unchanged. The hourly signal is applied to both half-hours.</li>
<li><strong>Combined:</strong> apply the Elexon revision rule to both the wind-only and wind-plus-solar 9am positions.</li>
</ul>
<p class="note">Thresholds are transparent illustrations, not optimized parameters. Shares are each forecast generation component divided by forecast demand, averaged over two half-hours to match the hourly 9am position. "Wind + solar + nuclear" is a simple total-share proxy, not a full merit-order model. SRMC evaluates the price relationship, not the position rule. Gas-referenced always-long/short are unconditional ±25 MW power positions benchmarked against the CCGT SRMC context; they are not gas-commodity trades or positions derived from a gas-generation forecast. No action means a zero position and zero P/L. P/L is 0.5 × [X × (DA-HH − DA-HR) + Y × (cashout − DA-HH)] for every half-hour.</p>

<h2>Generation mix, fair-value gap, and auction repricing</h2>
<div class="chart">{generation_gap_chart}</div>
<div class="chart">{wind_spread_chart}</div>
<div class="chart">{solar_gap_chart}</div>
{table(["Forecast feature","Bin","Days","Mean feature / demand","DA-HH − SRMC (£/MWh)","DA-HH below SRMC","DA-HH − DA-HR (£/MWh)"], generation_rows)}
<p>Matched price/forecast/SRMC coverage: {len(daily_market):,} delivery days. Wind and wind-plus-solar are sorted into quintiles; nuclear and total wind + solar + nuclear are shown separately because their shares behave differently. Solar is split at 0.5% of demand because the forecast is often zero overnight. The auction-spread chart is the more direct test of the 9am position’s payoff.</p>

<h2>Gross P/L: full historical sample</h2>
<div class="chart">{full_chart}</div>
{table(["Strategy","Days","Active days","Gross P/L","Profitable days","Daily Sharpe*","Max drawdown"], full_rows)}
<p>Usable observations: {len(valid):,} half-hours over {complete_dates:,} delivery days. The wind-only 30% rule traded in {wind_active_periods:,} half-hours across {full_stats[0]["active_days"]:,} days. Its most profitable day was {money(full_stats[0]["best_day"])} and its worst was {money(full_stats[0]["worst_day"])}. The level-rule P/L is highly dependent on the selected feature and threshold, and comparisons to the constant-short benchmark remain important.</p>
<h2>What if the signal went long instead of short?</h2>
<p>For each feature, the same active condition is used in both directions; long means +25 MW on active intervals and short means −25 MW, with zero position outside the condition. Both gas-referenced unconditional ±25 MW benchmarks and the zero-P/L no-action line are shown.</p>
<div class="chart">{long_chart}</div>
<div class="chart">{short_chart}</div>
{table(["Directional rule","Active days","Active half-hours","Gross P/L","Profitable days","Daily Sharpe*","Max drawdown"], directional_rows)}
<p class="small">*Annualised daily Sharpe-like statistic, calculated from daily gross P/L with no risk-free adjustment. Maximum drawdown is from cumulative daily P/L starting at £0. No fees, bid/offer, market impact, collateral, or transaction limits beyond ±25 MW are modelled.</p>

<h2>Does the 3pm Elexon signal help?</h2>
<div class="chart">{revision_chart}</div>
{table(["Elexon revision quintile","Hourly periods","Mean forecast revision (MW)","DA-HH − DA-HR (£/MWh)","Cashout − DA-HH (£/MWh)"], revision_rows)}
<div class="chart">{matched_chart}</div>
{table(["Strategy on Elexon overlap","Active days","Gross P/L","Profitable days","Daily Sharpe*","Max drawdown"], matched_rows)}
<p>Elexon-matched sample: {len(elexon):,} half-hours across {elexon["date"].nunique():,} days ({elexon["date"].min()} to {elexon["date"].max()}). The 9am and 3pm Elexon updates are wind-only, so the solar-inclusive base position is not revised by a separate solar update. The revision rule is unstable by year, so its full-sample profit should not be read as a repeatable edge.</p>

<h2>Threshold sensitivity and yearly P/L</h2>
{table(["Rule / threshold","Gross P/L","Profitable days","Max drawdown"], sensitivity_rows)}
<p>Changing the 9am wind threshold from 20% to 30% to 40% materially changes gross P/L. Revision magnitude cutoffs likewise change trade frequency and risk; the reported 30% / sign-only result is not a threshold search or selected optimum.</p>
{table(["Year","Sample","Wind","Solar","Nuclear","Wind + solar","Wind + solar + nuclear","Gas always long","Gas always short","No action","Revision only","Combined"], annual_table_rows)}
<p class="small">For Elexon strategies, the 2026 row is partial through 2 October. The gas-referenced always-long/short rows are unconditional power-position benchmarks using the challenge P/L formula; no action remains at zero. Annual P/L is gross.</p>

<h2>Interpretation</h2>
<ul>
<li>High wind is a useful <strong>fair-value/context</strong> feature: more wind tends to coincide with lower prices relative to gas SRMC.</li>
<li>The simple short-on-high-wind rule is profitable in aggregate but trails the strongest constant benchmark over the full sample and has substantial drawdown; its year-to-year results vary.</li>
<li>The Elexon revision direction had positive in-sample P/L over the overlap, but its 2023–2026 results reverse by year. From 2024 onward, revision-only is close to flat and combining it with the wind rule underperformed that rule alone.</li>
<li>These are gross profits over observed historical prices, not a claim of net returns. They do not include execution prices, transaction costs, slippage, or out-of-sample parameter selection.</li>
</ul>
<p class="small">Reproduce from the repository root with <code>python analysis/wind_hypothesis_backtest.py</code>. The script writes this report and <code>analysis/wind_hypothesis_annual_pnl.csv</code>.</p>
</body>
</html>"""
    OUTPUT.write_text(html_report, encoding="utf-8")
    return html_report, annual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--end-date",
        default="2026-10-02",
        help="last local delivery date to include (default: 2026-10-02)",
    )
    args = parser.parse_args()
    end_date = pd.Timestamp(args.end_date).date()
    build_report(end_date)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(f"Wrote {(ROOT / 'analysis' / 'wind_hypothesis_annual_pnl.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
