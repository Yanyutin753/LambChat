-- LambChat PG 巡检 SQL（patrol.sh 调用）
-- 慢 SQL Top8：平均执行 >20ms（排除 pg_stat_statements 自身与巡检语句）
SELECT round(total_exec_time::numeric, 0) AS total_ms,
       round(mean_exec_time::numeric, 1) AS mean_ms,
       round((mean_blk_read_time + mean_blk_write_time)::numeric, 1) AS io_ms,
       calls,
       left(regexp_replace(query, '[\s\n\r]+', ' ', 'g'), 90) AS query
FROM pg_stat_statements
WHERE mean_exec_time > 20
  AND dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND query NOT LIKE '%pg_stat_%'
ORDER BY mean_exec_time DESC
LIMIT 8;

-- 库体积概览
SELECT 'db_size=' || pg_size_pretty(pg_database_size(current_database()))
    || '  checkpoint_blobs=' || (SELECT pg_size_pretty(pg_total_relation_size('checkpoint_blobs')))
    || '  dead_tup=' || (SELECT sum(n_dead_tup) FROM pg_stat_user_tables);
