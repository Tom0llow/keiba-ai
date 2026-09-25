[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
    [string]$ExpectedHeadSha
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
$state = Load-TaskState
Assert-OriginExists
Assert-GhAuthenticated
Assert-CleanWorkingTree
Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)

if ([int]$state.prNumber -ne $PrNumber) {
    throw "PR #$PrNumber is not the recorded task PR #$($state.prNumber)."
}

$snapshot = Get-VerifiedTaskHeadSnapshot `
    -PrNumber $PrNumber `
    -State $state `
    -ExpectedHeadSha $ExpectedHeadSha
$pr = $snapshot.pr
$baseSha = [string]$snapshot.baseSha
$decision = Assert-PrReadyForMerge -Pr $pr

$checks = @(Get-CommitChecks -HeadSha $ExpectedHeadSha)
Assert-ChecksReady -Checks $checks

$snapshot = Get-VerifiedTaskHeadSnapshot `
    -PrNumber $PrNumber `
    -State $state `
    -ExpectedHeadSha $ExpectedHeadSha
$pr = $snapshot.pr
if ([string]$snapshot.baseSha -ne $baseSha) {
    throw "PR base changed during MERGE_READY validation. Retry review and CI."
}
$decision = Assert-PrReadyForMerge -Pr $pr
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
    throw "PR base changed during MERGE_READY validation. Retry review and CI."
}
$decision = Assert-PrReadyForMerge -Pr $pr

$now = (Get-Date).ToUniversalTime().ToString("o")
Set-TaskStateFields @{
    prNumber          = $PrNumber
    prUrl             = [string]$pr.url
    mergeReadyPrNumber = $PrNumber
    mergeReadySha     = $ExpectedHeadSha
    mergeReadyAt      = $now
    mergeAttemptPrNumber = $null
    mergeAttemptHeadSha  = $null
    mergeAttemptMethod   = $null
    mergeAttemptAt       = $null
} | Out-Null

Write-GuardedResult @{
    operation      = "merge-ready"
    ready          = $true
    prNumber       = $PrNumber
    url            = [string]$pr.url
    title          = [string]$pr.title
    baseSha        = $baseSha
    headSha        = $ExpectedHeadSha
    mergeable      = [string]$pr.mergeable
    mergeState     = [string]$pr.mergeStateStatus
    reviewDecision = $decision
    requiredChecks = $script:RequiredCheckNames
    checks         = $checks
    mergeReadyAt   = $now
}
}
