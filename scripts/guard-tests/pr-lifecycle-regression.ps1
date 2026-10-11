[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$sourceRoot = [System.IO.Directory]::GetParent($PSScriptRoot).FullName
$agentRoot = Join-Path $sourceRoot "agent"
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "guard-pr-lifecycle-" + [guid]::NewGuid().ToString("N")
)
$null = New-Item -ItemType Directory -Path $testRoot

function Read-TestSourceAst {
    param([Parameter(Mandatory = $true)][string]$Path)
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $Path, [ref]$tokens, [ref]$errors
    )
    if ($errors.Count -gt 0) { throw ($errors.Message -join "`n") }
    return $ast
}

function Get-TestWorkflowAction {
    param([Parameter(Mandatory = $true)]$Ast)
    $command = $Ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-WithGuardedWorkflowLock"
    }, $true)
    $actionText = $command.CommandElements[-1].ScriptBlock.Extent.Text
    return [scriptblock]::Create($actionText.Substring(1, $actionText.Length - 2))
}

$commonAst = Read-TestSourceAst -Path (Join-Path $agentRoot "_common.ps1")
$createAst = Read-TestSourceAst -Path (Join-Path $agentRoot "create-pr.ps1")
$updateAst = Read-TestSourceAst -Path (Join-Path $agentRoot "update-pr.ps1")
$closeAst = Read-TestSourceAst -Path (Join-Path $agentRoot "close-task.ps1")
$functionNames = @(
    "Read-TaskStateRaw", "Write-TaskStateObject", "Load-TaskState", "Set-TaskStateFields",
    "Get-TaskOriginCoordinates", "Get-PrHeadIdentity", "Test-PrHeadMatchesTask",
    "Assert-PrMatchesTask", "Get-VerifiedTaskHeadSnapshot", "Set-GuardedPrBinding",
    "Read-TaskCloseReceipt", "Assert-TaskCloseIdentity"
)
# Extract functions and workflow actions only; never execute a mutable entry point.
foreach ($ast in @($commonAst, $createAst, $closeAst)) {
    foreach ($definition in $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
    }, $true)) {
        if ($definition.Name -in $functionNames) {
            Invoke-Expression $definition.Extent.Text
        }
    }
}
$createAction = Get-TestWorkflowAction -Ast $createAst
$updateAction = Get-TestWorkflowAction -Ast $updateAst
$closeAction = Get-TestWorkflowAction -Ast $closeAst
$script:CaseCount = 0
$script:LockHeld = $false
$script:TaskStateFileName = "codex-task.json"

function Assert-TestCondition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-TestThrows {
    param([scriptblock]$Action, [string]$Pattern)
    try { & $Action }
    catch {
        if ($_.Exception.Message -notmatch $Pattern) {
            throw "Unexpected failure: $($_.Exception.Message) (expected $Pattern)."
        }
        return
    }
    throw "Expected failure matching $Pattern."
}

function Invoke-TestAction {
    param([scriptblock]$Action)
    $script:LockHeld = $true
    try { & $Action }
    finally { $script:LockHeld = $false }
}

