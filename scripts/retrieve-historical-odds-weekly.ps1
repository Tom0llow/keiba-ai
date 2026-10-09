[CmdletBinding()]
param(
    [switch]$PlanOnly,
    [switch]$Recover,
    [string]$DataConfig = "config/data.toml",
    [string]$JVLinkConfig = "config/jvlink.toml"
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$arguments = @(
    "run", "python", "src/main.py",
    "--retrieve", "--mode", "historical-weekly",
    "--data-config", $DataConfig,
    "--jvlink-config", $JVLinkConfig
)
if ($PlanOnly) {
    $arguments += "--plan-only"
}
if ($Recover) {
    $arguments += "--recover"
}

Push-Location $repoRoot
try {
    & uv @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
