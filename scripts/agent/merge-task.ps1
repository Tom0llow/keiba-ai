[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$ExpectedHeadSha
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
$state = Load-TaskState -AllowDefaultBranch
Assert-OriginExists
Assert-GhAuthenticated
Assert-CleanWorkingTree

if ([int]$state.prNumber -ne $PrNumber) {
    throw "PR #$PrNumber is not the recorded task PR #$($state.prNumber)."
}
if ([string]::IsNullOrWhiteSpace([string]$state.mergeReadySha)) {
    throw "No recorded MERGE_READY state. Run merge-ready.ps1 first."
}
if ([int]$state.mergeReadyPrNumber -ne $PrNumber) {
    throw "MERGE_READY was recorded for a different PR. Run merge-ready.ps1 again."
}
if (-not [string]::Equals(
    [string]$state.mergeReadySha,
    $ExpectedHeadSha,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Expected SHA is not the SHA that was recorded as MERGE_READY."
}

$pr = Get-PrObject -PrNumber $PrNumber
Assert-PrMatchesTask -Pr $pr -State $state
$coordinates = Get-TaskOriginCoordinates -State $state
$fetchUrl = [string]$coordinates.origin
$pushUrl = [string]$coordinates.pushUrl
$recovered = $false

if ([string]$pr.state -eq "MERGED") {
    Assert-MergeAttemptMatchesTask `
        -State $state `
        -PrNumber $PrNumber `
        -ExpectedHeadSha $ExpectedHeadSha
    Assert-MergedPrMatchesTask `
        -Pr $pr `
        -State $state `
        -ExpectedHeadSha $ExpectedHeadSha
    $null = Assert-MainProtectionVerified
    if ((Get-CurrentBranch) -eq [string]$state.branch) {
        $localHeadSha = Invoke-Git @("rev-parse", "HEAD")
        if (-not [string]::Equals(
            $localHeadSha,
            $ExpectedHeadSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Local task HEAD changed after MERGE_READY. Preserve it for separate review."
        }
    }
    $after = $pr
    $recovered = $true
}
else {
    if ((Get-CurrentBranch) -ne [string]$state.branch) {
        throw "An unmerged task can be completed only from its recorded task branch."
    }
    Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)

    $snapshot = Get-VerifiedTaskHeadSnapshot `
        -PrNumber $PrNumber `
        -State $state `
        -ExpectedHeadSha $ExpectedHeadSha
    $pr = $snapshot.pr
    $baseSha = [string]$snapshot.baseSha
    $fetchUrl = [string]$snapshot.fetchUrl
    $pushUrl = [string]$snapshot.pushUrl
    $null = Assert-PrReadyForMerge -Pr $pr

    $checks = @(Get-CommitChecks -HeadSha $ExpectedHeadSha)
    Assert-ChecksReady -Checks $checks
    $snapshot = Get-VerifiedTaskHeadSnapshot `
        -PrNumber $PrNumber `
        -State $state `
        -ExpectedHeadSha $ExpectedHeadSha
    $pr = $snapshot.pr
    if ([string]$snapshot.baseSha -ne $baseSha) {
        throw "PR base changed during merge validation. Run MERGE_READY again."
    }
    $null = Assert-PrReadyForMerge -Pr $pr
    Assert-CleanWorkingTree
    Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)
    $null = Assert-MainProtectionVerified

    $checks = @(Get-CommitChecks -HeadSha $ExpectedHeadSha)
    Assert-ChecksReady -Checks $checks
    $snapshot = Get-VerifiedTaskHeadSnapshot `
        -PrNumber $PrNumber `
        -State $state `
        -ExpectedHeadSha $ExpectedHeadSha
    $pr = $snapshot.pr
    if ([string]$snapshot.baseSha -ne $baseSha) {
        throw "PR base changed during merge validation. Run MERGE_READY again."
    }
    $null = Assert-PrReadyForMerge -Pr $pr

    $state = Set-TaskStateFields @{
        mergeAttemptPrNumber = $PrNumber
        mergeAttemptHeadSha  = $ExpectedHeadSha
        mergeAttemptMethod   = "squash"
        mergeAttemptAt       = (Get-Date).ToUniversalTime().ToString("o")
    }

    # Exact reviewed HEAD + squash only. Remote branch deletion is handled
    # explicitly below so local Git state is not implicitly changed by `gh`.
    $mergeCommandError = $null
    try {
        Invoke-GhRepo @(
            "pr", "merge", "$PrNumber",
            "--squash",
            "--match-head-commit", $ExpectedHeadSha
        ) | Out-Null
    }
    catch {
        $mergeCommandError = $_
    }

    try {
        $after = Get-PrObject -PrNumber $PrNumber
        Assert-MergedPrMatchesTask `
            -Pr $after `
            -State $state `
            -ExpectedHeadSha $ExpectedHeadSha
    }
    catch {
        if ($null -ne $mergeCommandError) {
            throw $mergeCommandError
        }
        throw
    }
}

