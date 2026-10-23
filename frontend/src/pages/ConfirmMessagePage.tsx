import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../api/client";
import type { CaseDetail, Context, RecipientRole } from "../api/types";
import { rememberResume } from "../checkpoints";
import { Breadcrumb, CaseHeader, useCaseDetail } from "../components/CaseParts";
import { BUTTON_STYLE, Card, ErrorNote, LlmPill, Mono, Spinner, ValidationBadge } from "../components/ui";
import { ACTION_LABEL, RECIPIENT_LABEL, tokenTotal } from "../format";
import { href, navigate } from "../router";

const STEPS = ["Action chosen", "Confirm message", "Execute"];

export function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm" aria-label="Decision steps">
      {STEPS.map((label, i) => {
        const state = i < current ? "done" : i === current ? "current" : "next";
        return (
          <li key={label} className="flex items-center gap-2" aria-current={state === "current" ? "step" : undefined}>
            <span
              className={`inline-flex h-7 w-7 items-center justify-center rounded-full font-mono text-xs font-semibold ${
                state === "done"
                  ? "bg-approve-bg text-approve-fg"
                  : state === "current"
                    ? "bg-primary text-white"
                    : "bg-neutral-bg text-neutral-fg"
              }`}
            >
              {state === "done" ? "✓" : i + 1}
            </span>
            <span className={state === "current" ? "font-semibold" : "text-muted"}>
              {label}
              {state === "done" && <span className="sr-only"> (done)</span>}
            </span>
            {i < STEPS.length - 1 && <span aria-hidden="true" className="mx-1 h-px w-6 bg-line" />}
          </li>
        );
      })}
    </ol>
  );
}

export function ConfirmMessagePage({ id, context }: { id: string; context: Context | null }) {
  const { detail, error } = useCaseDetail(id);
  if (error) return <ErrorNote>Could not load case {id}: {error}</ErrorNote>;
  if (!detail || !context) return <Spinner label="Loading the message" />;
  const action = detail.chosen_action;
  if (!detail.waiting_on.includes("message_checkpoint") || !action || action === "approve") {
    return (
      <div className="space-y-4">
        <Breadcrumb caseId={id} current="Confirm the message" />
        <Card>
          <p className="text-sm">
            This case is not waiting for a message.{" "}
            <a href={href({ name: "case", id })} className="font-semibold text-primary underline">
              Back to the case
            </a>
          </p>
        </Card>
      </div>
    );
  }
  return <MessageForm detail={detail} context={context} action={action} />;
}

