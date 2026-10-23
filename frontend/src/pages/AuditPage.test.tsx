import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { rememberResume } from "../checkpoints";
import { mockApi } from "../test/api-mock";
import { APPROVE_CASE, DRAFT, RETURN_AUDIT, RETURN_CASE, RETURNED_DETAIL, caseDetail } from "../test/fixtures";
import { AuditPage } from "./AuditPage";

describe("executed and audit trail", () => {
  it("shows the success banner and every audit entry kind in order", async () => {
    const outcome = { case_id: RETURN_CASE.id, status: "returned" as const, waiting_on: [], execution: null };
    rememberResume(RETURN_CASE.id, "decide", { ...outcome, checkpoint_id_before: "ckpt-a", checkpoint_id_after: "ckpt-b" });
    rememberResume(RETURN_CASE.id, "message", { ...outcome, checkpoint_id_before: "ckpt-b", checkpoint_id_after: "ckpt-c" });
    mockApi({
      [`GET /cases/${RETURN_CASE.id}`]: RETURNED_DETAIL,
      [`GET /cases/${RETURN_CASE.id}/audit`]: { case_id: RETURN_CASE.id, entries: RETURN_AUDIT },
    });
    render(<AuditPage id={RETURN_CASE.id} />);
    expect(await screen.findByText("Timecard returned to Jordan Okafor")).toBeInTheDocument();
    const banner = screen.getByText("Timecard returned to Jordan Okafor").parentElement!;
    expect(banner).toHaveTextContent("Case status Returned");
    expect(banner).toHaveTextContent("Timecard status Rejected");

    const entries = await screen.findAllByTestId("audit-entry");
    expect(entries.map((e) => e.getAttribute("data-kind"))).toEqual([
      "suggestion",
      "validation",
      "decision",
      "suggestion",
      "decision",
      "execution",
    ]);
    expect(within(entries[0]!).getByText("#3")).toBeInTheDocument();
    expect(within(entries[0]!).getByText("2026-10-22 04:36:03 UTC")).toBeInTheDocument();
    expect(entries[0]).toHaveTextContent("Model wrote the explanation and proposal");
    expect(entries[0]).toHaveTextContent("openai/gpt-oss-20b, 4000 tokens, 2140 ms");
    expect(entries[1]).toHaveTextContent("Validation passed");
    expect(entries[2]).toHaveTextContent("Action chosen: Return");
    expect(entries[3]).toHaveTextContent("Model drafted the message");
    expect(entries[4]).toHaveTextContent("Decision executed: Return");
    expect(entries[4]).toHaveTextContent("message draft edited by the approver, to Crew member");
    expect(within(entries[4]!).getByText("sam.verhoeven")).toBeInTheDocument();
    // Demo step 3: the human decision with the original draft and the edited text that was sent.
    const executedMessage = within(entries[4]!).getByTestId("executed-message");
    expect(within(executedMessage).getByTestId("sent-message")).toHaveTextContent(`${DRAFT.body} Thank you.`);
    expect(within(executedMessage).getByTestId("original-draft")).toHaveTextContent(DRAFT.body);
    expect(executedMessage).toHaveTextContent("Message sent (edited by the approver)");
    expect(within(executedMessage).getByText("LLM generated")).toBeInTheDocument();
    expect(within(executedMessage).getByTestId("validation-badge")).toHaveTextContent("Validated");
    expect(within(entries[2]!).queryByTestId("executed-message")).not.toBeInTheDocument();
    // ... and the resumed graph run, checkpoint id before and after.
    const resumes = within(screen.getByTestId("resumes")).getAllByRole("listitem");
    expect(resumes[0]).toHaveTextContent("Action chosen checkpoint ckpt-a to ckpt-b");
    expect(resumes[1]).toHaveTextContent("Message step checkpoint ckpt-b to ckpt-c");
    expect(entries[5]).toHaveTextContent("Executed: Return");
    expect(entries[5]).toHaveTextContent("Case Returned, timecard Rejected");
  });

  it("shows the approval with its premium line", async () => {
    mockApi({
      [`GET /cases/${APPROVE_CASE.id}`]: caseDetail(
        {
          case: { ...APPROVE_CASE, status: "approved" },
          waiting_on: [],
          execution: {
            action: "approve",
            actor: "sam.verhoeven",
            case_status: "approved",
            timecard_status: "Ready for approver 2",
            premium_total_usd: "8.25",
          },
        },
        APPROVE_CASE,
      ),
      [`GET /cases/${APPROVE_CASE.id}/audit`]: { case_id: APPROVE_CASE.id, entries: [] },
    });
    render(<AuditPage id={APPROVE_CASE.id} />);
    const banner = (await screen.findByText("Timecard approved for Avery Lindqvist")).parentElement!;
    expect(banner).toHaveTextContent("Timecard status Ready for approver 2");
    expect(banner).toHaveTextContent("$8.25");
    expect(screen.queryByTestId("resumes")).not.toBeInTheDocument();
  });

  // Provenance of the sent text comes from message_source (ADR-018), never from the draft's presence.
  it.each([
    ["draft_confirmed", DRAFT.body, true, "Message sent (draft unchanged)", false],
    ["human_written", DRAFT.body, false, "Message sent (written by the approver)", true],
    ["human_written", null, null, "Message sent (written by the approver)", false],
  ] as const)("labels a %s message honestly (draft %s, valid %s)", async (source, draft, valid, label, hiddenNote) => {
    const entry = {
      ...RETURN_AUDIT[4]!,
      payload: {
        stage: "executed",
        action: "return",
        policy_action: "return",
        message: "Please correct the meal in time on Wednesday.",
        original_draft: draft,
        original_draft_valid: valid,
        message_edited: false,
        message_source: source,
        recipient_role: "employee",
      },
    };
    mockApi({
      [`GET /cases/${RETURN_CASE.id}`]: RETURNED_DETAIL,
      [`GET /cases/${RETURN_CASE.id}/audit`]: { case_id: RETURN_CASE.id, entries: [entry] },
    });
    render(<AuditPage id={RETURN_CASE.id} />);
    const block = await screen.findByTestId("executed-message");
    expect(block).toHaveTextContent(label);
    expect(within(block).queryByText(/Not shown to the approver/) !== null).toBe(hiddenNote);
    if (draft) {
      expect(within(block).getByTestId("validation-badge")).toHaveTextContent(valid ? "Validated" : "Failed validation");
    } else {
      expect(within(block).getByTestId("original-draft")).toHaveTextContent("None");
    }
  });
});
