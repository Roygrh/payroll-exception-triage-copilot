import type { ReactNode } from "react";
import type { Action, CaseStatus, OutputStatus } from "../api/types";
import { ACTION_LABEL, OUTPUT_STATUS_LABEL, STATUS_LABEL } from "../format";

const PILL = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap";

const ACTION_STYLE: Record<Action, string> = {
  approve: "bg-approve-bg text-approve-fg",
  return: "bg-return-bg text-return-fg",
  escalate: "bg-escalate-bg text-escalate-fg",
};

export function ActionPill({ action }: { action: Action }) {
  return <span className={`${PILL} ${ACTION_STYLE[action]}`}>{ACTION_LABEL[action]}</span>;
}

const STATUS_STYLE: Partial<Record<CaseStatus, string>> = {
  needs_human_review: "bg-escalate-bg text-escalate-fg",
  approved: "bg-approve-bg text-approve-fg",
  returned: "bg-return-bg text-return-fg",
  escalated: "bg-escalate-bg text-escalate-fg",
};

export function StatusPill({ status }: { status: CaseStatus }) {
  const style = STATUS_STYLE[status] ?? "bg-neutral-bg text-neutral-fg";
  return <span className={`${PILL} ${style}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function NeutralPill({ children }: { children: ReactNode }) {
  return <span className={`${PILL} bg-neutral-bg text-neutral-fg`}>{children}</span>;
}

/** Marks content written by the LLM (explanation, proposal, draft). */
export function LlmPill() {
  return <span className={`${PILL} bg-llm-bg text-llm-fg`}>LLM generated</span>;
}

export function ValidationBadge({ status }: { status: OutputStatus }) {
  const style = status === "valid" ? "bg-approve-bg text-approve-fg" : "bg-escalate-bg text-escalate-fg";
  return (
    <span className={`${PILL} ${style}`} data-testid="validation-badge">
      {OUTPUT_STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Card({
  title,
  aside,
  children,
  className = "",
  labelledBy,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  labelledBy?: string;
}) {
  return (
    <section
      className={`rounded-card border border-line bg-white p-4 sm:p-5 ${className}`}
      aria-labelledby={labelledBy}
    >
      {(title || aside) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 id={labelledBy} className="text-base font-semibold text-text">
              {title}
            </h2>
          )}
          {aside && <div className="flex flex-wrap items-center gap-2">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

const BUTTON = "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60";

export const BUTTON_STYLE = {
  primary: `${BUTTON} bg-primary text-white hover:bg-primary-hover`,
  approve: `${BUTTON} bg-approve-bg text-approve-fg border border-approve-fg/30 hover:border-approve-fg`,
  return: `${BUTTON} bg-return-bg text-return-fg border border-return-fg/30 hover:border-return-fg`,
  escalate: `${BUTTON} bg-white text-escalate-fg border border-escalate-fg/40 hover:border-escalate-fg`,
  neutral: `${BUTTON} bg-neutral-bg text-neutral-fg border border-line hover:border-neutral-fg`,
};

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2" role="status">
      <span
        aria-hidden="true"
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
      />
      {label && <span>{label}</span>}
    </span>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg border border-escalate-fg/30 bg-escalate-bg px-3 py-2 text-sm text-escalate-fg">
      {children}
    </p>
  );
}

export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono ${className}`}>{children}</span>;
}
