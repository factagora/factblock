# FactBlock Table Format, version 1.0-draft.1

Status: draft. Nothing here is stable until 1.0.0.
License: Apache-2.0. Format, not platform: no account, SDK, or service is required to read, write, or validate a FactBlock bundle.

FactBlock is an open table format for knowledge that changes over time. It stores statements and the edges between them with **three clocks** (when it was said, when it holds, when it became known), typed causal edges, and attested knowledge time, so that a reader can answer "what did we know at instant T, and why did we change our mind" without trusting the writer's word for it.

It sits above Parquet and JSONL (how bytes are stored) and beside OKF (how people and agents read descriptions of assets). See section 9 for the OKF projection.

## 1. Terms

| Term | Meaning |
|---|---|
| **block** | One row of the ledger: a node or an edge. Immutable once written |
| **bundle** | A directory holding one ledger: a manifest, node and edge tables, resolutions, declarations |
| **node** | A statement or thing. `kind` says which: `claim`, `prediction`, `entity`, `factor`, `timeseries`, `episode`, or a producer-defined kind |
| **edge** | A typed relation between two nodes. An edge is itself a block with its own clocks |
| **asserted_at** | When the statement was made (content time) |
| **valid** | The interval `[valid_from, valid_to)` during which the content holds. `valid_to` null means open |
| **known_at** | When the ledger learned the block (knowledge time). Never set by the author of the statement |
| **attestation** | Who vouches for `known_at`: the ledger that stamped it, or a declared backfill |
| **as-of read** | A read that shows only blocks with `known_at <= as_of`, and reports what it hid |
| **supersession** | A later block replacing an earlier one through a `SUPERSEDES` edge. The earlier block stays |
| **fact** | A declared identity: which nodes are values of the same thing, and how one value is chosen |
| **certificate** | The record attached to an as-of read: what was masked, what was backfilled, which rules applied |

## 2. Invariants

A bundle is a FactBlock bundle only if all five hold. The validator (section 8) checks each.

| # | Invariant | Validator check |
|---|---|---|
| **I1** | **Three clocks on every block.** `asserted_at`, `valid_from`, and `known_at` are present and are instants. `valid_to` is an instant or null, and `valid_from < valid_to` when both exist | `I1.present`, `I1.ordered` |
| **I2** | **Knowledge time is attested.** Every `known_at` is accounted for by exactly one attestation: a ledger stamp (`attestation.ledger`) or a declared backfill batch (`attestation.batch` referencing `declarations`). A block cannot attest its own `known_at` | `I2.attested`, `I2.batch_exists`, `I2.no_self` |
| **I3** | **Append only.** Within a bundle no two nodes share `(id, overlapping valid)` and no two edges share `(source_id, target_id, edge_type, overlapping valid)`. There is no update or delete; a correction is a new block plus a `SUPERSEDES` edge | `I3.node_unique`, `I3.edge_unique` |
| **I4** | **Edges are typed, and the type decides the family.** `edge_type` is one of the core types or a producer type declared with a family. Family is derived, never stored. `CONCURRENT_SIGNAL` is temporal, not causal | `I4.known_type`, `I4.family_declared` |
| **I5** | **Facts and policies travel with the data.** Every `fact_key` used on a node appears in `declarations.facts` with a policy. A reader can compute `resolve` from the bundle alone | `I5.declared`, `I5.policy_known` |

## 3. Logical model

### 3.1 Node

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Stable within the bundle's namespace. Reused only with a non-overlapping `valid` |
| `kind` | string | yes | Core: `claim` `prediction` `entity` `factor` `timeseries` `episode`. Others preserved (section 7) |
| `statement` | string | no | The text. Required for `claim` and `prediction` |
| `category` | string | no | |
| `payload` | object | no | Free form. Conventions: `about` (the period the content refers to), `speaker` (who said it, as written), `quote` (the words), `source` (`{url, title, published_at}`, where it appeared), `factblock_id` |
| `asserted_at` | instant | yes | I1 |
| `valid_from` | instant | yes | I1 |
| `valid_to` | instant or null | no | I1 |
| `known_at` | instant | yes | I1, I2 |
| `attestation` | Attestation | yes | I2 |
| `fact_key` | string | no | I5 |
| `fact_value` | any | no | The value `resolve` returns for this candidate |
| `embedding` | float[] | no | Producer's vector. `declarations.embedding` names the model |
| `author` | actor | no | Who said it. Actor syntax in 3.5 |
| `space` | string | no | Whose memory this is: a user, an agent, a worldview. A filter axis, distinct from `author` |

### 3.2 Edge

