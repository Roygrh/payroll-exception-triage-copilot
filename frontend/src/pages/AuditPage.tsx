import { useEffect, useState } from "react";
import { api, errorText } from "../api/client";
import type { Action, AuditEntry, CaseDetail } from "../api/types";
import { Breadcrumb, useCaseDetail } from "../components/CaseParts";
import { type Resume, readResumes } from "../checkpoints";
import { Card, ErrorNote, LlmPill, Mono, Spinner, ValidationBadge } from "../components/ui";
import { ACTION_LABEL, RECIPIENT_LABEL, STATUS_LABEL, auditTime, tokenTotal, usd } from "../format";
import { Stepper } from "./ConfirmMessagePage";

const KIND_STYLE: Record<string, string> = {
  suggestion: "bg-llm-bg text-llm-fg",
  validation: "bg-neutral-bg text-neutral-fg",
  review: "bg-escalate-bg text-escalate-fg",
  decision: "bg-return-bg text-return-fg",
  execution: "bg-approve-bg text-approve-fg",
};

const SOURCE_LABEL: Record<string, string> = {
  draft_confirmed: "draft confirmed unchanged",
  draft_edited: "draft edited by the approver",
  human_written: "written by the approver",
};

const SENT_LABEL: Record<string, string> = {
  draft_confirmed: "draft unchanged",
  draft_edited: "edited by the approver",
  human_written: "written by the approver",
};

type Payload = Record<string, unknown>;
const str = (v: unknown) => (v == null ? "" : String(v));
const actionLabel = (v: unknown) => ACTION_LABEL[v as Action] ?? str(v);

/** One-line title and detail of an audit entry, read from its payload. */
export function describe(entry: AuditEntry): { title: string; detail: string } {
  const p = entry.payload as Payload;
  switch (entry.entry_kind) {
    case "suggestion": {
      const kinds = (p.kinds as string[] | undefined) ?? [];
      const llm = (p.llm as Payload | undefined) ?? {};
      const tokens = tokenTotal(llm.input_tokens as number | null, llm.output_tokens as number | null);
      return {
        title: kinds.includes("draft") ? "Model drafted the message" : "Model wrote the explanation and proposal",
        detail: `${str(llm.model)}${tokens != null ? `, ${tokens} tokens` : ""}${
          llm.latency_ms != null ? `, ${str(llm.latency_ms)} ms` : ""
        }`,
      };
    }
    case "validation": {
      const problems = (p.problems as string[] | undefined) ?? [];
      return p.valid
        ? { title: "Validation passed", detail: "Citations, numbers, units, clock times and the policy action checked" }
        : { title: "Validation failed", detail: problems.join("; ") };
    }
    case "review":
      return {
        title: p.output === "draft" ? "Draft routed to human review" : "Case routed to human review",
        detail: str(p.reason),
      };
    case "decision":
      switch (p.stage) {
        case "action_chosen":
          return { title: `Action chosen: ${actionLabel(p.action)}`, detail: `Policy action ${actionLabel(p.policy_action)}` };
        case "message_cancelled":
          return { title: "Message cancelled", detail: `${actionLabel(p.action)} withdrawn; back to the decision` };
        case "duplicate_attempt":
          return { title: "Repeated request", detail: "The case was already executed; nothing was written" };
        default: {
          const parts = [`Policy action ${actionLabel(p.policy_action)}`];
          if (p.message_source) parts.push(`message ${SOURCE_LABEL[str(p.message_source)] ?? str(p.message_source)}`);
          if (p.recipient_role) parts.push(`to ${RECIPIENT_LABEL[p.recipient_role as "employee"] ?? str(p.recipient_role)}`);
          return { title: `Decision executed: ${actionLabel(p.action)}`, detail: parts.join(", ") };
        }
      }
    case "execution": {
      const parts = [`Case ${STATUS_LABEL[p.case_status as "approved"] ?? str(p.case_status)}`];
      parts.push(`timecard ${p.timecard_status ? str(p.timecard_status) : "unchanged"}`);
      if (p.premium_total_usd) parts.push(`premium ${usd(str(p.premium_total_usd))}`);
      return { title: `Executed: ${actionLabel(p.action)}`, detail: parts.join(", ") };
    }
    default:
      return { title: entry.entry_kind, detail: "" };
  }
}

