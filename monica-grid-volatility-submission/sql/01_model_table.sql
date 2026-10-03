-- Build the half-hourly model table: one row per settled delivery half-hour.
-- Portable across DuckDB and SQLite: ts_key is UTC epoch seconds, date_utc is 'YYYY-MM-DD'.
--
-- Inputs available at the 09:00 auction (per the challenge brief):
--   hourly auction price (used as a price-contingent order, see README), daily SRMC,
--   third-party wind and demand forecasts.
-- Outcome columns, used only to score P&L: hh_price, cashout_price.
SELECT
    p.ts_key,
    p.date_utc,
    p.hr_price,
    p.hh_price,
    p.cashout_price,
    f.srmc,
    w.wind_fc,
    d.demand_fc,
    100.0 * (p.hr_price - f.srmc) / f.srmc   AS gap_pct,          -- how far above fair value
    d.demand_fc - w.wind_fc                  AS resid_demand_fc   -- forecast load left for gas and other flexible plant
FROM market   AS p
LEFT JOIN fuel     AS f ON f.power_day = p.date_utc
LEFT JOIN wind     AS w ON w.ts_key    = p.ts_key
LEFT JOIN demand   AS d ON d.ts_key    = p.ts_key
WHERE p.hr_price      IS NOT NULL
  AND p.cashout_price IS NOT NULL
  AND f.srmc          IS NOT NULL
ORDER BY p.ts_key;
