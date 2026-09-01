#!/bin/bash
# Fetch the 6 AdvisorDesk secrets from SSM Parameter Store and write them to
# /opt/advisordesk/.env (mode 600). Runs ON THE BOX using the instance role,
# which can decrypt the SecureString params. Prints only a count — never a value.
set -euo pipefail
REGION=us-east-1
OUT=/opt/advisordesk/.env
umask 077
: > "$OUT"
for P in DATABASE_URL NVIDIA_API_KEY SESSION_SECRET GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET ADMIN_EMAILS; do
  V="$(aws ssm get-parameter --region "$REGION" --name "/advisordesk/$P" --with-decryption \
        --query 'Parameter.Value' --output text)"
  printf '%s=%s\n' "$P" "$V" >> "$OUT"
done
chmod 600 "$OUT"
echo "OK wrote $(wc -l < "$OUT") vars to $OUT"
