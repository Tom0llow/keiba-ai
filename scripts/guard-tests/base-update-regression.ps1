[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$scriptsRoot = [System.IO.Directory]::GetParent($PSScriptRoot).FullName
$agentRoot = Join-Path $scriptsRoot "agent"
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "guard-base-update-" + [guid]::NewGuid().ToString("N")
)
$null = New-Item -ItemType Directory -Path $testRoot

function Read-BaseUpdateTestAst {
    param([string]$Path)
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) { throw ($errors.Message -join "`n") }
    return $ast
}

$commonAst = Read-BaseUpdateTestAst -Path (Join-Path $agentRoot "_common.ps1")
$updateAst = Read-BaseUpdateTestAst -Path (Join-Path $agentRoot "update-task-base.ps1")
$functionNames = @(
    "Read-TaskStateRaw", "Load-TaskState", "Set-TaskStateFields",
    "Assert-NoProtectedTaskChanges", "Assert-GuardSourcesMatchCommit"
)
# Extract only functions and the locked action; do not execute a workspace wrapper.
foreach ($definition in $commonAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
}, $true)) {
    if ($definition.Name -in $functionNames) {
        Invoke-Expression $definition.Extent.Text
    }
    if ($definition.Name -eq "Write-TaskStateObject") {
        Invoke-Expression ($definition.Extent.Text -replace '^function Write-TaskStateObject', 'function Write-TestStateObject')
    }
}
$updateCommand = $updateAst.Find({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -eq "Invoke-WithGuardedWorkflowLock"
}, $true)
$actionText = $updateCommand.CommandElements[-1].ScriptBlock.Extent.Text
$updateAction = [scriptblock]::Create(
    $actionText.Substring(1, $actionText.Length - 2).Replace('$PSScriptRoot', '$agentRoot')
)
$script:TaskStateFileName = "codex-task.json"
$script:GuardedSourcePaths = @("scripts/agent/_common.ps1")
$script:FixtureCount = 0
$script:LockHeld = $false

function Assert-BaseUpdateTest {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}
function Assert-BaseUpdateThrows {
    param([scriptblock]$Action, [string]$Pattern)
    try { & $Action }
    catch {
        if ($_.Exception.Message -notmatch $Pattern) {
            throw "Unexpected failure '$($_.Exception.Message)' (expected $Pattern)."
        }
        return
    }
    throw "Expected failure matching $Pattern."
}
function Invoke-BaseUpdateTestAction {
    $script:LockHeld = $true
    try { & $updateAction }
    finally { $script:LockHeld = $false }
}
function Assert-GuardedWorkflowLockHeld {
    Assert-BaseUpdateTest $script:LockHeld "Task state changed outside the workflow lock."
}
function Get-TaskStatePath { return $script:StatePath }
function Get-RepoRoot { return $script:repoRoot }
function Get-CurrentBranch { return "agent/base-update-fixture" }
function Assert-AgentBranch { param([string]$Branch) }
function Assert-CleanWorkingTree {}
function Assert-NoExternalMergeDrivers {
    if ($script:ExternalMergeDriver) { throw "External merge drivers are not supported" }
}
function Get-OriginGitHubCoordinates {
    return [pscustomobject]@{ nameWithOwner = "fixture/project"; owner = "fixture" }
}
function Get-CurrentPowerShellPath { return "fixture-powershell.exe" }
function Write-GuardedResult { param($Result) $script:Result = $Result }
function Get-GitPathList {
    param([string[]]$Arguments)
    $script:DiffCalls.Add(($Arguments -join " "))
    if ($Arguments -contains "$($script:BaseSha)..$($script:MergeSha)") {
        return $script:PreparedPaths
    }
    return @("src/task.py")
}
function Invoke-ExternalText {
    param([string]$FilePath, [string[]]$ArgumentList)
    $script:PreflightCalls++
    Assert-BaseUpdateTest ($ArgumentList[0] -eq "-NoProfile" -and $ArgumentList[1] -eq "-File") (
        "Base update did not invoke the installed preflight through its file contract."
    )
    return (@{ baseSha = $script:BaseSha } | ConvertTo-Json -Compress)
}
function Write-TaskStateObject {
    param($State)
    if ($script:Fault -eq "before-prepare" -and [string]$State.pendingOperation -eq "update-base") {
        throw "fixture interruption before state write"
    }
    Write-TestStateObject -State $State
    if ($script:Fault -eq "after-prepare" -and [string]$State.pendingOperation -eq "update-base") {
        throw "fixture interruption after state write"
    }
}
function Invoke-Git {
    param([string[]]$Arguments)
    $script:GitCalls.Add(($Arguments -join " "))
    if (($Arguments -join " ") -eq "rev-parse HEAD") { return $script:LocalSha }
    if ($Arguments[0] -eq "rev-parse" -and $Arguments[1] -like "*:scripts/agent/_common.ps1") {
        return $script:SourceBlob
    }
    if ($Arguments[0] -eq "merge-tree") {
        if ($script:Conflict) { throw "fixture merge conflict" }
        return $script:TreeSha
    }
    if ($Arguments[0] -eq "commit-tree") { return $script:MergeSha }
    if ($Arguments[0] -eq "show") { return "$($script:ParentSha) $($script:PreparedBaseSha)" }
    if ($Arguments[0] -eq "merge" -and $Arguments[1] -eq "--ff-only") {
        $script:LocalSha = $Arguments[2]
        if ($script:Fault -eq "after-fast-forward") { throw "fixture interruption after fast forward" }
        return "fixture fast-forward success"
    }
    throw "Unexpected Git operation in the isolated fixture: $($Arguments -join ' ')"
}

