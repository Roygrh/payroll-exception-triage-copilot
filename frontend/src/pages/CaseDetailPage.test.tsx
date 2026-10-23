import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { deferred, fail, mockApi } from "../test/api-mock";
import { APPROVE_CASE, CONTEXT, PASSAGE_8_2, RETURN_CASE, atMessage, caseDetail } from "../test/fixtures";
import { readResumes } from "../checkpoints";
import { CaseDetailPage } from "./CaseDetailPage";

const ID = RETURN_CASE.id;

function renderCase(detail = caseDetail(), extra: Record<string, unknown> = {}) {
  const calls = mockApi({ [`GET /cases/${detail.case.id}`]: detail, ...extra });
  render(<CaseDetailPage id={detail.case.id} context={CONTEXT} />);
  return calls;
}

describe("case detail", () => {
  it("shows the finding day as HH:MM events and the engine facts with units", async () => {
    renderCase();
    const events = await screen.findByLabelText("Timecard events");
    expect(within(events).getByText("Call").nextSibling).toHaveTextContent("07:00");
    expect(within(events).getByText("Meal out").nextSibling).toHaveTextContent("12:00");
    expect(within(events).getByText("Meal in").nextSibling).toHaveTextContent("12:24");
    expect(within(events).getByText("Wrap").nextSibling).toHaveTextContent("15:30");
    expect(screen.queryByText("12.4")).not.toBeInTheDocument();
    expect(screen.getByText("24 min, minimum 30 min")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Jordan Okafor" })).toBeInTheDocument();
    expect(screen.getByText("equals policy")).toBeInTheDocument();
    expect(screen.getAllByText("LLM generated")).toHaveLength(2);
  });

  it("opens the exact passage and its key when a citation is clicked", async () => {
    const calls = renderCase(caseDetail(), { "GET /passages/CGMA-2026.1-8.2": PASSAGE_8_2 });
    const explanation = (await screen.findByTestId("explanation-text")).closest("section")!;
    await userEvent.click(within(explanation).getByRole("button", { name: "CGMA-2026.1-8.2" }));
    const panel = screen.getByTestId("passage-panel");
    await waitFor(() => expect(within(panel).getByText(PASSAGE_8_2.body)).toBeInTheDocument());
    expect(within(panel).getByText("CGMA-2026.1-8.2")).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: PASSAGE_8_2.heading })).toBeInTheDocument();
    expect(within(panel).getByText("2026.1")).toBeInTheDocument();
    expect(calls.map((c) => c.key)).toContain("GET /passages/CGMA-2026.1-8.2");
  });

  it("lists the retrieved passages as sent to the model or ranked only, and the model call", async () => {
    renderCase();
    const list = (await screen.findByRole("heading", { name: "Passages retrieved" })).closest("section")!;
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(items[0]).toHaveTextContent("CGMA-2026.1-8.2");
    expect(items[0]).toHaveTextContent("sent to model");
    expect(items[1]).toHaveTextContent("ranked only");
    const call = screen.getByTestId("model-call");
    expect(call).toHaveTextContent("openai/gpt-oss-20b");
    expect(call).toHaveTextContent("3410");
    expect(call).toHaveTextContent("590");
    expect(call).toHaveTextContent("4000");
    expect(call).toHaveTextContent("2140 ms");
  });

  it("shows only the facts and the reason in the needs-human-review state", async () => {
    const reason = "explain: stray number 12.0 is not a fact";
    renderCase(
      caseDetail({
        case: { ...RETURN_CASE, status: "needs_human_review", review_reason: reason },
        review_reason: reason,
        output_status: { explain: "invalid", propose: "valid", draft: "missing" },
      }),
    );
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Needs human review");
    expect(banner).toHaveTextContent(reason);
    expect(screen.queryByTestId("explanation-text")).not.toBeInTheDocument();
    expect(screen.queryByTestId("proposal-text")).not.toBeInTheDocument();
    expect(screen.queryByText(/below the 30-minute minimum/)).not.toBeInTheDocument();
    expect(screen.queryByText("LLM generated")).not.toBeInTheDocument();
    expect(screen.getByText("24 min, minimum 30 min")).toBeInTheDocument();
    // The human still decides.
    expect(screen.getByRole("button", { name: "Return" })).toBeEnabled();
  });
});

