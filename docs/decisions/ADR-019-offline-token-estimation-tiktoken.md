# ADR-019: Offline token estimation with tiktoken (o200k_base)

Status: Accepted (author instruction of 2026-10-10: measure input tokens offline with a tokenizer suitable for the default model, no provider call)
Date: 2026-10-10

## Context

Iteration 2b (P1.I2b.S4, ADR-018) must cut the tokens per MEAL_PERIOD case to at most 5,000 and record the measurement before and after. The default provider's free tier allows 8,000 tokens per minute and an unreported number per day (ADR-016), and the author's budget is reserved for the acceptance run (P1.I2b.S6). The measurement during development must therefore be offline: the real prompts are built and their tokens counted locally, with no provider call.

The default model, `openai/gpt-oss-20b`, uses the `o200k_harmony` encoding, which is the public `o200k_base` byte-pair encoding plus the special tokens of the harmony chat format. `tiktoken` (MIT license, maintained by the model's publisher) ships `o200k_base`. No package already in the lockfile provides it: `tokenizers` (installed with fastembed) would need the model's tokenizer file downloaded from a model hub.

## Decision

- Add `tiktoken` as a runtime dependency of the backend, used only by `payroll_triage/tokens.py` and the `ptc showcase --dry-run` command. The graph, the adapter and the validators never call it.
- Count with `o200k_base`. The estimate for one call is: tokens of the system prompt, plus tokens of the user prompt, plus tokens of the response JSON schema (the provider injects the strict schema into the prompt), plus a fixed per-call overhead for the chat format (role headers and the provider's default system preamble). The overhead constant is calibrated against the first real run (`iteration-002.md`: about 3,100 to 3,500 input tokens per call) and documented in the code.
- The estimate is an estimate: the real counts reported by the provider in each response (`usage.prompt_tokens`, already recorded by the adapter per call) remain the measurement of record, recorded by the author in P1.I2b.S6.
- `tiktoken` downloads the encoding file (about 3.6 MB) from the publisher's public storage on first use and caches it, as fastembed does for the embedding model (ADR-017). No key, no account, no data sent.

## Consequences

- Prompt changes can be measured offline in CI or on any machine with no key; the evaluation harness of Iteration 3 can report estimated tokens per run before spending budget.
- Output tokens (including the model's reasoning tokens) cannot be estimated offline; the dry run prints the output cap (`max_output_tokens`) instead, and the real total per case comes from the provider.
- A provider or model change may need a different encoding; the module names the encoding in one constant.
