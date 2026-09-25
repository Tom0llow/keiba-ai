[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$guardManifest = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Assert-OriginExists

$Branch = $script:DefaultBaseBranch
$Workflow = "ci.yml"

$user = Get-GhLogin
$repository = Get-GitHubRepositoryBinding
$fetchUrl = [string]$repository.origin

$remoteMainText = Invoke-Git @("ls-remote", "--heads", $fetchUrl, "refs/heads/$Branch")
if ([string]::IsNullOrWhiteSpace($remoteMainText)) {
    throw "Remote branch 'origin/$Branch' was not found."
}
$remoteMainSha = ($remoteMainText -split "\s+")[0]

Invoke-Git @(
    "fetch", "--prune", $fetchUrl,
    "refs/heads/$Branch`:refs/remotes/origin/$Branch"
) | Out-Null
$fetchedMainSha = Invoke-Git @("rev-parse", "origin/$Branch")
if (-not [string]::Equals(
    $fetchedMainSha,
    $remoteMainSha,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "origin/$Branch changed during preflight. Retry against the new baseline."
}
Assert-GuardSourcesMatchCommit -Commit $remoteMainSha -Manifest $guardManifest

$null = Assert-MainProtectionVerified

# Baseline main must be green before starting an unrelated autonomous task.
$runJson = Invoke-GhRepo @(
    "run", "list",
    "--workflow", $Workflow,
    "--branch", $Branch,
    "--limit", "10",
    "--json", "databaseId,status,conclusion,headSha,url,name"
)
$runs = @($runJson | ConvertFrom-Json)
$run = @($runs | Where-Object { [string]$_.headSha -eq $remoteMainSha } | Select-Object -First 1)

if ($run.Count -eq 0) {
    throw "No '$Workflow' workflow run was found for current origin/$Branch HEAD $remoteMainSha."
}

$currentRun = $run[0]
if ([string]$currentRun.status -ne "completed" -or [string]$currentRun.conclusion -ne "success") {
    throw @"
Baseline CI for origin/$Branch is not green.

HEAD: $remoteMainSha
status: $($currentRun.status)
conclusion: $($currentRun.conclusion)
run: $($currentRun.url)

Fix the baseline before starting an unrelated autonomous task.
"@
}

Write-GuardedResult @{
    operation                = "github-preflight"
    authenticatedUser        = $user
    origin                   = $fetchUrl
    repository               = [string]$repository.nameWithOwner
    repositoryOwner          = [string]$repository.owner
    baseBranch               = $Branch
    baseSha                  = $remoteMainSha
    branchProtectionVerified = $true
    baselineCi               = "success"
    baselineCiUrl            = [string]$currentRun.url
}
