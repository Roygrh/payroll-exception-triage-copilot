// Response shapes of the API in backend/src/payroll_triage/api/app.py (Iteration 4).
// Only the fields the UI reads are typed; the API may return more.

export type Action = "approve" | "return" | "escalate";
export type CaseStatus =
  | "detected"
  | "awaiting_decision"
  | "needs_human_review"
  | "approved"
  | "returned"
  | "escalated";
export type OutputStatus = "valid" | "invalid" | "not_validated" | "missing";
export type RecipientRole = "employee" | "department_head" | "payroll_specialist";
export type WaitingNode = "human_checkpoint" | "message_checkpoint" | string;

export interface Context {
  week_ending: string;
  as_of_date: string;
  payroll_run_date: string;
  agreement: { code: string; name: string; version: string };
  demo_approver: string;
  recipients: Record<"return" | "escalate", RecipientRole[]>;
  max_message_length: number;
}

export type FactValue = number | string | boolean;

export interface Finding {
  rule_id: string;
  section: string;
  citation_keys: string[];
  situation: string;
  policy_action: Action;
  day_date: string | null;
  amount_usd: string;
  facts: Record<string, FactValue>;
  facts_schema_version: number;
}

export interface CaseRecord {
  id: string;
  timecard_id: string;
  deal_memo_id: string;
  week_ending: string;
  findings: Finding[];
  policy_action: Action;
  amount_usd: string;
  priority_score: number;
  status: CaseStatus;
  review_reason: string | null;
}

export interface QueueItem extends CaseRecord {
  employee_name: string | null;
  department: string | null;
  rule_ids: string[];
  employee_id?: string | null;
  occupation_code?: string | null;
  occupation_title?: string | null;
  rule_titles?: Record<string, string>;
}

export interface Queue {
  count: number;
  cases: QueueItem[];
}

export interface IngestResult {
  timecard_id: string;
  case_id: string | null;
  status: string;
}

export interface Ingest {
  week_ending: string;
  results: IngestResult[];
}

export interface Explanation {
  explanation: string;
  citation_keys: string[];
}

export interface Proposal {
  proposed_action: Action;
  justification: string;
  requested_correction: string;
  citation_keys: string[];
}

export interface Draft {
  for_action: Action;
  recipient_role: RecipientRole;
  subject: string;
  body: string;
  citation_keys: string[];
}

export interface LlmCall {
  node: string;
  provider: string;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  attempts?: number;
}

export interface ChunkRef {
  citation_key: string;
  source_type: string;
  version: string;
  heading: string;
  sent_to_model: boolean;
}

export interface Execution {
  action: Action;
  actor: string;
  case_status: CaseStatus;
  timecard_status: string | null;
  premium_total_usd?: string;
  message_source?: string;
  already_executed?: boolean;
}

export interface FindingDay {
  rule_id: string;
  day_date: string;
  weekday: string;
  events: { field: string; time: string | null }[];
}

export interface Timecard {
  id: string;
  employee_id: string;
  employee_name: string;
  deal_memo_id: string;
  occupation_code: string;
  department: string;
  week_ending: string;
  status: string;
}

export interface CaseDetail {
  case: CaseRecord;
  timecard: Timecard | null;
  explanation: Explanation | null;
  proposal: Proposal | null;
  draft: Draft | null;
  output_status: Record<"explain" | "propose" | "draft", OutputStatus>;
  review_reason: string | null;
  chunks: ChunkRef[];
  chosen_action: Action | null;
  decision: { action: Action; actor: string; message?: string; recipient_role?: RecipientRole } | null;
  execution: Execution | null;
  llm_calls: LlmCall[];
  pending_retry: boolean;
  waiting_on: WaitingNode[];
  finding_days?: FindingDay[];
  fact_units?: Record<string, Record<string, string>>;
  rule_titles?: Record<string, string>;
  occupation_title?: string | null;
}

export interface Passage {
  source_type: string;
  citation_key: string;
  version: string;
  section: string;
  heading: string;
  body: string;
}

export interface Outcome {
  case_id: string;
  status: CaseStatus;
  waiting_on: WaitingNode[];
  execution: Execution | null;
  chosen_action?: Action;
  draft?: Draft | null;
  draft_status?: OutputStatus;
  review_reason?: string | null;
  checkpoint_id_before?: string | null;
  checkpoint_id_after?: string | null;
}

export interface AuditEntry {
  id: number;
  case_id: string;
  entry_kind: string;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Audit {
  case_id: string;
  entries: AuditEntry[];
}