| Field | Type | Required | Notes |
|---|---|---|---|
| `source_id`, `target_id` | string | yes | Node ids in the same bundle |
| `edge_type` | string | yes | I4 |
| `confidence` | float 0..1 | no | |
| `lag` | ISO 8601 duration | no | Causal types only |
| `mechanism` | string | no | One sentence on why |
| `properties` | object | no | Free form |
| `asserted_at`, `valid_from`, `valid_to`, `known_at`, `attestation` | | as for nodes | I1, I2 |
| `author` | actor | no | |

### 3.3 Edge types and families

| family | core types | meaning in a read |
|---|---|---|
| `causal` | `CAUSES` `CONTRIBUTING_FACTOR` `TRIGGERS` `PREVENTS` | Expanded and scored as causation |
| `temporal` | `SUPERSEDES` `CONCURRENT_SIGNAL` `RESTATES` | `SUPERSEDES` drives supersession; `CONCURRENT_SIGNAL` is co-occurrence and is never scored as a cause; `RESTATES` is the same statement said again |
| `argumentative` | `SUPPORTS` `CONTRADICTS` `QUALIFIES` | Evidence for and against |
| `general` | `DEPENDS_ON` `DERIVED_FROM` `MENTIONS` | Structure. `MENTIONS` targets an entity |

A producer may add types by listing them in `declarations.edge_types` with a family. Consumers MUST preserve unknown types and MAY treat them as `general`.

### 3.4 Attestation

```
Attestation = { ledger: actor, batch: string | null }
```

`ledger` is the actor that stamped `known_at` (a service, a process, a person). When `batch` is set it names an entry in `declarations.backfills`, and `known_at` is that batch's `declared_known_at`; the ledger's own stamp for the row is kept as `captured_at` in the batch record. A reader that shows a backfilled block MUST report it in the certificate.

### 3.5 Actors

Actor strings follow one of four shapes. Three are taken from OKF v0.2 so the two formats agree on who did what:
`<producer>/<version>` for software (`tckg/0.2.0`), `human:<id>` for a person, `process:<id>` for an automated job. The fourth,
`org:<id>` (`org:factchecks.example`), names an organisation that speaks as one, such as a publisher or a central bank, where
neither a person nor a process is the right answer.

### 3.6 Resolution

Resolutions are append-only records about a node, never fields on it.

| Field | Type | Required |
|---|---|---|
| `target_id` | string | yes |
| `value` | any | yes |
| `decided_at` | instant | yes (when the verdict holds as content) |
| `known_at`, `attestation` | | yes (I1, I2) |
| `resolver` | actor | no |
| `method`, `criteria` | string | no | How the verdict was reached, and against what |
| `outcome` | string | no | Recommended vocabulary below; other values preserved (section 7) |
| `evidence` | array | no | Elements `{type, url, title, publisher, published_at}`; `type` free (`OFFICIAL_DOCUMENT`, `STATISTICS`, `NEWS_ARTICLE`, ...) |

Recommended `outcome` vocabulary, so that verdicts from different resolvers compare and project (section 9): for a `prediction`, `came_true`, `did_not`, `partial`, `undecidable`; for a `claim`, `true`, `mostly_true`, `mostly_false`, `false`, `misleading`, `unverifiable`. A verdict is a row, so a re-resolution is a second row with a later `decided_at`; readers that need one verdict take the latest visible one and say so.

### 3.7 Declarations

The bundle manifest carries what a reader needs to interpret the data:

```
facts:       [{ fact_key, key_fields: [string], policy, source_order: [string] | null, declared_at }]
backfills:   [{ batch, declared_known_at, reason, declared_by: actor, captured_at }]
edge_types:  [{ edge_type, family }]            // producer additions to 3.3
embedding:   { model, dimensions } | null
```

`policy` is one of `latest_valid` (latest `valid_from` wins), `latest_observed` (latest `asserted_at` wins), `source_priority` (first match in `source_order` wins), `strict` (two candidates is a refusal). Declarations have `declared_at` so that they are themselves as-of'd: a reader applies the declaration in force at `as_of`, or at an explicit `rules_as_of`.

## 4. Read semantics

A conforming reader implements these; an engine that embeds the reference library gets them for free.

**4.1 As-of.** `read(as_of, valid_at?)` returns blocks with `known_at <= as_of` that also hold at `valid_at`: `asserted_at <= valid_at` and `valid_from <= valid_at < valid_to` (null `valid_to` is open). `valid_at` defaults to `as_of`, so the one-argument read means "as best we knew on D, what held on D". `as_of` has no default. A date-only `as_of` means the end of that day in UTC.

**4.2 Certificate.** Every as-of read returns `{ as_of, read_at, masked: {node, edge, resolution}, backfill: {batches, rows} | null, rules_as_of? }`. `masked` counts blocks hidden by 4.1. Omit keys whose value is zero or null.

**4.3 Supersession.** A block is `superseded_by` X as of T when an edge `X SUPERSEDES block` is visible as of T. Superseded blocks are returned and flagged, not dropped.

