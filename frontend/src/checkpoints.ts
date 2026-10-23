import type { Outcome } from "./api/types";

// The checkpoint ids before and after each resume of a case (demo step 3: "the resumed graph
// run, checkpoint id before and after"). The API returns them only in the decide and message
// responses, so the UI keeps them for the audit screen in this browser tab. Storage can be
// unavailable (private mode, blocked site data): then the audit screen simply shows none.

export interface Resume {
  step: "decide" | "message";
  before: string | null;
  after: string | null;
}

const key = (caseId: string) => `ptc.resumes.${caseId}`;

export function readResumes(caseId: string): Resume[] {
  try {
    const raw = window.sessionStorage.getItem(key(caseId));
    return raw ? (JSON.parse(raw) as Resume[]) : [];
  } catch {
    return [];
  }
}

export function rememberResume(caseId: string, step: Resume["step"], outcome: Outcome): void {
  try {
    const resumes = [
      ...readResumes(caseId),
      { step, before: outcome.checkpoint_id_before ?? null, after: outcome.checkpoint_id_after ?? null },
    ];
    window.sessionStorage.setItem(key(caseId), JSON.stringify(resumes));
  } catch {
    // keep the decision flow working without storage
  }
}
