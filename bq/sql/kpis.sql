-- Alerts per day
SELECT DATE(ts) AS day, COUNTIF(approved) AS approved, COUNT(*) alerts
FROM `pradar.alerts`
GROUP BY day ORDER BY day DESC;

-- Duplicate suppression rate
SELECT SAFE_DIVIDE(SUM(CAST(is_duplicate AS INT64)), COUNT(*)) AS dup_rate
FROM `pradar.events_raw`;

-- Cost per approved alert
WITH c AS (
  SELECT DATE(ts) day, SUM(cost) cost, SUM(tokens) tokens, COUNT(*) calls
  FROM `pradar.events_raw` GROUP BY day
)
SELECT a.day, SAFE_DIVIDE(c.cost, NULLIF(SUM(CAST(a.approved AS INT64)),0)) AS cost_per_alert
FROM `pradar.alerts` a JOIN c USING(day)
GROUP BY a.day, c.cost;

