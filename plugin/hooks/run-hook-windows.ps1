param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptName,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = "Stop"

$pluginRoot = $env:PLUGIN_ROOT
if (-not $pluginRoot) {
    $pluginRoot = $env:CLAUDE_PLUGIN_ROOT
}
if (-not $pluginRoot) {
    throw "PLUGIN_ROOT is not set"
}

$pathFlavor = (& bash -lc 'if command -v cygpath >/dev/null 2>&1; then printf git-bash; elif command -v wslpath >/dev/null 2>&1; then printf wsl; fi')
if (-not $pathFlavor) {
    throw "Unable to identify the installed bash environment"
}

if ($pluginRoot -notmatch '^([A-Za-z]):[\\/](.*)$') {
    throw "PLUGIN_ROOT must be a drive-letter path on Windows"
}

$drive = $Matches[1].ToLowerInvariant()
$relative = $Matches[2] -replace '\\', '/'
$prefix = if ($pathFlavor -eq "wsl") { "/mnt/$drive" } else { "/$drive" }
$unixRoot = "$prefix/$relative"

& bash "$unixRoot/hooks/run-hook.sh" $ScriptName @ScriptArgs
exit $LASTEXITCODE
