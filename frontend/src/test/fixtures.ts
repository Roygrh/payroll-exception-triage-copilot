import type { AuditEntry, CaseDetail, Context, Passage, QueueItem } from "../api/types";

// Shapes captured from the API with the in-memory runtime and the fake adapter
// (backend/tests/test_api.py); the demo week's two MEAL_PERIOD cases (SC-05 and SC-03).

export const CONTEXT: Context = {
  week_ending: "2026-03-14",
  as_of_date: "2026-03-16",
  payroll_run_date: "2026-03-17",
  agreement: { code: "CGMA", name: "Crew Guild Master Agreement", version: "2026.1" },
  demo_approver: "sam.verhoeven",
  recipients: { return: ["employee", "department_head"], escalate: ["payroll_specialist"] },
  max_message_length: 4000,
};

const SHORT_MEAL_FACTS = {
  hours_to_meal: 5.0,
  meal_minutes: 24,
  minutes_late: 0,
  hours_late: 0.0,
  increments: 0,
  penalty_usd: "0.00",
  is_late: false,
  is_short: true,
  deadline_hours: 6.0,
  min_duration_minutes: 30,
  increment_minutes: 30,
};

export const RETURN_CASE: QueueItem = {
  id: "CASE-EMP-1002-20260314",
  timecard_id: "TC-EMP-1002-20260314",
  deal_memo_id: "DM-02",
  week_ending: "2026-03-14",
  findings: [
    {
      rule_id: "MEAL_PERIOD",
      section: "8.2",
      citation_keys: ["CGMA-2026.1-8.2", "CGMA-2026.1-8.3", "CGMA-2026.1-SCH-B"],
      situation: "incomplete_or_implausible",
      policy_action: "return",
      day_date: "2026-03-11",
      amount_usd: "0.00",
      facts: SHORT_MEAL_FACTS,
      facts_schema_version: 2,
    },
  ],
  policy_action: "return",
  amount_usd: "0.00",
  priority_score: 8,
  status: "awaiting_decision",
  review_reason: null,
  employee_name: "Jordan Okafor",
  department: "Camera",
  rule_ids: ["MEAL_PERIOD"],
  employee_id: "EMP-1002",
  occupation_code: "4125",
  occupation_title: "CAMERA ASSISTANT",
  rule_titles: { MEAL_PERIOD: "Timing and duration of the first meal period" },
};

export const APPROVE_CASE: QueueItem = {
  ...RETURN_CASE,
  id: "CASE-EMP-1001-20260314",
  timecard_id: "TC-EMP-1001-20260314",
  deal_memo_id: "DM-01",
  findings: [
    {
      ...RETURN_CASE.findings[0]!,
      situation: "premium_complete_plausible",
      policy_action: "approve",
      day_date: "2026-03-10",
      amount_usd: "8.25",
      facts: { ...SHORT_MEAL_FACTS, hours_to_meal: 6.5, meal_minutes: 30, minutes_late: 30, hours_late: 0.5, increments: 1, penalty_usd: "8.25", is_late: true, is_short: false },
    },
  ],
  policy_action: "approve",
  amount_usd: "8.25",
  priority_score: 6,
  employee_name: "Avery Lindqvist",
  employee_id: "EMP-1001",
  occupation_code: "4110",
  occupation_title: "CAMERA OPERATOR",
};

const CHUNKS = [
  ["CGMA-2026.1-8.2", "8.2 Timing and duration of the first meal period", true],
  ["CGMA-2026.1-1.2", "1.2 Defined terms", false],
  ["CGMA-2026.1-SCH-B", "Schedule B. Meal penalty table", true],
  ["CGMA-2026.1-8.3", "8.3 Meal penalty", true],
  ["DM-02", "Deal memo DM-02: Jordan Okafor, CAMERA ASSISTANT", true],
] as const;