function Assert-GuardedWorkflowLockHeld {
    Assert-TestCondition $script:LockHeld "State mutation occurred without the test workflow lock."
}
function Get-TaskStatePath { return $script:StatePath }
function Get-RepoRoot { return $script:repoRoot }
function Get-CurrentBranch { return $script:CurrentBranch }
function Assert-AgentBranch { param([string]$Branch) }
function Assert-OriginExists {}
function Assert-GhAuthenticated {}
function Assert-CleanWorkingTree {}
function Assert-NoProtectedTaskChanges { param([string]$BaseSha) }
function Get-OriginGitHubCoordinates {
    return [pscustomobject]@{
        nameWithOwner = "fixture/project"
        owner = "fixture"
        origin = "https://github.com/fixture/project.git"
        pushUrl = "https://github.com/fixture/project.git"
    }
}
function Get-PrObject {
    param([int]$PrNumber)
    return ($script:TestPr | ConvertTo-Json -Depth 10 | ConvertFrom-Json)
}
function Write-GuardedResult { param($Result) $script:Result = $Result }
function Invoke-Git {
    param([string[]]$Arguments)
    $script:GitCalls.Add(($Arguments -join " "))
    if (($Arguments -join " ") -eq "rev-parse HEAD") { return $script:LocalSha }
    if ($Arguments[0] -eq "ls-remote") {
        if ($Arguments[-1] -eq "refs/heads/main") {
            return "$($script:BaseSha)`trefs/heads/main"
        }
        return "$($script:RemoteSha)`trefs/heads/$($script:TestPr.headRefName)"
    }
    throw "Unexpected Git operation in isolated test: $($Arguments -join ' ')"
}
function Invoke-GhRepo {
    param([string[]]$Arguments)
    Assert-GuardedWorkflowLockHeld
    $script:GhCalls.Add(($Arguments -join " "))
    switch ($Arguments[1]) {
        "list" {
            if ($script:HasExistingPr) { return "[$($script:TestPr | ConvertTo-Json -Depth 10 -Compress)]" }
            return "[]"
        }
        "edit" {
            $state = Read-TaskStateRaw
            foreach ($field in @(
                "mergeReadyPrNumber", "mergeReadySha", "mergeReadyAt",
                "mergeAttemptPrNumber", "mergeAttemptHeadSha", "mergeAttemptMethod", "mergeAttemptAt"
            )) {
                Assert-TestCondition ([string]::IsNullOrEmpty([string]$state.$field)) (
                    "Review evidence $field was retained before remote mutation."
                )
            }
            if ($script:FailEdit) { throw "fixture edit failed" }
        }
        "create" { $script:HasExistingPr = $true }
        "ready" { $script:TestPr.isDraft = $false; return "ready" }
        default { throw "Unexpected GitHub operation in isolated test." }
    }
    for ($index = 2; $index -lt $Arguments.Count; $index++) {
        if ($Arguments[$index] -eq "--title") { $script:TestPr.title = $Arguments[$index + 1] }
        if ($Arguments[$index] -eq "--body-file") {
            $bodyPath = $Arguments[$index + 1]
            Assert-TestCondition ((Split-Path -Parent $bodyPath) -eq (Split-Path -Parent $script:StatePath)) (
                "PR body file was captured outside the protected Git directory."
            )
            $bytes = [System.IO.File]::ReadAllBytes($bodyPath)
            Assert-TestCondition ($bytes.Length -lt 3 -or -not (
                $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
            )) "PR body file contains a UTF-8 BOM."
            $script:TestPr.body = [System.Text.UTF8Encoding]::new($false).GetString($bytes)
        }
        Assert-TestCondition ($Arguments[$index] -ne "--body") "PR body was passed as an inline native argument."
    }
    if ($script:ChangeHeadAfterEdit) { $script:TestPr.headRefOid = "d" * 40 }
    return "fixture remote success"
}

