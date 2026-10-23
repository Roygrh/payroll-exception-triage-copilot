import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "../api/client";
import type { CaseDetail, ChunkRef, Finding, FindingDay, LlmCall, Passage } from "../api/types";
import { EVENT_LABEL, factTiles, tokenTotal, usd } from "../format";
import { href } from "../router";
import { ActionPill, Card, ErrorNote, Mono, Spinner, StatusPill } from "./ui";

export function useCaseDetail(id: string) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setDetail(await api.caseDetail(id));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [id]);
  useEffect(() => {
    setDetail(null);
    void reload();
  }, [reload]);
  return { detail, error, reload };
}

export function Breadcrumb({ caseId, current }: { caseId: string; current?: string }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm">
      <ol className="flex flex-wrap items-center gap-1 text-muted">
        <li>
          <a href={href({ name: "queue" })} className="inline-flex min-h-11 items-center text-primary hover:underline">
            Exception queue
          </a>
        </li>
        <li aria-hidden="true">/</li>
        <li>
          {current ? (
            <a href={href({ name: "case", id: caseId })} className="inline-flex min-h-11 items-center font-mono text-primary hover:underline">
              {caseId}
            </a>
          ) : (
            <span aria-current="page" className="font-mono">
              {caseId}
            </span>
          )}
        </li>
        {current && (
          <>
            <li aria-hidden="true">/</li>
            <li aria-current="page">{current}</li>
          </>
        )}
      </ol>
    </nav>
  );
}

export function CaseHeader({ detail }: { detail: CaseDetail }) {
  const { case: c, timecard: tc } = detail;
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{tc?.employee_name ?? c.timecard_id}</h1>
          <p className="text-sm text-muted">
            {detail.occupation_title ?? tc?.department}
            {tc && (
              <>
                {" "}
                · <Mono>{tc.occupation_code}</Mono> · <Mono>{tc.employee_id}</Mono>
              </>
            )}{" "}
            · Deal memo <Mono>{c.deal_memo_id}</Mono> · Week ending <Mono>{c.week_ending}</Mono>
          </p>
        </div>
        <dl className="flex flex-wrap gap-4 text-sm">
          <div>
            <dt className="text-xs text-muted">Policy action</dt>
            <dd>
              <ActionPill action={c.policy_action} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Status</dt>
            <dd>
              <StatusPill status={c.status} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Priority</dt>
            <dd className="font-mono text-base">{c.priority_score}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Amount</dt>
            <dd className="font-mono text-base">{usd(c.amount_usd)}</dd>
          </div>
        </dl>
      </div>
    </Card>
  );
}

export function ReviewBanner({ reason }: { reason: string | null }) {
  return (
    <div role="alert" className="rounded-card border border-escalate-fg/40 bg-escalate-bg p-4 text-escalate-fg">
      <p className="font-semibold">Needs human review</p>
      <p className="mt-1 text-sm">
        This case needs human review, so the model's explanation and proposal are not shown. Decide
        from the facts below.
      </p>
      {reason && (
        <p className="mt-2 text-sm">
          Reason: <span className="font-mono break-words">{reason}</span>
        </p>
      )}
    </div>
  );
}