function MessageForm({
  detail,
  context,
  action,
}: {
  detail: CaseDetail;
  context: Context;
  action: "return" | "escalate";
}) {
  const id = detail.case.id;
  // A validated draft is shown even when the analysis put the case in review (ADR-018: the
  // message step shows the validated draft or none); a draft that did not validate never is.
  const draftValid = detail.output_status.draft === "valid" && detail.draft !== null;
  const draft = draftValid ? detail.draft : null;
  const allowed = context.recipients[action];
  const suggested = draft && allowed.includes(draft.recipient_role) ? draft.recipient_role : allowed[0];
  const [recipient, setRecipient] = useState<RecipientRole>(suggested ?? allowed[0]!);
  // A draft that needs review is never shown: the approver writes the message (no template).
  const [body, setBody] = useState(draft?.body ?? "");
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!draftValid) textarea.current?.focus();
  }, [draftValid]);

  // With no draft in this round, the latest draft call belongs to a cancelled round.
  const draftCall =
    detail.output_status.draft === "missing" ? undefined : [...detail.llm_calls].reverse().find((c) => c.node === "draft");
  const draftTokens = draftCall ? tokenTotal(draftCall.input_tokens, draftCall.output_tokens) : null;
  const name = detail.timecard?.employee_name ?? "the crew member";
  const actor = detail.decision?.actor ?? context.demo_approver;

  async function run(kind: "confirm" | "cancel") {
    if (sending.current) return;
    sending.current = true;
    setBusy(kind);
    setError(null);
    try {
      if (kind === "cancel") {
        rememberResume(id, "message", await api.cancelMessage(id, context.demo_approver));
        navigate({ name: "case", id });
      } else {
        const outcome = await api.confirmMessage(id, actor, body.trim(), recipient);
        rememberResume(id, "message", outcome);
        navigate({ name: outcome.waiting_on.length ? "case" : "audit", id });
      }
    } catch (e) {
      setError(errorText(e));
      sending.current = false;
      setBusy(null);
    }
  }

  const tooLong = body.length > context.max_message_length;
  const canConfirm = body.trim().length > 0 && !tooLong && busy === null;

  return (
    <div className="space-y-4">
      <Breadcrumb caseId={id} current="Confirm the message" />
      <CaseHeader detail={detail} />
      <Card>
        <Stepper current={1} />
      </Card>
      <Card
        title={action === "return" ? "Confirm the return message" : "Confirm the escalation note"}
        labelledBy="confirm-message"
        aside={
          <>
            {draftValid && <LlmPill />}
            <ValidationBadge status={detail.output_status.draft} />
            {draftTokens != null && (
              <span className="text-xs text-muted">
                Draft tokens <Mono>{draftTokens}</Mono>
              </span>
            )}
          </>
        }
      >
        {!draftValid && (
          <div role="alert" className="mb-4 rounded-lg border border-escalate-fg/40 bg-escalate-bg p-3 text-sm text-escalate-fg">
            <p className="font-semibold">The draft needs human review</p>
            <p className="mt-1">No draft is shown. Write the message yourself, or cancel and choose another action.</p>
            {detail.review_reason && (
              <p className="mt-1">
                Reason: <span className="font-mono break-words">{detail.review_reason}</span>
              </p>
            )}
          </div>
        )}
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canConfirm) void run("confirm");
          }}
        >
          <div>
            {allowed.length > 1 ? (
              <label htmlFor="recipient" className="block text-sm font-semibold">
                Recipient
              </label>
            ) : (
              <p className="text-sm font-semibold">Recipient</p>
            )}
            {allowed.length > 1 ? (
              <select
                id="recipient"
                value={recipient}
                onChange={(e) => setRecipient(e.target.value as RecipientRole)}
                className="mt-1 min-h-11 w-full rounded-lg border border-line bg-white px-3 sm:w-80"
              >
                {allowed.map((r) => (
                  <option key={r} value={r}>
                    {r === "employee" ? `${RECIPIENT_LABEL[r]}: ${name}` : RECIPIENT_LABEL[r]}
                  </option>
                ))}
              </select>
            ) : (
              <p className="mt-1 text-sm">
                {RECIPIENT_LABEL[recipient]}
              </p>
            )}
            {draft && draft.recipient_role !== recipient && (
              <p className="mt-1 text-xs text-muted">The draft suggested {RECIPIENT_LABEL[draft.recipient_role]}.</p>
            )}
          </div>
          {draft && (
            <div>
              <p className="text-sm font-semibold">Subject (from the draft)</p>
              <p className="mt-1 rounded-lg border border-line bg-page px-3 py-2 text-sm">{draft.subject}</p>
              <p className="mt-1 text-xs text-muted">
                The subject is recorded with the draft; only the body is sent with the {ACTION_LABEL[action].toLowerCase()} today.
              </p>
            </div>
          )}
          <div>
            <label htmlFor="message-body" className="block text-sm font-semibold">
              Message
            </label>
            <textarea
              id="message-body"
              ref={textarea}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={10}
              aria-invalid={tooLong}
              aria-describedby="message-count"
              placeholder={draftValid ? undefined : "Write the message to send."}
              className="mt-1 w-full rounded-lg border border-line bg-white p-3 text-sm leading-relaxed"
            />
            <p id="message-count" className={`mt-1 text-xs ${tooLong ? "text-escalate-fg" : "text-muted"}`}>
              <Mono>
                {body.length} / {context.max_message_length}
              </Mono>{" "}
              characters
              {draftValid && body !== draft?.body && " · edited by you"}
            </p>
          </div>
          {error && <ErrorNote>{error}</ErrorNote>}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={BUTTON_STYLE.neutral} disabled={busy !== null} onClick={() => run("cancel")}>
              {busy === "cancel" ? <Spinner label="Cancelling" /> : "Cancel"}
            </button>
            <button type="submit" className={BUTTON_STYLE.primary} disabled={!canConfirm}>
              {busy === "confirm" ? (
                <Spinner label="Executing" />
              ) : action === "return" ? (
                "Confirm and return"
              ) : (
                "Confirm and escalate"
              )}
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
