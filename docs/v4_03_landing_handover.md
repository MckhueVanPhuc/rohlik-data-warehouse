# V4-03 Landing handover

Status: production-quality initial Landing foundation, with production execution still
blocked. This document is the handover boundary for future model-specific adapters.

## Scope decision

The proposed reduced-scope architecture stops the Data Engineering build after V4-03.
Future work may add one adapter per confirmed model, reading verified Landing data and
performing that model's documented cleaning, joins, feature engineering, and time-window
selection. It must not assume Landing is already model-ready.

This is a deliberate deviation from the original V4 pipeline. The original source of
truth, [Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md](../Rohlik_DE_Local_First_V4_HR_Header_Dong_Bo.md),
is retained unchanged for traceability. In particular, this handover does **not** claim
delivery of V4-04, 14 STG tables, six Core tables, five Mart views, model frames/runners,
model outputs, user upload/undo, or business dashboards. Those original V4 features are
intentionally outside the accepted V4-03 scope.

## Sources and immutable dataset identity

The registry is `config/sources.yaml` version 4 and the contract is
`config/contract.yaml` version 4. Every initial load rechecks the registered SHA-256
before and after its projections and checks all seven sources again before commit.

| Source ID | Original CSV | Rows | Type | SHA-256 |
| --- | --- | ---: | --- | --- |
| `orders` | `data/raw/orders/train.csv` | 7,340 | `KAGGLE_ORIGINAL` | `1d0e15de6f8edceb501bfc2c4007cc595781494c8c9c86954584c86e4710be67` |
| `sales` | `data/raw/sales/sales_train.csv` | 4,007,419 | `KAGGLE_ORIGINAL` | `af45f951bd0e9f6132bc64fddca14b00829d260abca0591c9f637437833e0469` |
| `inventory` | `data/raw/sales/inventory.csv` | 5,432 | `KAGGLE_ORIGINAL` | `e1ada9e6d5af544e1ccefd7e8ef2785a78ad7784e783c4b25811a909ca7e966b` |
| `calendar` | `data/raw/sales/calendar.csv` | 23,016 | `KAGGLE_ORIGINAL` | `2633d53eecd494a49080c748b0e335574dc3706342723c85d9ee9636a2e36e84` |
| `weights` | `data/raw/sales/test_weights.csv` | 5,390 | `KAGGLE_ORIGINAL` | `a3b33db34dbe0da26687496b6d98e8ec759a943f776e209a2573937406ccb783` |
| `cost_params` | `data/raw/assumptions/cost_params.csv` | 3 | `ASSUMED` | `22077d43769d06365ba1c39ea55b16ea6151e8d5da0edb019004d87493af8a24` |
| `workforce_params` | `data/raw/assumptions/workforce_params.csv` | 7 | `ASSUMED` | `2af353b29c5b08108b273b5bfed76ada3d2daadc0066523228c9e5e863d8d49b` |

Finance and HR values remain `ASSUMED`; they are planning inputs supplied by the project
team, not observed business actuals.

## Landing contract

Every table also has the non-null provenance columns `_batch_id VARCHAR`,
`_source VARCHAR`, `_loaded_at TIMESTAMP` (UTC wall-clock), and `_entered_by VARCHAR`.
Types below are the canonical business columns in physical order; `?` means nullable.

