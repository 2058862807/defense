#!/usr/bin/env bash
# Fails (exit 1) if any staged .env-pattern file contains a non-placeholder
# EVM_PRIVATE_KEY / FLASHBOTS_SIGNING_KEY value. Placeholders (0x000..., 0x...,
# empty, or a Vault/pilot-secrets reference comment) are allowed since prod
# secrets belong in Vault/HSM, never in a committed file.
#
# Used both as a git pre-commit hook (see .pre-commit-config.yaml) and as a
# CI check, since a hook can be skipped with --no-verify but CI can't.
set -euo pipefail

FAILED=0

is_placeholder() {
    local value="$1"
    case "$value" in
        ""|0x0000000000000000000000000000000000000000000000000000000000000000|0x000*|0x...|your-*|change_me*|dev-*|placeholder*)
            return 0 ;;
        *)
            return 1 ;;
    esac
}

check_file() {
    local file="$1"
    local content
    content="$(git show ":${file}" 2>/dev/null || cat "$file" 2>/dev/null || true)"
    [ -z "$content" ] && return 0

    while IFS= read -r line; do
        key="${line%%=*}"
        value="${line#*=}"
        value="${value%%#*}"                      # strip inline comment
        value="$(echo "$value" | xargs echo -n)"  # trim whitespace
        case "$key" in
            EVM_PRIVATE_KEY|FLASHBOTS_SIGNING_KEY|EVM_PRIVATE_KEY_DEV)
                if ! is_placeholder "$value"; then
                    echo "[✗] $file: $key has a non-placeholder value staged for commit."
                    echo "    Real signing keys belong in Vault/HSM (see app/hsm/custody.py), never in a committed .env file."
                    FAILED=1
                fi
                ;;
        esac
    done <<< "$content"
}

# Default (pre-commit hook): check what's staged right now.
# --tracked (CI): check everything already committed to the tree, as a
# backstop in case a hook was bypassed with --no-verify.
MODE="${1:-staged}"
if [ "$MODE" = "--tracked" ]; then
    CANDIDATE_FILES="$(git ls-files 2>/dev/null || true)"
else
    CANDIDATE_FILES="$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)"
fi

for f in $CANDIDATE_FILES; do
    case "$f" in
        .env|.env.*|*/.env|*/.env.*)
            check_file "$f"
            ;;
    esac
done

if [ "$FAILED" -eq 1 ]; then
    echo ""
    echo "Commit blocked: remove the real key or replace it with a placeholder before committing."
    exit 1
fi

exit 0
