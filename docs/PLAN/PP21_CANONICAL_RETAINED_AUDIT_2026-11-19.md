# PP21 complete retained-A read-only verification

November 19, 2026. A bounded diagnostic verified the complete retained A scope
with the qualified canonical-byte-reuse transport. The original seal window
had already expired. This result grants no retirement authority and does not
qualify collection continuity or application history after real retirement.

| Measure | Operator result |
| --- | --- |
| Raw scope | 57 objects / 28,411 rows, exact retained comparison |
| Structured scope | 63 pages / 31,162 rows, receipts/revisions/projections checked |
| Core operation | 214.390169 s of 240 s; 25.609910 s remaining |
| Attached-container interval | 219.458 s; excludes the complete SSH control lifecycle |
| First scoped structured read | 500 rows / 73 distinct projection keys, 2.163305 s of 4 s |
| Maximum structured-readback phase | 3.547267 s of 4 s |
| Budget charges | 122 requests / 53,779,250 logical bytes; not wire-byte measurements |
| Preservation | Independent retained-before and retained-after fingerprints equal |
| Exit/cleanup | Exit 0; diagnostic container removed |
| Original trial / retirement | Both false; original deadline already expired |

The local identity was `tradebot_reader`; structured reads used the restricted
`tradebot_pp_history` identity in read-only repeatable-read transactions. The
retained fingerprints cover A/B raw rows and generation metadata, A's 31,162
outbox rows including ACKs, A's 57 manifests, live writer state and outcomes.
Outcomes honestly remained zero. Generated services were left running and
collection remained OFF.

## Exact source and image binding

- Regular deployed PP21 source:
  `c1da8d688dd8e9b860c473c965feb9099435ef97`.
- Immutable base image:
  `sha256:880c013e6fd1936be6bfdf2fbd101f1b021357c45a1c454b42c6da7df7831040`;
  [normal PP21 deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44562705669).
- Diagnostic candidate source:
  `308bfcfa5d391bd24e810df08abec398d4398365`,
  [exact successful push CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44563923394).
- Only runtime-file difference from PP21:
  `backend/postgres/history_v2_transport.py`, SHA-256
  `86ab76801ce497b885ca16737450c026853d1c533890e6b055cab1f2b22e3142`.
  Requirements, Dockerfile and pinned base were unchanged.
- All 60 effective backend files were checked before imports/database use.
  Canonical file-manifest SHA-256:
  `6fe63cfe209f58ab62a2b1f13491e158c7e7488883fe65d36eefa8e34ee9da5c`.
- Controller SHA-256:
  `9a7b10324bb9376193a7a5263efd9bd5e40818682f0e2cb77ba84d4373d9081a`.
- Host-program SHA-256:
  `546582408d596bcea74884ee24395e19fa91121391f9967b05c8fddc7ee085ba`.
  Diagnostic-payload SHA-256:
  `55733a14f91383001426c0ea9b3539e09552a1f778371bcf539660139087a205`.

[Exact operator receipt](evidence/pp21-canonical-retained-audit-2026-11-19.json)
has SHA-256
`a7f8ce3958444876db9ac45e672090e2a3b87509a620c3cfeeeffe44cb5da83b`.
[Backend equivalence proof](evidence/pp21-canonical-backend-equivalence-2026-11-19.json)
records the full source-file manifest. A separate source review independently
recomputed all 60 file hashes, the manifest hash, the sole runtime-file
difference, unchanged requirements/Dockerfile scope, receipt counts and budget
bounds, and retained-before/after equality.

## Qualification boundaries

This was a one-off diagnostic transport override, not a normal deployment of
the candidate source or the later preprod source. The regular PP21 image/source
was unchanged. No index/DDL, detach/drop, permit, live ON, paid AI, production
change or cloud data write occurred.

The result closes this bounded retained-A verification attempt. It does not
change the expired original trial verdict, authorize removal, demonstrate
successor writes during verification, or qualify both legs of A→B→fresh-A.
Prepare the deterministic history probe before any separately authorized
retirement and repeat it afterward. Actual application history, official
outcome reconciliation and multi-generation recalculation remain separate.

The earlier PP19/PP20 holds remain valid historical results. Nested phase totals
overlap, and the previous full audit did not complete; no whole-audit percentage
improvement or causal attribution to one code change is established here.