| Landing table | Source | Business key | Canonical columns and DuckDB types |
| --- | --- | --- | --- |
| `src_sales.orders_daily` | `orders` | `warehouse,date` | `warehouse VARCHAR`, `date DATE`, `orders DOUBLE` |
| `src_sales.sku_sales_daily` | `sales` | `unique_id,date` | `unique_id BIGINT`, `date DATE`, `warehouse VARCHAR`, `sales DOUBLE?`, `total_orders DOUBLE?` |
| `src_marketing.prices` | `sales` | `unique_id,date` | `unique_id BIGINT`, `date DATE`, `sell_price_main DOUBLE` |
| `src_marketing.promotions` | `sales` | `unique_id,date` | `unique_id BIGINT`, `date DATE`, `type_0_discount` through `type_6_discount DOUBLE` |
| `src_marketing.mov_changes` | `orders` | `warehouse,date` | `warehouse VARCHAR`, `date DATE`, `mov_change DOUBLE` |
| `src_ops.availability` | `sales` | `unique_id,date` | `unique_id BIGINT`, `date DATE`, `availability DOUBLE` |
| `src_ops.ops_events` | `orders` | `warehouse,date` | `warehouse VARCHAR`, `date DATE`, `shutdown BIGINT`, `mini_shutdown BIGINT`, `blackout BIGINT`, `frankfurt_shutdown BIGINT` |
| `src_category.product_master` | `inventory` | `unique_id` | `unique_id BIGINT`, `product_unique_id BIGINT`, `name VARCHAR`, `L1_category_name_en` through `L4_category_name_en VARCHAR`, `warehouse VARCHAR` |
| `src_planning.calendar` | `calendar` | `warehouse,date` | `warehouse VARCHAR`, `date DATE`, `holiday_name VARCHAR?`, `holiday BIGINT`, `shops_closed BIGINT`, `winter_school_holidays BIGINT`, `school_holidays BIGINT` |
| `src_digital.user_activity` | `orders` | `warehouse,date` | `warehouse VARCHAR`, `date DATE`, `user_activity_1 DOUBLE`, `user_activity_2 DOUBLE` |
| `src_external.weather` | `orders` | `warehouse,date` | `warehouse VARCHAR`, `date DATE`, `precipitation DOUBLE?`, `snow DOUBLE?` |
| `src_finance.sku_weights` | `weights` | `unique_id` | `unique_id BIGINT`, `weight DOUBLE` |
| `src_finance.cost_params` | `cost_params` | `L1_category_name_en` | `L1_category_name_en VARCHAR`, `cost_ratio DOUBLE`, `shelf_life_days BIGINT`, `waste_handling_cost_ratio DOUBLE` |
| `src_hr.workforce_params` | `workforce_params` | `warehouse` | `warehouse VARCHAR`, `hourly_wage_eur DOUBLE`, `items_per_order DOUBLE`, `picks_per_hour DOUBLE`, `shift_hours DOUBLE`, `morning_shift_ratio DOUBLE`, `overtime_multiplier DOUBLE`, `overtime_cap_ratio DOUBLE`, `shortage_penalty_multiplier DOUBLE`, `legacy_rule_buffer_ratio DOUBLE`, `orders_per_driver_shift DOUBLE` |

The full raw-to-canonical mapping, nullability, checks, and all 14 unchanged
`PENDING_CONFIRMATION` update policies are authoritative in `config/contract.yaml`.

## Batch and provenance semantics

- `meta.source_batches.status` is the canonical current status. V4-03 creates one batch
  per source and commits all seven sources and 14 tables atomically.
- `meta.batch_status_events` and `meta.entry_audit_events` are append-only audit evidence;
  consumers must not infer current state from event timestamp or UUID ordering.
- `COMPLETED` means source fingerprint, contract version, source path, expected row count,
  table-load records, audit evidence, and Landing rows committed together. `RUNNING`,
  `FAILED`, `PARTIAL`, `UNDONE`, unknown, duplicate, or mixed histories fail closed.
- `NO_OP` is returned only after exact bidirectional business-content reconciliation and
  validation of completed-batch provenance against metadata v1. Rows owned by unrelated
  manual or future batches are not updated or deleted.
- A dataset version is the tuple `(registry_version, contract_version,
  source_fingerprint, batch_id)`. Persist all four with any derived model input.

Metadata v1 has no signed or external immutable ledger and no row-level source record ID.
It can detect unilateral Landing or metadata corruption and inconsistent duplicated audit
evidence, but cannot prove authenticity after a coordinated rewrite of every agreeing
Landing and metadata record. No historical values are invented to close that limitation.

## Safe read-only consumption

Use only the shared read-only connection helper. Never call `duckdb.connect` in writable
mode and never keep a reader open while a V4 writer is active.

```python
from src.db.duckdb import connection

with connection("data/acceptance/example.duckdb") as conn:
    rows = conn.execute(
        """SELECT l.*
           FROM src_sales.sku_sales_daily AS l
           JOIN meta.source_batches AS b ON b.batch_id = l._batch_id
           WHERE b.source_id = 'sales' AND b.status = 'COMPLETED'"""
    ).fetch_df()
```

Before an adapter uses a database, run the normal ingestion command against the same
verified source/config set and require `NO_OP`; that path performs the complete
reconciliation. Do not approximate active data with `max(started_at)`, event ordering,
or a row-count-only check. Copy a coherent, closed DuckDB snapshot for long-running
model jobs if concurrent ingestion will later be introduced.

## Known data limitations

- Landing preserves source values. It does not impute, clip, deduplicate, normalize,
  aggregate, or choose cross-source precedence.
- Sales has 52 null `sales` values and 52 null `total_orders` values. The contract keeps
  these fields nullable; adapters must obtain a model-approved policy rather than fill or
  drop silently.