export function FindingCard({
  finding,
  day,
  units,
  title,
}: {
  finding: Finding;
  day: FindingDay | undefined;
  units: Record<string, string> | undefined;
  title: string | undefined;
}) {
  const tiles = factTiles(finding.rule_id, finding.facts, units);
  return (
    <Card
      title={title ?? finding.rule_id}
      aside={
        <>
          <Mono className="text-xs text-muted">
            {finding.rule_id} · §{finding.section}
          </Mono>
          <ActionPill action={finding.policy_action} />
        </>
      }
    >
      {day && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold">
            Timecard, {day.weekday} <Mono>{day.day_date}</Mono>
          </h3>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Timecard events">
            {day.events.map((e) => (
              <div key={e.field} className="rounded-lg border border-line px-3 py-2">
                <dt className="text-xs text-muted">{EVENT_LABEL[e.field] ?? e.field}</dt>
                <dd className="font-mono text-lg">{e.time ?? "missing"}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      <h3 className="mb-2 text-sm font-semibold">Engine facts</h3>
      <dl className="grid gap-2 sm:grid-cols-2" aria-label="Engine facts">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-lg bg-page px-3 py-2" data-testid="fact-tile">
            <dt className="text-xs text-muted">{t.label}</dt>
            <dd className="font-mono">{t.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

export function CitationButtons({
  keys,
  selected,
  onSelect,
}: {
  keys: string[];
  selected: string | null;
  onSelect: (key: string) => void;
}) {
  if (!keys.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted">Citations</span>
      {keys.map((k) => (
        <button
          key={k}
          type="button"
          onClick={() => onSelect(k)}
          aria-pressed={selected === k}
          className={`inline-flex min-h-11 items-center rounded-lg border px-3 font-mono text-sm ${
            selected === k ? "border-primary bg-primary text-white" : "border-primary/40 bg-white text-primary hover:border-primary"
          }`}
        >
          {k}
        </button>
      ))}
    </div>
  );
}

export function PassagePanel({ citationKey }: { citationKey: string | null }) {
  const [passage, setPassage] = useState<Passage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!citationKey) return;
    let live = true;
    setPassage(null);
    setError(null);
    api
      .passage(citationKey)
      .then((p) => live && setPassage(p))
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [citationKey]);
  return (
    <Card title="Cited passage" labelledBy="cited-passage">
      <div aria-live="polite" data-testid="passage-panel">
        {!citationKey && <p className="text-sm text-muted">Select a citation to read its passage.</p>}
        {citationKey && !passage && !error && <Spinner label="Loading the passage" />}
        {error && <ErrorNote>{error}</ErrorNote>}
        {passage && (
          <article>
            <p className="font-mono text-sm font-semibold text-primary">{passage.citation_key}</p>
            <h3 className="mt-1 font-semibold">{passage.heading}</h3>
            <p className="mt-1 text-xs text-muted">
              Version <Mono>{passage.version}</Mono>
            </p>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{passage.body}</p>
          </article>
        )}
      </div>
    </Card>
  );
}

export function RetrievedList({ chunks, onSelect }: { chunks: ChunkRef[]; onSelect: (key: string) => void }) {
  return (
    <Card title="Passages retrieved" labelledBy="passages-retrieved">
      <ol className="space-y-1">
        {chunks.map((c, i) => (
          <li key={c.citation_key}>
            <button
              type="button"
              onClick={() => onSelect(c.citation_key)}
              className="flex min-h-11 w-full items-center gap-2 rounded-lg px-2 py-1 text-left hover:bg-page"
            >
              <span className="w-5 shrink-0 font-mono text-xs text-muted">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-mono text-xs">{c.citation_key}</span>
                <span className="block truncate text-xs text-muted">{c.heading}</span>
              </span>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
                  c.sent_to_model ? "bg-llm-bg text-llm-fg" : "bg-neutral-bg text-neutral-fg"
                }`}
              >
                {c.sent_to_model ? "sent to model" : "ranked only"}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function ModelCalls({ calls }: { calls: LlmCall[] }) {
  return (
    <Card title="Model call" labelledBy="model-call">
      {calls.length === 0 && <p className="text-sm text-muted">No model call recorded.</p>}
      <div className="space-y-3">
        {calls.map((call, i) => (
          <dl key={i} className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm" data-testid="model-call">
            <dt className="text-muted">Step</dt>
            <dd className="font-mono">{call.node}</dd>
            <dt className="text-muted">Model</dt>
            <dd className="font-mono break-all">{call.model}</dd>
            <dt className="text-muted">Input tokens</dt>
            <dd className="font-mono">{call.input_tokens ?? "n/a"}</dd>
            <dt className="text-muted">Output tokens</dt>
            <dd className="font-mono">{call.output_tokens ?? "n/a"}</dd>
            <dt className="text-muted">Total tokens</dt>
            <dd className="font-mono">{tokenTotal(call.input_tokens, call.output_tokens) ?? "n/a"}</dd>
            <dt className="text-muted">Latency</dt>
            <dd className="font-mono">{call.latency_ms != null ? `${call.latency_ms} ms` : "n/a"}</dd>
          </dl>
        ))}
      </div>
    </Card>
  );
}
