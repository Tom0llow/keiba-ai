[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $repoRoot "scripts/agent/_common.ps1")

function Assert-Rejected {
    param([scriptblock]$Action)
    $rejected = $false
    try { & $Action }
    catch { $rejected = $true }
    if (-not $rejected) { throw "Invalid baseline evidence was accepted." }
}

$checks = @(
    [pscustomobject]@{name="Quality"; bucket="pass"; state="success"; trustedForRequirement=$true; workflow="github-actions"},
    [pscustomobject]@{name="Test"; bucket="pass"; state="success"; trustedForRequirement=$true; workflow="github-actions"}
)
Assert-BaselineChecksReady -Checks $checks
Assert-Rejected { Assert-BaselineChecksReady -Checks @($checks[0]) }
$checks[1].state = "neutral"
Assert-Rejected { Assert-BaselineChecksReady -Checks $checks }
$checks[1].state = "success"
$checks[1].trustedForRequirement = $false
Assert-Rejected { Assert-BaselineChecksReady -Checks $checks }
$checks[1].trustedForRequirement = $true
$checks[1].bucket = "pending"
Assert-Rejected { Assert-BaselineChecksReady -Checks $checks }

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("guard-state-utf8-" + [guid]::NewGuid().ToString("N"))
try {
    $null = New-Item -ItemType Directory -Path $testRoot
    $statePath = Join-Path $testRoot "codex-task.json"
    function Get-TaskStatePath { return $statePath }
    $script:WorkflowLock = [pscustomobject]@{test=$true}
    $message = "fix: " + [char]0x65e5 + [char]0x672c + [char]0x8a9e + ' "quoted"'
    Write-TaskStateObject -State ([ordered]@{version=7; pendingCommitMessage=$message})
    if ((Read-TaskStateRaw).pendingCommitMessage -cne $message) {
        throw "UTF-8 task-state message changed while reading it."
    }

    $script:TrustedCommandOutputRoot = $testRoot
    $script:DisabledHooksPath = Join-Path $testRoot "empty-hooks"
    $null = New-Item -ItemType Directory -Path $script:DisabledHooksPath
    $script:GitPath = [string](Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $gitRoot = Join-Path $testRoot "repository"
    $null = New-Item -ItemType Directory -Path $gitRoot
    Push-Location -LiteralPath $gitRoot
    try {
        Invoke-Git @("-c", "init.templateDir=$script:DisabledHooksPath", "init", "--quiet") | Out-Null
        $samplePath = Join-Path $gitRoot "sample.txt"
        [System.IO.File]::WriteAllText($samplePath, "first`n", [System.Text.UTF8Encoding]::new($false))
        Invoke-Git @("-c", "core.autocrlf=false", "add", "sample.txt") | Out-Null
        Invoke-Git @("-c", "commit.gpgSign=false", "-c", "user.name=Guard Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture base") | Out-Null
        $baseSha = Invoke-Git @("rev-parse", "HEAD")
        [System.IO.File]::WriteAllText($samplePath, "first`nvalue  `n", [System.Text.UTF8Encoding]::new($false))
        Invoke-Git @("-c", "core.autocrlf=false", "add", "sample.txt") | Out-Null
        Invoke-Git @("-c", "commit.gpgSign=false", "-c", "user.name=Guard Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture head") | Out-Null
        $headSha = Invoke-Git @("rev-parse", "HEAD")
        $diff = Get-ImmutableCommitDiff -BaseSha $baseSha -HeadSha $headSha
        if (-not $diff.EndsWith("+value  `n", [System.StringComparison]::Ordinal)) {
            throw "Real Git diff lost trailing spaces or its final newline."
        }
        Invoke-Git @("config", "--local", "merge.guard-fixture.driver", "fixture-command-must-not-run") | Out-Null
        $driverRejected = $false
        try { Assert-NoExternalMergeDrivers }
        catch {
            if ($_.Exception.Message -notmatch 'External merge drivers') { throw }
            $driverRejected = $true
        }
        if (-not $driverRejected) { throw "External merge-driver configuration was accepted." }
        Invoke-Git @("config", "--local", "--unset", "merge.guard-fixture.driver") | Out-Null
    }
    finally { Pop-Location }
}
finally {
    $resolvedRoot = [System.IO.Path]::GetFullPath($testRoot)
    $tempPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedRoot.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a fixture outside the temporary directory."
    }
    Remove-Item -LiteralPath $resolvedRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Output "Baseline and task-state encoding regressions passed."
