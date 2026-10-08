#!/usr/bin/env bash
# PreToolUse hook: block every git invocation that can modify repository state.
# See docs/decisions/ADR-014-git-guard-hook.md.
#
# Contract (coding assistant PreToolUse hooks):
#   stdin  : JSON payload with tool_name and tool_input.command
#   exit 0 : allow
#   exit 2 : block; stderr is returned to the model as the reason
#
# Design: allowlist. Any git subcommand that is not known to be read-only is
# blocked. The scan looks for the token "git" in command position anywhere in
# the command string (segment start, after wrappers such as xargs, sudo, env,
# timeout, find -exec, or after VAR=value assignments), so "cd x && git commit",
# "sh -c 'git commit'", "ls | xargs git add", "git -C path commit" and
# "git -c k=v commit" are all caught, while prose such as
# "echo 'never run a git command'" is not. Pure bash: no jq, python or node.

set -u

MAX_DEPTH=4
QUOTED_MARK=$'\x01'   # prefix for tokens that came from a quoted span (data)
BOUNDARY=$'\x02'      # command separator marker

# ---------- JSON helpers (minimal, no external tools) ----------

# extract_json_string JSON KEY -> prints the unescaped string value of the
# first occurrence of "KEY": "...". Returns 1 if not found.
extract_json_string() {
  local json="$1" key="\"$2\"" rest val="" c i n esc=0
  rest="${json#*"$key"}"
  [ "$rest" = "$json" ] && return 1
  rest="${rest#"${rest%%[![:space:]]*}"}"
  [ "${rest:0:1}" = ":" ] || return 1
  rest="${rest:1}"
  rest="${rest#"${rest%%[![:space:]]*}"}"
  [ "${rest:0:1}" = '"' ] || return 1
  rest="${rest:1}"
  n=${#rest}
  for ((i = 0; i < n; i++)); do
    c="${rest:i:1}"
    if ((esc)); then
      case "$c" in
        n) val+=$'\n' ;;
        t) val+=$'\t' ;;
        r) val+=$'\r' ;;
        b | f) val+=" " ;;
        u) val+=" "; i=$((i + 4)) ;;
        *) val+="$c" ;;
      esac
      esc=0
    elif [ "$c" = '\' ]; then
      esc=1
    elif [ "$c" = '"' ]; then
      break
    else
      val+="$c"
    fi
  done
  printf '%s' "$val"
}

# ---------- git analysis ----------

BLOCK_REASON=""

block() {
  BLOCK_REASON="$1"
}

# has_any_flag "arg1 arg2 ..." flag1 flag2 ... -> 0 if any arg equals a flag
# (or starts with "flag=").
has_any_flag() {
  local args="$1"; shift
  local a f
  for a in $args; do
    for f in "$@"; do
      [ "$a" = "$f" ] && return 0
      case "$a" in "$f"=*) return 0 ;; esac
    done
  done
  return 1
}

count_positional() {
  local n=0 a
  for a in "$@"; do
    case "$a" in -*) ;; *) n=$((n + 1)) ;; esac
  done
  printf '%s' "$n"
}

first_positional() {
  local a
  for a in "$@"; do
    case "$a" in -*) ;; *) printf '%s' "$a"; return ;; esac
  done
  printf ''
}

