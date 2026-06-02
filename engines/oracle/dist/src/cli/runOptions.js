import { DEFAULT_MODEL, MODEL_CONFIGS } from "../oracle.js";
import { resolveEngine } from "./engine.js";
import { normalizeModelOption, inferModelFromLabel, resolveApiModel, normalizeBaseUrl, } from "./options.js";
import { resolveGeminiModelId } from "../oracle/gemini.js";
import { PromptValidationError } from "../oracle/errors.js";
import { normalizeChatGptModelForBrowser } from "./browserConfig.js";
import { resolveConfiguredMaxFileSizeBytes } from "./fileSize.js";
import { isAzureOpenAICandidateModel } from "../oracle/providerRouting.js";
export function resolveRunOptionsFromConfig({ prompt, files = [], model, models, engine, userConfig, env = process.env, }) {
    const resolvedEngine = resolveEngine({
        engine,
        configEngine: userConfig?.engine,
        env,
    });
    const envEnginePreference = (env.ORACLE_ENGINE ?? "").trim().toLowerCase();
    const browserRequested = engine === "browser";
    const explicitApiEngineRequested = engine === "api" || (!engine && envEnginePreference === "api");
    const browserConfigured = userConfig?.engine === "browser" && !explicitApiEngineRequested;
    const envBrowserConfigured = !engine && envEnginePreference === "browser";
    const browserEngineRequested = browserRequested || browserConfigured || envBrowserConfigured;
    const requestedModelList = Array.isArray(models) ? models : [];
    const normalizedRequestedModels = requestedModelList
        .map((entry) => normalizeModelOption(entry))
        .filter(Boolean);
    const cliModelArg = normalizeModelOption(model ?? userConfig?.model) || DEFAULT_MODEL;
    const apiModel = resolveApiModel(cliModelArg);
    const browserModel = normalizeChatGptModelForBrowser(inferModelFromLabel(cliModelArg));
    const isCodex = apiModel.startsWith("gpt-5.1-codex");
    const isClaude = apiModel.startsWith("claude");
    const isGrok = apiModel.startsWith("grok");
    const engineWasBrowser = resolvedEngine === "browser";
    const allModels = normalizedRequestedModels.length > 0
        ? Array.from(new Set(normalizedRequestedModels.map((entry) => resolveApiModel(entry))))
        : [apiModel];
    const browserCompatibilityModels = normalizedRequestedModels.length > 0 ? allModels : [browserModel];
    const isGeminiBrowserModel = (m) => m === "gemini-3.1-pro" || m === "gemini-3.5-flash" || m === "gemini-3.1-flash-lite";
    const isBrowserCompatible = (m) => m.startsWith("gpt-") || isGeminiBrowserModel(m);
    const hasNonBrowserCompatibleTarget = browserEngineRequested && browserCompatibilityModels.some((m) => !isBrowserCompatible(m));
    if (hasNonBrowserCompatibleTarget) {
        throw new PromptValidationError("Browser engine only supports GPT and Gemini models. Re-run with --engine api for Grok, Claude, or other models.", { engine: "browser", models: allModels });
    }
    const azure = resolveAzureOptions(userConfig, env);
    const azureAutoApi = Boolean(azure?.endpoint) &&
        !browserEngineRequested &&
        allModels.some(isAzureOpenAICandidateModel);
    const engineCoercedToApi = engineWasBrowser && (isCodex || isClaude || isGrok || azureAutoApi);
    const fixedEngine = isCodex ||
        isClaude ||
        isGrok ||
        azureAutoApi ||
        normalizedRequestedModels.length > 0
        ? "api"
        : resolvedEngine;
    // Browser runs use ChatGPT picker labels/aliases; API runs must keep API model ids intact.
    const resolvedModel = fixedEngine === "browser" ? browserModel : apiModel;
    const promptWithSuffix = userConfig?.promptSuffix && userConfig.promptSuffix.trim().length > 0
        ? `${prompt.trim()}\n${userConfig.promptSuffix}`
        : prompt;
    const search = userConfig?.search !== "off";
    const heartbeatIntervalMs = userConfig?.heartbeatSeconds !== undefined ? userConfig.heartbeatSeconds * 1000 : 30_000;
    const maxFileSizeBytes = resolveConfiguredMaxFileSizeBytes(userConfig, env);
    const baseUrl = normalizeBaseUrl(userConfig?.apiBaseUrl ??
        (isClaude ? env.ANTHROPIC_BASE_URL : isGrok ? env.XAI_BASE_URL : env.OPENAI_BASE_URL));
    const uniqueMultiModels = normalizedRequestedModels.length > 0 ? allModels : [];
    const includesCodexMultiModel = uniqueMultiModels.some((entry) => entry.startsWith("gpt-5.1-codex"));
    if (includesCodexMultiModel && browserRequested) {
        // Silent coerce; multi-model still forces API.
    }
    const chosenModel = uniqueMultiModels[0] ?? resolvedModel;
    const effectiveModelId = resolveEffectiveModelId(chosenModel);
    const runOptions = {
        prompt: promptWithSuffix,
        model: chosenModel,
        models: uniqueMultiModels.length > 0 ? uniqueMultiModels : undefined,
        file: files ?? [],
        maxFileSizeBytes,
        search,
        heartbeatIntervalMs,
        filesReport: userConfig?.filesReport,
        background: userConfig?.background,
        baseUrl,
        azure,
        effectiveModelId,
    };
    return { runOptions, resolvedEngine: fixedEngine, engineCoercedToApi };
}
function resolveAzureOptions(userConfig, env) {
    const endpoint = env.AZURE_OPENAI_ENDPOINT ?? userConfig?.azure?.endpoint;
    if (!endpoint?.trim()) {
        return undefined;
    }
    return {
        endpoint,
        deployment: env.AZURE_OPENAI_DEPLOYMENT ?? userConfig?.azure?.deployment,
        apiVersion: env.AZURE_OPENAI_API_VERSION ?? userConfig?.azure?.apiVersion,
    };
}
function resolveEffectiveModelId(model) {
    if (typeof model === "string" && model.startsWith("gemini")) {
        return resolveGeminiModelId(model);
    }
    const config = MODEL_CONFIGS[model];
    return config?.apiModel ?? model;
}