**4.4 Resolve.** `resolve(fact_key, as_of, valid_at?, rules_as_of?)`: candidates are visible nodes carrying `fact_key`; the declared policy picks one. Outcomes: `answered {value, candidates}`, or `no_answer {reason}` with reason in `undeclared_fact`, `no_data`, `not_yet`, `no_value_at`, `unresolved_conflict` (all candidates attached). A reader MUST NOT pick a value by any rule other than the declared policy.

**4.5 Expansion.** Walking edges from a set of nodes applies 4.1 at every hop and filters by family. `why(node_id, as_of, valid_at?, depth=3)` is the named walk: from one block over edges of the causal, argumentative and temporal families, in both directions, to `depth` hops. Each row carries the block, its `depth`, the `path` of ids from the root, the edge it came through (`via`), and a `role` that names which end of that edge the block sits at (for `CAUSES`: `cause` at the source, `effect` at the target; for `SUPERSEDES`: `successor` and `predecessor`; the root is `subject`). A root that is not visible as of T returns an empty chain with reason `not_yet` (exists, learned later) or `absent`, plus the certificate.

## 5. Physical profiles

### 5.1 Bundle layout

```
<bundle>/
  factblock.json        manifest: factblock_version, namespace, declarations (3.7), tables
  nodes.parquet         or nodes.jsonl
  edges.parquet         or edges.jsonl
  resolutions.parquet   or resolutions.jsonl (optional)
```

`factblock_version` is semantic: a minor bump adds fields only; a major bump may break. Readers that do not know the version SHOULD read best-effort, never refuse.

A bundle may travel as a `tar.gz` of the directory. The tckg ledger serves one from `GET /v1/export?as_of=`.

### 5.2 JSONL profile

One block per line. Instants are RFC 3339 with offset. `valid_to` null is written as `null`. `embedding` is a JSON array. The node and edge objects are exactly the tables in 3.1 and 3.2. This profile is the interchange and git-tracked form, and is byte-compatible with the tckg `POST /v1/memories` body items.

### 5.3 Parquet profile

One file per table, one explicit Arrow schema per table (`factblock/parquet.py` in this repository is the normative list). Instants are `timestamp[us, UTC]`; `valid_to` is nullable. `kind` and `edge_type` are utf8 (dictionary encoding is a writer option). `payload`, `properties`, `fact_value`, `value`, and `evidence` are utf8 columns holding JSON. `attestation` is `struct<ledger utf8, batch utf8>`. `embedding` is `list<float32>`; a writer MAY use `fixed_size_list` when `declarations.embedding.dimensions` is set. Fields the schema does not name go into an `extra` utf8 column as a JSON object, so a round trip loses nothing (section 7). Rows are sorted by `known_at`, so an as-of read is a prefix scan, and any engine can apply `WHERE known_at <= T` on the file directly. Compression is the writer's choice; the reference writer uses zstd.

`factblock to-parquet <bundle> <out>` converts a JSONL bundle. The manifest is copied with `tables` pointing at the `.parquet` files.

### 5.4 Iceberg (informative)

The three tables can be Iceberg tables. An Iceberg snapshot taken at T is an as-of boundary for `known_at <= T`. A normative mapping is deferred to a later minor version.

## 6. Writing

A writer that is not a ledger (an export tool, an adapter) MUST NOT invent `known_at`. It either copies `known_at` and `attestation` from the ledger it reads, or declares a backfill batch and sets `attestation.batch`. Writers MUST NOT emit `captured_at` on blocks; that field belongs to batch records.

**6.1 Importing a bundle into a store.** A store that takes a bundle in MUST keep every row's `known_at`. It does so by declaring the bundle's backfill batches as its own backfill batches (same `declared_known_at`, the reason carried over) and writing each row under its batch. A row the bundle's ledger stamped itself (`attestation.batch` null) is written under a batch declared at that row's `known_at`, named after that ledger. A store MUST NOT adopt an imported row as learned at import time: that would move knowledge forward and make the row visible to as-of reads that the source would have hidden. Re-importing a bundle MUST be a no-op: rows are identified by `id` (nodes), `(source_id, target_id, edge_type, asserted_at)` (edges), and `(target_id, decided_at)` (resolutions), not by their attestation. Resolutions are the store's own to make and are not imported by the reference implementation.

## 7. Compatibility rules (from OKF, adopted)

Consumers MUST preserve unknown fields when round-tripping, MUST NOT reject a bundle for unknown `kind` or `edge_type` values (section 3.3), and MUST NOT reject a bundle for a `factblock_version` they do not know. Producers MAY add fields; a field added by a producer that later becomes core keeps its name.

## 8. Conformance