# check_git_invocation SUB ARGS... -> allow (return 0) or block (return 1)
check_git_invocation() {
  local sub="$1"; shift
  local args="$*"
  local pos first
  pos=$(count_positional "$@")
  first=$(first_positional "$@")

  case "$sub" in
    "" | version | --version | help | --help | status | log | diff | show | blame | annotate \
    | shortlog | describe | rev-parse | rev-list | ls-files | ls-tree | ls-remote | cat-file \
    | grep | whatchanged | var | count-objects | check-ignore | check-attr | check-ref-format \
    | merge-base | diff-tree | diff-index | diff-files | for-each-ref | show-ref | fsck \
    | verify-commit | verify-tag | verify-pack | show-branch | range-diff | cherry | name-rev \
    | archive | format-patch | mailinfo | stripspace | get-tar-commit-id)
      return 0 ;;
    stash)
      case "$first" in list | show) return 0 ;; esac
      block "git stash ${first:-(push)} modifies the stash; only 'git stash list' and 'git stash show' are allowed" ;;
    branch)
      if has_any_flag "$args" -d -D -m -M -c -C -f -u -t --delete --move --copy --force \
          --set-upstream-to --unset-upstream --edit-description --track --no-track --create-reflog; then
        block "git branch with a write flag is not allowed"
      elif [ "$pos" -gt 0 ] && ! has_any_flag "$args" -l --list -a -r -v -vv --contains \
          --no-contains --merged --no-merged --points-at --show-current; then
        block "git branch <name> creates a branch; only listing forms are allowed"
      else
        return 0
      fi ;;
    tag)
      if has_any_flag "$args" -a -s -u -d -m -F -f -e --annotate --sign --local-user --delete \
          --message --file --force --edit --cleanup; then
        block "git tag with a write flag is not allowed"
      elif [ "$pos" -gt 0 ] && ! has_any_flag "$args" -l --list -n --contains --no-contains \
          --points-at --merged --no-merged --sort --format --column; then
        block "git tag <name> creates a tag; only listing forms are allowed"
      else
        return 0
      fi ;;
    config)
      if has_any_flag "$args" --unset --unset-all --add --replace-all --edit -e \
          --rename-section --remove-section --set; then
        block "git config write forms are not allowed"
      elif has_any_flag "$args" --get --get-all --get-regexp --list -l --show-origin --show-scope; then
        return 0
      elif [ "$pos" -le 1 ]; then
        return 0
      else
        block "git config <key> <value> writes configuration"
      fi ;;
    remote)
      case "$first" in "" | show | get-url) return 0 ;; esac
      block "git remote $first modifies remotes" ;;
    reflog)
      case "$first" in "" | show) return 0 ;; esac
      block "git reflog $first modifies the reflog" ;;
    worktree)
      case "$first" in list) return 0 ;; esac
      block "git worktree $first modifies worktrees" ;;
    submodule)
      case "$first" in "" | status | summary) return 0 ;; esac
      block "git submodule $first modifies submodules" ;;
    notes)
      case "$first" in "" | list | show) return 0 ;; esac
      block "git notes $first modifies notes" ;;
    bundle)
      case "$first" in verify | list-heads) return 0 ;; esac
      block "git bundle $first is not a read-only form" ;;
    symbolic-ref)
      if [ "$pos" -le 1 ] && ! has_any_flag "$args" -d --delete; then
        return 0
      fi
      block "git symbolic-ref write form is not allowed" ;;
    *)
      block "git $sub is not in the read-only allowlist" ;;
  esac
  return 1
}

# is_wrapper TOKEN -> 0 if the token is a command that runs its arguments
is_wrapper() {
  case "$1" in
    xargs | exec | command | builtin | time | nice | nohup | sudo | doas | env | watch | eval \
    | timeout | ionice | stdbuf | unbuffer | flock | setsid | find | busybox | parallel \
    | sh | bash | zsh | dash | ksh | fish | cmd | cmd.exe | powershell | powershell.exe | pwsh \
    | -exec | -execdir | -ok | -okdir)
      return 0 ;;
  esac
  return 1
}

# is_transparent TOKEN -> 0 for tokens that can precede a command without
# changing what runs (options, assignments, numbers, find placeholders)
is_transparent() {
  case "$1" in
    -*) return 0 ;;
    *=*) return 0 ;;
    '{}' | '+' | '\;' | ';') return 0 ;;
  esac
  case "$1" in
    '' | *[!0-9.]*) return 1 ;;
  esac
  return 0
}

# in_command_position TOKENS_ARRAY_NAME INDEX QUOTED_ARRAY_NAME -> 0 if the
# token at INDEX is where a shell would look for an executable.
in_command_position() {
  local -n _t="$1"
  local -n _q="$3"
  local i="$2" k tok all_transparent=1
  for ((k = i - 1; k >= 0; k--)); do
    tok="${_t[k]}"
    [ "$tok" = "$BOUNDARY" ] && break
    if [ "${_q[k]}" = "0" ] && is_wrapper "$tok"; then
      return 0
    fi
    is_transparent "$tok" || all_transparent=0
  done
  [ "$all_transparent" = "1" ]
}

# scan_tokens TOKEN... -> inspects every "git" token in command position
scan_tokens() {
  local -a toks=()
  local -a was_quoted=()
  local raw
  for raw in "$@"; do
    case "$raw" in
      "$QUOTED_MARK"*) toks+=("${raw#"$QUOTED_MARK"}"); was_quoted+=(1) ;;
      *) toks+=("$raw"); was_quoted+=(0) ;;
    esac
  done
  local n=${#toks[@]} i j b t sub
  local -a args
  for ((i = 0; i < n; i++)); do
    [ "${was_quoted[i]}" = "0" ] || continue
    t="${toks[i]}"
    [ "$t" = "$BOUNDARY" ] && continue
    b="${t##*/}"
    b="${b##*\\}"
    b="${b%.exe}"
    [ "$b" = "git" ] || continue
    in_command_position toks "$i" was_quoted || continue
    j=$((i + 1))
    sub=""
    while ((j < n)); do
      t="${toks[j]}"
      [ "$t" = "$BOUNDARY" ] && break
      case "$t" in
        -C | -c | --git-dir | --work-tree | --namespace | --super-prefix | --config-env)
          # Option with a separate value: skip the value unless a separator follows.
          j=$((j + 1))
          if ((j < n)) && [ "${toks[j]}" != "$BOUNDARY" ]; then j=$((j + 1)); fi ;;
        --exec-path | --git-dir=* | --work-tree=* | --namespace=* | --super-prefix=* \
        | --exec-path=* | --config-env=* | --no-pager | -p | -P | --paginate | --no-replace-objects \
        | --bare | --literal-pathspecs | --glob-pathspecs | --noglob-pathspecs | --icase-pathspecs \
        | --no-optional-locks | --no-lazy-fetch | --no-advice | --html-path | --man-path | --info-path)
          j=$((j + 1)) ;;
        --version | --help | -v | -h)
          sub="$t"; j=$((j + 1)); break ;;
        -*)
          # Unknown global option: assume it takes no value.
          j=$((j + 1)) ;;
        *)
          sub="$t"; j=$((j + 1)); break ;;
      esac
    done
    args=()
    while ((j < n)); do
      t="${toks[j]}"
      [ "$t" = "$BOUNDARY" ] && break
      args+=("$t")
      j=$((j + 1))
    done
    if ! check_git_invocation "$sub" "${args[@]+"${args[@]}"}"; then
      return 1
    fi
  done
  return 0
}