export function caseDetail(overrides: Partial<CaseDetail> = {}, item: QueueItem = RETURN_CASE): CaseDetail {
  return {
    case: item,
    timecard: {
      id: item.timecard_id,
      employee_id: item.employee_id ?? "",
      employee_name: item.employee_name ?? "",
      deal_memo_id: item.deal_memo_id,
      occupation_code: item.occupation_code ?? "",
      department: "Camera",
      week_ending: item.week_ending,
      status: "Ready for approver 1",
    },
    explanation: {
      explanation:
        "The meal on Wednesday lasted 24 minutes, below the 30-minute minimum [CGMA-2026.1-8.2]; the deal memo gives the crew member's terms [DM-02].",
      citation_keys: ["CGMA-2026.1-8.2", "DM-02"],
    },
    proposal: {
      proposed_action: item.policy_action,
      justification: "A meal under the minimum is a recording problem [CGMA-2026.1-8.2].",
      requested_correction: "Confirm the meal in time or correct it to the actual time.",
      citation_keys: ["CGMA-2026.1-8.2"],
    },
    draft: null,
    output_status: { explain: "valid", propose: "valid", draft: "missing" },
    review_reason: null,
    chunks: CHUNKS.map(([citation_key, heading, sent_to_model]) => ({
      citation_key,
      heading,
      sent_to_model,
      source_type: citation_key.startsWith("DM-") ? "deal_memo" : "agreement",
      version: citation_key.startsWith("DM-") ? citation_key : "2026.1",
    })),
    chosen_action: null,
    decision: null,
    execution: null,
    llm_calls: [
      { node: "explain_propose", provider: "groq", model: "openai/gpt-oss-20b", input_tokens: 3410, output_tokens: 590, latency_ms: 2140 },
    ],
    pending_retry: false,
    waiting_on: ["human_checkpoint"],
    finding_days: [
      {
        rule_id: "MEAL_PERIOD",
        day_date: item.findings[0]!.day_date!,
        weekday: "Wed",
        events: [
          { field: "call", time: "07:00" },
          { field: "meal_out", time: "12:00" },
          { field: "meal_in", time: "12:24" },
          { field: "wrap", time: "15:30" },
        ],
      },
    ],
    fact_units: {
      MEAL_PERIOD: {
        hours_to_meal: "hours",
        meal_minutes: "minutes",
        minutes_late: "minutes",
        hours_late: "hours",
        deadline_hours: "hours",
        min_duration_minutes: "minutes",
        increment_minutes: "minutes",
      },
    },
    rule_titles: { MEAL_PERIOD: "Timing and duration of the first meal period" },
    occupation_title: item.occupation_title ?? null,
    ...overrides,
  };
}

export const DRAFT = {
  for_action: "return" as const,
  recipient_role: "employee" as const,
  subject: "Timecard returned: meal on 2026-03-11",
  body: "Your meal on Wednesday lasted 24 minutes, under the 30-minute minimum [CGMA-2026.1-8.2]. Please confirm or correct the meal in time.",
  citation_keys: ["CGMA-2026.1-8.2"],
};

export function atMessage(overrides: Partial<CaseDetail> = {}): CaseDetail {
  return caseDetail({
    chosen_action: "return",
    decision: { action: "return", actor: "sam.verhoeven" },
    draft: DRAFT,
    output_status: { explain: "valid", propose: "valid", draft: "valid" },
    waiting_on: ["message_checkpoint"],
    llm_calls: [
      ...caseDetail().llm_calls,
      { node: "draft", provider: "groq", model: "openai/gpt-oss-20b", input_tokens: 600, output_tokens: 140, latency_ms: 1800 },
    ],
    ...overrides,
  });
}

export const PASSAGE_8_2: Passage = {
  source_type: "agreement",
  citation_key: "CGMA-2026.1-8.2",
  version: "2026.1",
  section: "8.2",
  heading: "8.2 Timing and duration of the first meal period",
  body: "The first Meal Period of a Workday shall begin not later than 6.0 hours after Call. A Meal Period shall last not less than 30 minutes.",
};

export const RETURNED_DETAIL: CaseDetail = caseDetail({
  case: { ...RETURN_CASE, status: "returned" },
  waiting_on: [],
  execution: {
    action: "return",
    actor: "sam.verhoeven",
    case_status: "returned",
    timecard_status: "Rejected",
    message_source: "draft_edited",
  },
});

const at = "2026-10-22T04:36:03.291513+00:00";
export const RETURN_AUDIT: AuditEntry[] = [
  { id: 3, case_id: RETURN_CASE.id, entry_kind: "suggestion", actor: "llm:groq/openai/gpt-oss-20b", created_at: at, payload: { kinds: ["explain", "propose"], llm: { model: "openai/gpt-oss-20b", input_tokens: 3410, output_tokens: 590, latency_ms: 2140 } } },
  { id: 4, case_id: RETURN_CASE.id, entry_kind: "validation", actor: "system", created_at: at, payload: { valid: true, problems: [] } },
  { id: 5, case_id: RETURN_CASE.id, entry_kind: "decision", actor: "sam.verhoeven", created_at: at, payload: { stage: "action_chosen", action: "return", policy_action: "return" } },
  { id: 6, case_id: RETURN_CASE.id, entry_kind: "suggestion", actor: "llm:groq/openai/gpt-oss-20b", created_at: at, payload: { kinds: ["draft"], llm: { model: "openai/gpt-oss-20b", input_tokens: 600, output_tokens: 140, latency_ms: 1800 } } },
  { id: 7, case_id: RETURN_CASE.id, entry_kind: "decision", actor: "sam.verhoeven", created_at: at, payload: { stage: "executed", action: "return", policy_action: "return", message: `${DRAFT.body} Thank you.`, original_draft: DRAFT.body, original_draft_valid: true, message_edited: true, message_source: "draft_edited", recipient_role: "employee" } },
  { id: 8, case_id: RETURN_CASE.id, entry_kind: "execution", actor: "sam.verhoeven", created_at: at, payload: { action: "return", case_status: "returned", timecard_status: "Rejected" } },
];
