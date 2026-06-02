import type { GeminiWebModelId, GeminiWebThinkingLevel } from "./client.js";

export type GeminiExecutionMode = "dom" | "http";

export interface GeminiExecutionModeSelection {
  mode: GeminiExecutionMode;
  reasons: string[];
}

export interface GeminiExecutionModeInput {
  model: GeminiWebModelId;
  thinkingLevel?: GeminiWebThinkingLevel;
  attachmentPaths: string[];
  generateImagePath?: string;
  editImagePath?: string;
}

export function selectGeminiExecutionMode(
  input: GeminiExecutionModeInput,
): GeminiExecutionModeSelection {
  return { mode: "http", reasons: [input.thinkingLevel ?? "standard", input.model] };
}
