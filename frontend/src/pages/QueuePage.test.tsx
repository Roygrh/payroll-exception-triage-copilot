import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { deferred, mockApi } from "../test/api-mock";
import { APPROVE_CASE, CONTEXT, RETURN_CASE } from "../test/fixtures";
import { QueuePage } from "./QueuePage";

const rowIds = () => screen.getAllByTestId("queue-row").map((r) => r.getAttribute("data-case-id"));

describe("queue", () => {
  it("keeps the API's priority order and shows each column", async () => {
    // The UI must not re-sort: the order the API returns is the order shown.
    const lowFirst = { ...APPROVE_CASE, priority_score: 9 };
    mockApi({ "GET /queue": { count: 2, cases: [RETURN_CASE, lowFirst] } });
    render(<QueuePage context={CONTEXT} />);
    await waitFor(() => expect(rowIds()).toEqual([RETURN_CASE.id, APPROVE_CASE.id]));

    const first = within(screen.getAllByTestId("queue-row")[0]!);
    expect(first.getByRole("link", { name: "Jordan Okafor" })).toHaveAttribute("href", `#/cases/${RETURN_CASE.id}`);
    expect(first.getByText(/EMP-1002/)).toBeInTheDocument();
    expect(first.getByText("CAMERA ASSISTANT")).toBeInTheDocument();
    expect(first.getByText("Timing and duration of the first meal period")).toBeInTheDocument();
    expect(first.getByText("MEAL_PERIOD · §8.2")).toBeInTheDocument();
    expect(first.getByText("2026-03-11")).toBeInTheDocument();
    expect(first.getByText("Return")).toBeInTheDocument();
    expect(first.getByText("$0.00")).toBeInTheDocument();
    expect(first.getByText("Awaiting decision")).toBeInTheDocument();

    expect(screen.getByLabelText("Approve: 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Return: 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Escalate: 0")).toBeInTheDocument();
    expect(screen.getByLabelText("Awaiting decision: 2")).toBeInTheDocument();
    expect(screen.getByLabelText("Needs human review: 0")).toBeInTheDocument();
  });

  it("opens the case when a row is clicked", async () => {
    mockApi({ "GET /queue": { count: 1, cases: [RETURN_CASE] } });
    render(<QueuePage context={CONTEXT} />);
    const row = await screen.findByTestId("queue-row");
    await userEvent.click(within(row).getByText("$0.00"));
    expect(window.location.hash).toBe(`#/cases/${RETURN_CASE.id}`);
  });

  it("ingests the week once, shows progress, then refreshes; clean timecards stay absent", async () => {
    const held = deferred<unknown>();
    let ingested = false;
    const results = [
      { timecard_id: "TC-EMP-1001-20260314", case_id: APPROVE_CASE.id, status: "awaiting_decision" },
      { timecard_id: "TC-EMP-1002-20260314", case_id: RETURN_CASE.id, status: "awaiting_decision" },
      ...Array.from({ length: 8 }, (_, i) => ({ timecard_id: `TC-EMP-20${i}-20260314`, case_id: null, status: "clean" })),
    ];
    const calls = mockApi({
      "GET /queue": () => (ingested ? { count: 2, cases: [RETURN_CASE, APPROVE_CASE] } : { count: 0, cases: [] }),
      "POST /ingest": async () => {
        await held.promise;
        ingested = true;
        return { week_ending: "2026-03-14", results };
      },
    });
    render(<QueuePage context={CONTEXT} />);
    expect(await screen.findByText(/No open cases/)).toBeInTheDocument();

    const button = screen.getByRole("button", { name: "Ingest week" });
    await userEvent.click(button);
    const busy = screen.getByRole("button", { name: /Ingesting/ });
    expect(busy).toBeDisabled();
    expect(screen.getByText(/the model explains each finding/)).toBeInTheDocument();
    await userEvent.click(busy);
    expect(calls.filter((c) => c.key === "POST /ingest")).toHaveLength(1);
    expect(calls.find((c) => c.key === "POST /ingest")!.body).toEqual({ week_ending: "2026-03-14" });

    held.resolve(null);
    await waitFor(() => expect(rowIds()).toEqual([RETURN_CASE.id, APPROVE_CASE.id]));
    expect(screen.getByRole("button", { name: "Ingest week" })).toBeEnabled();
    expect(screen.getByText(/10 timecards checked, 2 with a case, 8 clean/)).toBeInTheDocument();
    expect(screen.queryByText(/TC-EMP-20/)).not.toBeInTheDocument();
  });
});
