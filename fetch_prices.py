#!/usr/bin/env python3
"""Fetch one historical Polymarket price at or before each requested cutoff."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://data-api.polymarket.com/v2/prices-history"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def cutoff_timestamp(value: object) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("cutoff must be a positive epoch integer or an ISO-8601 string")
    text = value.strip()
    if text.isdigit():
        timestamp = int(text)
        if timestamp > 0:
            return timestamp
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("cutoff must include a timezone, preferably Z")
    return int(parsed.timestamp())


def validate_item(item: object, index: int) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"request {index} must be an object")
    token_id = str(item.get("token_id", "")).strip()
    if not token_id.isdigit():
        raise ValueError(f"request {index} has an invalid token_id")
    cutoff = cutoff_timestamp(item.get("cutoff"))
    return {
        "request_id": str(item.get("request_id", index)),
        "token_id": token_id,
        "cutoff": cutoff,
    }


def load_requests(raw: str) -> list[dict]:
    value = json.loads(raw)
    if not isinstance(value, list) or not value:
        raise ValueError("input must be a non-empty JSON array")
    if len(value) > 500:
        raise ValueError("one run accepts at most 500 requests")
    return [validate_item(item, index) for index, item in enumerate(value)]


def get_json(url: str, attempts: int = 4) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "kfc-api/1.0"})
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS or attempt == attempts - 1:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"Polymarket returned HTTP {exc.code}: {detail}") from exc
            delay = min(float(exc.headers.get("Retry-After", 2 ** attempt)), 30)
        except (URLError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise RuntimeError(f"Polymarket request failed: {exc}") from exc
            delay = 2 ** attempt
        time.sleep(delay)
    raise AssertionError("unreachable")


def fetch_one(item: dict) -> dict:
    query = urlencode({"token_id": item["token_id"], "as_of": item["cutoff"], "limit": 1})
    payload = get_json(f"{ENDPOINT}?{query}")
    points = payload.get("data")
    if not isinstance(points, list):
        raise RuntimeError("Polymarket response is missing the data array")
    base = {
        "request_id": item["request_id"],
        "token_id": item["token_id"],
        "cutoff": datetime.fromtimestamp(item["cutoff"], timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if not points:
        return {**base, "status": "not_found", "price": None,
                "observed_at": None, "resolution_seconds": None}
    point = points[-1]
    observed = int(point["timestamp"])
    if observed > item["cutoff"]:
        raise RuntimeError("Polymarket returned an observation after the requested cutoff")
    price = float(point["price"])
    if not 0 <= price <= 1:
        raise RuntimeError("Polymarket returned a price outside 0..1")
    return {
        **base,
        "status": "ok",
        "price": price,
        "observed_at": datetime.fromtimestamp(observed, timezone.utc).isoformat().replace("+00:00", "Z"),
        "resolution_seconds": int(point["resolution_seconds"]),
    }


def write_results(results: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "prices.json").write_text(json.dumps(results, indent=2) + "\n")
    fields = ["request_id", "token_id", "cutoff", "status", "price",
              "observed_at", "resolution_seconds"]
    with (output_dir / "prices.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--input", type=Path, help="JSON request file")
    source.add_argument("--requests-json", help="JSON request array")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--require-all", action="store_true",
                        help="exit unsuccessfully if any requested price is unavailable")
    args = parser.parse_args()
    raw = args.input.read_text() if args.input else (args.requests_json or os.environ.get("REQUEST_JSON", ""))
    requests = load_requests(raw)
    results = [fetch_one(item) for item in requests]
    write_results(results, args.output_dir)
    found = sum(item["status"] == "ok" for item in results)
    print(f"Fetched {found}/{len(results)} point-in-time prices into {args.output_dir}")
    return 1 if args.require_all and found != len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
