import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../api/client";
import type { Action, CaseDetail, Context, Outcome } from "../api/types";
import { rememberResume } from "../checkpoints";
import {
  Breadcrumb,
  CaseHeader,
  CitationButtons,
  FindingCard,
  ModelCalls,
  PassagePanel,
  RetrievedList,
  ReviewBanner,
  useCaseDetail,
} from "../components/CaseParts";
import { ActionPill, BUTTON_STYLE, Card, ErrorNote, LlmPill, Spinner, ValidationBadge } from "../components/ui";
import { ACTION_LABEL } from "../format";
import { href, navigate } from "../router";

const EXECUTED = new Set(["approved", "returned", "escalated"]);

export function CaseDetailPage({ id, context }: { id: string; context: Context | null }) {
  const { detail, error, reload } = useCaseDetail(id);
  const [citation, setCitation] = useState<string | null>(null);

  if (error) return <ErrorNote>Could not load case {id}: {error}</ErrorNote>;
  if (!detail) return <Spinner label="Loading the case" />;

  const review = detail.case.status === "needs_human_review";
  // The LLM's text is shown only when it validated and the case is not in review (ADR-018).
  const showExplanation = !review && detail.output_status.explain === "valid" && detail.explanation;
  const showProposal = !review && detail.output_status.propose === "valid" && detail.proposal;
  const atMessage = detail.waiting_on.includes("message_checkpoint");
  const executed = EXECUTED.has(detail.case.status);

  return (
    <div className="space-y-4">
      <Breadcrumb caseId={id} />
      <CaseHeader detail={detail} />
      {review && <ReviewBanner reason={detail.review_reason} />}
      {atMessage && detail.chosen_action && (
        <Card>
          <p className="text-sm">
            {ACTION_LABEL[detail.chosen_action]} was chosen and the message waits for confirmation.{" "}
            <a href={href({ name: "message", id })} className="font-semibold text-primary underline">
              Confirm the message
            </a>
          </p>
        </Card>
      )}
      {executed && (
        <Card>
          <p className="text-sm">
            This case was executed.{" "}
            <a href={href({ name: "audit", id })} className="font-semibold text-primary underline">
              Open the audit trail
            </a>
          </p>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          {detail.case.findings.map((f, i) => (
            <FindingCard
              key={`${f.rule_id}-${f.day_date}-${i}`}
              finding={f}
              day={detail.finding_days?.find((d) => d.rule_id === f.rule_id && d.day_date === f.day_date)}
              units={detail.fact_units?.[f.rule_id]}
              title={detail.rule_titles?.[f.rule_id]}
            />
          ))}

          {showExplanation && detail.explanation && (
            <Card
              title="Explanation"
              labelledBy="explanation"
              aside={
                <>
                  <LlmPill />
                  <ValidationBadge status={detail.output_status.explain} />
                </>
              }
            >
              <p className="whitespace-pre-wrap text-sm leading-relaxed" data-testid="explanation-text">
                {detail.explanation.explanation}
              </p>
              <CitationButtons keys={detail.explanation.citation_keys} selected={citation} onSelect={setCitation} />
            </Card>
          )}

          {showProposal && detail.proposal && (
            <Card
              title="Proposal"
              labelledBy="proposal"
              aside={
                <>
                  <LlmPill />
                  <ValidationBadge status={detail.output_status.propose} />
                </>
              }
            >
              <p className="flex flex-wrap items-center gap-2 text-sm">
                Proposed action <ActionPill action={detail.proposal.proposed_action} />
                {detail.proposal.proposed_action === detail.case.policy_action && (
                  <span className="text-xs font-semibold text-approve-fg">equals policy</span>
                )}
              </p>
              <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Justification</h3>
              <p className="whitespace-pre-wrap text-sm leading-relaxed" data-testid="proposal-text">
                {detail.proposal.justification}
              </p>
              {detail.proposal.requested_correction && (
                <>
                  <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Requested correction</h3>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{detail.proposal.requested_correction}</p>
                </>
              )}
              <CitationButtons keys={detail.proposal.citation_keys} selected={citation} onSelect={setCitation} />
            </Card>
          )}

          {detail.waiting_on.includes("human_checkpoint") && (
            <DecisionCard detail={detail} context={context} onChanged={reload} />
          )}
          {detail.pending_retry && detail.decision && (
            <RetryCard detail={detail} context={context} onChanged={reload} />
          )}
        </div>

        <aside className="min-w-0 space-y-4" aria-label="Sources and model call">
          <PassagePanel citationKey={citation} />
          <RetrievedList chunks={detail.chunks} onSelect={setCitation} />
          <ModelCalls calls={detail.llm_calls} />
        </aside>
      </div>
    </div>
  );
}

const PROGRESS: Record<Action, string> = {
  approve: "Executing the approval",
  return: "Writing the return message",
  escalate: "Writing the escalation note",
};

function useElapsed(active: boolean) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!active) return;
    setElapsed(0);
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return elapsed;
}