function Reset-TestFixture {
    param([string]$PathSuffix = "")
    $script:CaseCount++
    $script:repoRoot = Join-Path $testRoot ([guid]::NewGuid().ToString("N") + $PathSuffix)
    $gitDirectory = Join-Path $script:repoRoot ".git"
    $null = New-Item -ItemType Directory -Path $gitDirectory
    $script:StatePath = Join-Path $gitDirectory "codex-task.json"
    $script:PrNumber = 17
    $script:ExpectedHeadSha = "a" * 40
    $script:BaseSha = "b" * 40
    $script:LocalSha = $script:ExpectedHeadSha
    $script:RemoteSha = $script:ExpectedHeadSha
    $script:CurrentBranch = "agent/fixture-20261011"
    $script:Title = 'fix: handle "quoted" values'
    $script:Body = "first line`n" + [char]0x65e5 + [char]0x672c + [char]0x8a9e + "`nlast line`n"
    $script:Draft = $true
    $script:Ready = $false
    $script:updateTitle = $true
    $script:updateBody = $true
    $script:HasExistingPr = $true
    $script:FailEdit = $false
    $script:ChangeHeadAfterEdit = $false
    $script:GitCalls = New-Object System.Collections.Generic.List[string]
    $script:GhCalls = New-Object System.Collections.Generic.List[string]
    $script:Result = $null
    $script:TestPr = [pscustomobject]@{
        number = 17
        url = "https://github.com/fixture/project/pull/17"
        title = "previous title"
        body = "previous body"
        state = "OPEN"
        baseRefName = "main"
        baseRefOid = $script:BaseSha
        headRefName = $script:CurrentBranch
        headRefOid = $script:ExpectedHeadSha
        headRepository = "fixture/project"
        headRepositoryOwner = "fixture"
        isDraft = $true
        mergedAt = ""
    }
    $state = [ordered]@{
        version = 6
        repoRoot = $script:repoRoot
        repository = "fixture/project"
        repositoryOwner = "fixture"
        branch = $script:CurrentBranch
        base = "main"
        startSha = $script:BaseSha
        headSha = $script:ExpectedHeadSha
        taskName = "fixture"
        createdAt = "2026-10-11T00:00:00Z"
        prNumber = 17
        prUrl = $script:TestPr.url
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
    [System.IO.File]::WriteAllText($script:StatePath, ($state | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
}

function Set-TestPrMerged {
    $script:TestPr.state = "MERGED"
    $script:TestPr.mergedAt = "2026-10-11T00:01:00Z"
    Invoke-TestAction {
        Set-TaskStateFields -Fields @{
            mergeReadyPrNumber = $null; mergeReadySha = $null; mergeReadyAt = $null
            mergeAttemptPrNumber = $null; mergeAttemptHeadSha = $null
            mergeAttemptMethod = $null; mergeAttemptAt = $null
        } | Out-Null
    }
}

try {
    Reset-TestFixture
    Assert-TestThrows { Invoke-TestAction $createAction } "title/body differs"
    Assert-TestCondition ($script:GhCalls.Count -eq 1) "Conflicting create-pr silently mutated or reused the PR."

    Reset-TestFixture
    $script:TestPr.title = $script:Title
    $script:TestPr.body = $script:Body
    Invoke-TestAction $createAction
    Assert-TestCondition (-not $script:Result.created) "Identical create-pr did not reuse the PR."

    Reset-TestFixture
    $script:HasExistingPr = $false
    Invoke-TestAction $createAction
    Assert-TestCondition ($script:Result.created -and $script:TestPr.body -ceq $script:Body) "PR creation did not preserve its UTF-8 multiline body."
    Assert-TestCondition (@(Get-ChildItem -LiteralPath (Split-Path -Parent $script:StatePath) -Filter ".codex-pr-body-*").Count -eq 0) "Created PR body file was not cleaned up."

    Reset-TestFixture
    $script:Ready = $true
    Invoke-TestAction $updateAction
    Assert-TestCondition ($script:TestPr.title -ceq $script:Title -and $script:TestPr.body -ceq $script:Body -and -not $script:TestPr.isDraft) "PR update lost title/body or did not explicitly mark ready."
    Assert-TestCondition (@(Get-ChildItem -LiteralPath (Split-Path -Parent $script:StatePath) -Filter ".codex-pr-body-*").Count -eq 0) "Updated PR body file was not cleaned up."

    Reset-TestFixture
    Invoke-TestAction $updateAction
    Assert-TestCondition $script:TestPr.isDraft "PR update implicitly removed draft state."

    Reset-TestFixture
    $script:Body = ""
    Invoke-TestAction $updateAction
    Assert-TestCondition ($script:TestPr.body -ceq "") "An explicit empty body was not applied."

    Reset-TestFixture
    $script:FailEdit = $true
    Assert-TestThrows { Invoke-TestAction $updateAction } "fixture edit failed"
    Assert-TestCondition ([string]::IsNullOrEmpty([string](Read-TaskStateRaw).mergeReadySha)) "Failed edit retained review evidence."
    $script:FailEdit = $false
    Invoke-TestAction $updateAction

    Reset-TestFixture
    $script:RemoteSha = "c" * 40
    Assert-TestThrows { Invoke-TestAction $updateAction } "remote HEAD"
    Assert-TestCondition ($script:GhCalls.Count -eq 0) "PR updated despite a mismatched remote HEAD."

    Reset-TestFixture
    $script:TestPr.headRepository = "other/project"
    Assert-TestThrows { Invoke-TestAction $updateAction } "head repository"
    Assert-TestCondition ($script:GhCalls.Count -eq 0) "A foreign PR was updated."

    Reset-TestFixture
    $script:ChangeHeadAfterEdit = $true
    $script:Ready = $true
    Assert-TestThrows { Invoke-TestAction $updateAction } "PR HEAD"
    Assert-TestCondition $script:TestPr.isDraft "PR was marked ready after its HEAD changed."

    Reset-TestFixture
    Assert-TestThrows { Invoke-TestAction $closeAction } "MERGED state"
    Assert-TestCondition (Test-Path -LiteralPath $script:StatePath) "An unmerged task was closed."

    Reset-TestFixture
    Set-TestPrMerged
    $originalHash = (Get-FileHash -LiteralPath $script:StatePath -Algorithm SHA256).Hash
    Invoke-TestAction $closeAction
    Assert-TestCondition (-not (Test-Path -LiteralPath $script:StatePath)) "Merged task remained active."
    Assert-TestCondition ((Get-FileHash -LiteralPath $script:Result.archivePath -Algorithm SHA256).Hash -eq $originalHash) "Closing changed the original task state."
    $archivePath = $script:Result.archivePath
    Invoke-TestAction $closeAction
    Assert-TestCondition ($script:Result.archivePath -eq $archivePath) "Exact close retry produced a different archive."
    Assert-TestCondition ($script:GhCalls.Count -eq 0) "Closing a task mutated GitHub."

    Reset-TestFixture
    Set-TestPrMerged
    $script:CurrentBranch = "main"
    Invoke-TestAction $closeAction
    Assert-TestCondition ($script:GitCalls.Count -eq 0) "Closing from main performed a Git ref mutation."

    Reset-TestFixture
    Set-TestPrMerged
    $state = Read-TaskStateRaw
    $state.version = 7
    foreach ($entry in @{
        initialStartSha = $script:BaseSha
        pendingUpdateParentSha = $null
        pendingUpdateBaseSha = $null
        pendingUpdateHeadSha = $null
    }.GetEnumerator()) {
        $state | Add-Member -NotePropertyName $entry.Key -NotePropertyValue $entry.Value
    }
    Invoke-TestAction { Write-TaskStateObject -State $state }
    Invoke-TestAction $closeAction
    Assert-TestCondition (-not (Test-Path -LiteralPath $script:StatePath)) "Closing rejected task state version 7."

    Reset-TestFixture -PathSuffix ([string][char]0x65e5 + [char]0x672c + [char]0x8a9e)
    Set-TestPrMerged
    Invoke-TestAction $closeAction
    $archivePath = $script:Result.archivePath
    Invoke-TestAction $closeAction
    Assert-TestCondition ($script:Result.archivePath -eq $archivePath) "Exact close retry failed for a Unicode repository path."

    Reset-TestFixture
    Set-TestPrMerged
    Invoke-TestAction $closeAction
    [System.IO.File]::Move($script:Result.archivePath, $script:StatePath)
    Invoke-TestAction $closeAction
    Assert-TestCondition (-not (Test-Path -LiteralPath $script:StatePath)) "Close did not recover after its receipt had been written."

    Reset-TestFixture
    Set-TestPrMerged
    Invoke-TestAction $closeAction
    [System.IO.File]::AppendAllText($script:Result.archivePath, " ")
    Assert-TestThrows { Invoke-TestAction $closeAction } "archive hash differs"

    Reset-TestFixture
    Set-TestPrMerged
    $script:TestPr.headRefOid = "c" * 40
    Assert-TestThrows { Invoke-TestAction $closeAction } "MERGED state"
    Assert-TestCondition (Test-Path -LiteralPath $script:StatePath) "Closing accepted a different PR HEAD."

    Reset-TestFixture
    Set-TestPrMerged
    $state = Read-TaskStateRaw
    $state.pendingOperation = "start"
    Invoke-TestAction { Write-TaskStateObject -State $state }
    Assert-TestThrows { Invoke-TestAction $closeAction } "incomplete 'start'"

    Write-Output "PR lifecycle regression passed ($script:CaseCount isolated fixtures)."
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
