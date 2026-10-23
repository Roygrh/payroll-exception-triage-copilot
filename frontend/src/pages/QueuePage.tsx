import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText } from "../api/client";
import type { Action, CaseStatus, Context, Ingest, QueueItem } from "../api/types";
import { ActionPill, BUTTON_STYLE, Card, ErrorNote, Mono, Spinner, StatusPill } from "../components/ui";
import { ACTION_LABEL, STATUS_LABEL, usd } from "../format";
import { href, navigate } from "../router";

const ACTIONS: Action[] = ["approve", "return", "escalate"];
const OPEN_STATUSES: CaseStatus[] = ["awaiting_decision", "needs_human_review"];

function countBy<K extends string>(cases: QueueItem[], key: (c: QueueItem) => K, keys: K[]) {
  return keys.map((k) => [k, cases.filter((c) => key(c) === k).length] as const);
}

export function QueuePage({ context }: { context: Context | null }) {
  const [cases, setCases] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [lastIngest, setLastIngest] = useState<Ingest | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const running = useRef(false);

  const load = useCallback(async () => {
    try {
      const queue = await api.queue();
      // Rows keep the API's priority order (priority, then week ending, then id).
      setCases(queue.cases);
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!ingesting) return;
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [ingesting]);

  async function ingest() {
    if (!context || running.current) return;
    running.current = true;
    setIngesting(true);
    setElapsed(0);
    setIngestError(null);
    try {
      setLastIngest(await api.ingest(context.week_ending));
      await load();
    } catch (e) {
      setIngestError(errorText(e));
    } finally {
      running.current = false;
      setIngesting(false);
    }
  }

  const created = lastIngest?.results.filter((r) => r.case_id).length ?? 0;
  const clean = lastIngest?.results.filter((r) => r.status === "clean").length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Exception queue</h1>
          <p className="text-sm text-muted">
            Open cases in priority order. Clean timecards never appear here.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button type="button" className={BUTTON_STYLE.primary} onClick={ingest} disabled={ingesting || !context}>
            {ingesting ? <Spinner label="Ingesting" /> : "Ingest week"}
          </button>
        </div>
      </div>

      {ingesting && context && (
        <p role="status" aria-live="polite" className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
          Ingesting the week ending <Mono>{context.week_ending}</Mono>: the rule engine checks every
          timecard and the model explains each finding (one call per case). {elapsed} s elapsed.
        </p>
      )}
      {ingestError && <ErrorNote>Ingest failed: {ingestError}</ErrorNote>}
      {lastIngest && !ingesting && (
        <p aria-live="polite" className="text-sm text-muted">
          Last ingest: {lastIngest.results.length} timecards checked, {created} with a case, {clean} clean.
        </p>
      )}

      {cases && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Card title="By suggested action" labelledBy="by-action">
            <ul className="flex flex-wrap gap-4">
              {countBy(cases, (c) => c.policy_action, ACTIONS).map(([a, n]) => (
                <li key={a} className="flex items-center gap-2">
                  <ActionPill action={a} />
                  <span className="font-mono text-lg" aria-label={`${ACTION_LABEL[a]}: ${n}`}>
                    {n}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="By status" labelledBy="by-status">
            <ul className="flex flex-wrap gap-4">
              {countBy(cases, (c) => c.status, OPEN_STATUSES).map(([s, n]) => (
                <li key={s} className="flex items-center gap-2">
                  <StatusPill status={s} />
                  <span className="font-mono text-lg" aria-label={`${STATUS_LABEL[s]}: ${n}`}>
                    {n}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      {error && <ErrorNote>Could not load the queue: {error}</ErrorNote>}
      {!cases && !error && <Spinner label="Loading the queue" />}
      {cases && cases.length === 0 && (
        <Card>
          <p className="text-sm text-muted">No open cases. Press "Ingest week" to check the week's timecards.</p>
        </Card>
      )}
      {cases && cases.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-line bg-white">
          <table className="w-full min-w-[960px] text-left text-sm">
            <caption className="sr-only">Open exception cases in priority order</caption>
            <thead className="border-b border-line bg-neutral-bg text-xs uppercase tracking-wide text-neutral-fg">
              <tr>
                {["Priority", "Crew member", "Occupation", "Finding", "Day", "Suggested action", "Amount", "Status"].map(
                  (h) => (
                    <th key={h} scope="col" className="px-3 py-2 font-semibold">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <QueueRow key={c.id} item={c} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function QueueRow({ item }: { item: QueueItem }) {
  const open = () => navigate({ name: "case", id: item.id });
  return (
    <tr
      data-testid="queue-row"
      data-case-id={item.id}
      onClick={open}
      className="cursor-pointer border-b border-line last:border-0 hover:bg-page"
    >
      <td className="px-3 py-2 font-mono text-base">{item.priority_score}</td>
      <td className="px-3 py-2">
        <a
          href={href({ name: "case", id: item.id })}
          onClick={(e) => e.stopPropagation()}
          className="inline-flex min-h-11 flex-col justify-center font-semibold text-primary underline-offset-2 hover:underline"
        >
          {item.employee_name ?? item.timecard_id}
        </a>
        <div className="font-mono text-xs text-muted">
          {item.employee_id ?? ""} · {item.deal_memo_id}
        </div>
      </td>
      <td className="px-3 py-2">
        <div>{item.occupation_title ?? item.department ?? ""}</div>
        {item.occupation_code && <div className="font-mono text-xs text-muted">{item.occupation_code}</div>}
      </td>
      <td className="px-3 py-2">
        {item.findings.map((f, i) => (
          <div key={`${f.rule_id}-${f.day_date}-${i}`}>
            <div>{item.rule_titles?.[f.rule_id] ?? f.rule_id}</div>
            <div className="font-mono text-xs text-muted">
              {f.rule_id} · §{f.section}
            </div>
          </div>
        ))}
      </td>
      <td className="px-3 py-2 font-mono">
        {item.findings.map((f, i) => (
          <div key={i}>{f.day_date ?? "week"}</div>
        ))}
      </td>
      <td className="px-3 py-2">
        <ActionPill action={item.policy_action} />
      </td>
      <td className="px-3 py-2 font-mono">{usd(item.amount_usd)}</td>
      <td className="px-3 py-2">
        <StatusPill status={item.status} />
      </td>
    </tr>
  );
}
