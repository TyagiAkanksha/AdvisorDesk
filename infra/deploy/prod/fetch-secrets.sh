#!/bin/bash
# Fetch the AdvisorDesk secrets from SSM Parameter Store and write them to
# /opt/advisordesk/.env (mode 600). Runs ON THE BOX using the instance role,
# which can decrypt the SecureString params. Prints only a count — never a value.
# OPENAI_API_KEY added 2026-09-06 (provider switched to OpenAI); NVIDIA_API_KEY
# kept for back-compat but unused while LLM_PROVIDER=openai.
set -euo pipefail
REGION=us-east-1
OUT=/opt/advisordesk/.env
umask 077
: > "$OUT"
for P in DATABASE_URL OPENAI_API_KEY NVIDIA_API_KEY SESSION_SECRET GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET ADMIN_EMAILS; do
  V="$(aws ssm get-parameter --region "$REGION" --name "/advisordesk/$P" --with-decryption \
        --query 'Parameter.Value' --output text)"
  printf '%s=%s\n' "$P" "$V" >> "$OUT"
done
# OPTIONAL params (anthropic-haiku provider): skipped — never written empty — when the
# SSM parameter does not exist. Any OTHER failure (e.g. AccessDenied) still aborts.
for P in ANTHROPIC_API_KEY; do
  if V="$(aws ssm get-parameter --region "$REGION" --name "/advisordesk/$P" --with-decryption \
        --query 'Parameter.Value' --output text 2>"$OUT.err")"; then
    printf '%s=%s\n' "$P" "$V" >> "$OUT"
  elif grep -q 'ParameterNotFound' "$OUT.err"; then
    echo "skip optional $P (not set in SSM)"
  else
    rm -f "$OUT.err"
    echo "ERROR fetching optional $P" >&2
    exit 1
  fi
done
rm -f "$OUT.err"
chmod 600 "$OUT"
echo "OK wrote $(wc -l < "$OUT") vars to $OUT"
