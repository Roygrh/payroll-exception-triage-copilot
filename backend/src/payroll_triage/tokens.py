"""Offline input-token estimate for one LLM request (ADR-019). No provider call.

Used only by `ptc showcase --dry-run` and the token tests; the graph never calls it. The
provider's own `usage.prompt_tokens` (recorded by the adapter per call) is the measurement of
record; this module estimates it so prompt changes can be measured without spending budget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from payroll_triage.llm.v1 import LLMRequest

# gpt-oss models use o200k_harmony: o200k_base plus the harmony special tokens.
ENCODING = "o200k_base"

# Chat-format overhead per call: the provider's default system preamble (model identity,
# dates, reasoning level, valid channels), the role headers and the response-format heading
# around the schema. Calibration: the Iteration 2 prompts for SC-03 count 3,007, 3,195 and
# 3,171 tokens (system + user + schema) for explain, propose and draft; the first real run
# reported about 3,100 to 3,500 input tokens per call (iteration-002.md). An overhead of 80
# puts the three estimates at 3,087, 3,275 and 3,251, inside the measured range; the author's
# acceptance run (P1.I2b.S6) records the provider counts that confirm or correct it.
CHAT_OVERHEAD_TOKENS = 80


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    return tiktoken.get_encoding(ENCODING)


def count(text: str) -> int:
    return len(_encoding().encode(text))


@dataclass(frozen=True)
class RequestEstimate:
    system: int
    messages: int
    schema: int
    overhead: int
    max_output_tokens: int

    @property
    def input_tokens(self) -> int:
        return self.system + self.messages + self.schema + self.overhead

    def to_dict(self) -> dict[str, int]:
        return {
            "system": self.system,
            "messages": self.messages,
            "schema": self.schema,
            "overhead": self.overhead,
            "input_tokens": self.input_tokens,
            "max_output_tokens": self.max_output_tokens,
        }


def estimate_request(request: LLMRequest) -> RequestEstimate:
    schema = 0
    if request.response_schema is not None:
        schema = count(json.dumps(request.response_schema, separators=(",", ":")))
    return RequestEstimate(
        system=count(request.system),
        messages=sum(count(m.content) for m in request.messages),
        schema=schema,
        overhead=CHAT_OVERHEAD_TOKENS,
        max_output_tokens=request.max_output_tokens,
    )
