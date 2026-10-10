-- FactBlock for DuckDB: as-of reads over a Parquet bundle in SQL alone (SPEC 4, 5.3).
--
--   duckdb -init duckdb/factblock.sql
--   SELECT id, statement, superseded_by FROM factblock_nodes('path/to/bundle', TIMESTAMPTZ '2024-08-01');
--   SELECT * FROM factblock_certificate('path/to/bundle', TIMESTAMPTZ '2024-08-01');
--   SELECT target_id, outcome, decided_at FROM factblock_verdicts('path/to/bundle', TIMESTAMPTZ '2024-08-01');
--
-- Same rules as factblock.scan(): known_at <= as_of masks, valid_at (default as_of)
-- selects, SUPERSEDES edges visible as of as_of (known, and in force at valid_at) flag the row they replace. The bundle
-- must be the Parquet profile (factblock to-parquet). A date-only as_of means the
-- end of that day: pass factblock_day(DATE '2024-08-01').
-- Table macros, so this is one file to load, no build, no extension install.

CREATE OR REPLACE MACRO factblock_day(d) AS CAST(d AS DATE) + INTERVAL 1 DAY - INTERVAL 1 MICROSECOND;

CREATE OR REPLACE MACRO factblock_nodes(bundle, as_of, valid_at := NULL) AS TABLE
  WITH t AS (SELECT CAST(as_of AS TIMESTAMPTZ) AS a, CAST(COALESCE(valid_at, as_of) AS TIMESTAMPTZ) AS v)
  SELECT n.*,
         (SELECT e.source_id
            FROM read_parquet(bundle || '/edges.parquet') e, t
           WHERE e.target_id = n.id AND e.edge_type = 'SUPERSEDES' AND e.known_at <= t.a
             AND e.asserted_at <= t.v AND e.valid_from <= t.v AND (e.valid_to IS NULL OR t.v < e.valid_to)
           ORDER BY e.asserted_at DESC, e.source_id DESC LIMIT 1) AS superseded_by
    FROM read_parquet(bundle || '/nodes.parquet') n, t
   WHERE n.known_at <= t.a
     AND n.asserted_at <= t.v
     AND n.valid_from <= t.v
     AND (n.valid_to IS NULL OR t.v < n.valid_to);

CREATE OR REPLACE MACRO factblock_edges(bundle, as_of, valid_at := NULL) AS TABLE
  WITH t AS (SELECT CAST(as_of AS TIMESTAMPTZ) AS a, CAST(COALESCE(valid_at, as_of) AS TIMESTAMPTZ) AS v)
  SELECT e.*
    FROM read_parquet(bundle || '/edges.parquet') e, t
   WHERE e.known_at <= t.a
     AND e.asserted_at <= t.v
     AND e.valid_from <= t.v
     AND (e.valid_to IS NULL OR t.v < e.valid_to);

-- The latest verdict on each block, among those known by as_of (SPEC 3.6: a re-resolution is a later row,
-- and a reader that needs one verdict takes the latest visible one). One row per target_id.
CREATE OR REPLACE MACRO factblock_verdicts(bundle, as_of) AS TABLE
  SELECT r.*
    FROM read_parquet(bundle || '/resolutions.parquet') r
   WHERE r.known_at <= CAST(as_of AS TIMESTAMPTZ)
 QUALIFY row_number() OVER (PARTITION BY r.target_id ORDER BY r.decided_at DESC, r.known_at DESC) = 1;

-- What the read hid and what it rests on (SPEC 4.2). One row.
CREATE OR REPLACE MACRO factblock_certificate(bundle, as_of, valid_at := NULL) AS TABLE
  WITH t AS (SELECT CAST(as_of AS TIMESTAMPTZ) AS a, CAST(COALESCE(valid_at, as_of) AS TIMESTAMPTZ) AS v),
  vis_n AS (SELECT * FROM factblock_nodes(bundle, as_of, valid_at := valid_at)),
  vis_e AS (SELECT * FROM factblock_edges(bundle, as_of, valid_at := valid_at)),
  all_n AS (SELECT count(*) AS c FROM read_parquet(bundle || '/nodes.parquet') n, t WHERE n.known_at > t.a),
  all_e AS (SELECT count(*) AS c FROM read_parquet(bundle || '/edges.parquet') e, t WHERE e.known_at > t.a),
  known_n AS (SELECT count(*) AS c FROM read_parquet(bundle || '/nodes.parquet') n, t WHERE n.known_at <= t.a),
  known_e AS (SELECT count(*) AS c FROM read_parquet(bundle || '/edges.parquet') e, t WHERE e.known_at <= t.a),
  bf AS (SELECT count(DISTINCT batch) AS batches, count(*) AS rows_
           FROM (SELECT attestation.batch AS batch FROM vis_n WHERE attestation.batch IS NOT NULL
                 UNION ALL SELECT attestation.batch FROM vis_e WHERE attestation.batch IS NOT NULL))
  SELECT t.a AS as_of, t.v AS valid_at, now() AS read_at,
         (SELECT c FROM all_n) AS masked_nodes, (SELECT c FROM all_e) AS masked_edges,
         (SELECT c FROM known_n) - (SELECT count(*) FROM vis_n) AS not_in_force_nodes,
         (SELECT c FROM known_e) - (SELECT count(*) FROM vis_e) AS not_in_force_edges,
         bf.batches AS backfill_batches, bf.rows_ AS backfill_rows
    FROM t, bf;
