# kfc-api

Small GitHub Actions worker that returns the latest Polymarket observation at or before each requested UTC cutoff. It does not contain or require the FightSystem codebase.

## Request format

Each request needs a public Polymarket outcome token ID and a cutoff with a timezone:

```json
[
  {
    "request_id": "ufc300-pereira-t24h",
    "token_id": "46781513554324371811777291805102302770686983063627910722127672314397656785488",
    "cutoff": "2024-04-12T12:00:00Z"
  }
]
```

`request_id` is optional and is copied into the result. A run accepts at most 500 requests.

## Run on GitHub

1. Open **Actions → Fetch historical prices → Run workflow**.
2. Paste the JSON array into `requests_json`.
3. Run the workflow.
4. Download the `historical-prices-...` artifact from the completed run.

Pushes to `main` also run the included UFC 300 example as a live connectivity check.

The artifact contains `prices.json` and `prices.csv`. A successful row includes the selected price, its observation time, and `resolution_seconds`. `not_found` means Polymarket had no observation at or before that cutoff.

## Run locally

No dependencies are required beyond Python 3.10 or later.

```bash
python fetch_prices.py --input requests.example.json --output-dir output
python -m unittest -v
```

## Data rule

The worker uses Polymarket Data API v2 `/prices-history?token_id=...&as_of=...`. The `as_of` request is inclusive and returns the latest observation at or before the cutoff. The worker rejects a response whose timestamp is later than the requested cutoff.

## SSH-only batch return

If GitHub CLI artifact download is unavailable, put a request array in `requests/pending.json` and push it to `main`. The `Fetch saved price batch` workflow uses the same worker and commits its public result to `results/latest.json`, which can be fetched with ordinary Git over SSH. These files contain only public token IDs and historical prices; do not put secrets in a request.