`factblock validate <bundle>` runs every check in section 2 and the schema of section 3 and reports `check_id | ok | detail`. A bundle conforms when every check passes. The validator needs no engine and no network. Each MUST in this document has a check id; the checks are the normative list, the prose explains them.

## 9. Projections (informative)

### 9.1 OKF

A FactBlock node maps to one OKF concept document: `type` = `kind`, `title` = `statement`, `resource` = a URI for the node, `generated.at` = `asserted_at`, `generated.by` = `author`, `stale_after` = `valid_to`, `sources[]` from `payload.source`, and `supersedes:` / `superseded_by:` as additional frontmatter keys holding bundle-relative links. `known_at` and `attestation` are carried as additional keys. The reverse direction (OKF to FactBlock) MUST declare a backfill batch, because an OKF document's timestamps are self-reported and the importer's capture instant is the only knowledge time it can attest.

### 9.2 ClaimReview

A verdict visible as of an instant maps to one schema.org `ClaimReview`. The projection is lossy: ClaimReview holds one verdict per claim and two dates, so the chain, the interval, the certificate and earlier verdicts have no field. The reference projection (`factblock to-claimreview`) takes the latest visible verdict per block and carries the rest under `factblock:` keys that a consumer may ignore.

| ClaimReview | FactBlock |
|---|---|
| `claimReviewed` | node `statement` |
| `itemReviewed` (`Claim`) `.author` | `payload.speaker`, else node `author` |
| `itemReviewed.datePublished` | node `asserted_at` (date) |
| `itemReviewed.appearance.url` | `payload.source.url` |
| `reviewRating.alternateName`, `.ratingValue` (1..5) | resolution `outcome` through the recommended vocabulary (3.6): `true`/`came_true` 5, `mostly_true` 4, `partial` 3, `mostly_false`/`misleading` 2, `false`/`did_not` 1, `unverifiable`/`undecidable` no `ratingValue` |
| `author` | resolution `resolver` (`human:` becomes `Person`, else `Organization`) |
| `datePublished` | resolution `decided_at` (date) |
| `url` | caller's base URL plus the node id |
| `factblock:id`, `factblock:kind`, `factblock:known_at`, `factblock:method`, `factblock:certificate` | what ClaimReview cannot say |

The reverse direction (ClaimReview, or a fact-check feed such as Google's Fact Check Tools API, to FactBlock) maps the claim to a node (`text` to `statement`, `claimant` to `payload.speaker`, `claimDate` to `asserted_at`) and each review to a resolution row (`textualRating` to `value`, normalised to the vocabulary where it fits, `reviewDate` to `decided_at`, `publisher` to `resolver`, `url` to `evidence`). Its dates are self-reported, so the importer MUST declare a backfill batch per `reviewDate`, as in 9.1 and section 6.

## 10. Reference implementations

- `factblock` (Python, `factblock/` in this repository): `scan`, `validate`, `resolve`, `why`, `leak`, `write_parquet`, `extract`, `to_claimreview` (9.2), `to_okf` (9.1). Returns Arrow tables plus a certificate.
- `factblock.adapters.factcheck` (Python, this repository): a third writer. Reads a fact-check feed in the shape of Google's Fact Check Tools API and writes claims as nodes and reviews as resolution rows, each under a backfill batch declared at its review date (9.2, section 6).
- `factblock.sync` (Python, this repository): moves a bundle between a folder and a store under 6.1. A store is two methods, `pull(as_of)` and `push(manifest, nodes, edges)`; `TckgStore` implements them over tckg's HTTP API (`GET /v1/export`, `POST /v1/memories` with one backfill declaration per batch), and `tests/test_sync.py` holds an in-memory store as the minimal example. tckg's `smoke/10-sync.sh` runs the round trip against a live ledger.
- tckg `GET /v1/export` writes bundles that `factblock validate` accepts; tckg's smoke suite proves the round trip on every commit.
- [tckg](https://docs.tckg.factagora.com) (PostgreSQL ledger service, hosted by Factagora): stamps `known_at`, enforces I1 to I5 at write time, exports and imports bundles.

- `duckdb/factblock.sql` (SQL, this repository): a reader for DuckDB as table macros over the Parquet profile. Same as-of, valid_at, supersession, and certificate rules as `scan`; a test holds the two equal.
- `factblock.adapters.graphiti` (Python, this repository): a second writer. It reads a Graphiti graph through Graphiti's own object model (any backend: Neo4j, FalkorDB, Kuzu) and writes a bundle, declaring one backfill batch per distinct `created_at` because that clock is self-reported (section 6). tckg's `memory/graphiti_to_factblock.py` runs it against an embedded Kuzu store and imports the result into the tckg ledger.

Two writers exist (a ledger and an adapter). 1.0.0 still waits for a reader or writer maintained outside this repository.
