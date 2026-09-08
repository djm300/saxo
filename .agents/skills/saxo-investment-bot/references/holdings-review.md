# Holdings review schema

Every run writes `holdings-review.json` before plan validation. The artifact proves that every current Saxo position was considered for adding, holding, trimming, or exiting.

```json
{
  "run_id": "20260820T140000Z-review",
  "snapshot_timestamp": "2026-08-20T14:00:00+00:00",
  "portfolio_conclusion": "Why the combined set of dispositions is preferable to cash and researched alternatives.",
  "positions": [
    {
      "symbol": "EXACT.SAXO",
      "uic": 123456,
      "asset_type": "Stock",
      "quantity": 10,
      "decision": "hold",
      "thesis_status": "intact",
      "rationale": "Position-specific reason for add, hold, trim, or exit.",
      "supporting_evidence": ["Dated evidence or current portfolio/price fact, with a link when external"],
      "contrary_evidence": ["Dated risk, disconfirming fact, or explicit evidence gap"],
      "review_trigger": "Observable event or date requiring reassessment"
    }
  ]
}
```

Allowed decisions are `add`, `hold`, `trim`, and `exit`. Allowed thesis states are `strengthened`, `intact`, `weakened`, `broken`, and `uncovered`. `uncovered` means the position was found without a prior ledger thesis; it still requires a real current assessment and must be added to the thesis ledger during the run.

Identity and quantity must match the sanitized snapshot exactly. There must be exactly one record per snapshot position and no extra records. Evidence arrays must each contain at least one meaningful string; an explicit, position-specific evidence gap belongs in contrary evidence.

The reconciliation helper also checks the plan: a buy order for an already-held identity requires an `add` decision, while a sell requires `trim` or `exit`. An `exit` sell should liquidate the snapshot quantity; deterministic execution remains authoritative for quantities and risk controls. A non-hold decision may be deferred when market, identity, evidence, or risk gates prevent an order, but the rationale must say so.
