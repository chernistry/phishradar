-- BigQuery DDL placeholders (see dev/prep/project.md for full spec)
CREATE SCHEMA IF NOT EXISTS `pradar`;

CREATE TABLE IF NOT EXISTS `pradar.events_raw` (
  url STRING, title STRING, ts TIMESTAMP, model STRING,
  tokens INT64, ms INT64, cost NUMERIC, is_duplicate BOOL, similarity FLOAT64
);

CREATE TABLE IF NOT EXISTS `pradar.alerts` (
  url STRING, ts TIMESTAMP, domain STRING, similarity FLOAT64,
  approved BOOL, reviewer STRING
);

CREATE TABLE IF NOT EXISTS `pradar.costs` (
  day DATE, total_cost NUMERIC, total_tokens INT64, calls INT64
);

