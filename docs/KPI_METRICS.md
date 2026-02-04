# Dashboard KPIs (17) — Formulas & WebSocket Fields

The WebSocket payload (`/data/dashboard`) includes a **`kpis`** object. Pipeline/pods can publish metrics via the queue (`increment_metric`, `get_metrics`) to drive real values; until then the collector uses telemetry and placeholders.

| # | KPI | Formula | Fields in payload |
|---|-----|---------|-------------------|
| 1 | Fraud Exposure Identified | SUM(amt) WHERE risk_score ≥ 75 | `kpis.1_fraud_exposure_identified_usd` |
| 2 | Transactions Analyzed | COUNT(*) | `kpis.2_transactions_analyzed` |
| 3 | High-Risk Flagged | COUNT(*) WHERE risk_score ≥ 75 | `kpis.3_high_risk_flagged` |
| 4 | Decision Latency | AVG(t_output − t_input) | `kpis.4_decision_latency_ms` (placeholder until timestamps) |
| 5 | Precision @ Threshold | TP / (TP + FP) | `kpis.5_precision_at_threshold` |
| 6 | Fraud Rate | SUM(amt flagged) / SUM(amt total) | `kpis.6_fraud_rate_pct` |
| 7 | Alerts per 1M | (flagged / total) × 1,000,000 | `kpis.7_alerts_per_1m` |
| 8 | High-Risk Txn Rate | COUNT(flagged) / COUNT(total) | `kpis.8_high_risk_txn_rate` |
| 9 | Annual Savings | (fraud_exposure / hours_elapsed) × 8,760 | `kpis.9_annual_savings_usd` |
| 10 | Risk Distribution | GROUP BY risk_score bins | `kpis.10_risk_distribution` (low_0_60, medium_60_90, high_90_100) |
| 11 | Fraud Velocity | COUNT(flagged) GROUP BY minute | `kpis.11_fraud_velocity_per_min` |
| 12 | Category Risk | SUM(amt flagged) GROUP BY category | `kpis.12_category_risk` (object; fill from pipeline) |
| 13 | Risk Concentration | SUM(amt top 1%) / SUM(amt flagged) | `kpis.13_risk_concentration_pct` |
| 14 | State Risk | SUM(amt flagged) GROUP BY state | `kpis.14_state_risk` (object; fill from pipeline) |
| 15 | Recall | TP / (TP + FN) | `kpis.15_recall` |
| 16 | False Positive Rate | FP / (FP + TN) | `kpis.16_false_positive_rate` |
| 17 | FlashBlade Util | current_bw / max_bw (Pure1 API) | `kpis.17_flashblade_util_pct` |

**Data sources (current):**

- **Telemetry:** `generated`, `data_prep_cpu`, `data_prep_gpu`, `txns_scored`, `fraud_blocked`, `throughput`, `total_elapsed`.
- **Queue metrics:** `fraud_dist_low`, `fraud_dist_medium`, `fraud_dist_high` (when inference publishes them).
- **Placeholders:** Decision latency, precision/recall/FP rate (until TP/FP/TN/FN published), category_risk, state_risk, FlashBlade util (Pure1 API).
