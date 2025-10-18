CREATE OR REPLACE VIEW `pradar.alerts_per_day` AS
SELECT DATE(ts) AS day, COUNTIF(approved) AS approved, COUNT(*) AS total
FROM `pradar.alerts`
GROUP BY day
ORDER BY day DESC;

