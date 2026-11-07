# Dependency remediation for the storage owner

This is a tested **proposal**, not an applied application dependency change.
Apply `cryptography-50.patch` to `backend/requirements.txt` only after the storage
owner reviews it. `git apply --check .github/ci/proposals/cryptography-50.patch`
passes against the current pin. Normal CI continues auditing the actual runtime
requirements; it does not use this alternative requirements file or ignore alerts.

## Upstream evidence

| Audit advisory | Upstream issue | Earliest fixed version |
| --- | --- | --- |
| PYSEC-2026-3552 / CVE-2026-69247 | [PKCS#7 decryption oracle](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5) | 50.0.0 |
| PYSEC-2026-3553 / CVE-2026-69249 | [Duplicate-certificate path building](https://github.com/pyca/cryptography/security/advisories/GHSA-jwv3-5hgf-82ww) | 49.0.0 |
| PYSEC-2026-3554 / CVE-2026-69248 | [Wildcard certificate name constraints](https://github.com/pyca/cryptography/security/advisories/GHSA-m2h6-j472-rp4c) | 49.0.0 |
| GHSA-537c-gmf6-5ccf | [Bundled vulnerable OpenSSL](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf) | 48.0.1 |

The [upstream changelog](https://cryptography.io/en/latest/changelog/#v50-0-0)
confirms the 50.0.0 security fix. Therefore 50.0.0 is the smallest version fixing
all four reported advisories. Later releases exist; this proposal tests the
minimum change requested, not a claim that 50.0.0 is the latest version.

The repository's direct cryptography use is Ed25519 message signing in
`backend/app/streaming.py`, tested by `test_streaming.StreamTests.test_signed_headers`.
No application PKCS#7 or X.509 verification call was found in the source search.
This limits known direct exposure but does not waive a genuine dependency alert.
The upgrade crosses major versions and changes bundled OpenSSL; local tests
cannot prove every platform/build or deployment combination compatible.

## Isolated candidate qualification

Base source: `7bee563aa05c09592f4758520bab83477470d1db`. Only the proposed
requirements input in an ignored isolated environment was altered; neither
checkout's application requirements file was edited. See
`cryptography-50-local-evidence.json` for exact requirements/patch hashes,
resolved packages, runtime versions, counts and elapsed time.

Environment: macOS 26.5.2 arm64, CPython 3.13.1, cryptography 50.0.0 wheel,
bundled OpenSSL 4.0.1 (9 June 2026). Dependency consistency PASS; pip-audit 2.9.0
reports zero known vulnerabilities for the full proposed dependency set.
Backend 367 tests PASS with 20 platform/privilege skips; application 67 PASS,
zero skips (including signed headers); deployment controls 123 PASS with three
platform skips. Linux/Python 3.12, root qualification, production and full-scale
capacity with this dependency candidate: NOT PERFORMED. No live credentials,
network feed, paid AI or production operation were used by application tests.

## Safe review and merge order

1. Storage owner reviews/applies the one-line pin change on the existing working
   branch, in a separate small dependency commit. No PR #9 merge is needed.
2. Refresh the CI branch from that reviewed base in coordination with the storage
   owner, keeping the PR #10 diff restricted to CI changes. Requalify the actual
   resulting source and PR merge SHAs; older or local candidate results do not
   certify new storage changes.
3. Before PR #10 can merge, exact-source push CI and PR CI must pass source/static/
   workflow checks, dependency audit, application contracts, deployment controls,
   backend/root/import/joint/integrated qualification and `PR readiness`, with
   complete reports and SHA bindings. Pending/skipped/cancelled required jobs
   block readiness. Review PR #10 into the working branch only.
4. After that merge, qualify the resulting working-branch SHA. PR #9 still needs
   its independent storage review and currently documented history/replay,
   reconciliation, retirement-authorization and release-readiness gates. Passing
   CI does not supply missing storage evidence or authorize production.
5. Require the stable `PR readiness` check on intended protected branches only
   after passing evidence exists; re-inspect current protection first. Exact
   deployment-branch push CI remains separately required by verify_ci.py.

No merge, enforcement change or production dispatch is authorized by this proposal.
