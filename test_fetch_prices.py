import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_prices


class FetchPricesTests(unittest.TestCase):
    def test_cutoff_requires_timezone(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            fetch_prices.cutoff_timestamp("2024-04-12T23:00:00")

    def test_fetch_selects_point_and_rejects_future(self):
        request = fetch_prices.validate_item({
            "request_id": "pereira",
            "token_id": "123456789",
            "cutoff": "2024-04-12T23:00:00Z",
        }, 0)
        with patch.object(fetch_prices, "get_json", return_value={"data": [{
            "timestamp": request["cutoff"] - 60,
            "price": 0.6,
            "resolution_seconds": 300,
        }]}):
            result = fetch_prices.fetch_one(request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["price"], 0.6)
        self.assertLessEqual(result["observed_at"], result["cutoff"])

    def test_empty_history_is_explicit(self):
        request = fetch_prices.validate_item({"token_id": "123", "cutoff": 1712962800}, 0)
        with patch.object(fetch_prices, "get_json", return_value={"data": []}):
            self.assertEqual(fetch_prices.fetch_one(request)["status"], "not_found")

    def test_future_observation_is_rejected(self):
        request = fetch_prices.validate_item({"token_id": "123", "cutoff": 1712962800}, 0)
        with patch.object(fetch_prices, "get_json", return_value={"data": [{
            "timestamp": request["cutoff"] + 1,
            "price": 0.5,
            "resolution_seconds": 0,
        }]}):
            with self.assertRaisesRegex(RuntimeError, "after the requested cutoff"):
                fetch_prices.fetch_one(request)

    def test_output_contains_json_and_csv(self):
        result = [{"request_id": "x", "token_id": "1", "cutoff": "2024-01-01T00:00:00Z",
                   "status": "ok", "price": 0.5, "observed_at": "2023-12-31T23:00:00Z",
                   "resolution_seconds": 10800}]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            fetch_prices.write_results(result, output)
            self.assertEqual(json.loads((output / "prices.json").read_text()), result)
            self.assertIn("request_id,token_id,cutoff", (output / "prices.csv").read_text())


if __name__ == "__main__":
    unittest.main()
