[CmdletBinding()]
param(
    [string]$MarketplaceRoot = (Join-Path $env:USERPROFILE ".codex\local-marketplaces"),
    [string]$MarketplaceName = "local-marketplaces",
    [string]$PluginName = "multi-aiweb-runtime",
    [string]$PythonCommand = "python",
    [string]$StateRoot = (Join-Path $env:USERPROFILE ".codex\state\multi-aiweb-runtime"),
    [switch]$DryRun,
    [switch]$SkipMarketplaceRegistration,
    [switch]$SkipPluginInstall,
    [switch]$SkipOracleDeps,
    [switch]$NoCachebuster,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginRoot = Join-Path $MarketplaceRoot (Join-Path $PluginName "plugins")
$MarketplaceConfig = Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json"
$ServerScript = Join-Path $PluginRoot "multi_aiweb_runtime_server.py"
$McpJson = Join-Path $PluginRoot ".mcp.json"
$InstallManifest = Join-Path $PluginRoot "install-manifest.json"

function Convert-ToPosixPath([string]$PathValue) {
    return $PathValue.Replace('\\', '/')
}

function Write-Info([string]$Message) {
    Write-Host "[multi-aiweb-runtime] $Message"
}

function Write-Utf8NoBom([string]$PathValue, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($PathValue, $Content, $encoding)
}

function Invoke-CheckedCommand([string]$CommandName, [string[]]$CommandArgs, [string]$WorkingDirectory = $null) {
    $display = "$CommandName $($CommandArgs -join ' ')"
    if ($WorkingDirectory) {
        $display = "cd $WorkingDirectory; $display"
    }
    if ($DryRun) {
        Write-Info "DRY-RUN $display"
        return
    }
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $CommandName"
    }
    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
        try { & $CommandName @CommandArgs }
        finally { Pop-Location }
    } else {
        & $CommandName @CommandArgs
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $display"
    }
}

function Assert-NodeMajorVersion([int]$MinimumMajor) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Oracle backend dependency install requires Node $MinimumMajor or newer. Install Node $MinimumMajor+ or rerun with -SkipOracleDeps."
    }
    $rawVersion = (& node --version).Trim()
    if ($LASTEXITCODE -ne 0 -or -not ($rawVersion -match '^v?(\d+)\.')) {
        throw "Could not determine Node version for Oracle dependency install. Install Node $MinimumMajor+ or rerun with -SkipOracleDeps."
    }
    $major = [int]$Matches[1]
    if ($major -lt $MinimumMajor) {
        throw "Oracle backend requires Node $MinimumMajor or newer. Current Node is $rawVersion. Upgrade Node or rerun with -SkipOracleDeps to install the plugin without Oracle dependencies."
    }
}

