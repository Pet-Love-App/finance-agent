#!/usr/bin/env bash
set -euo pipefail

if ! command -v sonar-scanner >/dev/null 2>&1; then
  echo "sonar-scanner not found"
  exit 1
fi

sonar-scanner \
  -Dsonar.projectKey=agent-sandbox \
  -Dsonar.projectName=agent-sandbox \
  -Dsonar.sources=agent/sandbox \
  -Dsonar.tests=tests \
  -Dsonar.python.version=3.11 \
  -Dsonar.qualitygate.wait=true
