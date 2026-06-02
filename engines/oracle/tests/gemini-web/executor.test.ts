import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import os from "node:os";
import path from "node:path";
import { mkdtemp } from "node:fs/promises";

const {
  launchChrome,
  connectWithNewTab,
  closeTab,
  killChrome,
  resolveBrowserConfig,
  readDevToolsPort,
  writeDevToolsActivePort,
  writeChromePid,
  cleanupStaleProfileState,
  verifyDevToolsReachable,
  delay,
} = vi.hoisted(() => ({
  launchChrome: vi.fn(),
  connectWithNewTab: vi.fn(),
  closeTab: vi.fn(async () => undefined),
  killChrome: vi.fn(async () => undefined),
  resolveBrowserConfig: vi.fn((input: unknown) => input),
  readDevToolsPort: vi.fn(async () => null),
  writeDevToolsActivePort: vi.fn(async () => undefined),
  writeChromePid: vi.fn(async () => undefined),
  cleanupStaleProfileState: vi.fn(async () => undefined),
  verifyDevToolsReachable: vi.fn(async () => ({ ok: false, error: "unreachable" })),
  delay: vi.fn(async () => undefined),
}));

const runGeminiWebWithFallback = vi.fn<(...args: unknown[]) => Promise<unknown>>(async (input) => ({
  rawResponseText: "",
  text: "ok",
  thoughts: "thinking",
  metadata: { cid: "1" },
  images: [],
  effectiveModel: (input as { model?: string }).model ?? "gemini-3.1-pro",
}));

const saveFirstGeminiImageFromOutput = vi.fn<(...args: unknown[]) => Promise<unknown>>(
  async () => ({
    saved: true,
    imageCount: 1,
  }),
);

vi.mock("../../src/gemini-web/client.js", () => ({
  runGeminiWebWithFallback,
  saveFirstGeminiImageFromOutput,
}));

const getCookies = vi.fn(async () => ({
  cookies: [
    {
      name: "__Secure-1PSID",
      value: "psid",
      domain: "google.com",
      path: "/",
      secure: true,
      httpOnly: true,
    },
    {
      name: "__Secure-1PSIDTS",
      value: "psidts",
      domain: "google.com",
      path: "/",
      secure: true,
      httpOnly: true,
    },
  ],
  warnings: [] as string[],
}));
vi.mock("@steipete/sweet-cookie", () => ({ getCookies }));
vi.mock("../../src/browser/chromeLifecycle.js", () => ({
  launchChrome,
  connectWithNewTab,
  closeTab,
}));
vi.mock("../../src/browser/config.js", () => ({
  resolveBrowserConfig,
}));
vi.mock("../../src/browser/profileState.js", () => ({
  readDevToolsPort,
  writeDevToolsActivePort,
  writeChromePid,
  cleanupStaleProfileState,
  verifyDevToolsReachable,
}));
vi.mock("../../src/browser/utils.js", () => ({
  delay,
}));

function requiredGeminiCookies() {
  return [
    {
      name: "__Secure-1PSID",
      value: "psid",
      domain: "google.com",
      path: "/",
      secure: true,
      httpOnly: true,
    },
    {
      name: "__Secure-1PSIDTS",
      value: "psidts",
      domain: "google.com",
      path: "/",
      secure: true,
      httpOnly: true,
    },
  ];
}

