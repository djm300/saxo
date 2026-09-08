# Plan schema

The plan is a JSON object:

```json
{
  "run_id": "20260820T140000Z-review",
  "environment": "sim",
  "created_at": "2026-08-20T14:00:00Z",
  "orders": [
    {
      "symbol": "EXACT.SAXO",
      "uic": 123456,
      "asset_type": "Stock",
      "side": "buy",
      "quantity": 1,
      "thesis": {
        "summary": "Falsifiable thesis",
        "supporting_evidence": ["Evidence with source"],
        "contrary_evidence": ["Contrary evidence with source"],
        "bull_case": "Upside scenario",
        "base_case": "Expected scenario",
        "bear_case": "Downside scenario",
        "catalysts": ["Dated or observable catalyst"],
        "invalidation_conditions": ["Observable failure condition"],
        "review_trigger": "Event or date that forces review"
      }
    }
  ]
}
```

Sell orders omit `thesis`. The deterministic validator permits only exact Saxo-validated, long-only `Stock` and `Etf` instruments and rejects leveraged/inverse ETFs. The mandate enforces concentration, cash, order-count, spread, turnover, quote, pre-check, and SIM-only rules.
