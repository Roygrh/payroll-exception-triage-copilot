import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { deferred, mockApi } from "../test/api-mock";
import { CONTEXT, DRAFT, RETURN_CASE, atMessage, caseDetail } from "../test/fixtures";
import { ConfirmMessagePage } from "./ConfirmMessagePage";

const ID = RETURN_CASE.id;

function renderMessage(detail = atMessage(), extra: Record<string, unknown> = {}) {
  const calls = mockApi({ [`GET /cases/${ID}`]: detail, ...extra });
  render(<ConfirmMessagePage id={ID} context={CONTEXT} />);
  return calls;
}

const executed = { case_id: ID, status: "returned", waiting_on: [], execution: null };

describe("confirm the message", () => {
  it("shows the steps, the recipient, the draft, its validity and token count", async () => {
    renderMessage();
    const steps = await screen.findByLabelText("Decision steps");
    expect(steps).toHaveTextContent("Action chosen");
    expect(steps).toHaveTextContent("Confirm message");
    expect(steps).toHaveTextContent("Execute");
    expect(screen.getByLabelText("Recipient")).toHaveValue("employee");
    expect(screen.getByText(DRAFT.subject)).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toHaveValue(DRAFT.body);
    expect(screen.getByTestId("validation-badge")).toHaveTextContent("Validated");
    expect(screen.getByText("LLM generated")).toBeInTheDocument();
    expect(screen.getByText("740")).toBeInTheDocument(); // 600 input + 140 output tokens of the draft call
  });

  it("sends the edited message once and opens the audit trail", async () => {
    const calls = renderMessage(atMessage(), { [`POST /cases/${ID}/message`]: executed });
    const body = await screen.findByLabelText("Message");
    await userEvent.type(body, " Thank you.");
    await userEvent.selectOptions(screen.getByLabelText("Recipient"), "department_head");
    await userEvent.click(screen.getByRole("button", { name: "Confirm and return" }));
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}/audit`));
    const sent = calls.filter((c) => c.key === `POST /cases/${ID}/message`);
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toEqual({
      actor: "sam.verhoeven",
      message: `${DRAFT.body} Thank you.`,
      recipient_role: "department_head",
    });
  });

  it("starts with an empty body when the draft needs review, and the approver writes it", async () => {
    const reason = "draft: stray number 45 is not a fact";
    const calls = renderMessage(
      atMessage({
        draft: null,
        output_status: { explain: "valid", propose: "valid", draft: "invalid" },
        review_reason: reason,
        case: { ...RETURN_CASE, status: "needs_human_review", review_reason: reason },
      }),
      { [`POST /cases/${ID}/message`]: executed },
    );
    const body = await screen.findByLabelText("Message");
    expect(body).toHaveValue("");
    expect(screen.getByRole("alert")).toHaveTextContent("The draft needs human review");
    expect(screen.getByRole("alert")).toHaveTextContent(reason);
    expect(screen.queryByText("LLM generated")).not.toBeInTheDocument();
    expect(screen.queryByText(DRAFT.subject)).not.toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirm and return" });
    expect(confirm).toBeDisabled();
    await userEvent.type(body, "Please correct the meal in time on Wednesday.");
    await userEvent.click(confirm);
    await waitFor(() => expect(calls.some((c) => c.key === `POST /cases/${ID}/message`)).toBe(true));
    expect(calls.find((c) => c.key === `POST /cases/${ID}/message`)!.body).toMatchObject({
      message: "Please correct the meal in time on Wednesday.",
      recipient_role: "employee",
    });
  });

  it("a repeated confirm click sends one message only", async () => {
    const held = deferred<unknown>();
    const calls = renderMessage(atMessage(), {
      [`POST /cases/${ID}/message`]: async () => {
        await held.promise;
        return executed;
      },
    });
    const confirm = await screen.findByRole("button", { name: "Confirm and return" });
    await userEvent.click(confirm);
    expect(screen.getByRole("button", { name: /Executing/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /Executing/ }));
    held.resolve(null);
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}/audit`));
    expect(calls.filter((c) => c.key === `POST /cases/${ID}/message`)).toHaveLength(1);
  });

  it("shows a validated draft on a case already in review, as ADR-018 allows", async () => {
    const reason = "explain: stray number 12.0 is not a fact";
    renderMessage(atMessage({ case: { ...RETURN_CASE, status: "needs_human_review", review_reason: reason }, review_reason: reason }));
    expect(await screen.findByLabelText("Message")).toHaveValue(DRAFT.body);
    expect(screen.getByTestId("validation-badge")).toHaveTextContent("Validated");
  });

  it("cancel withdraws the action and goes back to the case", async () => {
    const calls = renderMessage(atMessage(), {
      [`POST /cases/${ID}/message`]: { case_id: ID, status: "awaiting_decision", waiting_on: ["human_checkpoint"] },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}`));
    expect(calls.find((c) => c.key === `POST /cases/${ID}/message`)!.body).toEqual({ actor: "sam.verhoeven", cancel: true });
  });

  it("confirms the escalation note once, addressed to the payroll specialist", async () => {
    const calls = renderMessage(
      atMessage({
        chosen_action: "escalate",
        decision: { action: "escalate", actor: "sam.verhoeven" },
        draft: { ...DRAFT, for_action: "escalate", recipient_role: "payroll_specialist" },
      }),
      { [`POST /cases/${ID}/message`]: { ...executed, status: "escalated" } },
    );
    const confirm = await screen.findByRole("button", { name: "Confirm and escalate" });
    expect(screen.getByText("Payroll specialist")).toBeInTheDocument();
    await userEvent.click(confirm);
    await waitFor(() => expect(window.location.hash).toBe(`#/cases/${ID}/audit`));
    const sent = calls.filter((c) => c.key === `POST /cases/${ID}/message`);
    expect(sent.map((c) => c.body)).toEqual([
      { actor: "sam.verhoeven", message: DRAFT.body, recipient_role: "payroll_specialist" },
    ]);
  });

  it("says so when the case is not waiting for a message", async () => {
    renderMessage(caseDetail());
    expect(await screen.findByText(/not waiting for a message/)).toBeInTheDocument();
  });
});
