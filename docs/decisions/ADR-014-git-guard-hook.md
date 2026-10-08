# ADR-014: A PreToolUse hook blocks state-modifying git commands

Status: Accepted
Date: 2026-10-07

## Context

The author commits by hand (hard constraint 1). A written rule is not enough: an agent under time pressure may run `git stash` or `git checkout` to "clean up". Permission deny rules match command prefixes and are a useful first layer, but they do not understand `git -C <path> commit`, `git -c key=value commit`, wrappers such as `sh -c "git commit"` or `xargs git add`, or the difference between `git stash` (writes) and `git stash list` (reads). The author works on Windows with Git Bash, and the coding assistant exposes both a Bash tool and a PowerShell tool.

## Decision

Three layers, all in `.claude/`:

1. **Permission deny rules** in `.claude/settings.json` for the common state-modifying subcommands, written for both the Bash and the PowerShell tools (the documentation notes that on Windows a scoped Bash deny rule without a matching PowerShell rule turns the PowerShell tool off; providing both keeps behavior explicit).
2. **A PreToolUse hook** with matcher `Bash|PowerShell` that runs `.claude/hooks/block-git-write.sh` with the tool payload on stdin. The script is pure bash (no jq, python or node), tokenizes the command honoring quotes and backslash escapes, splits on shell separators, and inspects every `git` token in command position (segment start, after wrappers such as `xargs`, `sudo`, `env`, `timeout`, `find -exec`, or after `VAR=value` assignments). It skips git's global options (`-C`, `-c`, `--git-dir`, `--no-pager` and similar) before reading the subcommand, and recurses into quoted strings so `sh -c "git commit"` is caught. It is an allowlist: only read-only subcommands pass (status, log, diff, show, blame, stash list, stash show, branch and tag listing forms, config read forms, rev-parse, ls-files and the like); everything else exits with code 2 and a reason on stderr, which the assistant reports back to the model. Prose containing the word git (for example documentation written through a heredoc) is not treated as an invocation unless it is in command position.
3. **Attribution disabled** in the same settings file (`attribution.commit` and `attribution.pr` set to empty strings, `sessionUrl` false), so that even a hand-made commit assisted by the tool carries no AI trailer.

## Verification (2026-10-07, coding assistant version 2.1.293, Windows 11, Git Bash)

- Hook syntax checked against the current hooks documentation: `hooks.PreToolUse[].matcher` with `hooks[].type = "command"`, `command`, `timeout`; stdin JSON with `tool_name` and `tool_input.command`; exit code 2 blocks and returns stderr. The documented placeholder form `"${CLAUDE_PROJECT_DIR}/..."` in double quotes is used. Project-scope `.claude/settings.json` may contain hooks and can be committed.
- The hook was exercised with a harness of 86 payloads covering the required pair (`git stash list` passes, `git stash` is blocked) plus `-C` and `-c` forms, chained commands, wrappers, quoted and escaped forms, PowerShell payloads and prose false positives. All 86 behaved as expected.
- The hook was also observed live in the bootstrap session: the coding assistant loaded the new settings and the hook blocked a shell command, confirming the wiring on this machine.
- Settings keys checked against the settings reference: `attribution` replaced the deprecated `includeCoAuthoredBy` and accepts empty strings to hide attribution; `permissions.deny` entries use the `Tool(prefix:*)` form and are evaluated per subcommand of compound commands.

## Test harness (added in Iteration 1 by the author's decision)

The payload cases live in the repository at `.claude/hooks/tests/run.sh` (pure bash, no dependencies). Run from the repository root:

```
bash .claude/hooks/tests/run.sh
```

It exits 0 when every case behaves as expected and prints each failing case otherwise. The suite holds 86 cases: the required pair (`git stash list` allowed, `git stash` blocked), read-only forms, state-modifying forms, `-C` and `-c` forms, chained commands, wrappers (`sh -c`, `xargs`, `env`, `timeout`, `find -exec`, Python `os.system`), quoting and escaping, PowerShell payloads, prose and heredoc false positives, and payload handling. Any change to the hook script must keep this suite green and add a case for the behavior changed.

## Consequences

- Agents cannot modify git state through the shell tools; they can still inspect. Any other write path (an MCP git tool, for example) must be denied explicitly if ever added.
- The hook fails closed: an unparseable payload that mentions git is blocked. False positives are acceptable; the fix is to use the file-writing tool for prose or to rephrase the command.
- The script is part of the repository and is reviewed like code; changes to it require updating the harness cases recorded in the iteration log.
- The deny list and the hook are redundant by design; the hook is the precise layer, the deny list the coarse one.
