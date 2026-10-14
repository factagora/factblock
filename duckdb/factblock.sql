-- FactBlock for DuckDB: as-of reads over a Parquet bundle in SQL alone (SPEC 4, 5.3).
--
--   duckdb -init duckdb/factblock.sql
--   SELECT id, statement, superseded_by FROM factblock_nodes('path/to/bundle', TIMESTAMPTZ '2024-08-01');
--   SELECT * FROM factblock_certificate('path/to/bundle', TIMESTAMPTZ '2024-08-01');
--   SELECT target_id, outcome, decided_at FROM factblock_verdicts('path/to/bundle', TIMESTAMPTZ '2024-08-01');
--
-- Same rules as factblock.scan(): known_at <= as_of masks, valid_at (default as_of)
-- selects, SUPERSEDES edges visible as of as_of (known, and in force at valid_at) flag the row they replace, as
-- superseded_by or, when the successor applies to fewer cases, superseded_for (SPEC 4.3). The bundle
-- must be the Parquet profile (factblock to-parquet). A date-only as_of means the
-- end of that day: pass factblock_day(DATE '2024-08-01').
-- Table macros, so this is one file to load, no build, no extension install. factblock_nodes and factblock_edges always
-- have a `namespace` column, and factblock_nodes an `applies_if` column (SPEC 3.1), null for files written before they existed.

CREATE OR REPLACE MACRO factblock_day(d) AS CAST(d AS DATE) + INTERVAL 1 DAY - INTERVAL 1 MICROSECOND;

-- A node's applies_if (a JSON string) as comparable conditions, key/op/values with an eq list as a set (SPEC 3.1, 4.3).
CREATE OR REPLACE MACRO factblock_conds(j) AS
  list_transform(COALESCE(from_json(j, '[{"key":"VARCHAR","op":"VARCHAR","value":"JSON"}]'), []),
    c -> c.key || chr(31) || c.op || chr(31) || array_to_string(list_sort(list_distinct(
           CASE WHEN json_type(c.value) = 'ARRAY' THEN from_json(c.value, '["VARCHAR"]') ELSE [c.value ->> '$'] END)), chr(31)));

-- superseded_by: the latest visible SUPERSEDES whose successor's applies_if is among the row's own (a total replacement).
-- superseded_for: the others, [{by, applies_if}] in asserted order, null when none (a replacement for some cases only).
CREATE OR REPLACE MACRO factblock_nodes(bundle, as_of, valid_at := NULL) AS TABLE
  WITH t AS (SELECT CAST(as_of AS TIMESTAMPTZ) AS a, CAST(COALESCE(valid_at, as_of) AS TIMESTAMPTZ) AS v),
  n_all AS (FROM read_parquet(bundle || '/nodes.parquet') UNION ALL BY NAME SELECT NULL::VARCHAR AS namespace, NULL::VARCHAR AS applies_if WHERE false),
  sup AS (SELECT e.target_id, e.source_id, e.asserted_at,
                 (SELECT s.applies_if FROM n_all s WHERE s.id = e.source_id AND s.known_at <= t.a
                   ORDER BY s.known_at DESC, s.valid_from DESC LIMIT 1) AS src_if
            FROM read_parquet(bundle || '/edges.parquet') e, t
           WHERE e.edge_type = 'SUPERSEDES' AND e.known_at <= t.a
             AND e.valid_from <= t.v AND (e.valid_to IS NULL OR t.v < e.valid_to))
  SELECT n.*,
         (SELECT s.source_id FROM sup s
           WHERE s.target_id = n.id AND list_has_all(factblock_conds(n.applies_if), factblock_conds(s.src_if))
           ORDER BY s.asserted_at DESC, s.source_id DESC LIMIT 1) AS superseded_by,
         (SELECT list({'by': s.source_id, 'applies_if': s.src_if} ORDER BY s.asserted_at, s.source_id) FROM sup s
           WHERE s.target_id = n.id AND NOT list_has_all(factblock_conds(n.applies_if), factblock_conds(s.src_if))) AS superseded_for
    FROM n_all n, t
   WHERE n.known_at <= t.a
     AND n.valid_from <= t.v
     AND (n.valid_to IS NULL OR t.v < n.valid_to);

CREATE OR REPLACE MACRO factblock_edges(bundle, as_of, valid_at := NULL) AS TABLE
  WITH t AS (SELECT CAST(as_of AS TIMESTAMPTZ) AS a, CAST(COALESCE(valid_at, as_of) AS TIMESTAMPTZ) AS v)
  SELECT e.*
    FROM (FROM read_parquet(bundle || '/edges.parquet') UNION ALL BY NAME SELECT NULL::VARCHAR AS namespace WHERE false) e, t
   WHERE e.known_at <= t.a
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
