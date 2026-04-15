#!/usr/bin/env bash
# Mini Orchestrator pre-commit hygiene check.
#
# Wired via .git/hooks/pre-commit. Refuses commits that include junk files,
# likely secrets, gitignore violations, uncompilable Python, or TypeScript
# that fails `tsc --noEmit`. Emits soft warnings for doc-freshness drift.
#
# Exit codes:
#   0  all clear (warnings may still have printed)
#   1  at least one blocking check failed
#
# Bypass with `git commit --no-verify` ONLY when you have a real reason
# and document that reason in the commit message.

set -u
cd "$(git rev-parse --show-toplevel)"

errors=0
warnings=0
RED=$'\033[31m'; YELLOW=$'\033[33m'; GREEN=$'\033[32m'; DIM=$'\033[2m'; RESET=$'\033[0m'

fail() { echo "${RED}✗${RESET} $*"; errors=$((errors+1)); }
warn() { echo "${YELLOW}⚠${RESET} $*"; warnings=$((warnings+1)); }
ok()   { echo "${GREEN}✓${RESET} $*"; }
info() { echo "${DIM}·${RESET} $*"; }

# --- branch guard: never commit directly to main ----------------------------
# Per CLAUDE.md the workflow is feature → master → main. main only ever
# receives merge commits. This catches accidental forgetting (mine or yours).
current_branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "(detached)")
if [ "$current_branch" = "main" ]; then
    # Allow when in the middle of a merge (the master → main promotion).
    if [ ! -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]; then
        echo "${RED}✗${RESET} you are on 'main' — direct commits to main are not allowed."
        echo "    Per CLAUDE.md: feature → master → main."
        echo "    Switch with:    git stash && git checkout master && git stash pop"
        echo "    Or, if intentional, bypass with --no-verify and document why."
        exit 1
    fi
fi

# --- staged files (added / copied / modified / renamed; not deletions) ---
# Portable substitute for `mapfile` — macOS's /bin/bash is 3.2.
STAGED=()
while IFS= read -r line; do
    [ -n "$line" ] && STAGED+=("$line")
done < <(git diff --cached --name-only --diff-filter=ACMR)

if [ "${#STAGED[@]}" -eq 0 ]; then
    ok "nothing staged, skipping checks"
    exit 0
fi

echo "Pre-commit check: ${#STAGED[@]} staged file(s)"

# ------------------------------------------------------------------------
# 1. Junk files
# ------------------------------------------------------------------------
JUNK_PATTERNS=(
    '\.DS_Store$'
    'Thumbs\.db$'
    '\.pyc$'
    '__pycache__/'
    '\.log$'
    '\.tmp$'
    '\.swp$'
    '\.swo$'
    '\.bak$'
    '~$'
)

junk_found=0
for f in "${STAGED[@]}"; do
    for pat in "${JUNK_PATTERNS[@]}"; do
        if [[ "$f" =~ $pat ]]; then
            fail "junk file staged: $f (matches /$pat/)"
            junk_found=1
        fi
    done
    # .env explicit — allow .env.example, block .env* otherwise
    if [[ "$f" =~ (^|/)\.env$ ]] || [[ "$f" =~ (^|/)\.env\.[a-z]+$ && "$f" != *.example ]]; then
        fail "env file staged: $f (commit to .env.example instead)"
        junk_found=1
    fi
done
[ $junk_found -eq 0 ] && ok "no junk files staged"

# ------------------------------------------------------------------------
# 2. Secret scan in staged content
# ------------------------------------------------------------------------
# Patterns worth catching. .env.example is whitelisted — it deliberately
# contains placeholder-shaped tokens.
SECRET_REGEXES=(
    'sk-ant-[a-zA-Z0-9_-]{16,}'
    'ghp_[a-zA-Z0-9]{36,}'
    'gho_[a-zA-Z0-9]{36,}'
    'github_pat_[a-zA-Z0-9_]{22,}'
    'AKIA[0-9A-Z]{16}'
    'aws_secret_access_key[[:space:]]*=[[:space:]]*["'\'']?[A-Za-z0-9/+=]{40}'
    'BEGIN (RSA|OPENSSH|EC) PRIVATE KEY'
)

secret_found=0
for f in "${STAGED[@]}"; do
    # skip whitelisted files
    if [ "$f" = ".env.example" ]; then continue; fi
    # only scan text-like files
    if [ ! -f "$f" ]; then continue; fi
    if ! file --mime "$f" 2>/dev/null | grep -qE 'text|json|xml'; then continue; fi

    staged_content=$(git show ":$f" 2>/dev/null || cat "$f")
    for pat in "${SECRET_REGEXES[@]}"; do
        if echo "$staged_content" | grep -qE "$pat"; then
            fail "possible secret in $f (pattern /$pat/)"
            secret_found=1
        fi
    done
done
[ $secret_found -eq 0 ] && ok "no secrets detected"

