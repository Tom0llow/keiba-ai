[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)][ValidateSet("Runs", "FailedLogs")][string]$Mode,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
    [string]$ExpectedHeadSha
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
$state = Load-TaskState
Assert-GhAuthenticated

if ([int]$state.prNumber -ne $PrNumber) {
    throw "PR #$PrNumber is not the recorded task PR #$($state.prNumber)."
}

$beforeSnapshot = Get-VerifiedTaskHeadSnapshot `
    -PrNumber $PrNumber `
    -State $state `
    -ExpectedHeadSha $ExpectedHeadSha
$baseSha = [string]$beforeSnapshot.baseSha

$runJson = Invoke-GhRepo @(
    "run", "list",
    "--commit", $ExpectedHeadSha,
    "--limit", "100",
    "--json", "databaseId,status,conclusion,headSha,url,name"
)
$runs = @($runJson | ConvertFrom-Json | Where-Object {
    [string]$_.headSha -eq $ExpectedHeadSha
})

if ($Mode -eq "Runs") {
    $afterSnapshot = Get-VerifiedTaskHeadSnapshot `
        -PrNumber $PrNumber `
        -State $state `
        -ExpectedHeadSha $ExpectedHeadSha
    if ([string]$afterSnapshot.baseSha -ne $baseSha) {
        throw "PR base changed while collecting workflow runs. Retry the inspection."
    }
    @{
        status   = "ok"
        prNumber = $PrNumber
        baseSha  = $baseSha
        headSha  = $ExpectedHeadSha
        runs     = $runs
    } | ConvertTo-Json -Depth 10
    exit 0
}

$failedRuns = @($runs | Where-Object {
    ([string]$_.status -eq "completed") -and
    ([string]$_.conclusion -notin @("success", "skipped"))
})
$logs = @($failedRuns | ForEach-Object {
    @{
        databaseId = [long]$_.databaseId
        name       = [string]$_.name
        url        = [string]$_.url
        conclusion = [string]$_.conclusion
        log        = (Invoke-GhRepo @("run", "view", "$($_.databaseId)", "--log-failed"))
    }
})

$afterSnapshot = Get-VerifiedTaskHeadSnapshot `
    -PrNumber $PrNumber `
    -State $state `
    -ExpectedHeadSha $ExpectedHeadSha
if ([string]$afterSnapshot.baseSha -ne $baseSha) {
    throw "PR base changed while collecting failed logs. Retry the inspection."
}

@{
    status   = "ok"
    prNumber = $PrNumber
    baseSha  = $baseSha
    headSha  = $ExpectedHeadSha
    logs     = $logs
} | ConvertTo-Json -Depth 10