function Copy-PluginSource {
    Write-Info "Copy plugin files to $PluginRoot"
    if ($DryRun) { return }
    New-Item -ItemType Directory -Path $PluginRoot -Force | Out-Null
    $excludeDirs = @('.git', 'node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.venv', 'venv')
    $excludeFiles = @('*.pyc', 'install-manifest.json', 'mcp-config-snippet.local.toml')
    $args = @($RepoRoot, $PluginRoot, '/E', '/XD') + $excludeDirs + @('/XF') + $excludeFiles + @('/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    & robocopy @args | Out-Null
    $code = $LASTEXITCODE
    if ($code -gt 7) {
        throw "robocopy failed with exit code $code"
    }
}

function Update-InstalledPluginVersion {
    $manifestPath = Join-Path $PluginRoot ".codex-plugin\plugin.json"
    if ($DryRun) {
        Write-Info "DRY-RUN update installed plugin cachebuster in $manifestPath"
        return
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $baseVersion = ([string]$manifest.version).Split('+')[0]
    if (-not $NoCachebuster) {
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
        $manifest.version = "$baseVersion+codex.$stamp"
    } else {
        $manifest.version = $baseVersion
    }
    Write-Utf8NoBom -PathValue $manifestPath -Content ($manifest | ConvertTo-Json -Depth 30)
}

function Write-McpJson {
    Write-Info "Write MCP config to $McpJson"
    if ($DryRun) { return }
    $payload = [ordered]@{
        mcpServers = [ordered]@{
            multi_aiweb_runtime = [ordered]@{
                command = $PythonCommand
                args = @((Convert-ToPosixPath $ServerScript))
                startup_timeout_sec = 10
                tool_timeout_sec = 7200
                env = [ordered]@{
                    MULTI_AIWEB_RUNTIME_STATE_DIR = Convert-ToPosixPath $StateRoot
                    MULTI_AIWEB_RUNTIME_PLUGIN_ROOT = Convert-ToPosixPath $PluginRoot
                    MULTI_AIWEB_RUNTIME_ORACLE_ENGINE_SOURCE = "bundled"
                }
            }
        }
    }
    Write-Utf8NoBom -PathValue $McpJson -Content ($payload | ConvertTo-Json -Depth 20)
}

function Update-MarketplaceManifest {
    Write-Info "Update marketplace manifest at $MarketplaceConfig"
    if ($DryRun) { return $MarketplaceName }
    New-Item -ItemType Directory -Path (Split-Path -Parent $MarketplaceConfig) -Force | Out-Null
    if (Test-Path -LiteralPath $MarketplaceConfig) {
        $rawMarketplace = Get-Content -LiteralPath $MarketplaceConfig -Raw
        if ([string]::IsNullOrWhiteSpace($rawMarketplace)) {
            Write-Info "Existing marketplace manifest is empty; recreating it."
            $resolvedName = $MarketplaceName
            $interface = [ordered]@{ displayName = "Local Codex Plugins" }
            $plugins = @()
        } else {
            try {
                $existing = $rawMarketplace | ConvertFrom-Json
                $resolvedName = if ($existing.name) { [string]$existing.name } else { $MarketplaceName }
                $interface = if ($existing.interface) { $existing.interface } else { [ordered]@{ displayName = "Local Codex Plugins" } }
                $plugins = @($existing.plugins)
            } catch {
                $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
                $backupPath = "$MarketplaceConfig.invalid.$stamp.bak"
                Move-Item -LiteralPath $MarketplaceConfig -Destination $backupPath -Force
                Write-Info "Existing marketplace manifest was invalid JSON and was backed up to $backupPath"
                $resolvedName = $MarketplaceName
                $interface = [ordered]@{ displayName = "Local Codex Plugins" }
                $plugins = @()
            }
        }
    } else {
        $resolvedName = $MarketplaceName
        $interface = [ordered]@{ displayName = "Local Codex Plugins" }
        $plugins = @()
    }
    $entry = [ordered]@{
        name = $PluginName
        source = [ordered]@{
            source = "local"
            path = "./$PluginName/plugins"
        }
        policy = [ordered]@{
            installation = "AVAILABLE"
            authentication = "ON_INSTALL"
        }
        category = "Automation"
    }
    $kept = @($plugins | Where-Object { $_.name -ne $PluginName })
    $payload = [ordered]@{
        name = $resolvedName
        interface = $interface
        plugins = @($kept + @($entry))
    }
    Write-Utf8NoBom -PathValue $MarketplaceConfig -Content ($payload | ConvertTo-Json -Depth 30)
    return $resolvedName
}

function Install-OracleDependencies {
    if ($SkipOracleDeps) {
        Write-Info "Skip Oracle dependency install"
        return
    }
    $engineRoot = Join-Path $PluginRoot "engines\oracle"
    $packageJson = Join-Path $engineRoot "package.json"
    if (-not (Test-Path -LiteralPath $packageJson)) {
        Write-Info "Oracle package.json not found; skip dependency install"
        return
    }
    Assert-NodeMajorVersion -MinimumMajor 24
    Invoke-CheckedCommand -CommandName "pnpm" -CommandArgs @("install", "--prod", "--frozen-lockfile", "--ignore-scripts") -WorkingDirectory $engineRoot
}

function Write-InstallManifest([string]$ResolvedMarketplaceName) {
    Write-Info "Write install manifest to $InstallManifest"
    if ($DryRun) { return }
    $payload = [ordered]@{
        installed_at = (Get-Date).ToString("o")
        dry_run = $false
        marketplace_name = $ResolvedMarketplaceName
        marketplace_root = $MarketplaceRoot
        plugin_name = $PluginName
        plugin_selector = "$PluginName@$ResolvedMarketplaceName"
        plugin_root = $PluginRoot
        marketplace_config = $MarketplaceConfig
        mcp_json = $McpJson
        server_script = $ServerScript
        engine_root = (Join-Path $PluginRoot "engines\oracle")
        oracle_engine_source = "bundled"
        state_root = $StateRoot
        python_command = $PythonCommand
        note = "Generated by install.ps1. Do not commit this machine-local file."
    }
    Write-Utf8NoBom -PathValue $InstallManifest -Content ($payload | ConvertTo-Json -Depth 20)
}

Write-Info "Repository root: $RepoRoot"
Write-Info "Marketplace root: $MarketplaceRoot"
Write-Info "Plugin root: $PluginRoot"
if ($DryRun) {
    Write-Info "Dry run only; no files or Codex settings will be changed."
}

Copy-PluginSource
Update-InstalledPluginVersion
Write-McpJson
$resolvedMarketplaceName = Update-MarketplaceManifest
Install-OracleDependencies
Write-InstallManifest -ResolvedMarketplaceName $resolvedMarketplaceName

if (-not $SkipMarketplaceRegistration) {
    Invoke-CheckedCommand -CommandName "codex" -CommandArgs @("plugin", "marketplace", "add", $MarketplaceRoot)
}
if (-not $SkipPluginInstall) {
    Invoke-CheckedCommand -CommandName "codex" -CommandArgs @("plugin", "add", "$PluginName@$resolvedMarketplaceName")
}

Write-Info "Install flow finished. Start a new Codex thread or restart Codex to pick up plugin changes."
exit 0