# ------------------------------------------------------------------------
# 3. Gitignore alignment — nothing force-added that matches ignore rules
# ------------------------------------------------------------------------
ignore_violations=0
for f in "${STAGED[@]}"; do
    if git check-ignore -q "$f"; then
        fail "staged file matches .gitignore: $f (was it force-added?)"
        ignore_violations=1
    fi
done
[ $ignore_violations -eq 0 ] && ok "no gitignore violations"

# ------------------------------------------------------------------------
# 4. Unexpected top-level entries
# ------------------------------------------------------------------------
ALLOWED_TOP=(
    backend frontend docs tests scripts venv node_modules data
    CLAUDE.md README.md README LICENSE LICENSE.md
    pyproject.toml
    .env.example .gitignore .gitattributes
    .git .github .vscode .idea
)
top_unknown=0
for f in "${STAGED[@]}"; do
    top="${f%%/*}"
    [ "$top" = "$f" ] || top="${top}"
    # skip repo-root files too — match against ALLOWED_TOP anyway
    hit=0
    for allowed in "${ALLOWED_TOP[@]}"; do
        if [ "$top" = "$allowed" ]; then hit=1; break; fi
    done
    if [ $hit -eq 0 ]; then
        warn "unknown top-level entry: $top (update ALLOWED_TOP in scripts/precommit.sh if intentional)"
        top_unknown=1
    fi
done
[ $top_unknown -eq 0 ] && ok "top-level structure intact"

# ------------------------------------------------------------------------
# 5. Python compile check on staged .py files
# ------------------------------------------------------------------------
py_files=()
for f in "${STAGED[@]}"; do
    [[ "$f" == *.py ]] && [ -f "$f" ] && py_files+=("$f")
done

if [ ${#py_files[@]} -gt 0 ]; then
    python_bin=""
    if [ -x "venv/bin/python" ]; then python_bin="venv/bin/python";
    elif command -v python3 >/dev/null; then python_bin="python3";
    elif command -v python >/dev/null; then python_bin="python"; fi

    if [ -z "$python_bin" ]; then
        warn "no python interpreter found; skipping py_compile"
    else
        compile_errors=0
        for f in "${py_files[@]}"; do
            if ! "$python_bin" -m py_compile "$f" 2>/tmp/precommit_py_err; then
                fail "python compile failed: $f"
                sed 's/^/    /' /tmp/precommit_py_err
                compile_errors=1
            fi
        done
        [ $compile_errors -eq 0 ] && ok "${#py_files[@]} python file(s) compile"
    fi

    # ruff lint on the staged python files — fast (~100ms) and catches issues
    # that py_compile doesn't (unused imports, style, bugbear, etc).
    ruff_bin=""
    if [ -x "venv/bin/ruff" ]; then ruff_bin="venv/bin/ruff";
    elif command -v ruff >/dev/null; then ruff_bin="ruff"; fi

    if [ -n "$ruff_bin" ]; then
        if ! "$ruff_bin" check "${py_files[@]}" 2>/tmp/precommit_ruff_err; then
            fail "ruff check failed:"
            sed 's/^/    /' /tmp/precommit_ruff_err
        else
            ok "ruff clean on staged python"
        fi
    fi
fi

# ------------------------------------------------------------------------
# 6. TypeScript type-check if any frontend source changed
# ------------------------------------------------------------------------
frontend_changed=0
for f in "${STAGED[@]}"; do
    if [[ "$f" == frontend/src/* ]] && [[ "$f" =~ \.(ts|tsx)$ ]]; then
        frontend_changed=1
        break
    fi
done

if [ $frontend_changed -eq 1 ]; then
    if [ ! -d frontend/node_modules ]; then
        warn "frontend source changed but node_modules missing; skipping tsc"
    elif ! (cd frontend && npx --no-install tsc --noEmit 2>/tmp/precommit_tsc_err); then
        fail "TypeScript type-check failed:"
        sed 's/^/    /' /tmp/precommit_tsc_err
    else
        ok "frontend type-check passes"
    fi
fi

# ------------------------------------------------------------------------
# 7. Docs-freshness soft warning
# ------------------------------------------------------------------------
backend_changed=0
docs_touched=0
for f in "${STAGED[@]}"; do
    [[ "$f" == backend/* ]] && backend_changed=1
    [[ "$f" == CLAUDE.md || "$f" == docs/plan.md ]] && docs_touched=1
done
if [ $backend_changed -eq 1 ] && [ $docs_touched -eq 0 ]; then
    warn "backend changed but CLAUDE.md / docs/plan.md untouched — consider whether the change deserves a note"
fi

# ------------------------------------------------------------------------
# summary
# ------------------------------------------------------------------------
echo
if [ $errors -gt 0 ]; then
    echo "${RED}$errors error(s), $warnings warning(s).${RESET} Commit blocked."
    echo "  Bypass only if you know why: git commit --no-verify"
    exit 1
fi

if [ $warnings -gt 0 ]; then
    echo "${YELLOW}$warnings warning(s)${RESET} — commit proceeding."
else
    echo "${GREEN}all checks passed.${RESET}"
fi
exit 0