$cleanupMessages = New-Object System.Collections.Generic.List[string]
$taskBranch = [string]$state.branch
$cleanupComplete = $true

try {
    Invoke-Git @(
        "fetch", "--prune", $fetchUrl,
        "refs/heads/$($script:DefaultBaseBranch)`:refs/remotes/origin/$($script:DefaultBaseBranch)"
    ) | Out-Null
    Invoke-Git @("switch", $script:DefaultBaseBranch) | Out-Null
    Invoke-Git @("merge", "--ff-only", "origin/$($script:DefaultBaseBranch)") | Out-Null

    $remoteTask = Invoke-Git @("ls-remote", "--heads", $pushUrl, "refs/heads/$taskBranch")
    if ([string]::IsNullOrWhiteSpace($remoteTask)) {
        $cleanupMessages.Add("remote-branch-already-absent")
    }
    else {
        $remoteTaskSha = ($remoteTask -split "\s+")[0]
        if ([string]::Equals(
            $remoteTaskSha,
            $ExpectedHeadSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Invoke-Git @(
                "push",
                "--force-with-lease=refs/heads/$taskBranch`:$ExpectedHeadSha",
                $pushUrl,
                ":refs/heads/$taskBranch"
            ) | Out-Null
            $cleanupMessages.Add("remote-branch-deleted")
        }
        else {
            $cleanupMessages.Add("remote-branch-preserved-sha-mismatch:$remoteTaskSha")
        }
    }

    if (Test-GitSuccess @("show-ref", "--verify", "--quiet", "refs/heads/$taskBranch")) {
        $localTaskSha = Invoke-Git @("rev-parse", "refs/heads/$taskBranch")
        if ([string]::Equals(
            $localTaskSha,
            $ExpectedHeadSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            # Delete atomically only while the local ref still has the reviewed
            # value. This preserves concurrently-created local work.
            Invoke-Git @("update-ref", "-d", "refs/heads/$taskBranch", $ExpectedHeadSha) | Out-Null
            $cleanupMessages.Add("local-branch-deleted")
        }
        else {
            $cleanupMessages.Add("local-branch-preserved-sha-mismatch:$localTaskSha")
        }
    }
    else {
        $cleanupMessages.Add("local-branch-already-absent")
    }
}
catch {
    $cleanupComplete = $false
    $cleanupMessages.Add("manual-cleanup-required: $($_.Exception.Message)")
}

# Preserve task identity whenever cleanup is incomplete so the same approved
# PR/SHA can resume through the verified MERGED recovery path.
if ($cleanupComplete) {
    try {
        Remove-TaskState
    }
    catch {
        $cleanupComplete = $false
        $cleanupMessages.Add("task-state-cleanup-failed: $($_.Exception.Message)")
    }
}

Write-GuardedResult @{
    operation     = "merge-task"
    number        = [int]$after.number
    url           = [string]$after.url
    state         = [string]$after.state
    mergedAt      = [string]$after.mergedAt
    mergedHeadSha = $ExpectedHeadSha
    method        = [string]$state.mergeAttemptMethod
    recovered     = $recovered
    cleanupComplete = $cleanupComplete
    localCleanup  = ($cleanupMessages -join "; ")
}
if (-not $cleanupComplete) {
    throw "Remote merge succeeded, but guarded cleanup is incomplete. Retry merge-task.ps1 with the same PR number and approved HEAD SHA."
}
}
