[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)][ValidateSet("Metadata", "Diff", "Checks")][string]$Mode,
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
$before = $beforeSnapshot.pr
$baseSha = [string]$beforeSnapshot.baseSha
$diffBaseSha = [string]$state.startSha

switch ($Mode) {
    "Metadata" {
        $afterSnapshot = Get-VerifiedTaskHeadSnapshot `
            -PrNumber $PrNumber `
            -State $state `
            -ExpectedHeadSha $ExpectedHeadSha
        if ([string]$afterSnapshot.baseSha -ne $baseSha) {
            throw "PR base changed while collecting metadata. Retry the inspection."
        }
        @{
            status   = "ok"
            prNumber = $PrNumber
            baseSha  = $baseSha
            diffBaseSha = $diffBaseSha
            headSha  = $ExpectedHeadSha
            metadata = $before
        } | ConvertTo-Json -Depth 10
    }
    "Diff" {
        $diff = Get-ImmutableCommitDiff `
            -BaseSha $diffBaseSha `
            -HeadSha $ExpectedHeadSha
        $afterSnapshot = Get-VerifiedTaskHeadSnapshot `
            -PrNumber $PrNumber `
            -State $state `
            -ExpectedHeadSha $ExpectedHeadSha
        if ([string]$afterSnapshot.baseSha -ne $baseSha) {
            throw "PR base changed while collecting the immutable diff. Retry the inspection."
        }
        @{
            status   = "ok"
            prNumber = $PrNumber
            baseSha  = $baseSha
            diffBaseSha = $diffBaseSha
            headSha  = $ExpectedHeadSha
            diff     = $diff
        } | ConvertTo-Json -Depth 10
    }
    "Checks" {
        $checks = @(Get-CommitChecks -HeadSha $ExpectedHeadSha)
        $afterSnapshot = Get-VerifiedTaskHeadSnapshot `
            -PrNumber $PrNumber `
            -State $state `
            -ExpectedHeadSha $ExpectedHeadSha
        if ([string]$afterSnapshot.baseSha -ne $baseSha) {
            throw "PR base changed while collecting checks. Retry the inspection."
        }
        @{
            status   = "ok"
            prNumber = $PrNumber
            baseSha  = $baseSha
            diffBaseSha = $diffBaseSha
            headSha  = $ExpectedHeadSha
            checks   = $checks
        } | ConvertTo-Json -Depth 10
    }
}
