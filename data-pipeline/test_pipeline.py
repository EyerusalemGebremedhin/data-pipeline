import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

import pipeline

GOOD_DATA = {"base": "USD", "date": "2026-10-16", "rates": {"EUR": 0.86, "KES": 129.1}}


class TestPipeline(unittest.TestCase):
    def test_transform_makes_rows(self):
        rows = pipeline.transform(GOOD_DATA)
        self.assertEqual(rows[0], ("2026-10-16", "USD", "EUR", 0.86))
        self.assertEqual(len(rows), 2)

    def test_transform_skips_bad_rate(self):
        data = {"base": "USD", "date": "2026-10-16", "rates": {"EUR": 0.86, "GBP": -1}}
        self.assertEqual(len(pipeline.transform(data)), 1)

    def test_transform_rejects_missing_field(self):
        with self.assertRaises(ValueError):
            pipeline.transform({"base": "USD"})

    def test_load_twice_has_no_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            db = os.path.join(folder, "test.db")
            rows = pipeline.transform(GOOD_DATA)
            pipeline.load(rows, db)
            pipeline.load(rows, db)
            count = sqlite3.connect(db).execute(
                "SELECT COUNT(*) FROM exchange_rates"
            ).fetchone()[0]
            self.assertEqual(count, 2)

    @patch("pipeline.time.sleep")
    @patch("pipeline.requests.get")
    def test_extract_retries_then_succeeds(self, mock_get, _sleep):
        good = MagicMock()
        good.json.return_value = GOOD_DATA
        mock_get.side_effect = [requests.ConnectionError("down"), good]
        self.assertEqual(pipeline.extract(), GOOD_DATA)
        self.assertEqual(mock_get.call_count, 2)

    @patch("pipeline.time.sleep")
    @patch("pipeline.requests.get")
    def test_extract_gives_up_after_max_attempts(self, mock_get, _sleep):
        mock_get.side_effect = requests.ConnectionError("down")
        with self.assertRaises(requests.ConnectionError):
            pipeline.extract()
        self.assertEqual(mock_get.call_count, pipeline.MAX_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
