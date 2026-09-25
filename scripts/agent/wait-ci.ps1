[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
    [string]$ExpectedHeadSha,
    [Parameter()][ValidateRange(1, 7200)][int]$TimeoutSeconds = 1800,
    [Parameter()][ValidateRange(5, 300)][int]$IntervalSeconds = 15
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
$state = Load-TaskState
Assert-GhAuthenticated
Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)

if ([int]$state.prNumber -ne $PrNumber) {
    throw "PR #$PrNumber is not the recorded task PR #$($state.prNumber)."
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$last = @()
$lastHeadSha = $ExpectedHeadSha
$lastBaseSha = $null

while ((Get-Date) -lt $deadline) {
    $snapshot = Get-VerifiedTaskHeadSnapshot `
        -PrNumber $PrNumber `
        -State $state `
        -ExpectedHeadSha $ExpectedHeadSha
    $pr = $snapshot.pr
    $baseSha = [string]$snapshot.baseSha

    $checks = @(Get-CommitChecks -HeadSha $ExpectedHeadSha)
    $afterSnapshot = Get-VerifiedTaskHeadSnapshot `
        -PrNumber $PrNumber `
        -State $state `
        -ExpectedHeadSha $ExpectedHeadSha
    if ([string]$afterSnapshot.baseSha -ne $baseSha) {
        throw "PR base changed while waiting for checks. Retry for the current base."
    }
    $pr = $afterSnapshot.pr
    $last = $checks
    $lastBaseSha = $baseSha

    if ($checks.Count -eq 0) {
        Start-Sleep -Seconds $IntervalSeconds
        continue
    }

    $failed = @($checks | Where-Object {
        $bucket = [string]$_.bucket
        ($bucket -eq "fail") -or
        ($bucket -eq "cancel") -or
        (
            ([string]$_.name -in $script:RequiredCheckNames) -and
            ($bucket -eq "skipping")
        )
    })

    if ($failed.Count -gt 0) {
        @{
            status   = "failed"
            prNumber = $PrNumber
            baseSha  = $lastBaseSha
            headSha  = $lastHeadSha
            checks   = $checks
        } | ConvertTo-Json -Depth 10
        exit 2
    }

    # Do not declare success just because an unrelated check passed before
    # Quality/Test were created.
    $missing = @(Get-MissingRequiredCheckNames -Checks $checks)
    if ($missing.Count -gt 0) {
        Start-Sleep -Seconds $IntervalSeconds
        continue
    }

    $pending = @($checks | Where-Object {
        $bucket = [string]$_.bucket
        ($bucket -ne "pass") -and ($bucket -ne "skipping")
    })

    if ($pending.Count -eq 0) {
        @{
            status         = "passed"
            prNumber       = $PrNumber
            baseSha        = $lastBaseSha
            headSha        = $lastHeadSha
            requiredChecks = $script:RequiredCheckNames
            checks         = $checks
        } | ConvertTo-Json -Depth 10
        exit 0
    }

    Start-Sleep -Seconds $IntervalSeconds
}

@{
    status         = "timeout"
    prNumber       = $PrNumber
    baseSha        = $lastBaseSha
    headSha        = $lastHeadSha
    requiredChecks = $script:RequiredCheckNames
    checks         = $last
} | ConvertTo-Json -Depth 10

exit 3