- The source contains 32 known negative discount cells: 27 in `type_0_discount`, one in
  `type_4_discount`, and four in `type_6_discount`. They are preserved and reported as
  warnings, not corrected. This is a cell count, not a claim of 32 distinct rows.
- Orders weather has 270 null values in each of `precipitation` and `snow`; planning
  `holiday_name` is nullable. Zero and null are not interchangeable.
- `orders` and Sales `total_orders` are not equivalent. A direct orders-to-SKU join can
  multiply measures; grain must be made explicit by each adapter.
- Units, currencies, model time cutoffs, future-known fields, calendar precedence,
  effective dating, and update/conflict policy remain unconfirmed.

## Model-adapter boundary

Each future adapter owns only transformations supported by that model's actual handover:
column selection/renaming, joins, grain changes, feature engineering, approved anomaly
and null handling, leakage-safe date filtering, training/inference windows, `as_of`,
dependency inputs, and input validation. It must produce a versioned model-specific
dataset without modifying Landing.

For each of the eight model owners, all of the following are currently
`PENDING_MODEL_HANDOVER`:

- actual notebook and source code, including a reproducible revision;
- input datasets, columns, datatypes, units, business keys, and grain;
- feature engineering, preprocessing, anomaly/null policy, and leakage controls;
- training range, inference range, forecast horizon, timezone, and `as_of` semantics;
- upstream/downstream dependencies between models and required execution order;
- model/preprocessor artifacts, checksums, loading method, runtime/package versions,
  CPU/GPU and operating-system requirements;
- output schema, keys, grain, units, allowed/null values, validation rules, metrics, and
  acceptable reproduction tolerance.

No adapter schema, prediction, or inferred model dependency should be created until that
evidence is supplied and reviewed with the model owner.

## Real-data acceptance evidence

Acceptance ran on 21 October 2026 against byte-identical, fingerprint-verified,
filesystem-read-only copies of all seven approved CSVs. The original `data/raw/**`
files were only read. The final-code database was newly created at
`data/acceptance/v4_03_20261021T2038/warehouse/v4_03_initial_benchmark.duckdb`; neither
production warehouse nor Task08A database was opened for writing.

Precheck observed 295.72 MiB of source CSVs, including the 293.74 MiB / 4,007,419-row
Sales file. The host exposed 15.73 GiB physical memory, only 0.83 GiB immediately
available physical memory, 10.47 GiB available pagefile, and 53.71 GiB free disk. The
expected uncompressed projection size was approximately 2–3 GiB, so the run used the
1 GB DuckDB memory limit and monitored spill files.

| Measurement | Initial load | Exact `NO_OP` reconciliation |
| --- | ---: | ---: |
| Status | `COMPLETED` | `NO_OP` |
| Wall time | 20.03 s | 22.20 s |
| Peak Python working set | 884.70 MiB | 1,205.45 MiB |
| Peak Python private bytes | 1,542.37 MiB | 1,844.38 MiB |
| Peak auxiliary/temp disk | 10.70 MiB | 690.00 MiB |
| Final DuckDB size | 75.26 MiB | unchanged |

A later byte-identity confirmation on the same final-code database also returned
`NO_OP` but took 40.47 s. The observed 22.20–40.47 s range reflects host memory/pagefile
pressure and spill I/O; exact reconciliation of the four 4,007,419-row Sales projections
is the dominant resource bottleneck.

The initial run produced exactly seven `COMPLETED` source batches, 14 table loads,
14 Landing tables, nine `src_*` schemas, seven RUNNING/COMPLETED status-event pairs
(14 events), and 14 entry-audit events. Counts and physical types matched the contract.
The repeat run left the database byte-identical and created no batch or audit record. The
three negative-discount counts were 27/1/4 and the four Finance/HR status events retained
`ASSUMED` lineage.

An uncapped comparison was also measured before the limit was added: 35.95 s and a
2.73 GB peak working set. The 1 GB DuckDB limit preserves bidirectional `EXCEPT ALL`
comparison while reducing peak working set; its tradeoff is up to 690 MiB temporary
spill. The acceptance disk had sufficient headroom. Exact checks were not replaced by
row-count-only or probabilistic hashes.

Synthetic failure acceptance covers missing Landing rows, equal-count business-value
changes, all four provenance fields (directly or through batch ownership), corrupted
metadata/audit evidence, mixed/incomplete histories, in-flight CSV changes, writer
contention, and injected transaction failure. Every unsafe case fails without a partial
Landing or batch-data commit. The full local suite passed 170 tests.
