# Data Dictionary

GB power market data: settlement prices, demand/generation outturns, and third-party forecasts. All timestamps are UTC.

## Folder structure

```
├── market_prices.parquet
├── fuel_prices.xlsx
└── 3rd Party Forecasts/
    ├── demand_forecasts.parquet
    ├── generation_forecasts.parquet
    ├── gfs_renewables_forecast.parquet
    ├── interconnector_forecasts.parquet
    └── Elexon Forecasts/
        ├── elexon_da_gen_fc.parquet
        ├── elexon_da_gen_fc_wind_solar.parquet
        └── elexon_wind_fc.parquet
```

## Root

| File | Description | Valid from | Valid to |
|---|---|---|---|
| `market_prices.parquet` | Day-ahead EPEX prices/volumes (hourly + half-hourly) and imbalance price | 2016-01-01 00:00 | 2026-10-08 23:00 |
| `fuel_prices.xlsx` | Fuel prices + Short Run Marginal Costs for Various Efficiencies | 2016-01-01 00:00 | 2026-10-08 23:00 |

## 3rd Party Forecasts

| File | Description | Valid from | Valid to |
|---|---|---|---|
| `demand_forecasts.parquet` | GB demand outturn and forecasts (INDO, ITSDO, National Grid, ENTSOE, NDF, TSDF) | 2016-01-01 00:00 | 2026-10-08 23:30 |
| `generation_forecasts.parquet` | Generation outturn and forecasts by fuel type (CCGT, nuclear, wind, solar, etc.) | 2016-01-01 00:00 | 2026-10-08 23:30 |
| `gfs_renewables_forecast.parquet` | GFS weather-model solar/wind outturn and forecast | 2016-01-01 00:00 | 2026-10-08 23:30 |
| `interconnector_forecasts.parquet` | Interconnector flow forecasts (BE, DE, IE, NL, FR) | 2016-01-01 00:00 | 2026-10-08 23:00 |

### Elexon Forecasts

Raw feeds pulled from the Elexon BMRS API (`startTime` is the settlement period start).

| File | Description | Valid from | Valid to |
|---|---|---|---|
| `elexon_da_gen_fc.parquet` | Day-ahead generation forecast (DAG) | 2023-07-05 00:00 | 2026-09-29 23:30 |
| `elexon_da_gen_fc_wind_solar.parquet` | Day-ahead generation forecast, wind & solar (DGWS) | 2023-01-02 00:00 | 2026-10-02 23:30 |
| `elexon_wind_fc.parquet` | Wind generation forecast (WINDFOR) | 2023-01-01 21:00 | 2026-10-04 20:00 |
