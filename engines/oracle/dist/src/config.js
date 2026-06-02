import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import JSON5 from "json5";
import { getOracleHomeDir } from "./oracleHome.js";
export const PROJECT_CONFIG_RELATIVE_PATH = path.join(".oracle", "config.json");
function resolveUserConfigPath() {
    return path.join(getOracleHomeDir(), "config.json");
}
export async function loadUserConfig(options = {}) {
    const userConfigPath = resolveUserConfigPath();
    const userConfig = await readConfigFile(userConfigPath);
    const projectConfigPaths = options.includeProject === false
        ? []
        : await discoverProjectConfigPaths({
            cwd: options.cwd ?? process.cwd(),
            userConfigPath,
        });
    const loadedConfigs = [];
    if (userConfig.loaded) {
        loadedConfigs.push(userConfig);
    }
    let merged = userConfig.loaded ? userConfig.config : {};
    for (const projectConfigPath of projectConfigPaths) {
        const projectConfig = await readConfigFile(projectConfigPath);
        if (!projectConfig.loaded)
            continue;
        loadedConfigs.push(projectConfig);
        merged = mergeUserConfig(merged, sanitizeProjectConfig(projectConfig.config));
    }
    const loadedPaths = loadedConfigs.map((entry) => entry.path);
    return {
        config: merged,
        path: userConfigPath,
        paths: loadedPaths,
        loaded: userConfig.loaded,
    };
}
async function readConfigFile(configPath) {
    try {
        const raw = await fs.readFile(configPath, "utf8");
        const parsed = JSON5.parse(raw);
        return { config: parsed ?? {}, path: configPath, loaded: true };
    }
    catch (error) {
        const code = error.code;
        if (code === "ENOENT") {
            return { config: {}, path: configPath, loaded: false };
        }
        console.warn(`Failed to read ${configPath}: ${error instanceof Error ? error.message : String(error)}`);
        return { config: {}, path: configPath, loaded: false };
    }
}
export function configPath() {
    return resolveUserConfigPath();
}
async function discoverProjectConfigPaths({ cwd, userConfigPath, }) {
    const start = path.resolve(cwd);
    const home = os.homedir();
    const candidates = [];
    const seen = new Set([path.resolve(userConfigPath)]);
    let current = start;
    while (true) {
        if (current === home) {
            break;
        }
        const candidate = path.join(current, PROJECT_CONFIG_RELATIVE_PATH);
        const resolved = path.resolve(candidate);
        if (!seen.has(resolved)) {
            try {
                const stat = await fs.stat(resolved);
                if (stat.isFile()) {
                    candidates.unshift(resolved);
                    seen.add(resolved);
                }
            }
            catch (error) {
                if (error.code !== "ENOENT") {
                    console.warn(`Failed to inspect ${resolved}: ${error instanceof Error ? error.message : String(error)}`);
                }
            }
        }
        const parent = path.dirname(current);
        if (parent === current) {
            break;
        }
        current = parent;
    }
    return candidates;
}
function mergeUserConfig(base, override) {
    return deepMerge(base, override);
}
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
function deepMerge(base, override) {
    if (!isRecord(base) || !isRecord(override)) {
        return override;
    }
    const result = { ...base };
    for (const [key, value] of Object.entries(override)) {
        const existing = result[key];
        result[key] = isRecord(existing) && isRecord(value) ? deepMerge(existing, value) : value;
    }
    return result;
}
function sanitizeProjectConfig(config) {
    const sanitized = {};
    if (config.engine !== undefined)
        sanitized.engine = config.engine;
    if (config.model !== undefined)
        sanitized.model = config.model;
    if (config.search !== undefined)
        sanitized.search = config.search;
    if (config.maxFileSizeBytes !== undefined)
        sanitized.maxFileSizeBytes = config.maxFileSizeBytes;
    if (config.notify !== undefined)
        sanitized.notify = config.notify;
    if (config.heartbeatSeconds !== undefined)
        sanitized.heartbeatSeconds = config.heartbeatSeconds;
    if (config.filesReport !== undefined)
        sanitized.filesReport = config.filesReport;
    if (config.background !== undefined)
        sanitized.background = config.background;
    if (config.promptSuffix !== undefined)
        sanitized.promptSuffix = config.promptSuffix;
    if (config.browser) {
        sanitized.browser = {};
        const browser = config.browser;
        const allowedBrowserKeys = [
            "attachRunning",
            "timeoutMs",
            "inputTimeoutMs",
            "attachmentTimeoutMs",
            "assistantRecheckDelayMs",
            "assistantRecheckTimeoutMs",
            "reuseChromeWaitMs",
            "profileLockTimeoutMs",
            "maxConcurrentTabs",
            "autoReattachDelayMs",
            "autoReattachIntervalMs",
            "autoReattachTimeoutMs",
            "cookieSyncWaitMs",
            "hideWindow",
            "keepBrowser",
            "modelStrategy",
            "thinkingTime",
            "researchMode",
            "archiveConversations",
            "manualLogin",
        ];
        for (const key of allowedBrowserKeys) {
            if (browser[key] !== undefined) {
                sanitized.browser[key] = browser[key];
            }
        }
        const chatgptUrl = browser.chatgptUrl ?? browser.url;
        if (chatgptUrl === null ||
            (chatgptUrl !== undefined && isTrustedProjectChatgptUrl(chatgptUrl))) {
            sanitized.browser.chatgptUrl = chatgptUrl;
            sanitized.browser.url = chatgptUrl;
        }
    }
    return sanitized;
}
function isTrustedProjectChatgptUrl(rawUrl) {
    if (!rawUrl) {
        return false;
    }
    try {
        const parsed = new URL(rawUrl);
        if (parsed.protocol !== "https:") {
            return false;
        }
        return parsed.hostname === "chatgpt.com" || parsed.hostname === "chat.openai.com";
    }
    catch {
        return false;
    }
}
