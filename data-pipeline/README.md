# Data Pipeline

A small Python data pipeline. It gets USD exchange rates from the Frankfurter API (European Central Bank data), checks them, and saves them in a SQLite database.

## Steps

### 1. Extract
Calls the API: `https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,GBP,JPY,KES`

If the call fails, it retries up to 3 times with increasing wait (2s on the first retry, 4s on the second). If all 3 attempts fail, it raises an error. In single-run mode the pipeline stops. In --loop mode it logs the failure and tries again after 24 hours.

### 2. Transform
Checks the response has the fields we need: `date`, `base`, `rates`.

Turns the data into rows: `(date, base, target, rate)`.

Skips bad rates (negative numbers, zero, non-numbers). If no valid rates are found, it raises an error.

### 3. Load
Saves the rows in the `exchange_rates` table.

Uses `INSERT OR REPLACE` so running it twice does not create duplicates. The primary key is `(rate_date, base, target)` - this makes each row unique.

## Why retry?

APIs can fail for many reasons: slow connection, server down, timeout. Retrying gives it a second (and third) chance instead of failing immediately. This is important for a data pipeline - if it fails, you get no data that day.

## Why the primary key?

If you run the pipeline twice on the same day, you do not want duplicate rows. The primary key `(date, base, target)` means each combination is unique. `INSERT OR REPLACE` says: if this row already exists, replace it. If not, insert it. This is called idempotency - running it any number of times gives the same result.

## Logging

Writes to the screen (so you can see what happened) AND to `pipeline.log` (a file). Uses Python's logging module with INFO level for normal messages and WARNING for problems.

## Scheduling

- Run once: `python pipeline.py`
- Run every 24 hours: `python pipeline.py --loop`

The `--loop` flag runs the pipeline in a loop with a 24-hour sleep between runs. For production, you would use cron (Linux) or Task Scheduler (Windows) instead.

## Tests

6 unit tests in `test_pipeline.py`. They use a fake API response, no real network needed.

- `test_transform_makes_rows` - transform() turns good data into rows
- `test_transform_skips_bad_rate` - negative rates are skipped
- `test_transform_rejects_missing_field` - missing fields raise an error
- `test_load_twice_has_no_duplicates` - running load() twice gives same row count
- `test_extract_retries_then_succeeds` - retries on failure, succeeds on second try
- `test_extract_gives_up_after_max_attempts` - gives up after 3 attempts

Run them with:
```bash
python3 -m unittest -v
```

## Run it

```bash
pip install requests
python3 pipeline.py            # run once
python3 pipeline.py --loop     # run every 24 hours
```

## Check the data

```bash
sqlite3 rates.db "SELECT * FROM exchange_rates;"
```

## Possible next steps

- Use PostgreSQL instead of SQLite
- Add more currencies in `TARGET_CURRENCIES`
- Load the history with the API's date range endpoint
- Add an alert if the API fails (email, Slack, etc.)
- Add data quality checks (is the rate realistic? is it fresh?)