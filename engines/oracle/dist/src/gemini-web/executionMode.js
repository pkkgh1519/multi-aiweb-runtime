export function selectGeminiExecutionMode(input) {
    return { mode: "http", reasons: [input.thinkingLevel ?? "standard", input.model] };
}
