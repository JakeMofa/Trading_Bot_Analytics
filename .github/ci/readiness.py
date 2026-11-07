"""Fail closed on missing/failed job results or required exact-candidate evidence."""
import json
import os
from pathlib import Path
import time
from run_tests import write_evidence

CATEGORIES = ['backend', 'application', 'root', 'controls', 'ci-controls', 'source', 'static', 'workflows', 'dependencies']
JOBS = {'quality', 'security', 'application', 'controls', 'test', 'integrated'}
REQUIRED = ['ab-generated-report.json', 'ab-joint-report.json', 'ab-import-report.json',
            'integrated-report.json', 'AB_CANDIDATE_MANIFEST.json']


def validate(directory, jobs, tested_sha, source_sha):
    problems = [] if set(jobs) == JOBS else ['jobs: BLOCKED incomplete job evidence']
    problems += [f'{name}: {state}' for name, state in jobs.items() if state != 'success']
    for category in CATEGORIES:
        files = list(directory.rglob(category + '.json'))
        if len(files) != 1:
            problems.append(f'{category}: BLOCKED missing or ambiguous evidence')
            continue
        evidence = json.loads(files[0].read_text())
        if (evidence.get('gate') != 'PASS' or evidence.get('tested_sha') != tested_sha
                or evidence.get('source_sha') != source_sha):
            problems.append(f'{category}: FAIL result or SHA binding')
        if category in CATEGORIES[:5] and evidence.get('tests', 0) <= evidence.get('skips', 0):
            problems.append(f'{category}: BLOCKED no executed tests')
    for name in REQUIRED:
        files = list(directory.rglob(name))
        if len(files) != 1:
            problems.append(f'{name}: BLOCKED required report missing or ambiguous')
        else:
            report = json.loads(files[0].read_text())
            if not report:
                problems.append(f'{name}: BLOCKED empty report')
            if name == 'AB_CANDIDATE_MANIFEST.json' and report.get('source_sha') != tested_sha:
                problems.append(f'{name}: FAIL SHA binding')
    return problems


if __name__ == '__main__':
    started = time.monotonic()
    try:
        problems = validate(Path(os.environ['CI_ARTIFACTS']), json.loads(os.environ['CI_JOB_RESULTS']),
                            os.environ['GITHUB_SHA'], os.environ['CI_SOURCE_SHA'])
    except (ValueError, KeyError, OSError):
        problems = ['evidence: BLOCKED unreadable or malformed report']
    for problem in problems:
        print(problem)
    write_evidence('readiness', {'gate': 'BLOCKED' if problems else 'PASS', 'issues': problems,
                   'candidate': 'qualified' if not problems else 'unqualified',
                   'deployed': 'NOT PERFORMED', 'acceptance_validated': 'NOT PERFORMED'}, started)
    raise SystemExit(bool(problems))
