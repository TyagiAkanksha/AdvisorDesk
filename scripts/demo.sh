#!/usr/bin/env bash
# scripts/demo.sh — client-story walkthrough from the README's "## Demo" section (PRD §2.2).
#
# Runs the three public, no-auth commands against a local or live API: browse published content,
# ask a real answerable question from seed/eval_questions.yaml, ask a real unanswerable one.
#
# Usage:
#   ./scripts/demo.sh                                                       # local API
#   BASE_URL=https://api.advisordesk.tyagiakanksha.com ./scripts/demo.sh    # live API
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "== 1. Browse published content: GET /api/v1/public/content =="
curl -s "$BASE_URL/api/v1/public/content"
echo
echo

echo "== 2. Ask an answerable question (expects a streamed, cited answer) =="
curl -N -s -X POST "$BASE_URL/api/v1/public/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is a Roth IRA conversion and how is it taxed?"}'
echo

echo "== 3. Ask an unanswerable question (expects a refusal, no general-knowledge answer) =="
curl -N -s -X POST "$BASE_URL/api/v1/public/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "What does the firm recommend about cryptocurrency staking rewards?"}'
echo