/** Moves on after a resume; returns false when the case stays on this page. */
function afterOutcome(id: string, outcome: Outcome, step: "decide" | "message", onChanged: () => void): boolean {
  rememberResume(id, step, outcome);
  if (outcome.waiting_on.includes("message_checkpoint")) navigate({ name: "message", id });
  else if (EXECUTED.has(outcome.status)) navigate({ name: "audit", id });
  else {
    onChanged();
    return false;
  }
  return true;
}

function DecisionCard({
  detail,
  context,
  onChanged,
}: {
  detail: CaseDetail;
  context: Context | null;
  onChanged: () => void;
}) {
  const id = detail.case.id;
  const [pending, setPending] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  // One decision per click sequence: a repeated click never sends a second request.
  const sending = useRef(false);
  const elapsed = useElapsed(pending !== null);

  async function decide(action: Action) {
    if (!context || sending.current) return;
    sending.current = true;
    setPending(action);
    setError(null);
    try {
      const outcome = await api.decide(id, action, context.demo_approver);
      if (!afterOutcome(id, outcome, "decide", onChanged)) {
        sending.current = false;
        setPending(null);
      }
    } catch (e) {
      setError(errorText(e));
      sending.current = false;
      setPending(null);
    }
  }

  return (
    <Card title="Decision" labelledBy="decision">
      <p className="mb-3 text-sm text-muted">
        Your decision as <span className="font-mono">{context?.demo_approver ?? "..."}</span>. Approve
        executes now; Return and Escalate first draft a message for you to confirm.
      </p>
      <div className="flex flex-wrap gap-2">
        {(["approve", "return", "escalate"] as Action[]).map((a) => (
          <button
            key={a}
            type="button"
            className={BUTTON_STYLE[a]}
            disabled={pending !== null || !context}
            aria-busy={pending === a}
            onClick={() => decide(a)}
          >
            {ACTION_LABEL[a]}
          </button>
        ))}
      </div>
      {pending && (
        <div className="mt-3 rounded-lg bg-page px-3 py-2 text-sm" aria-live="polite">
          <Spinner label={`${PROGRESS[pending]}...`} />
          {pending !== "approve" && (
            <p className="mt-1 text-muted">
              One model call drafts the message for your choice; this takes seconds to tens of seconds. {elapsed} s
              elapsed.
            </p>
          )}
        </div>
      )}
      {error && (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
    </Card>
  );
}

/** A decision whose run stalled after the service accepted it: repeat exactly that decision. */
function RetryCard({
  detail,
  context,
  onChanged,
}: {
  detail: CaseDetail;
  context: Context | null;
  onChanged: () => void;
}) {
  const id = detail.case.id;
  const decision = detail.decision!;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);

  async function repeat() {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      const recipient =
        decision.recipient_role ??
        (decision.action === "approve" ? undefined : context?.recipients[decision.action]?.[0]);
      const message = recipient ? decision.message : undefined;
      const outcome =
        message && recipient
          ? await api.confirmMessage(id, decision.actor, message, recipient)
          : await api.decide(id, decision.action, decision.actor);
      afterOutcome(id, outcome, message ? "message" : "decide", onChanged);
    } catch (e) {
      setError(errorText(e));
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  return (
    <Card title="Decision pending completion" labelledBy="pending">
      <p className="mb-3 text-sm">
        The {ACTION_LABEL[decision.action]} of <span className="font-mono">{decision.actor}</span> was accepted but did
        not finish. Repeat the same decision to complete it; nothing is sent twice.
      </p>
      <button type="button" className={BUTTON_STYLE.primary} onClick={repeat} disabled={busy}>
        {busy ? <Spinner label="Repeating" /> : "Repeat the decision"}
      </button>
      {error && (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
    </Card>
  );
}
