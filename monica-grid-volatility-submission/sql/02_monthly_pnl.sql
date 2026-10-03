-- Monthly P&L per strategy, from the half-hourly results table `pnl`.
SELECT
    SUBSTR(date_utc, 1, 7)     AS month,
    SUM(pnl_always_long)       AS always_long,
    SUM(pnl_always_short)      AS always_short,
    SUM(pnl_v1)                AS v1,
    SUM(pnl_v2)                AS v2
FROM pnl
GROUP BY SUBSTR(date_utc, 1, 7)
ORDER BY month;
