[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$null = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
$state = Load-TaskState
Assert-OriginExists
Assert-CleanWorkingTree
Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)

$branch = [string]$state.branch
$ahead = [int](Invoke-Git @("rev-list", "--count", "$($state.startSha)..HEAD"))
if ($ahead -lt 1) {
    throw "Task branch has no commits beyond its starting SHA."
}

$coordinates = Get-TaskOriginCoordinates -State $state
$pushUrl = [string]$coordinates.pushUrl
$localSha = Invoke-Git @("rev-parse", "HEAD")
if (-not [string]::Equals(
    $localSha,
    [string]$state.headSha,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Local HEAD does not match the HEAD recorded by guarded commit-task."
}
Invoke-Git @("push", $pushUrl, "HEAD:refs/heads/$branch") | Out-Null

$remoteText = Invoke-Git @("ls-remote", "--heads", $pushUrl, "refs/heads/$branch")
if ([string]::IsNullOrWhiteSpace($remoteText)) {
    throw "Remote task branch was not found after push."
}

$remoteSha = ($remoteText -split "\s+")[0]
if ($remoteSha -ne $localSha) {
    throw "Remote SHA '$remoteSha' != local HEAD '$localSha'."
}

Write-GuardedResult @{
    operation = "push-task"
    branch    = $branch
    commit    = $localSha
    remote    = [string]$coordinates.nameWithOwner
}
}
