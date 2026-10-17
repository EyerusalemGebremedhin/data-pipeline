import argparse
import logging
import os
import sys
import time

import requests

import psycopg2

API_URL = "https://api.frankfurter.dev/v1/latest"
BASE_CURRENCY = "USD"
TARGET_CURRENCIES = "EUR,GBP,JPY,KES"
MAX_ATTEMPTS = 3
WAIT_SECONDS = 2

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE", "rates"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("pipeline.log")],
)
log = logging.getLogger("pipeline")


def extract():
    params = {"base": BASE_CURRENCY, "symbols": TARGET_CURRENCIES}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(API_URL, params=params, timeout=10)
            response.raise_for_status()
            log.info("Got data from the API (attempt %d)", attempt)
            return response.json()
        except requests.RequestException as error:
            log.warning("Attempt %d failed: %s", attempt, error)
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(WAIT_SECONDS * attempt)


def transform(data):
    for key in ("date", "base", "rates"):
        if key not in data:
            raise ValueError(f"API response is missing '{key}'")

    rows = []
    for target, rate in data["rates"].items():
        if not isinstance(rate, (int, float)) or rate <= 0:
            log.warning("Skipping bad rate for %s: %r", target, rate)
            continue
        rows.append((data["date"], data["base"], target, float(rate)))

    if not rows:
        raise ValueError("No valid rates found in the response")
    return rows


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def load(rows, db_file=None):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS exchange_rates (
                        rate_date TEXT NOT NULL,
                        base      TEXT NOT NULL,
                        target    TEXT NOT NULL,
                        rate      REAL NOT NULL,
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (rate_date, base, target)
                    )
                    """
                )
                cur.executemany(
                    """
                    INSERT INTO exchange_rates (rate_date, base, target, rate)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (rate_date, base, target)
                    DO UPDATE SET rate = EXCLUDED.rate,
                                  loaded_at = CURRENT_TIMESTAMP
                    """,
                    rows,
                )
        log.info("Saved %d rows to PostgreSQL", len(rows))
        return len(rows)
    finally:
        conn.close()


def run():
    try:
        data = extract()
        rows = transform(data)
        return load(rows)
    except Exception:
        log.exception("Pipeline failed")
        return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="run once every 24 hours")
    args = parser.parse_args()

    if not args.loop:
        saved = run()
        sys.exit(0 if saved else 1)

    while True:
        run()
        log.info("Sleeping for 24 hours")
        time.sleep(24 * 60 * 60)


if __name__ == "__main__":
    main()