describe("gemini-web executor", () => {
  beforeEach(() => {
    runGeminiWebWithFallback.mockClear();
    saveFirstGeminiImageFromOutput.mockClear();
    getCookies.mockClear();
    launchChrome.mockReset();
    connectWithNewTab.mockReset();
    closeTab.mockClear();
    resolveBrowserConfig.mockClear();
    readDevToolsPort.mockReset();
    writeDevToolsActivePort.mockClear();
    writeChromePid.mockClear();
    cleanupStaleProfileState.mockClear();
    verifyDevToolsReachable.mockReset();
    delay.mockClear();
    killChrome.mockClear();

    launchChrome.mockResolvedValue({
      port: 9222,
      pid: 12345,
      kill: killChrome,
    });
    const runtimeEvaluate = vi.fn(async ({ expression }: { expression?: string }) => {
      const source = String(expression ?? "");
      if (source.includes("requiresLogin")) {
        return {
          result: {
            value: {
              ready: true,
              requiresLogin: false,
              href: "https://gemini.google.com/app",
            },
          },
        };
      }
      if (source.includes("toolbox-drawer-button")) {
        return { result: { value: "clicked" } };
      }
      if (source.includes("includes('deep think')")) {
        return { result: { value: "clicked" } };
      }
      if (source.includes("Deselect Deep Think")) {
        return { result: { value: true } };
      }
      if (source.includes("document.execCommand")) {
        return { result: { value: "typed" } };
      }
      if (source.includes("button.send-button")) {
        return { result: { value: "clicked" } };
      }
      if (source.includes("response-footer") && source.includes("status: 'done'")) {
        return {
          result: {
            value: JSON.stringify({ status: "done", text: "deep-think answer" }),
          },
        };
      }
      if (source.includes("thoughts-header-button") && source.includes("click")) {
        return { result: { value: "no-toggle" } };
      }
      if (source.includes("model-thoughts") && source.includes("textContent")) {
        return { result: { value: "" } };
      }
      return { result: { value: null } };
    });
    connectWithNewTab.mockResolvedValue({
      targetId: "target-1",
      client: {
        Runtime: {
          enable: vi.fn(async () => undefined),
          evaluate: runtimeEvaluate,
        },
        Network: {
          enable: vi.fn(async () => undefined),
          getCookies: vi.fn(async () => ({ cookies: requiredGeminiCookies() })),
        },
        Page: {
          enable: vi.fn(async () => undefined),
          navigate: vi.fn(async () => ({ frameId: "f-1" })),
        },
        close: vi.fn(async () => undefined),
      },
    });
    readDevToolsPort.mockResolvedValue(null);
    verifyDevToolsReachable.mockResolvedValue({ ok: false, error: "unreachable" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds a generate-image prompt with aspect ratio and passes attachments", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const tempDir = await mkdtemp(path.join(os.tmpdir(), "oracle-gemini-exec-"));
    const outPath = path.join(tempDir, "gen.jpg");

    const exec = createGeminiWebExecutor({
      generateImage: outPath,
      aspectRatio: "1:1",
      showThoughts: true,
    });
    const result = await exec({
      prompt: "a cute robot holding a banana",
      attachments: [{ path: "/tmp/attach.txt", displayPath: "attach.txt" }],
      config: { desiredModel: "Gemini 3.1 Pro", chromeProfile: "Default" },
      log: () => {},
    });

    expect(runGeminiWebWithFallback).toHaveBeenCalledWith(
      expect.objectContaining({
        model: "gemini-3.1-pro",
        prompt: "Generate an image: a cute robot holding a banana (aspect ratio: 1:1)",
        files: ["/tmp/attach.txt"],
      }),
    );
    expect(saveFirstGeminiImageFromOutput).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      outPath,
      expect.any(AbortSignal),
    );
    expect(result.answerMarkdown).toContain("## Thinking");
    expect(result.answerMarkdown).toContain("Generated 1 image(s).");
  });

  it("runs the edit flow as two calls and uses intro metadata", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const tempDir = await mkdtemp(path.join(os.tmpdir(), "oracle-gemini-exec-"));
    const inPath = path.join(tempDir, "in.png");
    const outPath = path.join(tempDir, "out.jpg");

    runGeminiWebWithFallback
      .mockResolvedValueOnce({
        rawResponseText: "",
        text: "intro",
        thoughts: null,
        metadata: { chat: "meta" },
        images: [],
        effectiveModel: "gemini-3.1-pro",
      })
      .mockResolvedValueOnce({
        rawResponseText: "",
        text: "edited",
        thoughts: null,
        metadata: null,
        images: [],
        effectiveModel: "gemini-3.1-pro",
      });

    const exec = createGeminiWebExecutor({ editImage: inPath, outputPath: outPath });
    await exec({
      prompt: "add sunglasses",
      attachments: [],
      config: { desiredModel: "Gemini 3.1 Pro", chromeProfile: "Default" },
      log: () => {},
    });

    expect(runGeminiWebWithFallback).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        prompt: "Here is an image to edit",
        files: [inPath],
        chatMetadata: null,
      }),
    );
    expect(runGeminiWebWithFallback).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ chatMetadata: { chat: "meta" } }),
    );
    expect(saveFirstGeminiImageFromOutput).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      outPath,
      expect.any(AbortSignal),
    );
  });

  it("uses chromeCookiePath when provided", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const exec = createGeminiWebExecutor({});
    await exec({
      prompt: "hello",
      attachments: [],
      config: { desiredModel: "Gemini 3.1 Pro", chromeCookiePath: "/tmp/Cookies" },
      log: () => {},
    });
    expect(getCookies).toHaveBeenCalledWith(
      expect.objectContaining({ chromeProfile: "/tmp/Cookies" }),
    );
  });

  it("resolves verified Gemini 3.5 Flash to the HTTP model id", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const run = createGeminiWebExecutor({});

    await run({
      prompt: "hello",
      attachments: [],
      config: { desiredModel: "Gemini 3.5 Flash", chromeProfile: "Default" },
      log: () => {},
    });

    expect(runGeminiWebWithFallback).toHaveBeenCalledWith(
      expect.objectContaining({ model: "gemini-3.5-flash" }),
    );
    expect(getCookies).toHaveBeenCalled();
  });

  it("rejects Gemini HTTP helper fallback model mismatches", async () => {
    runGeminiWebWithFallback.mockResolvedValueOnce({
      rawResponseText: "",
      text: "fallback answer",
      thoughts: null,
      metadata: null,
      images: [],
      effectiveModel: "gemini-3.1-flash-lite",
    });
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const run = createGeminiWebExecutor({});

    await expect(
      run({
        prompt: "hello",
        attachments: [],
        config: { desiredModel: "gemini-3.5-flash", chromeProfile: "Default" },
        log: () => {},
      }),
    ).rejects.toThrow(/effective Gemini web model .*gemini-3\.1-flash-lite.*requested .*gemini-3\.5-flash/i);
  });

  it("uses inline cookies when cookie sync is disabled", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const exec = createGeminiWebExecutor({});
    await exec({
      prompt: "hello",
      attachments: [],
      config: {
        desiredModel: "Gemini 3.1 Pro",
        cookieSync: false,
        inlineCookies: [
          { name: "__Secure-1PSID", value: "psid", domain: "google.com", path: "/" },
          { name: "__Secure-1PSIDTS", value: "psidts", domain: "google.com", path: "/" },
        ],
        inlineCookiesSource: "test",
      },
      log: () => {},
    });
    expect(getCookies).not.toHaveBeenCalled();
  });

  it("includes cookie read warnings in the missing-cookie error", async () => {
    getCookies.mockImplementationOnce(async () => ({
      cookies: [],
      warnings: [
        "node:sqlite failed reading Chrome cookies (requires modern Chromium, e.g. Chrome >= 100): Value is too large to be represented as a JavaScript number: 13449189465095212",
      ],
    }));

    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const exec = createGeminiWebExecutor({});

    await expect(
      exec({
        prompt: "hello",
        attachments: [],
        config: { desiredModel: "Gemini 3.1 Pro", chromeProfile: "Default" },
        log: () => {},
      }),
    ).rejects.toThrow(
      /Cookie read warnings:.*Value is too large to be represented as a JavaScript number[\s\S]*--browser-manual-login[\s\S]*--browser-inline-cookies-file/s,
    );
  });

  it("rejects explicit unsupported Gemini web models instead of falling back to gemini-3.1-pro", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const exec = createGeminiWebExecutor({});

    await expect(
      exec({
        prompt: "hello",
        attachments: [],
        config: { desiredModel: "gemini-9-fake", chromeProfile: "Default" },
        log: () => {},
      }),
    ).rejects.toThrow(/Unsupported Gemini web model/);

    expect(runGeminiWebWithFallback).not.toHaveBeenCalled();
  });

  it("uses the Gemini 3.1 Pro extended HTTP/header path without DOM automation", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const exec = createGeminiWebExecutor({});
    const result = await exec({
      prompt: "hello",
      attachments: [],
      config: { desiredModel: "gemini-3.1-pro", thinkingTime: "extended", chromeProfile: "Default" },
      log: () => {},
    });

    expect(result.answerText).toBe("ok");
    expect(getCookies).toHaveBeenCalled();
    expect(launchChrome).not.toHaveBeenCalled();
    expect(runGeminiWebWithFallback).toHaveBeenCalledWith(
      expect.objectContaining({ model: "gemini-3.1-pro", thinkingLevel: "extended" }),
    );
  });

  it("rejects Gemini Flash extended thinking before cookies or browser launch", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const exec = createGeminiWebExecutor({});

    await expect(
      exec({
        prompt: "hello",
        attachments: [],
        config: { desiredModel: "gemini-3.5-flash", thinkingTime: "extended", chromeProfile: "Default" },
        log: () => {},
      }),
    ).rejects.toThrow(/extended.*only supported for gemini-3\.1-pro/);

    expect(getCookies).not.toHaveBeenCalled();
    expect(launchChrome).not.toHaveBeenCalled();
    expect(runGeminiWebWithFallback).not.toHaveBeenCalled();
  });

  it("rejects retired Gemini deep-think models", async () => {
    const { createGeminiWebExecutor } = await import("../../src/gemini-web/executor.js");
    const exec = createGeminiWebExecutor({});

    await expect(
      exec({
        prompt: "hello",
        attachments: [],
        config: { desiredModel: "gemini-3-deep-think", chromeProfile: "Default" },
        log: () => {},
      }),
    ).rejects.toThrow(/Unsupported Gemini web model/);

    expect(runGeminiWebWithFallback).not.toHaveBeenCalled();
  });
});
