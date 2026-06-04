import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "vitest";

const repoRoot = path.resolve(__dirname, "../..");

function read(relativePath: string): string {
  return readFileSync(path.join(repoRoot, relativePath), "utf8");
}

describe("Oracle browser reliability markers", () => {
  test("profile and Chrome lifecycle modules expose classifiable profile diagnostics", () => {
    const profileState = read("src/browser/profileState.ts");
    const chromeLifecycle = read("src/browser/chromeLifecycle.ts");

    expect(profileState).toContain("PROFILE_BUSY");
    expect(profileState).toContain("STALE_DEVTOOLS_PORT");
    expect(chromeLifecycle).toContain("PROFILE_BUSY");
    expect(chromeLifecycle).toContain('logger("STALE_DEVTOOLS_PORT');
  });

  test("session runner exposes classifiable Pro long-running states", () => {
    const sessionRunner = read("src/cli/sessionRunner.ts");

    expect(sessionRunner).toContain("PROMPT_NOT_SUBMITTED");
    expect(sessionRunner).toContain("LONG_THINKING_IN_PROGRESS");
    expect(sessionRunner).toContain("CAPTURE_INCOMPLETE");
  });
});