# check_line STRING DEPTH -> tokenizes a shell line (honoring quotes) and
# scans it; quoted tokens that contain whitespace are scanned recursively so
# that wrappers like sh -c "git commit" are caught.
check_line() {
  local line="$1" depth="$2"
  local -a toks=()
  local -a quoted=()
  local cur="" q="" c i n hadq=0
  n=${#line}
  for ((i = 0; i < n; i++)); do
    c="${line:i:1}"
    if [ -n "$q" ]; then
      if [ "$q" = '"' ] && [ "$c" = '\' ] && ((i + 1 < n)); then
        # Backslash escape inside double quotes: take the next char literally.
        i=$((i + 1)); cur+="${line:i:1}"
      elif [ "$c" = "$q" ]; then
        q=""
      else
        cur+="$c"
      fi
      continue
    fi
    case "$c" in
      '\')
        # Backslash escape outside quotes (for example "Program\ Files").
        if ((i + 1 < n)); then i=$((i + 1)); cur+="${line:i:1}"; fi ;;
      '"' | "'") q="$c"; hadq=1 ;;
      ' ' | $'\t')
        if [ -n "$cur" ] || ((hadq)); then
          if ((hadq)); then toks+=("${QUOTED_MARK}${cur}"); quoted+=("$cur"); else toks+=("$cur"); fi
        fi
        cur=""; hadq=0 ;;
      $'\n' | $'\r' | ';' | '|' | '&' | '(' | ')' | '`' | '<' | '>' | '{' | '}')
        if [ -n "$cur" ] || ((hadq)); then
          if ((hadq)); then toks+=("${QUOTED_MARK}${cur}"); quoted+=("$cur"); else toks+=("$cur"); fi
        fi
        toks+=("$BOUNDARY")
        cur=""; hadq=0 ;;
      *) cur+="$c" ;;
    esac
  done
  if [ -n "$cur" ] || ((hadq)); then
    if ((hadq)); then toks+=("${QUOTED_MARK}${cur}"); quoted+=("$cur"); else toks+=("$cur"); fi
  fi

  if [ ${#toks[@]} -gt 0 ]; then
    scan_tokens "${toks[@]}" || return 1
  fi

  if ((depth < MAX_DEPTH)); then
    local qt
    for qt in "${quoted[@]+"${quoted[@]}"}"; do
      case "$qt" in
        *[[:space:]]*) check_line "$qt" $((depth + 1)) || return 1 ;;
      esac
    done
  fi
  return 0
}

# ---------- main ----------

input=$(cat)

tool_name=$(extract_json_string "$input" tool_name 2>/dev/null || printf '')
case "$tool_name" in
  Bash | PowerShell | "") ;;
  *) exit 0 ;;
esac

command_str=$(extract_json_string "$input" command 2>/dev/null || printf '')
if [ -z "$command_str" ]; then
  # Could not parse the payload. Fail closed only if git is mentioned at all.
  case "$input" in
    *git*)
      echo "git guard: could not parse the tool payload but it mentions git; blocked (ADR-014)." >&2
      exit 2 ;;
    *) exit 0 ;;
  esac
fi

case "$command_str" in
  *git*) ;;
  *) exit 0 ;;
esac

if check_line "$command_str" 0; then
  exit 0
fi

{
  echo "git guard (ADR-014): blocked a git command that can modify repository state."
  echo "Reason: ${BLOCK_REASON:-not in the read-only allowlist}."
  echo "Allowed: status, log, diff, show, blame, stash list, stash show, branch/tag listing, rev-parse, ls-files and similar read-only forms."
  echo "The author runs state-modifying git commands by hand."
} >&2
exit 2
