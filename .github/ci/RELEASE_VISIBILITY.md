# Manual versioned candidates and release visibility

Implemented in `release-candidate.yml` (**Release — Tradebot candidate**), triggered
**only** by workflow_dispatch. This implements candidate preparation/publication;
no real version, tag or release has been selected or published by this PR.

## Version authority and usage

`release-manifest.json` is the single authoritative version record for each
candidate. The operator supplies a reviewed SemVer without a `v` prefix; its exact
tag is `v<version>`. There is no invented production version, package.json, or
independent VERSION file that could disagree. Phase1.75 is a roadmap phase, not
an app version. Test `0.0.0-example.1` is illustrative only. A base SemVer can be
used for a candidate, but GitHub publication always remains a **prerelease**, never
latest or acceptance-validated.

After this workflow is available for dispatch (GitHub requires the workflow on
the default branch), select the intended existing allowed branch in the GitHub
Actions UI, then supply the same branch in `branch`, its full current HEAD SHA
in `revision`, an explicitly reviewed `version`, scope
`read-only-analysis-candidate`, and operation `build` or `publish`. No dispatch
is executed by implementation/tests. Default-branch workflow registration must
follow normal review; PR9 deployment is not required to design/test this module.

Allowed branches: main, codex/lightsail-deployment,
codex/phase1-75-retention-enable and codex/ci-pr-quality-gates. Exact dispatch SHA,
checkout SHA, allowed branch HEAD, and passing **push** CI for that branch/SHA
must agree. A successful synthetic PR merge run cannot substitute. Qualifying
workflow remains `python-tests.yml`; existing deployment lookup is unchanged.
Branch movement or missing/failed/in-progress CI blocks the operation. Build and
publication recheck qualification; publication also rebuilds and byte-compares
all downloaded prepared artifacts before any write. This validates current HEAD,
not an arbitrary historical commit. Approved earlier versions need their own
separate release policy; this implementation does not silently broaden it.

## Artifacts and provenance

The existing exact Git export helper selects tracked source with its sensitive-
file/data/symlink exclusions. Bundle ordering, gzip time/header and tar ownership
are deterministic. File bytes and executable modes are reverified against exact
Git objects and the bundle. Uploaded assets:

- `source.tar.gz`: tracked sanitized source and AB_CANDIDATE_MANIFEST.json.
- `requirements.txt`: byte-identical direct runtime dependency manifest.
- `ci-evidence.json`: successful push CI identity/source/tested SHA and evidence links.
- `compatibility.json`: schema SQL hashes, finite generated compatibility scope,
  migration/forward-recovery requirements and unresolved release gates.
- `release-manifest.json`: version/tag/scope/source/tested SHA, CI identity, dependency
  hash, every other asset's SHA-256/size, roadmap link and candidate/deployed/
  acceptance-validated states. Its own hash is bound by the release-notes marker
  and GitHub asset digest; it cannot contain a circular hash of itself.

This is a source candidate, **not an operator/deploy bundle**. It contains no
frozen Python interpreter, native runtime, virtualenv, resolved transitive lock
or guaranteed offline installation. Existing requirements have direct pins;
platform/transitive builds still need separate compatibility qualification.
CI artifact links can expire; the release retains the evidence snapshot and
hashes, not a promise that every original CI artifact remains available forever.

## Publication and partial failure

Prepare uses read-only contents/actions permissions. Only the explicit publish
job has contents:write, with actions:read to requalify CI. Checkout never persists
credentials. Version-scoped concurrency does not cancel an existing candidate
run and is separate from production deployment concurrency.

Publication checks existing release metadata before writing, creates a lightweight
tag only when absent, and never updates a tag. A same-tag different source, release
notes/manifest marker, asset hash, extra asset or missing server digest blocks
publication. Existing exact draft assets are retained; only missing assets are
uploaded, and the draft is published as a prerelease only after all digests and
the final tag binding verify. An identical completed release reconciles without
writes. A published incomplete release requires manual review; no assets are
replaced/deleted. Ambiguous API failures leave explicit FAIL/BLOCKED output and
may leave a tag or draft: inspect, then dispatch identical inputs to reconcile,
never force-move tags. A newer successful qualifying CI run changes the bound
CI evidence and may require a new version rather than altering a prior manifest.

The source evidence API examines at most the latest100 matching runs; failure to
find valid evidence is a hold, not a fallback. No automated retry bypasses it.
Repository admins can still mutate ordinary releases/tags outside this tool.
GitHub immutable releases could strengthen published assets/tag protection, but
changing that setting and its draft/publication behavior requires separate review;
no immutability guarantee or repository-setting change is made here.

Tags/releases never dispatch production: existing CD operations remain manual,
branch-restricted, exact-SHA checked and protected by their existing operator
scopes. No release/push-tag trigger was added to CD.

## Deployment state and rollback dependency

Current manual CD records revision/operation and sanitized verification/smoke/
recovery evidence; it does not consume this candidate manifest, record its semantic
version or prove its artifact hash was installed. Candidate publication therefore
always records deployed and acceptance-validated as NOT PERFORMED. A deployment
attempt is not acceptance and the release page is not live production telemetry.

Exact storage-owned controller extension needed before version-aware deployment:
accept reviewed manifest SHA-256 and selected version/tag/source/bundle hashes;
verify them against the approved revision and allowed artifact format before use;
append immutable attempt/outcome evidence binding host/database layout identity,
previous revision/version, new revision/version, verification/smoke/forward-recovery
results, and separately timestamped acceptance. The new source tar must not be
passed to the current operator-bundle dispatcher as if formats were compatible.
This worker changes no host/controller/runtime code or production state.

After acknowledged A/B writes, checking out old code does not roll back database
state. Code rollback requires schema/data compatibility and reviewed forward
recovery; automatic database rollback, canary collectors, new infrastructure and
cloud schema/permission changes remain unimplemented. Phase1.75 operator,
capacity/runway, legacy verification, mutation-fence and sustained-acceptance gates
remain open in the linked live roadmap. Passing candidate CI is not release approval.

## Validation and review boundary

Mock tests cover SemVer/ref/SHA/scope rejection, missing/failed/PR-only CI, tag and
release collisions, asset hash mismatch, idempotent publication, and real exact
source export/deterministic bundle/artifact tampering. No GitHub write is performed
by tests. Final exact-source push and PR CI must pass for this new source; the
previous 9847353 successful runs certify only that original SHA. Branch enforcement
remains a separately reviewed gate, not implied by a candidate workflow.

Official references: [SemVer](https://semver.org/),
[GitHub releases API](https://docs.github.com/en/rest/releases/releases),
[Git refs API](https://docs.github.com/en/rest/git/refs).