/** The executed decision's message: the text that was sent next to the LLM's original draft. */
function ExecutedMessage({ payload }: { payload: Payload }) {
  if (payload.stage !== "executed" || !payload.message) return null;
  const draft = payload.original_draft ? str(payload.original_draft) : null;
  // Provenance comes from the backend's message_source, never inferred here.
  const source = str(payload.message_source);
  const validity =
    payload.original_draft_valid === true ? "valid" : payload.original_draft_valid === false ? "invalid" : "not_validated";
  return (
    <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="executed-message">
      <div className="rounded-lg border border-line p-3">
        <p className="text-xs font-semibold text-muted">Message sent ({SENT_LABEL[source] ?? (source || "source not recorded")})</p>
        <p className="mt-1 whitespace-pre-wrap text-sm" data-testid="sent-message">
          {str(payload.message)}
        </p>
      </div>
      <div className="rounded-lg border border-line p-3">
        <p className="flex flex-wrap items-center gap-2 text-xs font-semibold text-muted">
          Original draft
          {draft && <LlmPill />}
          {draft && <ValidationBadge status={validity} />}
        </p>
        <p className="mt-1 whitespace-pre-wrap text-sm" data-testid="original-draft">
          {draft ?? "None: no draft was produced for this round."}
        </p>
        {draft && validity !== "valid" && (
          <p className="mt-1 text-xs text-muted">
            Not shown to the approver: {validity === "invalid" ? "it did not pass validation" : "it was not validated"}.
          </p>
        )}
      </div>
    </div>
  );
}

function Checkpoints({ resumes }: { resumes: Resume[] }) {
  if (!resumes.length) return null;
  return (
    <Card title="Graph resumes" labelledBy="graph-resumes">
      <ol className="space-y-1 text-sm" data-testid="resumes">
        {resumes.map((r, i) => (
          <li key={i} className="break-all">
            <span className="font-semibold">{r.step === "decide" ? "Action chosen" : "Message step"}</span> checkpoint{" "}
            <Mono>{r.before ?? "none"}</Mono> to <Mono>{r.after ?? "none"}</Mono>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function successText(detail: CaseDetail): string {
  const name = detail.timecard?.employee_name ?? detail.case.timecard_id;
  switch (detail.case.status) {
    case "approved":
      return `Timecard approved for ${name}`;
    case "returned":
      return `Timecard returned to ${name}`;
    case "escalated":
      return `Timecard of ${name} escalated to a payroll specialist`;
    default:
      return "";
  }
}

export function AuditPage({ id }: { id: string }) {
  const { detail, error } = useCaseDetail(id);
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);

  useEffect(() => {
    api
      .audit(id)
      .then((a) => setEntries(a.entries))
      .catch((e) => setAuditError(errorText(e)));
  }, [id]);

  if (error) return <ErrorNote>Could not load case {id}: {error}</ErrorNote>;
  if (!detail) return <Spinner label="Loading the case" />;

  const success = successText(detail);
  const execution = detail.execution;

  return (
    <div className="space-y-4">
      <Breadcrumb caseId={id} current="Audit trail" />
      {success && (
        <div role="status" className="rounded-card border border-approve-fg/40 bg-approve-bg p-4 text-approve-fg">
          <p className="text-lg font-semibold">{success}</p>
          <p className="mt-1 text-sm">
            Case status <span className="font-semibold">{STATUS_LABEL[detail.case.status]}</span> · Timecard status{" "}
            <span className="font-semibold">{execution?.timecard_status ?? "unchanged"}</span>
            {execution?.premium_total_usd && (
              <>
                {" "}
                · Premium line <Mono>{usd(execution.premium_total_usd)}</Mono>
              </>
            )}
          </p>
        </div>
      )}
      {success && detail.case.status !== "approved" && (
        <Card>
          <Stepper current={3} />
        </Card>
      )}

      <Checkpoints resumes={readResumes(id)} />

      <Card title="Audit trail" labelledBy="audit-trail">
        {auditError && <ErrorNote>{auditError}</ErrorNote>}
        {!entries && !auditError && <Spinner label="Loading the audit trail" />}
        {entries && (
          <ol className="relative ml-2 border-l border-line">
            {entries.map((e) => {
              const { title, detail: text } = describe(e);
              return (
                <li key={e.id} className="mb-5 ml-5" data-testid="audit-entry" data-kind={e.entry_kind}>
                  <span aria-hidden="true" className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-primary" />
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <Mono>#{e.id}</Mono>
                    <Mono>{auditTime(e.created_at)}</Mono>
                    <span className={`rounded-full px-2 py-0.5 font-semibold ${KIND_STYLE[e.entry_kind] ?? KIND_STYLE.validation}`}>
                      {e.entry_kind}
                    </span>
                    <Mono>{e.actor}</Mono>
                  </div>
                  <p className="mt-1 text-sm font-semibold">{title}</p>
                  {text && <p className="text-sm text-muted break-words">{text}</p>}
                  {e.entry_kind === "decision" && <ExecutedMessage payload={e.payload} />}
                </li>
              );
            })}
          </ol>
        )}
      </Card>
    </div>
  );
}
