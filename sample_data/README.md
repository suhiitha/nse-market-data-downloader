# Sample Market Data

> **Notice**: The files in this folder contain representative synthetic/mock sample data for documentation, offline unit testing, and reference schemas.
>
> They are **NOT** live production files. Live downloaded production data is saved under `data/<YYYY-MM-DD>/` when running the application.

## Sample Files

1. `sample_top_gainers_losers.csv`
   - Demonstrates schema for combined top gainers and losers.
   - Includes columns: `symbol`, `series`, `open_price`, `high_price`, `low_price`, `ltp`, `prev_price`, `net_price`, `trade_quantity`, `turnover`, `perChange`, `category`.

2. `sample_upper_band_hitters.csv`
   - Demonstrates schema for securities touching upper circuit bands.
   - Includes columns: `symbol`, `series`, `ltp`, `change`, `pChange`, `priceBand`, `highPrice`, `lowPrice`, `totalTradedVol`, `turnover`.

3. `sample_volume_gainers_spurts.csv`
   - Demonstrates schema for volume spikes and spurts.
   - Includes columns: `symbol`, `companyName`, `volume`, `week1AvgVolume`, `week1volChange`, `week2AvgVolume`, `week2volChange`, `ltp`, `pChange`, `turnover`.

4. `sample_52_week_high.csv`
   - Demonstrates schema for stocks touching 52-week highs.
   - Includes columns: `symbol`, `comapnyName`, `series`, `ltp`, `new52WHL`, `prev52WHL`, `prevClose`, `change`, `pChange`, `prevHLDate`.
