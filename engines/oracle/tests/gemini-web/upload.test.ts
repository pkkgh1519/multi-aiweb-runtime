import { afterEach, describe, expect, it, vi } from "vitest";
import os from "node:os";
import path from "node:path";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { runGeminiWebOnce, runGeminiWebWithFallback } from "../../src/gemini-web/client.js";

function makeRawResponseWithBody(body: unknown): string {
  const responseJson = [[null, null, JSON.stringify(body)]];
  return `)]}'\n\n${JSON.stringify(responseJson)}`;
}

function makeModelUnavailableRawResponse(): string {
  const responseJson: unknown[] = [];
  responseJson[0] = [];
  (responseJson[0] as unknown[])[5] = [];
  ((responseJson[0] as unknown[])[5] as unknown[])[2] = [];
  (((responseJson[0] as unknown[])[5] as unknown[])[2] as unknown[])[0] = [];
  ((((responseJson[0] as unknown[])[5] as unknown[])[2] as unknown[])[0] as unknown[])[1] = [];
  (
    (
      (((responseJson[0] as unknown[])[5] as unknown[])[2] as unknown[])[0] as unknown[]
    )[1] as unknown[]
  )[0] = 1052;
  return `)]}'\n\n${JSON.stringify(responseJson)}`;
}

describe("gemini-web uploads", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the verified Gemini 3.5 Flash model header", async () => {
    let modelHeader: string | undefined;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "https://gemini.google.com/app") {
        return new Response('<html>"SNlM0e":"test-access-token"</html>', { status: 200 });
      }
      if (url.includes("/StreamGenerate")) {
        modelHeader = (init?.headers as Record<string, string> | undefined)?.[
          "x-goog-ext-525001261-jspb"
        ];
        const candidate: unknown[] = [];
        candidate[0] = "rcid-1";
        candidate[1] = ["Gemini 3.5 Flash ok"];
        const body: unknown[] = [];
        body[1] = ["cid", "rid", "rcid-1"];
        body[4] = [candidate];
        return new Response(makeRawResponseWithBody(body), { status: 200 });
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    const result = await runGeminiWebOnce({
      prompt: "Reply exactly: Gemini 3.5 Flash ok",
      files: [],
      model: "gemini-3.5-flash",
      cookieMap: { sid: "cookie" },
    });

    expect(result.text).toBe("Gemini 3.5 Flash ok");
    expect(modelHeader).toContain("56fdd199312815e2");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });



  it("sends the Gemini 3.1 Pro extended thinking header", async () => {
    let modelHeader: string | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "https://gemini.google.com/app") {
        return new Response('<html>"SNlM0e":"test-access-token"</html>', { status: 200 });
      }
      if (url.includes("/StreamGenerate")) {
        modelHeader = (init?.headers as Record<string, string> | undefined)?.[
          "x-goog-ext-525001261-jspb"
        ];
        const candidate: unknown[] = [];
        candidate[0] = "rcid-1";
        candidate[1] = ["Gemini 3.1 Pro extended ok"];
        const body: unknown[] = [];
        body[1] = ["cid", "rid", "rcid-1"];
        body[4] = [candidate];
        return new Response(makeRawResponseWithBody(body), { status: 200 });
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    const result = await runGeminiWebOnce({
      prompt: "Reply exactly: Gemini 3.1 Pro extended ok",
      files: [],
      model: "gemini-3.1-pro",
      thinkingLevel: "extended",
      cookieMap: { sid: "cookie" },
    });

    expect(result.text).toBe("Gemini 3.1 Pro extended ok");
    expect(modelHeader).toContain("e6fa609c3fa255c0");
    expect(modelHeader).toContain(",null,null,3]");
  });

  it("rejects retired Gemini Web models before network access", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    await expect(
      runGeminiWebOnce({
        prompt: "hello",
        files: [],
        model: "gemini-3-pro" as never,
        cookieMap: { sid: "cookie" },
      }),
    ).rejects.toThrow(/Unsupported Gemini web model/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails closed when Gemini 3.5 Flash is unavailable instead of falling back", async () => {
    let streamGenerateCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "https://gemini.google.com/app") {
        return new Response('<html>"SNlM0e":"test-access-token"</html>', { status: 200 });
      }
      if (url.includes("/StreamGenerate")) {
        streamGenerateCalls += 1;
        if (streamGenerateCalls > 1) {
          throw new Error("unexpected fallback request");
        }
        return new Response(makeModelUnavailableRawResponse(), { status: 200 });
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    await expect(
      runGeminiWebWithFallback({
        prompt: "hello",
        files: [],
        model: "gemini-3.5-flash",
        cookieMap: { sid: "cookie" },
      }),
    ).rejects.toThrow(/requested Gemini web model .*gemini-3\.5-flash.*unavailable/i);
    expect(streamGenerateCalls).toBe(1);
  });

  it("sends mime metadata for image and non-image uploads", async () => {
    const tempDir = await mkdtemp(path.join(os.tmpdir(), "oracle-gemini-upload-"));
    const imagePath = path.join(tempDir, "input.png");
    const textPath = path.join(tempDir, "notes.txt");
    await writeFile(
      imagePath,
      Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/Pm2zXwAAAABJRU5ErkJggg==",
        "base64",
      ),
    );
    await writeFile(textPath, "hello from oracle", "utf8");

    const uploadBodies: Array<{ name: string; type: string }> = [];
    let requestPayload: unknown[] | null = null;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "https://gemini.google.com/app") {
        return new Response('<html>"SNlM0e":"test-access-token"</html>', { status: 200 });
      }
      if (url === "https://content-push.googleapis.com/upload") {
        const form = init?.body as FormData;
        const file = form.get("file");
        expect(file).toBeInstanceOf(Blob);
        uploadBodies.push({
          name: file instanceof File ? file.name : "",
          type: file instanceof Blob ? file.type : "",
        });
        return new Response(`upload-${uploadBodies.length}`, { status: 200 });
      }
      if (url.includes("/StreamGenerate")) {
        const params = new URLSearchParams(String(init?.body ?? ""));
        const fReq = params.get("f.req");
        expect(fReq).toBeTruthy();
        const outer = JSON.parse(fReq ?? "[]") as [unknown, string];
        requestPayload = JSON.parse(outer[1]) as unknown[];
        const candidate: unknown[] = [];
        candidate[0] = "rcid-1";
        candidate[1] = ["Upload ok"];
        const body: unknown[] = [];
        body[1] = ["cid", "rid", "rcid-1"];
        body[4] = [candidate];
        return new Response(makeRawResponseWithBody(body), { status: 200 });
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    try {
      const result = await runGeminiWebOnce({
        prompt: "Describe the attachments.",
        files: [imagePath, textPath],
        model: "gemini-3.1-pro",
        cookieMap: { sid: "cookie" },
      });

      expect(result.text).toBe("Upload ok");
      expect(uploadBodies).toEqual([
        { name: "input.png", type: "image/png" },
        { name: "notes.txt", type: "application/octet-stream" },
      ]);
      expect(requestPayload).toEqual([
        [
          "Describe the attachments.",
          0,
          null,
          [
            [["upload-1", 1, null, "image/png"], "input.png"],
            [["upload-2", 1, null, "application/octet-stream"], "notes.txt"],
          ],
        ],
        null,
        null,
      ]);
      expect(fetchMock).toHaveBeenCalledTimes(4);
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });
});
