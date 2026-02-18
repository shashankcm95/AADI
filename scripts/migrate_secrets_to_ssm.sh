#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  migrate_secrets_to_ssm.sh
#  Reads .env and stores each value as an SSM SecureString parameter.
#
#  Usage:
#    ./scripts/migrate_secrets_to_ssm.sh [stage]
#    ./scripts/migrate_secrets_to_ssm.sh dev
#    ./scripts/migrate_secrets_to_ssm.sh prod
#
#  This creates parameters like:
#    /aadi/dev/OPENAI_API_KEY
#    /aadi/prod/AWS_ACCESS_KEY_ID
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

STAGE="${1:-dev}"
ENV_FILE="${2:-.env}"
PREFIX="/aadi/${STAGE}"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ $ENV_FILE not found."
  exit 1
fi

echo "📦 Migrating secrets from $ENV_FILE to SSM under prefix: $PREFIX"
echo ""

while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip comments and blank lines
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ -z "$line" ]] && continue

  KEY="${line%%=*}"
  VALUE="${line#*=}"
  # Strip surrounding quotes from value
  VALUE="${VALUE%\'}"
  VALUE="${VALUE#\'}"
  VALUE="${VALUE%\"}"
  VALUE="${VALUE#\"}"

  PARAM_NAME="${PREFIX}/${KEY}"

  echo "  → ${PARAM_NAME}"
  aws ssm put-parameter \
    --name "${PARAM_NAME}" \
    --value "${VALUE}" \
    --type "SecureString" \
    --overwrite \
    --no-cli-pager

done < "$ENV_FILE"

echo ""
echo "✅ All secrets migrated to SSM under ${PREFIX}/"
echo ""
echo "⚠️  NEXT STEPS:"
echo "  1. Rotate the exposed AWS credentials in IAM console"
echo "  2. Rotate the OpenAI API key in the OpenAI dashboard"
echo "  3. Delete the .env file: rm ${ENV_FILE}"
echo "  4. Ensure .env is in .gitignore"