describe("needs human review with valid outputs", () => {
  it("still hides the explanation and proposal (for example after a draft failed)", async () => {
    const reason = "draft: stray number 45 is not a fact";
    renderCase(
      caseDetail({
        case: { ...RETURN_CASE, status: "needs_human_review", review_reason: reason },
        review_reason: reason,
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(reason);
    expect(screen.queryByTestId("explanation-text")).not.toBeInTheDocument();
    expect(screen.queryByTestId("proposal-text")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button", { pressed: false })).toHaveLength(0); // no citation buttons
    expect(screen.queryByText("LLM generated")).not.toBeInTheDocument();
  });
});

describe("retry of a stalled decision", () => {
  it("repeats the stored message decision exactly once", async () => {
    const calls = renderCase(
      caseDetail({
        waiting_on: ["execute"],
        pending_retry: true,
        chosen_action: "return",
        decision: { action: "return", actor: "sam.verhoeven", message: "Please fix Wednesday.", recipient_role: "department_head" },
      }),
      { [`POST /cases/${ID}/message`]: { case_id: ID, status: "returned", waiting_on: [], execution: null } },
    );
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Repeat the decision" }));
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}/audit`));
    expect(calls.filter((c) => c.key.startsWith("POST")).map((c) => [c.key, c.body])).toEqual([
      [`POST /cases/${ID}/message`, { actor: "sam.verhoeven", message: "Please fix Wednesday.", recipient_role: "department_head" }],
    ]);
  });

  it("repeats a stalled draft through decide with the stored action and actor", async () => {
    const calls = renderCase(
      caseDetail({
        waiting_on: ["draft"],
        pending_retry: true,
        chosen_action: "escalate",
        decision: { action: "escalate", actor: "sam.verhoeven" },
      }),
      { [`POST /cases/${ID}/decide`]: { case_id: ID, status: "awaiting_decision", waiting_on: ["message_checkpoint"], execution: null } },
    );
    await userEvent.click(await screen.findByRole("button", { name: "Repeat the decision" }));
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}/message`));
    expect(calls.find((c) => c.key.endsWith("/decide"))!.body).toEqual({ action: "escalate", actor: "sam.verhoeven" });
  });
});

describe("decision", () => {
  it("approve executes and opens the audit trail", async () => {
    const detail = caseDetail({}, APPROVE_CASE);
    const calls = renderCase(detail, {
      [`POST /cases/${APPROVE_CASE.id}/decide`]: { case_id: APPROVE_CASE.id, status: "approved", waiting_on: [], execution: null },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${APPROVE_CASE.id}/audit`));
    expect(calls.find((c) => c.key.endsWith("/decide"))!.body).toEqual({ action: "approve", actor: "sam.verhoeven" });
  });

  it("return shows progress while the draft is written and sends one decision only", async () => {
    const held = deferred<unknown>();
    const calls = renderCase(caseDetail(), {
      [`POST /cases/${ID}/decide`]: async () => {
        await held.promise;
        return {
          case_id: ID,
          status: "awaiting_decision",
          waiting_on: ["message_checkpoint"],
          execution: null,
          checkpoint_id_before: "ckpt-a",
          checkpoint_id_after: "ckpt-b",
        };
      },
    });
    const button = await screen.findByRole("button", { name: "Return" });
    await userEvent.click(button);
    expect(screen.getByText("Writing the return message...")).toBeInTheDocument();
    expect(screen.getByText(/seconds to tens of seconds/)).toBeInTheDocument();
    for (const name of ["Approve", "Return", "Escalate"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    await userEvent.click(button);
    button.click(); // even a click event on the disabled button sends nothing
    held.resolve(null);
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}/message`));
    expect(calls.filter((c) => c.key.endsWith("/decide"))).toHaveLength(1);
    expect(calls.find((c) => c.key.endsWith("/decide"))!.body).toEqual({ action: "return", actor: "sam.verhoeven" });
    expect(readResumes(ID)).toEqual([{ step: "decide", before: "ckpt-a", after: "ckpt-b" }]);
  });

  it("unlocks the buttons when a decision leaves the case on this page", async () => {
    renderCase(caseDetail(), {
      [`POST /cases/${ID}/decide`]: { case_id: ID, status: "awaiting_decision", waiting_on: ["human_checkpoint"], execution: null },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled());
    expect(window.location.hash).toBe("");
  });

  it("escalate shows the escalation progress and goes to the message step", async () => {
    const held = deferred<unknown>();
    const calls = renderCase(caseDetail(), {
      [`POST /cases/${ID}/decide`]: async () => {
        await held.promise;
        return { case_id: ID, status: "awaiting_decision", waiting_on: ["message_checkpoint"], execution: null };
      },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Escalate" }));
    expect(screen.getByText("Writing the escalation note...")).toBeInTheDocument();
    held.resolve(null);
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}/message`));
    expect(calls.filter((c) => c.key.endsWith("/decide")).map((c) => c.body)).toEqual([
      { action: "escalate", actor: "sam.verhoeven" },
    ]);
  });

  it("an API refusal shows the reason and re-enables the buttons", async () => {
    renderCase(caseDetail(), { [`POST /cases/${ID}/decide`]: fail(409, "case is not waiting at the human checkpoint") });
    await userEvent.click(await screen.findByRole("button", { name: "Escalate" }));
    expect(await screen.findByText("case is not waiting at the human checkpoint")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Escalate" })).toBeEnabled();
  });

  it("points to the message step when an action is already chosen", async () => {
    renderCase(atMessage());
    expect(await screen.findByRole("link", { name: "Confirm the message" })).toHaveAttribute("href", `#/cases/${ID}/message`);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});
