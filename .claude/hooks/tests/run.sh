#!/usr/bin/env bash
# Test cases for .claude/hooks/block-git-write.sh (ADR-014).
# Run from the repository root:  bash .claude/hooks/tests/run.sh
# Exit code 0 when every case behaves as expected. Pure bash, no dependencies.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${1:-$HERE/../block-git-write.sh}"
fail=0
pass=0
ERR="$(mktemp)"
trap 'rm -f "$ERR"' EXIT

json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\t'/\\t}"
  s="${s//$'\r'/\\r}"
  printf '"%s"' "$s"
}

run() { # run <allow|block> <command> [tool]
  local exp="$1" cmd="$2" tool="${3:-Bash}" payload rc got
  payload=$(printf '{"session_id":"s","cwd":"x","hook_event_name":"PreToolUse","tool_name":"%s","tool_input":{"command":%s,"description":"d"}}' "$tool" "$(json_escape "$cmd")")
  printf '%s' "$payload" | bash "$HOOK" >/dev/null 2>"$ERR"; rc=$?
  got="allow"; [ $rc -eq 2 ] && got="block"
  if [ "$got" = "$exp" ]; then
    pass=$((pass + 1))
  else
    echo "FAIL expected $exp got $got (rc=$rc) [$tool]: ${cmd//$'\n'/ | }"
    cat "$ERR"
    fail=1
  fi
}

# --- the required pair ---
run allow 'git stash list'
run block 'git stash'

# --- read-only forms allowed ---
run allow 'git status'
run allow 'git status --porcelain'
run allow 'git log --oneline -20'
run allow 'git diff HEAD~1 -- docs/'
run allow 'git show HEAD:README.md'
run allow 'git stash show -p stash@{0}'
run allow 'git -C /c/repo status'
run allow 'git -C "C:/my path/repo" log -3'
run allow 'git --no-pager log -1'
run allow 'git tag'
run allow 'git tag -l "v*"'
run allow 'git branch -a'
run allow 'git branch --show-current'
run allow 'git config --get user.name'
run allow 'git config --list'
run allow 'git remote -v'
run allow 'git rev-parse --show-toplevel'
run allow 'git ls-files | head'
run allow '/usr/bin/git status'
run allow 'git --version'
run allow 'git worktree list'
run allow 'git tag; echo done'
run allow 'git log -1 && echo ok'
run allow 'git -C'
run allow 'git stash list' PowerShell

# --- state-modifying forms blocked ---
run block 'git stash push -m x'
run block 'git stash pop'
run block 'git add .'
run block 'git commit -m "msg"'
run block 'git commit --amend --no-edit'
run block 'git -C /c/repo commit -m x'
run block 'git -c user.name=x commit -m x'
run block 'git -C "C:/my path/repo" push'
run block 'git -C . commit -m x'
run block 'cd /c/repo && git checkout main'
run block 'git switch -c feat'
run block 'git reset --hard'
run block 'git restore .'
run block 'git rebase -i HEAD~3'
run block 'git merge feature'
run block 'git cherry-pick abc'
run block 'git push origin main'
run block 'git tag v1.0'
run block 'git branch -D feat'
run block 'git branch feat'
run block 'git init'
run block 'git pull'
run block 'git fetch --all'
run block 'git clean -fd'
run block 'git config user.name "x"'
run block 'git remote add origin url'
run block 'git worktree add ../x'
run block 'C:/Program\ Files/Git/bin/git.exe commit -m x'
run block 'git stash' PowerShell
run block 'git commit -m x' PowerShell

# --- wrappers, chaining, quoting ---
run block 'sh -c "git commit -m x"'
run block "bash -lc 'git -C . commit -m x'"
run block 'echo hi; git stash'
run block 'ls | xargs git add'
run block 'GIT_DIR=.git git commit -m x'
run block 'x=1 git commit -m x'
run block 'git $(echo commit) -m x'
run block 'git "commit" -m x'
run block 'git commit -m "git stash list"'
run block 'find . -name "*.py" -exec git add {} +'
run block 'timeout 10 git commit -m x'
run block 'sudo -u someone git push'
run block 'env -i git commit -m x'
run block 'python -c "import os; os.system(\"git commit -m x\")"'
run block 'bash <<X
git commit -m x
X'
run block '(git commit -m x)'
run block 'true && git commit -m x'
run block $'ls\ngit commit -m x'
run allow $'ls\ngit log -1'

# --- prose and data are not invocations ---
run allow 'ls -la'
run allow 'echo "digital"'
run allow 'grep -r "git" docs/'
run allow 'echo "git" && git log'
run allow 'echo "never run a git command"'
run allow 'printf "%s" "a git commit is made by the author"'
run allow 'docs mention git commit by the author'
run allow 'cat > AGENTS.md <<X
Never run a git command that modifies state.
This holds for `git -C <path>` and `git -c <key>=<value>` forms.
X'

# --- payload handling ---
printf '{"tool_name":"Read","tool_input":{"file_path":"git commit"}}' | bash "$HOOK" >/dev/null 2>&1
if [ $? -eq 0 ]; then pass=$((pass + 1)); else echo "FAIL Read tool payload should pass"; fail=1; fi
printf '{"tool_name":"Bash","tool_input":{"description":"git"}}' | bash "$HOOK" >/dev/null 2>&1
if [ $? -eq 2 ]; then pass=$((pass + 1)); else echo "FAIL unparseable payload mentioning git should block"; fail=1; fi

echo "hook tests: $pass passed, fail=$fail"
exit $fail
