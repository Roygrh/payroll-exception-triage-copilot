import type { Context } from "../api/types";
import { href } from "../router";

export function Header({ context }: { context: Context | null }) {
  const items: [string, string][] = context
    ? [
        ["Week ending", context.week_ending],
        ["Payroll cut-off", context.payroll_run_date],
        ["Agreement", `${context.agreement.code} ${context.agreement.version}`],
        ["Approver", context.demo_approver],
      ]
    : [];
  return (
    <header className="bg-ink text-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
        <a href={href({ name: "queue" })} className="inline-flex min-h-11 items-center text-base font-semibold">
          Exception Triage Copilot
        </a>
        <dl className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          {items.map(([label, value]) => (
            <div key={label} className="flex gap-1.5">
              <dt className="text-header-muted">{label}</dt>
              <dd className="font-mono">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </header>
  );
}