function Reset-BaseUpdateFixture {
    param([int]$Version = 7)
    $script:FixtureCount++
    $script:repoRoot = Join-Path $testRoot ([guid]::NewGuid().ToString("N"))
    $gitDirectory = Join-Path $script:repoRoot ".git"
    $null = New-Item -ItemType Directory -Path $gitDirectory
    $script:StatePath = Join-Path $gitDirectory "codex-task.json"
    $script:ExpectedHeadSha = "a" * 40
    $script:ParentSha = $script:ExpectedHeadSha
    $script:LocalSha = $script:ExpectedHeadSha
    $script:InitialSha = "b" * 40
    $script:BaseSha = "c" * 40
    $script:PreparedBaseSha = $script:BaseSha
    $script:MergeSha = "d" * 40
    $script:TreeSha = "e" * 40
    $script:SourceBlob = "f" * 40
    $script:guardManifest = [pscustomobject]@{
        files = @([pscustomobject]@{ sourcePath = "scripts/agent/_common.ps1"; sourceBlob = $script:SourceBlob })
    }
    $script:PreparedPaths = @("src/task.py")
    $script:Fault = ""
    $script:Conflict = $false
    $script:ExternalMergeDriver = $false
    $script:PreflightCalls = 0
    $script:GitCalls = New-Object System.Collections.Generic.List[string]
    $script:DiffCalls = New-Object System.Collections.Generic.List[string]
    $script:Result = $null
    $state = [ordered]@{
        version = $Version
        repoRoot = $script:repoRoot
        repository = "fixture/project"
        repositoryOwner = "fixture"
        branch = "agent/base-update-fixture"
        base = "main"
        startSha = $script:InitialSha
        headSha = $script:ExpectedHeadSha
        taskName = "base-update-fixture"
        createdAt = "2026-10-11T00:00:00Z"
        prNumber = 17
        prUrl = "https://github.com/fixture/project/pull/17"
        mergeReadyPrNumber = 17
        mergeReadySha = $script:ExpectedHeadSha
        mergeReadyAt = "2026-10-11T00:00:00Z"
        mergeAttemptPrNumber = 17
        mergeAttemptHeadSha = $script:ExpectedHeadSha
        mergeAttemptMethod = "squash"
        mergeAttemptAt = "2026-10-11T00:00:01Z"
        pendingOperation = $null
        pendingCommitPhase = $null
        pendingCommitParentSha = $null
        pendingCommitTreeSha = $null
        pendingCommitMessage = $null
    }
    if ($Version -eq 7) {
        $state.initialStartSha = $script:InitialSha
        $state.pendingUpdateParentSha = $null
        $state.pendingUpdateBaseSha = $null
        $state.pendingUpdateHeadSha = $null
    }
    [System.IO.File]::WriteAllText($script:StatePath, ($state | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
}

function Assert-BaseUpdateCompleted {
    $state = Load-TaskState
    Assert-BaseUpdateTest ([int]$state.version -eq 7) "Completed update did not use state version 7."
    Assert-BaseUpdateTest ([string]$state.initialStartSha -eq $script:InitialSha) "Base update lost the initial task start SHA."
    Assert-BaseUpdateTest ([string]$state.startSha -eq $script:BaseSha) "Review diff base was not moved to the verified main SHA."
    Assert-BaseUpdateTest ([string]$state.headSha -eq $script:MergeSha -and $script:LocalSha -eq $script:MergeSha) "Local and recorded HEAD do not identify the prepared merge."
    foreach ($field in @(
        "pendingOperation", "pendingUpdateParentSha", "pendingUpdateBaseSha", "pendingUpdateHeadSha",
        "mergeReadyPrNumber", "mergeReadySha", "mergeReadyAt",
        "mergeAttemptPrNumber", "mergeAttemptHeadSha", "mergeAttemptMethod", "mergeAttemptAt"
    )) {
        Assert-BaseUpdateTest ([string]::IsNullOrEmpty([string]$state.$field)) "Completed base update retained '$field'."
    }
    Assert-BaseUpdateTest $script:Result.requiresPushAndReview "Updated task did not require a new push and review."
}

function Invoke-ConflictFixtureGit {
    param([string[]]$Arguments, [int]$ExpectedExitCode = 0)
    $gitArguments = @(
        "-C", $script:ConflictFixtureRoot,
        "-c", "core.hooksPath=$script:ConflictFixtureHooks",
        "-c", "core.fsmonitor=false",
        "-c", "core.autocrlf=false",
        "-c", "core.attributesFile=$script:ConflictFixtureEmptyConfig",
        "-c", "commit.gpgsign=false",
        "-c", "user.name=Guard Fixture",
        "-c", "user.email=guard-fixture@example.invalid"
    ) + $Arguments
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $script:FixtureGitPath @gitArguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $savedPreference }
    if ($exitCode -ne $ExpectedExitCode) {
        throw "Temporary Git fixture exited $exitCode, expected $ExpectedExitCode`: $output"
    }
    return ($output | ForEach-Object { $_.ToString() }) -join "`n"
}

function Assert-RealMergeTreeConflictPreservesWorktree {
    $script:ConflictFixtureRoot = Join-Path $testRoot "real-merge-conflict"
    $null = New-Item -ItemType Directory -Path $script:ConflictFixtureRoot
    $script:ConflictFixtureHooks = Join-Path $testRoot "empty-hooks"
    $null = New-Item -ItemType Directory -Path $script:ConflictFixtureHooks
    $script:ConflictFixtureEmptyConfig = Join-Path $testRoot "empty-git-config"
    [System.IO.File]::WriteAllText($script:ConflictFixtureEmptyConfig, "")
    $script:FixtureGitPath = [string](Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $savedGlobalConfig = [Environment]::GetEnvironmentVariable("GIT_CONFIG_GLOBAL", "Process")
    $savedNoSystem = [Environment]::GetEnvironmentVariable("GIT_CONFIG_NOSYSTEM", "Process")
    try {
        [Environment]::SetEnvironmentVariable("GIT_CONFIG_GLOBAL", $script:ConflictFixtureEmptyConfig, "Process")
        [Environment]::SetEnvironmentVariable("GIT_CONFIG_NOSYSTEM", "1", "Process")
        Invoke-ConflictFixtureGit -Arguments @("init", "--initial-branch=main") | Out-Null
        $conflictFile = Join-Path $script:ConflictFixtureRoot "conflict.txt"
        [System.IO.File]::WriteAllText($conflictFile, "base`n")
        Invoke-ConflictFixtureGit -Arguments @("add", "conflict.txt") | Out-Null
        Invoke-ConflictFixtureGit -Arguments @("commit", "-m", "fixture initial") | Out-Null
        Invoke-ConflictFixtureGit -Arguments @("switch", "-c", "agent/conflict-fixture") | Out-Null
        [System.IO.File]::WriteAllText($conflictFile, "task change`n")
        Invoke-ConflictFixtureGit -Arguments @("add", "conflict.txt") | Out-Null
        Invoke-ConflictFixtureGit -Arguments @("commit", "-m", "fixture task") | Out-Null
        $taskSha = Invoke-ConflictFixtureGit -Arguments @("rev-parse", "HEAD")
        Invoke-ConflictFixtureGit -Arguments @("switch", "main") | Out-Null
        [System.IO.File]::WriteAllText($conflictFile, "main change`n")
        Invoke-ConflictFixtureGit -Arguments @("add", "conflict.txt") | Out-Null
        Invoke-ConflictFixtureGit -Arguments @("commit", "-m", "fixture main") | Out-Null
        $baseSha = Invoke-ConflictFixtureGit -Arguments @("rev-parse", "HEAD")
        Invoke-ConflictFixtureGit -Arguments @("switch", "agent/conflict-fixture") | Out-Null
        $indexPath = Join-Path $script:ConflictFixtureRoot ".git/index"
        $indexHash = (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash
        $worktreeHash = (Get-FileHash -LiteralPath $conflictFile -Algorithm SHA256).Hash
        $status = Invoke-ConflictFixtureGit -Arguments @("status", "--porcelain=v1", "--untracked-files=all")
        Invoke-ConflictFixtureGit -Arguments @("merge-tree", "--write-tree", $taskSha, $baseSha) -ExpectedExitCode 1 | Out-Null
        Assert-BaseUpdateTest ((Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash -eq $indexHash) "Conflicting merge-tree changed the Git index."
        Assert-BaseUpdateTest ((Get-FileHash -LiteralPath $conflictFile -Algorithm SHA256).Hash -eq $worktreeHash) "Conflicting merge-tree changed worktree contents."
        Assert-BaseUpdateTest ((Invoke-ConflictFixtureGit -Arguments @("rev-parse", "HEAD")) -eq $taskSha) "Conflicting merge-tree moved HEAD."
        Assert-BaseUpdateTest ((Invoke-ConflictFixtureGit -Arguments @("status", "--porcelain=v1", "--untracked-files=all")) -ceq $status) "Conflicting merge-tree changed the worktree status."
    }
    finally {
        [Environment]::SetEnvironmentVariable("GIT_CONFIG_GLOBAL", $savedGlobalConfig, "Process")
        [Environment]::SetEnvironmentVariable("GIT_CONFIG_NOSYSTEM", $savedNoSystem, "Process")
    }
}

try {
    Reset-BaseUpdateFixture
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateCompleted

    Reset-BaseUpdateFixture -Version 6
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateCompleted

    Reset-BaseUpdateFixture
    $state = Read-TaskStateRaw
    $state.startSha = "7" * 40
    $script:LockHeld = $true
    try { Write-TestStateObject -State $state }
    finally { $script:LockHeld = $false }
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateCompleted

    Reset-BaseUpdateFixture
    $script:BaseSha = $script:InitialSha
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateTest (-not $script:Result.updated) "Unchanged main caused a base update."
    Assert-BaseUpdateTest (@($script:GitCalls | Where-Object { $_ -like "commit-tree *" }).Count -eq 0) "Unchanged main created a merge commit."

    Reset-BaseUpdateFixture
    $script:LocalSha = "1" * 40
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "Local HEAD changed"
    Assert-BaseUpdateTest ([string]::IsNullOrEmpty([string](Read-TaskStateRaw).pendingOperation)) "Local HEAD drift left a pending update."

    Reset-BaseUpdateFixture
    $script:SourceBlob = "2" * 40
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "workflow source changed"
    Assert-BaseUpdateTest (@($script:GitCalls | Where-Object { $_ -like "merge-tree *" }).Count -eq 0) "Changed guard source reached merge-tree."

    Reset-BaseUpdateFixture
    $script:Conflict = $true
    $stateHash = (Get-FileHash -LiteralPath $script:StatePath -Algorithm SHA256).Hash
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "fixture merge conflict"
    Assert-BaseUpdateTest ((Get-FileHash -LiteralPath $script:StatePath -Algorithm SHA256).Hash -eq $stateHash) "A merge conflict changed task state."
    Assert-BaseUpdateTest ($script:LocalSha -eq $script:ExpectedHeadSha) "A merge conflict moved local HEAD."

    Reset-BaseUpdateFixture
    $script:Fault = "before-prepare"
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "before state write"
    Assert-BaseUpdateTest ([string]::IsNullOrEmpty([string](Read-TaskStateRaw).pendingOperation)) "Interrupted initial write left a malformed pending update."
    $script:Fault = ""
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateCompleted

    Reset-BaseUpdateFixture
    $script:Fault = "after-prepare"
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "after state write"
    Assert-BaseUpdateThrows { Load-TaskState } "incomplete 'update-base'"
    $pending = Load-TaskState -AllowPendingOperation "update-base"
    Assert-BaseUpdateTest ([string]$pending.pendingUpdateParentSha -eq $script:ExpectedHeadSha) "Pending recovery was not bound to the original expected SHA."
    $script:Fault = ""
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateCompleted
    Assert-BaseUpdateTest ($script:PreflightCalls -eq 1) "Pending update reran preflight against a different main."

    Reset-BaseUpdateFixture
    $script:Fault = "after-fast-forward"
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "after fast forward"
    Assert-BaseUpdateTest ($script:LocalSha -eq $script:MergeSha) "Fixture did not interrupt after the fast-forward."
    $script:Fault = ""
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateCompleted
    Assert-BaseUpdateTest (@($script:GitCalls | Where-Object { $_ -like "merge --ff-only *" }).Count -eq 1) "Recovery repeated the completed fast-forward."

    Reset-BaseUpdateFixture
    $script:Fault = "after-prepare"
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "after state write"
    $script:Fault = ""
    $script:ExpectedHeadSha = "3" * 40
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "recorded task HEAD"

    Reset-BaseUpdateFixture
    $script:Fault = "after-prepare"
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "after state write"
    $script:Fault = ""
    $script:LocalSha = "4" * 40
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "HEAD changed during"

    Reset-BaseUpdateFixture
    $script:PreparedPaths = @("src/task.py", "nested/AGENTS.md")
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "trust boundary are forbidden"
    Assert-BaseUpdateTest ($script:LocalSha -eq $script:ExpectedHeadSha) "Protected-path rejection moved local HEAD."
    Assert-BaseUpdateTest ([string]::IsNullOrEmpty((Read-TaskStateRaw).pendingOperation)) "Protected-path rejection left pending state."

    Reset-BaseUpdateFixture
    $script:ExternalMergeDriver = $true
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "External merge drivers"
    Assert-BaseUpdateTest ([string]::IsNullOrEmpty((Read-TaskStateRaw).pendingOperation)) "External-driver rejection left pending state."
    Assert-BaseUpdateTest (@($script:GitCalls | Where-Object { $_ -like 'merge-tree*' }).Count -eq 0) "External driver reached merge-tree."

    Reset-BaseUpdateFixture
    $script:Fault = "after-prepare"
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "after state write"
    $script:Fault = ""
    $script:PreparedBaseSha = "5" * 40
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "different parents"

    Reset-BaseUpdateFixture
    $state = Read-TaskStateRaw
    $state.pendingUpdateHeadSha = "6" * 40
    $script:LockHeld = $true
    try { Write-TestStateObject -State $state }
    finally { $script:LockHeld = $false }
    Assert-BaseUpdateThrows { Load-TaskState } "without a pending base update"

    Reset-BaseUpdateFixture
    Invoke-BaseUpdateTestAction
    $completedSha = $script:LocalSha
    Invoke-BaseUpdateTestAction
    Assert-BaseUpdateTest ($script:LocalSha -eq $completedSha -and $script:Result.resumed) "Completed update did not reconcile a lost result."
    $script:LocalSha = "7" * 40
    Assert-BaseUpdateThrows { Invoke-BaseUpdateTestAction } "Local HEAD changed after"

    Assert-RealMergeTreeConflictPreservesWorktree
    Write-Output "Base update regression passed ($script:FixtureCount isolated fixtures and a real Git conflict fixture)."
}
finally {
    $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
    $temporaryPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedTestRoot.StartsWith($temporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing cleanup outside the temporary fixture directory."
    }
    Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
}
