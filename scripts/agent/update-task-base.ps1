[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
    [string]$ExpectedHeadSha
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
$guardManifest = Assert-TrustedGuardInstallation -RepoRoot $repoRoot
Invoke-WithGuardedWorkflowLock -RepoRoot $repoRoot -Action {
    $state = Load-TaskState -AllowPendingOperation "update-base"
    if ([string]$state.headSha -ne $ExpectedHeadSha) {
        $completedParent = $state.PSObject.Properties["completedUpdateParentSha"]
        $completedHead = $state.PSObject.Properties["completedUpdateHeadSha"]
        if (
            [string]::IsNullOrWhiteSpace([string]$state.pendingOperation) -and
            $null -ne $completedParent -and $null -ne $completedHead -and
            [string]$completedParent.Value -eq $ExpectedHeadSha -and
            [string]$completedHead.Value -eq [string]$state.headSha
        ) {
            Assert-CleanWorkingTree
            if ((Invoke-Git @("rev-parse", "HEAD")).Trim() -ne [string]$state.headSha) {
                throw "Local HEAD changed after the completed base update."
            }
            Write-GuardedResult @{
                operation = "update-task-base"; updated = $true; resumed = $true
                previousHeadSha = $ExpectedHeadSha; headSha = [string]$state.headSha
                baseSha = [string]$state.startSha; requiresPushAndReview = $true
            }
            return
        }
        throw "Base update does not match the recorded task HEAD."
    }
    Assert-CleanWorkingTree

    if ([string]::IsNullOrWhiteSpace([string]$state.pendingOperation)) {
        $localSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
        if ($localSha -ne $ExpectedHeadSha) { throw "Local HEAD changed before the base update." }
        Assert-NoProtectedTaskChanges -BaseSha ([string]$state.startSha)
        $preflight = Invoke-ExternalText -FilePath (Get-CurrentPowerShellPath) -ArgumentList @(
            "-NoProfile", "-File", (Join-Path $PSScriptRoot "github-preflight.ps1")
        ) | ConvertFrom-Json
        $baseSha = [string]$preflight.baseSha
        if ($baseSha -notmatch '^[0-9a-fA-F]{40,64}$') { throw "Preflight returned an invalid base SHA." }
        if ([string]$state.startSha -eq $baseSha) {
            Write-GuardedResult @{ operation = "update-task-base"; updated = $false; headSha = $localSha; baseSha = $baseSha }
            return
        }
        Assert-GuardSourcesMatchCommit -Commit $baseSha -Manifest $guardManifest
        Assert-NoExternalMergeDrivers
        # merge-tree leaves the user's index and worktree untouched on conflicts.
        $mergeOutput = Invoke-Git @("merge-tree", "--write-tree", $ExpectedHeadSha, $baseSha)
        $treeSha = ($mergeOutput -split "\r?\n")[0].Trim()
        if ($treeSha -notmatch '^[0-9a-fA-F]{40,64}$') { throw "Base merge returned an invalid tree SHA." }
        $mergeSha = (Invoke-Git @(
            "commit-tree", $treeSha, "-p", $ExpectedHeadSha, "-p", $baseSha,
            "-m", "Merge verified main into guarded task"
        )).Trim()
        if ($mergeSha -notmatch '^[0-9a-fA-F]{40,64}$') { throw "Base merge returned an invalid commit SHA." }
        Assert-NoProtectedTaskChanges -BaseSha $baseSha -HeadSha $mergeSha
        $initialSha = if ([int]$state.version -eq 7) { [string]$state.initialStartSha } else { [string]$state.startSha }
        $state = Set-TaskStateFields @{
            version = 7
            initialStartSha = $initialSha
            pendingOperation = "update-base"
            pendingUpdateParentSha = $ExpectedHeadSha
            pendingUpdateBaseSha = $baseSha
            pendingUpdateHeadSha = $mergeSha
            mergeReadyPrNumber = $null; mergeReadySha = $null; mergeReadyAt = $null
            mergeAttemptPrNumber = $null; mergeAttemptHeadSha = $null
            mergeAttemptMethod = $null; mergeAttemptAt = $null
        }
    }

    $parentSha = [string]$state.pendingUpdateParentSha
    $baseSha = [string]$state.pendingUpdateBaseSha
    $mergeSha = [string]$state.pendingUpdateHeadSha
    Assert-GuardSourcesMatchCommit -Commit $baseSha -Manifest $guardManifest
    $parents = (Invoke-Git @("show", "-s", "--format=%P", $mergeSha)).Trim()
    if ($parents -ne "$parentSha $baseSha") { throw "Prepared base update has different parents." }
    Assert-NoProtectedTaskChanges -BaseSha $baseSha -HeadSha $mergeSha
    $localSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
    if ($localSha -eq $parentSha) {
        Invoke-Git @("merge", "--ff-only", $mergeSha) | Out-Null
    }
    elseif ($localSha -ne $mergeSha) {
        throw "HEAD changed during the pending base update. Retry only the recorded update."
    }
    Assert-CleanWorkingTree
    if ((Invoke-Git @("rev-parse", "HEAD")).Trim() -ne $mergeSha) { throw "Base update did not reach its prepared HEAD." }
    Set-TaskStateFields -AllowPendingOperation "update-base" -Fields @{
        startSha = $baseSha
        headSha = $mergeSha
        completedUpdateParentSha = $parentSha
        completedUpdateHeadSha = $mergeSha
        pendingOperation = $null
        pendingUpdateParentSha = $null; pendingUpdateBaseSha = $null; pendingUpdateHeadSha = $null
    } | Out-Null
    Write-GuardedResult @{
        operation = "update-task-base"; updated = $true
        previousHeadSha = $parentSha; headSha = $mergeSha; baseSha = $baseSha
        requiresPushAndReview = $true
    }
}
