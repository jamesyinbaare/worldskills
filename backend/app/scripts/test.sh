#!/usr/bin/env bash

set -e
set -x

# Coverage gate: fail if total coverage drops below 60% (foundations + Epic A).
COVERAGE_FAIL_UNDER="${COVERAGE_FAIL_UNDER:-60}"

coverage run -m pytest pytest_tests/
coverage report --fail-under="${COVERAGE_FAIL_UNDER}"
coverage html --title "${@-coverage}"
