"""Readable readiness evidence; missing, failed and unperformed work stay distinct."""
import json


def state(value):
    return {'success': 'PASS', 'failure': 'FAIL', 'skipped': 'NOT PERFORMED',
            'cancelled': 'BLOCKED'}.get(value, 'BLOCKED')


def readiness_summary(directory, jobs, categories, source_sha, tested_sha, run_url, problems):
    lines = ['## Required gate evidence', '', f'Source SHA: `{source_sha}`',
             f'Tested SHA: `{tested_sha}`', '',
             f'[Run, logs and evidence artifacts]({run_url})', '',
             '| Required job | Result |', '| --- | --- |']
    for name in sorted(jobs):
        lines.append(f'| {name} | {state(jobs[name])} |')
    lines += ['', '| Test/check category | Gate | Tests | Skips | Seconds |',
              '| --- | --- | ---: | ---: | ---: |']
    for category in categories:
        files = list(directory.rglob(category + '.json'))
        evidence = {}
        if len(files) == 1:
            try:
                evidence = json.loads(files[0].read_text())
                if not isinstance(evidence, dict):
                    evidence = {}
            except (OSError, ValueError):
                pass
        lines.append(f"| {category} | {evidence.get('gate', 'BLOCKED')} | "
                     f"{evidence.get('tests', 'NOT PERFORMED')} | "
                     f"{evidence.get('skips', 'NOT PERFORMED')} | "
                     f"{evidence.get('elapsed_seconds', 'unknown')} |")
    lines += ['', '### Readiness: ' + ('BLOCKED' if problems else 'PASS'), '']
    lines += ['- ' + problem for problem in problems]
    lines += ['', 'Production deployment, acceptance and full-scale capacity: NOT PERFORMED.',
              'A passing PR merge run does not replace exact-source push CI for release.',
              '[Before/during/after database coverage and remaining production gates]'
              f'({run_url.split("/actions/")[0]}/blob/{tested_sha}/.github/ci/DATABASE_COVERAGE.md)',
              'Postgres uses minimal generated roles/storage fixtures; live Supabase drift/auth/Storage: NOT PERFORMED.',
              'Production A/B/core/retained-legacy operator route and aggregate capacity: BLOCKED pending storage-owner qualification.', '']
    return '\n'.join(lines)
