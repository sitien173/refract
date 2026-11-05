import { describe, expect, it, vi } from "vitest";
import { getJob, getJobs, postJobAction } from "./api";
function response(status: number, body: unknown, json = vi.fn().mockResolvedValue(body)) {
  return { ok: status >= 200 && status < 300, status, json } as unknown as Response;
}
describe("dashboard API", () => {
  it("uses encoded identifiers and no-store cache", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(200, { jobs: [] }));
    await getJobs({ state: "running" }, fetcher as typeof fetch);
    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining("state=running"),
      expect.objectContaining({ cache: "no-store" }),
    );
    fetcher.mockClear();
    fetcher.mockResolvedValue(response(200, {}));
    await getJob("a/b?c", fetcher as typeof fetch);
    expect(fetcher.mock.calls[0][0]).toBe("/dashboard/api/jobs/a%2Fb%3Fc");
    expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
  });
  it("posts answer JSON with question_id and answer and CSRF headers", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(200, {}));
    await postJobAction("j1", "answer", { question_id: "q1", answer: "yes" }, fetcher as typeof fetch);
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      method: "POST",
      headers: { "X-Refract-Dashboard": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: "q1", answer: "yes" }),
      cache: "no-store",
    });
  });
  it("preserves status and error code for JSON errors including 409", async () => {
    for (const [status, code] of [
      [400, "bad_request"],
      [409, "invalid_state"],
    ] as const) {
      const fetcher = vi.fn().mockResolvedValue(response(status, { error: "Request failed", code }));
      try {
        await postJobAction("j1", "answer", {}, fetcher as typeof fetch);
        throw Error("expected rejection");
      } catch (error) {
        expect(error).toMatchObject({ status, code });
      }
    }
  });
  it("handles non-JSON error bodies without losing HTTP status", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(response(502, null, vi.fn().mockRejectedValue(Error("Unexpected token"))));
    try {
      await getJobs({}, fetcher as typeof fetch);
      throw Error("expected rejection");
    } catch (error) {
      expect(error).toMatchObject({ status: 502 });
      expect(error).toBeInstanceOf(Error);
    }
  });
});
