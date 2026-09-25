[CmdletBinding()]
param(
    [Parameter()][string]$CodexExecutablePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$originalLocation = Get-Location
$scriptsRoot = [System.IO.Directory]::GetParent($PSScriptRoot).FullName
$repoRoot = [System.IO.Directory]::GetParent($scriptsRoot).FullName
Set-Location -LiteralPath $repoRoot

$codexVersionFile = Join-Path $PSScriptRoot "codex-cli-version.txt"

function Assert-ReparsePathRejected {
    param([Parameter(Mandatory = $true)][string]$Implementation)

    $testRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-reparse-" + [guid]::NewGuid().ToString("N"))
    $targetPath = Join-Path $testRoot "target"
    $linkPath = Join-Path $testRoot "link"
    try {
        $null = New-Item -ItemType Directory -Path (Join-Path $targetPath "child") -Force
        $linkType = if ($env:OS -eq "Windows_NT") { "Junction" } else { "SymbolicLink" }
        $null = New-Item -ItemType $linkType -Path $linkPath -Target $targetPath

        $rejected = $false
        try {
            Assert-NoReparsePointInPath `
                -Path (Join-Path $linkPath "child") `
                -Role "$Implementation test path"
        }
        catch {
            $rejected = $true
        }
        if (-not $rejected) {
            throw "$Implementation did not reject an ancestor reparse point."
        }
    }
    finally {
        if (Test-Path -LiteralPath $linkPath) {
            [System.IO.Directory]::Delete($linkPath)
        }
        $tempPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
        if ($resolvedTestRoot.StartsWith(
            $tempPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item `
                -LiteralPath $resolvedTestRoot `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }
}

try {
    $failures = New-Object System.Collections.Generic.List[string]
    foreach ($file in (Get-ChildItem -LiteralPath "scripts" -Recurse -File -Filter "*.ps1")) {
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            $file.FullName,
            [ref]$tokens,
            [ref]$errors
        )
        foreach ($error in $errors) {
            $failures.Add(
                "$($file.FullName):$($error.Extent.StartLineNumber): $($error.Message)"
            )
        }
    }
    if ($failures.Count -gt 0) {
        throw ($failures -join "`n")
    }

    . (Join-Path $repoRoot "scripts/agent/_path-security.ps1")
    Assert-ReparsePathRejected -Implementation "Shared path security"
    foreach ($writableCandidate in @(
        (Join-Path $repoRoot "guard-installation"),
        (Join-Path ([System.IO.Path]::GetTempPath()) "guard-installation")
    )) {
        $writableCandidateRejected = $false
        try {
            Assert-PathOutsideKnownSandboxWritableRoots `
                -Path $writableCandidate `
                -RepoRoot $repoRoot `
                -Role "Guard installation test path"
        }
        catch {
            $writableCandidateRejected = $true
        }
        if (-not $writableCandidateRejected) {
            throw "Sandbox-writable guard installation path was not rejected: $writableCandidate"
        }
    }
    $workspaceShellTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "workspace-shell-test"
    $workspaceShellTestPath = Join-Path $workspaceShellTestRoot "pwsh.exe"
    if (-not (Test-GuardPathWithinRoot `
        -Path $workspaceShellTestPath `
        -Root $workspaceShellTestRoot
    )) {
        throw "Workspace-contained PowerShell path was not identified."
    }

    if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
        $aliasTestRoot = Join-Path (
            [System.IO.Path]::GetTempPath()
        ) ("guard-alias-" + [guid]::NewGuid().ToString("N"))
        try {
            $null = New-Item -ItemType Directory -Path $aliasTestRoot
            Assert-CanonicalPhysicalPath -Path $aliasTestRoot -Role "Normal test path"
            $extendedPath = "\\?\$aliasTestRoot"
            $aliasRejected = $false
            try {
                Assert-CanonicalPhysicalPath -Path $extendedPath -Role "Alias test path"
            }
            catch {
                $aliasRejected = $true
            }
            if (-not $aliasRejected) {
                throw "Extended-path alias was not rejected."
            }
        }
        finally {
            Remove-Item `
                -LiteralPath $aliasTestRoot `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }

        $currentShellPath = [System.IO.Path]::GetFullPath(
            [string](Get-Process -Id $PID).Path
        )
        Assert-TrustedPowerShellHostPath `
            -ShellPath $currentShellPath `
            -RepoRoot $repoRoot

        $workspaceShellRoot = Join-Path (
            [System.IO.Path]::GetTempPath()
        ) ("guard-workspace-shell-" + [guid]::NewGuid().ToString("N"))
        try {
            $fakeShellPath = Join-Path $workspaceShellRoot "pwsh.exe"
            $null = New-Item -ItemType Directory -Path $workspaceShellRoot
            [System.IO.File]::WriteAllBytes($fakeShellPath, [byte[]]@(0))
            $workspaceShellRejected = $false
            try {
                Assert-TrustedPowerShellHostPath `
                    -ShellPath $fakeShellPath `
                    -RepoRoot $workspaceShellRoot
            }
            catch {
                $workspaceShellRejected = $true
            }
            if (-not $workspaceShellRejected) {
                throw "Workspace-contained PowerShell executable was not rejected."
            }
        }
        finally {
            Remove-Item `
                -LiteralPath $workspaceShellRoot `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }

    $installerPath = Join-Path $repoRoot "scripts/setup/install-guarded-wrappers.ps1"
    $installerTokens = $null
    $installerErrors = $null
    $installerAst = [System.Management.Automation.Language.Parser]::ParseFile(
        $installerPath,
        [ref]$installerTokens,
        [ref]$installerErrors
    )
    foreach ($functionName in @(
        "Invoke-Checked",
        "Enter-GuardInstallationLock",
        "Publish-ImmutableGuardInstallation",
        "ConvertTo-StarlarkString",
        "New-GuardExecPolicyText"
    )) {
        $definition = @($installerAst.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        }, $true))
        if ($definition.Count -ne 1) {
            throw "Could not isolate installer function '$functionName'."
        }
        . ([scriptblock]::Create($definition[0].Extent.Text))
    }

    $installerLockRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-installer-lock-" + [guid]::NewGuid().ToString("N"))
    try {
        $installerDotGit = Join-Path $installerLockRoot ".git"
        $null = New-Item -ItemType Directory -Path $installerDotGit -Force
        $firstInstallerLock = Enter-GuardInstallationLock -DotGit $installerDotGit
        try {
            $parallelInstallerRejected = $false
            try {
                $null = Enter-GuardInstallationLock -DotGit $installerDotGit
            }
            catch {
                $parallelInstallerRejected = $true
            }
            if (-not $parallelInstallerRejected) {
                throw "Parallel guard installation was not rejected."
            }
        }
        finally {
            $firstInstallerLock.Dispose()
        }
    }
    finally {
        Remove-Item `
            -LiteralPath $installerLockRoot `
            -Recurse `
            -Force `
                -ErrorAction SilentlyContinue
    }

    $immutableStoreRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-immutable-" + [guid]::NewGuid().ToString("N"))
    $oldStream = $null
    try {
        $null = New-Item -ItemType Directory -Path $immutableStoreRoot
        $policyId = "a" * 24
        $sourceSha = "b" * 40
        $oldDirectoryName = Get-GuardInstallationDirectoryName `
            -RepositoryPolicyId $policyId `
            -SourceSha $sourceSha `
            -InstallationId ("1" * 32)
        $newDirectoryName = Get-GuardInstallationDirectoryName `
            -RepositoryPolicyId $policyId `
            -SourceSha $sourceSha `
            -InstallationId ("2" * 32)
        if ($oldDirectoryName -eq $newDirectoryName) {
            throw "Separate guard installations resolved to the same immutable path."
        }

        $oldGuardRoot = Join-Path $immutableStoreRoot $oldDirectoryName
        $newGuardRoot = Join-Path $immutableStoreRoot $newDirectoryName
        $newStagingRoot = Join-Path $immutableStoreRoot ".new-staging"
        $null = New-Item -ItemType Directory -Path $oldGuardRoot
        $null = New-Item -ItemType Directory -Path $newStagingRoot
        $oldWrapperPath = Join-Path $oldGuardRoot "running-wrapper.ps1"
        $newWrapperPath = Join-Path $newStagingRoot "new-wrapper.ps1"
        [System.IO.File]::WriteAllText($oldWrapperPath, "old")
        [System.IO.File]::WriteAllText($newWrapperPath, "new")
        $oldStream = [System.IO.File]::Open(
            $oldWrapperPath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )

        Publish-ImmutableGuardInstallation `
            -StagingRoot $newStagingRoot `
            -GuardRoot $newGuardRoot `
            -GuardStoreRoot $immutableStoreRoot
        if (
            -not (Test-Path -LiteralPath $oldWrapperPath -PathType Leaf) -or
            -not (Test-Path -LiteralPath (Join-Path $newGuardRoot "new-wrapper.ps1") -PathType Leaf)
        ) {
            throw "Publishing a new guard changed an existing running installation."
        }

        $collisionStagingRoot = Join-Path $immutableStoreRoot ".collision-staging"
        $null = New-Item -ItemType Directory -Path $collisionStagingRoot
        $collisionRejected = $false
        try {
            Publish-ImmutableGuardInstallation `
                -StagingRoot $collisionStagingRoot `
                -GuardRoot $newGuardRoot `
                -GuardStoreRoot $immutableStoreRoot
        }
        catch {
            $collisionRejected = $true
        }
        if (-not $collisionRejected) {
            throw "Immutable guard publication overwrote an existing installation."
        }
    }
    finally {
        if ($null -ne $oldStream) {
            $oldStream.Dispose()
        }
        Remove-Item `
            -LiteralPath $immutableStoreRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }

    $policyTestRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-policy-" + [guid]::NewGuid().ToString("N"))
    $testShell = Join-Path $policyTestRoot "shell/pwsh"
    $testGit = Join-Path $policyTestRoot "tools/git.exe"
    $testGh = Join-Path $policyTestRoot "tools/gh.exe"
    $testCodex = Join-Path $policyTestRoot "tools/codex.exe"
    $testStart = Join-Path $policyTestRoot "guard/scripts/agent/start-task.ps1"
    $testCommit = Join-Path $policyTestRoot "guard/scripts/agent/commit-task.ps1"
    $testMerge = Join-Path $policyTestRoot "guard/scripts/agent/merge-task.ps1"
    $testWorkspaceStart = Join-Path $policyTestRoot "workspace/scripts/agent/start-task.ps1"
    $testWorkspaceInstall = Join-Path $policyTestRoot "workspace/scripts/setup/install-guarded-wrappers.ps1"
    $policyText = New-GuardExecPolicyText `
        -Repository "example/repository" `
        -SourceSha ("a" * 40) `
        -ShellPath $testShell `
        -GitPath $testGit `
        -GhPath $testGh `
        -CodexPath $testCodex `
        -AutonomousPaths @($testStart, $testCommit) `
        -MergePath $testMerge `
        -ForbiddenWorkspacePaths @($testWorkspaceStart, $testWorkspaceInstall)

    foreach ($expectedText in @(
        'decision = "allow"',
        'decision = "prompt"',
        'decision = "forbidden"',
        (ConvertTo-StarlarkString -Value $testStart),
        (ConvertTo-StarlarkString -Value $testMerge),
        (ConvertTo-StarlarkString -Value $testWorkspaceStart),
        (ConvertTo-StarlarkString -Value $testGit),
        (ConvertTo-StarlarkString -Value $testGh),
        (ConvertTo-StarlarkString -Value $testCodex)
    )) {
        if (-not $policyText.Contains($expectedText)) {
            throw "Generated policy omitted expected contract text: $expectedText"
        }
    }

    $codexPath = if ([string]::IsNullOrWhiteSpace($CodexExecutablePath)) {
        Resolve-TrustedCommandPath `
            -Name "codex.exe" `
            -ExpectedFileNames @("codex.exe") `
            -RepoRoot $repoRoot `
            -Role "Native Codex CLI regression executable"
    }
    else {
        Assert-TrustedCommandPath `
            -CommandPath $CodexExecutablePath `
            -ExpectedFileNames @("codex.exe") `
            -RepoRoot $repoRoot `
            -Role "Native Codex CLI regression executable"
    }
    if ((Split-Path -Leaf $codexPath) -ne "codex.exe") {
        throw "Guard regression resolved a non-native Codex launcher: $codexPath"
    }
    $script:InstallerCommandOutputRoot = [System.IO.Path]::GetTempPath()
    $fakeNodeRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-fake-node-" + [guid]::NewGuid().ToString("N"))
    $originalPath = $env:PATH
    try {
        $null = New-Item -ItemType Directory -Path $fakeNodeRoot
        [System.IO.File]::WriteAllBytes(
            (Join-Path $fakeNodeRoot "node.exe"),
            [byte[]]@(0)
        )
        $env:PATH = "$fakeNodeRoot$([System.IO.Path]::PathSeparator)$originalPath"
        $codexVersionOutput = Invoke-Checked `
            -FilePath $codexPath `
            -ArgumentList @("--version")
    }
    finally {
        $env:PATH = $originalPath
        Remove-Item `
            -LiteralPath $fakeNodeRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }
    $codexVersion = Get-CodexCliVersionFromOutput -VersionOutput $codexVersionOutput
    Assert-CodexCliVersionAllowed `
        -Version $codexVersion `
        -VersionFile $codexVersionFile

    $policyPath = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText(
            $policyPath,
            $policyText,
            [System.Text.UTF8Encoding]::new($false)
        )
        $policyCases = @(
            [pscustomobject]@{
                expected = "allow"
                command  = @(
                    $testShell, "-NoProfile", "-File", $testStart,
                    "-TaskName", "example"
                )
            },
            [pscustomobject]@{
                expected = "prompt"
                command  = @(
                    $testShell, "-NoProfile", "-File", $testMerge,
                    "-PrNumber", "1", "-ExpectedHeadSha", ("0" * 40)
                )
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @(
                    $testShell, "-NoProfile", "-File", $testWorkspaceStart,
                    "-TaskName", "example"
                )
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @($testGit, "clean", "-fdx")
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @($testGit, "-C", ".", "clean", "-fdx")
            },
            [pscustomobject]@{
                expected = "prompt"
                command  = @($testGit, "status", "--short")
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @($testGh, "api", "user")
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @(
                    $testCodex, "exec",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "echo unsafe"
                )
            }
        )
        foreach ($case in $policyCases) {
            $arguments = @("execpolicy", "check", "--rules", $policyPath, "--") +
                @($case.command)
            $output = Invoke-Checked -FilePath $codexPath -ArgumentList $arguments
            $decision = [string](($output | ConvertFrom-Json).decision)
            if ($decision -ne [string]$case.expected) {
                throw "Generated policy decision '$decision' != '$($case.expected)'."
            }
        }

        $projectPolicyPath = Join-Path $repoRoot ".codex/rules/default.rules"
        $projectPolicyCases = @(
            [pscustomobject]@{
                expected = "forbidden"
                command  = @("git", "clean", "-f")
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @("git", "-C", ".", "clean", "-fdx")
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @("C:\Program Files\Git\cmd\git.exe", "clean", "-fd")
            },
            [pscustomobject]@{
                expected = "prompt"
                command  = @("git", "--no-pager", "clean", "-f")
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @("C:\Program Files\GitHub CLI\gh.exe", "api", "user")
            },
            [pscustomobject]@{
                expected = "forbidden"
                command  = @(
                    "codex", "exec",
                    "--dangerously-bypass-approvals-and-sandbox", "echo unsafe"
                )
            }
        )
        foreach ($case in $projectPolicyCases) {
            $arguments = @("execpolicy", "check", "--rules", $projectPolicyPath, "--") +
                @($case.command)
            $output = Invoke-Checked -FilePath $codexPath -ArgumentList $arguments
            $decision = [string](($output | ConvertFrom-Json).decision)
            if ($decision -ne [string]$case.expected) {
                throw "Project policy decision '$decision' != '$($case.expected)'."
            }
        }
    }
    finally {
        Remove-Item -LiteralPath $policyPath -Force -ErrorAction SilentlyContinue
    }

    . (Join-Path $repoRoot "scripts/agent/_common.ps1")
    Assert-ReparsePathRejected -Implementation "Runtime guard"

    $uninitializedGitRejected = $false
    try {
        $null = Invoke-Git @("status", "--short")
    }
    catch {
        $uninitializedGitRejected = $true
    }
    if (-not $uninitializedGitRejected) {
        throw "Runtime guard used PATH before its trusted Git path was initialized."
    }

    $ignoredPathTestRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-ignored-path-" + [guid]::NewGuid().ToString("N"))
    $previousGitPath = $script:GitPath
    $previousOutputRoot = $script:TrustedCommandOutputRoot
    try {
        $trustedTestGit = Resolve-TrustedCommandPath `
            -Name "git.exe" `
            -ExpectedFileNames @("git.exe") `
            -RepoRoot $repoRoot `
            -Role "Guard regression Git executable"
        $null = New-Item -ItemType Directory -Path $ignoredPathTestRoot
        & $trustedTestGit init --quiet $ignoredPathTestRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Could not initialize ignored-path regression repository."
        }
        $ignoredDotGit = Join-Path $ignoredPathTestRoot ".git"
        $script:GitPath = $trustedTestGit
        $script:TrustedCommandOutputRoot = $ignoredDotGit
        Set-Location -LiteralPath $ignoredPathTestRoot

        [System.IO.File]::WriteAllText(
            (Join-Path $ignoredPathTestRoot ".gitignore"),
            "**/AGENTS.md`n.agents/`n",
            [System.Text.UTF8Encoding]::new($false)
        )
        $null = New-Item `
            -ItemType Directory `
            -Path (Join-Path $ignoredPathTestRoot "ignored/deeper") `
            -Force
        $null = New-Item `
            -ItemType Directory `
            -Path (Join-Path $ignoredPathTestRoot ".agents") `
            -Force
        [System.IO.File]::WriteAllText(
            (Join-Path $ignoredPathTestRoot "ignored/deeper/AGENTS.md"),
            "hidden instruction",
            [System.Text.UTF8Encoding]::new($false)
        )
        [System.IO.File]::WriteAllText(
            (Join-Path $ignoredPathTestRoot ".agents/hidden.txt"),
            "hidden skill",
            [System.Text.UTF8Encoding]::new($false)
        )

        $ignoredProtected = @(Get-IgnoredProtectedPaths)
        foreach ($expectedIgnoredPath in @(
            ".agents/hidden.txt",
            "ignored/deeper/AGENTS.md"
        )) {
            if ($expectedIgnoredPath -notin $ignoredProtected) {
                throw "Ignored protected path was not enumerated: $expectedIgnoredPath"
            }
        }

        Remove-Item -LiteralPath (Join-Path $ignoredPathTestRoot "ignored/deeper/AGENTS.md") -Force
        Remove-Item -LiteralPath (Join-Path $ignoredPathTestRoot ".agents/hidden.txt") -Force
        [System.IO.File]::WriteAllText(
            (Join-Path $ignoredPathTestRoot ".gitignore"),
            "",
            [System.Text.UTF8Encoding]::new($false)
        )
        Invoke-Git @("config", "core.quotePath", "true") | Out-Null
        Invoke-Git @("add", "--", ".gitignore") | Out-Null
        Invoke-Git @(
            "-c", "user.name=Guard Test",
            "-c", "user.email=guard-test@example.invalid",
            "commit", "-m", "test: establish path baseline"
        ) | Out-Null
        $baselineSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
        $unicodeName = [string][char]0x3042
        [System.IO.File]::WriteAllText(
            (Join-Path $ignoredPathTestRoot ".agents/$unicodeName.txt"),
            "protected skill",
            [System.Text.UTF8Encoding]::new($false)
        )
        $quotedProtectedRejected = $false
        try {
            Assert-NoProtectedTaskChanges -BaseSha $baselineSha -IncludeWorktree
        }
        catch {
            $quotedProtectedRejected = $true
        }
        if (-not $quotedProtectedRejected) {
            throw "Git-quoted protected path bypassed trust-boundary validation."
        }

        Invoke-Git @("add", "--", ".agents") | Out-Null
        Invoke-Git @(
            "-c", "user.name=Guard Test",
            "-c", "user.email=guard-test@example.invalid",
            "commit", "-m", "test: record quoted path"
        ) | Out-Null
        $quotedCommitRejected = $false
        try {
            Assert-NoProtectedTaskChanges -BaseSha $baselineSha
        }
        catch {
            $quotedCommitRejected = $true
        }
        if (-not $quotedCommitRejected) {
            throw "Committed Git-quoted protected path bypassed trust-boundary validation."
        }

        $nestedBaselineSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
        $nestedUnicodeDirectory = Join-Path $ignoredPathTestRoot "nested/$unicodeName"
        $null = New-Item -ItemType Directory -Path $nestedUnicodeDirectory -Force
        [System.IO.File]::WriteAllText(
            (Join-Path $nestedUnicodeDirectory "AGENTS.md"),
            "protected instructions",
            [System.Text.UTF8Encoding]::new($false)
        )
        $quotedInstructionRejected = $false
        try {
            Assert-NoProtectedTaskChanges -BaseSha $nestedBaselineSha -IncludeWorktree
        }
        catch {
            $quotedInstructionRejected = $true
        }
        if (-not $quotedInstructionRejected) {
            throw "Git-quoted nested AGENTS.md bypassed trust-boundary validation."
        }

        [System.IO.File]::WriteAllText(
            (Join-Path $nestedUnicodeDirectory ".env"),
            "dummy value",
            [System.Text.UTF8Encoding]::new($false)
        )
        Invoke-Git @("add", "--", "nested/$unicodeName/.env") | Out-Null
        $quotedSensitiveRejected = $false
        try {
            Assert-NoSensitiveStagedPaths
        }
        catch {
            $quotedSensitiveRejected = $true
        }
        if (-not $quotedSensitiveRejected) {
            throw "Git-quoted staged .env path bypassed sensitive-path validation."
        }
        $stagedAfterRejection = Invoke-Git @("diff", "--cached", "--name-only")
        if (-not [string]::IsNullOrWhiteSpace($stagedAfterRejection)) {
            throw "Sensitive-path rejection left changes staged."
        }
    }
    finally {
        Set-Location -LiteralPath $repoRoot
        $script:GitPath = $previousGitPath
        $script:TrustedCommandOutputRoot = $previousOutputRoot
        $tempPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $resolvedIgnoredPathTestRoot = [System.IO.Path]::GetFullPath($ignoredPathTestRoot)
        if ($resolvedIgnoredPathTestRoot.StartsWith(
            $tempPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item `
                -LiteralPath $resolvedIgnoredPathTestRoot `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }

    $httpsCoordinates = ConvertTo-GitHubRemoteCoordinates `
        -Url "https://github.com/example/repository.git" `
        -Role "test"
    $sshCoordinates = ConvertTo-GitHubRemoteCoordinates `
        -Url "git@github.com:example/repository.git" `
        -Role "test"
    if (
        $httpsCoordinates.nameWithOwner -ne "example/repository" -or
        $sshCoordinates.nameWithOwner -ne "example/repository"
    ) {
        throw "GitHub remote identity parsing failed."
    }

    $lockTestRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-lock-" + [guid]::NewGuid().ToString("N"))
    try {
        $null = New-Item -ItemType Directory -Path (Join-Path $lockTestRoot ".git") -Force
        $firstLock = Enter-GuardedWorkflowLock -RepoRoot $lockTestRoot
        try {
            $nestedRejected = $false
            try {
                $null = Enter-GuardedWorkflowLock -RepoRoot $lockTestRoot
            }
            catch {
                $nestedRejected = $true
            }
            if (-not $nestedRejected) {
                throw "Nested guarded workflow lock was not rejected."
            }
        }
        finally {
            Exit-GuardedWorkflowLock -Lock $firstLock
        }
        $secondLock = Enter-GuardedWorkflowLock -RepoRoot $lockTestRoot
        Exit-GuardedWorkflowLock -Lock $secondLock
    }
    finally {
        $tempPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $resolvedLockTestRoot = [System.IO.Path]::GetFullPath($lockTestRoot)
        if ($resolvedLockTestRoot.StartsWith(
            $tempPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item `
                -LiteralPath $resolvedLockTestRoot `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }

    $script:MockGitDiff = "src/AGENTS.md"
    $script:MockIgnoredProtected = ""
    function Invoke-Git {
        param(
            [Parameter()][string[]]$Arguments = @(),
            [Parameter()][switch]$RawOutput
        )
        if ($Arguments[0] -eq "ls-files" -and $Arguments -contains "--ignored") {
            if ([string]::IsNullOrEmpty($script:MockIgnoredProtected)) { return "" }
            return "$($script:MockIgnoredProtected)`0"
        }
        if ($Arguments[0] -eq "diff" -or $Arguments[0] -eq "ls-files") {
            if ([string]::IsNullOrEmpty($script:MockGitDiff)) { return "" }
            return "$($script:MockGitDiff)`0"
        }
        if ($Arguments[0] -eq "status") { return "" }
        throw "Unexpected mocked Git call: $($Arguments -join ' ')"
    }

    foreach ($protectedInstructionPath in @(
        "src/AGENTS.md",
        "nested/deeper/AGENTS.override.md",
        "scripts/guard-tests/guard-regression.ps1"
    )) {
        $script:MockGitDiff = $protectedInstructionPath
        $rejected = $false
        try {
            Assert-NoProtectedTaskChanges -BaseSha ("a" * 40)
        }
        catch {
            $rejected = $true
        }
        if (-not $rejected) {
            throw "Protected trust-boundary path was not rejected: $protectedInstructionPath"
        }
    }
    $script:MockGitDiff = "src/keiba_ai/example.py"
    Assert-NoProtectedTaskChanges -BaseSha ("a" * 40)

    $script:MockIgnoredProtected = "ignored/deeper/AGENTS.md"
    $ignoredProtectedRejected = $false
    try {
        Assert-NoProtectedTaskChanges -BaseSha ("a" * 40) -IncludeWorktree
    }
    catch {
        $ignoredProtectedRejected = $true
    }
    if (-not $ignoredProtectedRejected) {
        throw "An ignored untracked AGENTS.md bypassed protected-path validation."
    }

    $ignoredProtectedCleanRejected = $false
    try {
        Assert-CleanWorkingTree
    }
    catch {
        $ignoredProtectedCleanRejected = $true
    }
    if (-not $ignoredProtectedCleanRejected) {
        throw "A clean-tree check accepted an ignored workflow trust-boundary path."
    }
    $script:MockIgnoredProtected = ""

    $trailingCommitWhitespaceRejected = $false
    try {
        Assert-ConventionalCommitMessage -Message "fix: guarded state "
    }
    catch {
        $trailingCommitWhitespaceRejected = $true
    }
    if (-not $trailingCommitWhitespaceRejected) {
        throw "Commit message trailing whitespace was not rejected."
    }

    $script:MockHeadSha = "a" * 40
    $script:MockBaseSha = "b" * 40
    $script:MockPr = [pscustomobject]@{
        number              = 7
        baseRefName         = "main"
        baseRefOid          = $script:MockBaseSha
        headRefName         = "agent/example"
        headRefOid          = $script:MockHeadSha
        headRepositoryOwner = "example"
        headRepository      = "example/repository"
    }
    $script:MockState = [pscustomobject]@{
        prNumber        = 7
        base            = "main"
        branch          = "agent/example"
        repositoryOwner = "example"
        repository      = "example/repository"
        headSha         = $script:MockHeadSha
        mergeReadyPrNumber = 7
        mergeReadySha   = $script:MockHeadSha
        mergeAttemptPrNumber = 7
        mergeAttemptHeadSha  = $script:MockHeadSha
        mergeAttemptMethod   = "squash"
        mergeAttemptAt       = "2026-09-24T00:00:00Z"
    }
    function Get-PrObject {
        param([Parameter(Mandatory = $true)][int]$PrNumber)
        return $script:MockPr
    }
    function Get-OriginGitHubCoordinates {
        return [pscustomobject]@{
            owner         = "example"
            repository    = "repository"
            nameWithOwner = "example/repository"
            origin        = "https://github.com/example/repository.git"
            pushUrl       = "https://github.com/example/repository.git"
        }
    }
    $script:MockImmutableDiffCalls = New-Object System.Collections.Generic.List[string]
    function Invoke-Git {
        param([Parameter()][string[]]$Arguments = @())
        if ($Arguments[0] -eq "rev-parse") { return $script:MockHeadSha }
        if ($Arguments[0] -eq "ls-remote") {
            if ($Arguments[-1] -eq "refs/heads/main") {
                return "$($script:MockBaseSha)`trefs/heads/main"
            }
            return "$($script:MockHeadSha)`trefs/heads/agent/example"
        }
        if ($Arguments[0] -eq "cat-file") { return "" }
        if ($Arguments[0] -eq "merge-base") { return [string]$Arguments[1] }
        if ($Arguments[0] -eq "diff") {
            $script:MockImmutableDiffCalls.Add(($Arguments -join " "))
            return "immutable diff"
        }
        throw "Unexpected mocked Git call: $($Arguments -join ' ')"
    }

    $null = Get-VerifiedTaskHeadSnapshot `
        -PrNumber 7 `
        -State $script:MockState `
        -ExpectedHeadSha $script:MockHeadSha

    $script:GitHubRepositoryBinding = [pscustomobject]@{
        host          = "github.com"
        nameWithOwner = "example/repository"
    }
    $script:MockApiHeadSha = $script:MockHeadSha
    $script:MockApiEndpoints = New-Object System.Collections.Generic.List[string]
    function Invoke-GhRepositoryApi {
        param(
            [Parameter(Mandatory = $true)][string]$Endpoint,
            [Parameter()][string]$Accept = "application/vnd.github+json"
        )
        $script:MockApiEndpoints.Add("$Accept $Endpoint")
        if ($Endpoint -match '/check-runs\?') {
            return @{
                total_count = 2
                check_runs  = @(
                    @{
                        head_sha = $script:MockApiHeadSha
                        status = "completed"
                        conclusion = "success"
                        name = "Quality"
                        details_url = "https://example.invalid/quality"
                        app = @{ slug = "github-actions" }
                    },
                    @{
                        head_sha = $script:MockApiHeadSha
                        status = "completed"
                        conclusion = "success"
                        name = "Test"
                        details_url = "https://example.invalid/test"
                        app = @{ slug = "github-actions" }
                    }
                )
            } | ConvertTo-Json -Depth 10
        }
        if ($Endpoint -match '/status\?') {
            return @{
                sha = $script:MockApiHeadSha
                total_count = 0
                statuses = @()
            } | ConvertTo-Json -Depth 10
        }
        throw "Unexpected mocked GitHub API endpoint: $Endpoint"
    }

    $mockChecks = @(Get-CommitChecks -HeadSha $script:MockHeadSha)
    Assert-ChecksReady -Checks $mockChecks
    $mockDiff = Get-ImmutableCommitDiff `
        -BaseSha $script:MockBaseSha `
        -HeadSha $script:MockHeadSha
    if (
        $mockDiff -ne "immutable diff" -or
        $script:MockImmutableDiffCalls.Count -ne 1 -or
        -not $script:MockImmutableDiffCalls[0].Contains("--no-ext-diff") -or
        -not $script:MockImmutableDiffCalls[0].Contains("--no-textconv") -or
        -not $script:MockImmutableDiffCalls[0].Contains(
            "$($script:MockBaseSha)...$($script:MockHeadSha)"
        )
    ) {
        throw "Immutable comparison was not bound to exact base and HEAD SHAs."
    }

    $script:MockApiHeadSha = "c" * 40
    $mismatchedCheckShaRejected = $false
    try {
        $null = Get-CommitChecks -HeadSha $script:MockHeadSha
    }
    catch {
        $mismatchedCheckShaRejected = $true
    }
    if (-not $mismatchedCheckShaRejected) {
        throw "Check API response for a different HEAD SHA was accepted."
    }
    $script:MockApiHeadSha = $script:MockHeadSha

    $mergedPr = $script:MockPr.PSObject.Copy()
    $mergedPr | Add-Member -NotePropertyName state -NotePropertyValue "MERGED"
    $mergedPr | Add-Member -NotePropertyName mergedAt -NotePropertyValue "2026-09-24T00:00:00Z"
    Assert-MergedPrMatchesTask `
        -Pr $mergedPr `
        -State $script:MockState `
        -ExpectedHeadSha $script:MockHeadSha
    Assert-MergeAttemptMatchesTask `
        -State $script:MockState `
        -PrNumber 7 `
        -ExpectedHeadSha $script:MockHeadSha

    $mismatchedAttemptState = $script:MockState.PSObject.Copy()
    $mismatchedAttemptState.mergeAttemptHeadSha = "d" * 40
    $mergeAttemptMismatchRejected = $false
    try {
        Assert-MergeAttemptMatchesTask `
            -State $mismatchedAttemptState `
            -PrNumber 7 `
            -ExpectedHeadSha $script:MockHeadSha
    }
    catch {
        $mergeAttemptMismatchRejected = $true
    }
    if (-not $mergeAttemptMismatchRejected) {
        throw "Merged PR recovery accepted a different recorded merge-attempt HEAD."
    }

    $mergedPr.headRefOid = "c" * 40
    $mergedHeadMismatchRejected = $false
    try {
        Assert-MergedPrMatchesTask `
            -Pr $mergedPr `
            -State $script:MockState `
            -ExpectedHeadSha $script:MockHeadSha
    }
    catch {
        $mergedHeadMismatchRejected = $true
    }
    if (-not $mergedHeadMismatchRejected) {
        throw "Merged PR recovery accepted a different HEAD."
    }
    $mergedPr.headRefOid = $script:MockHeadSha

    $mismatchedState = $script:MockState.PSObject.Copy()
    $mismatchedState.repository = "attacker/repository"
    $originMismatchRejected = $false
    try {
        $null = Get-TaskOriginCoordinates -State $mismatchedState
    }
    catch {
        $originMismatchRejected = $true
    }
    if (-not $originMismatchRejected) {
        throw "Task repository mismatch was not rejected."
    }

    $script:MockPr.headRefOid = "b" * 40
    $headChangeRejected = $false
    try {
        $null = Get-VerifiedTaskHeadSnapshot `
            -PrNumber 7 `
            -State $script:MockState `
            -ExpectedHeadSha $script:MockHeadSha
    }
    catch {
        $headChangeRejected = $true
    }
    if (-not $headChangeRejected) {
        throw "PR HEAD change during check collection was not rejected."
    }

    $stateTestRoot = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("guard-state-" + [guid]::NewGuid().ToString("N"))
    $statePath = Join-Path $stateTestRoot "codex-task.json"
    try {
        $null = New-Item -ItemType Directory -Path $stateTestRoot -Force
        function Get-TaskStatePath { return $statePath }
        $script:WorkflowLock = [pscustomobject]@{ test = $true }
        Write-TaskStateObject -State ([ordered]@{ version = 1; value = "first" })
        Write-TaskStateObject -State ([ordered]@{ version = 1; value = "second" })
        $writtenState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ([string]$writtenState.value -ne "second") {
            throw "Atomic task-state replacement did not persist the complete new state."
        }
        $temporaryStateFiles = @(Get-ChildItem -LiteralPath $stateTestRoot | Where-Object {
            $_.Name.EndsWith(".tmp") -or $_.Name.EndsWith(".bak")
        })
        if ($temporaryStateFiles.Count -ne 0) {
            throw "Atomic task-state replacement left temporary files behind."
        }

        function Get-RepoRoot { return $repoRoot }
        function Get-CurrentBranch { return "agent/example" }
        $validTaskState = [ordered]@{
            version              = 6
            repoRoot             = $repoRoot
            repository           = "example/repository"
            repositoryOwner      = "example"
            branch               = "agent/example"
            base                 = "main"
            startSha             = "a" * 40
            headSha              = "a" * 40
            taskName             = "example"
            createdAt            = "2026-09-24T00:00:00Z"
            prNumber             = 7
            prUrl                = "https://github.com/example/repository/pull/7"
            mergeReadyPrNumber   = 7
            mergeReadySha        = "a" * 40
            mergeReadyAt         = "2026-09-24T00:01:00Z"
            mergeAttemptPrNumber = 7
            mergeAttemptHeadSha  = "a" * 40
            mergeAttemptMethod   = "squash"
            mergeAttemptAt       = "2026-09-24T00:02:00Z"
            pendingOperation       = $null
            pendingCommitPhase     = $null
            pendingCommitParentSha = $null
            pendingCommitTreeSha   = $null
            pendingCommitMessage   = $null
        }
        Write-TaskStateObject -State $validTaskState
        $null = Load-TaskState

        $validTaskState.mergeReadyPrNumber = 8
        Write-TaskStateObject -State $validTaskState
        $readyPrMismatchRejected = $false
        try {
            $null = Load-TaskState
        }
        catch {
            $readyPrMismatchRejected = $true
        }
        if (-not $readyPrMismatchRejected) {
            throw "MERGE_READY state was accepted for a different PR number."
        }
        $validTaskState.mergeReadyPrNumber = 7

        $validTaskState.pendingOperation = "commit"
        $validTaskState.pendingCommitPhase = "staging"
        $validTaskState.pendingCommitParentSha = "a" * 40
        $validTaskState.pendingCommitMessage = "fix: resume guarded commit"
        Write-TaskStateObject -State $validTaskState
        $pendingCommitBlocked = $false
        try {
            $null = Load-TaskState
        }
        catch {
            $pendingCommitBlocked = $true
        }
        if (-not $pendingCommitBlocked) {
            throw "A pending commit was exposed to unrelated guarded wrappers."
        }
        $null = Load-TaskState -AllowPendingOperation "commit"
        $validTaskState.pendingOperation = $null
        $validTaskState.pendingCommitPhase = $null
        $validTaskState.pendingCommitParentSha = $null
        $validTaskState.pendingCommitMessage = $null

        $validTaskState.mergeAttemptAt = $null
        Write-TaskStateObject -State $validTaskState
        $partialAttemptRejected = $false
        try {
            $null = Load-TaskState
        }
        catch {
            $partialAttemptRejected = $true
        }
        if (-not $partialAttemptRejected) {
            throw "A partial merge-attempt task-state record was not rejected."
        }
    }
    finally {
        $script:WorkflowLock = $null
        $tempPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $resolvedStateTestRoot = [System.IO.Path]::GetFullPath($stateTestRoot)
        if ($resolvedStateTestRoot.StartsWith(
            $tempPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item `
                -LiteralPath $resolvedStateTestRoot `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }

    $configureProtection = Get-Content `
        -LiteralPath "scripts/github/configure-main-protection.ps1" `
        -Raw
    $verifyProtection = Get-Content `
        -LiteralPath "scripts/github/verify-main-protection.ps1" `
        -Raw
    if (
        -not $configureProtection.Contains('app_id  = $githubActionsAppId') -or
        -not $verifyProtection.Contains('$_.appId -eq $expectedCheck.appId') -or
        -not $verifyProtection.Contains('$configuredChecks.Count -eq $expectedChecks.Count')
    ) {
        throw "Branch-protection checks are no longer bound exactly to an application ID."
    }

    $installerText = Get-Content -LiteralPath $installerPath -Raw
    foreach ($requiredInstallerControl in @(
        '$repoRoot',
        'Assert-NoReparsePointInPath',
        'Assert-CanonicalPhysicalPath',
        'Assert-TrustedPowerShellHostPath',
        'Enter-GuardInstallationLock',
        'Publish-ImmutableGuardInstallation',
        '$newGuardPublished',
        '$gitPath',
        '$ghPath',
        '$codexPath',
        '$codexVersion',
        '$policyRollbackPath',
        '$retainPolicyRollback',
        "Previous policy backup retained at",
        'Assert-PathOutsideKnownSandboxWritableRoots',
        '$script:InstallerCommandOutputRoot = $dotGit'
    )) {
        if (-not $installerText.Contains($requiredInstallerControl)) {
            throw "Installer safety control is missing: $requiredInstallerControl"
        }
    }
    $commonText = Get-Content -LiteralPath "scripts/agent/_common.ps1" -Raw
    if (
        $installerText.Contains('[System.IO.Path]::GetTempFileName()') -or
        $commonText.Contains('[System.IO.Path]::GetTempFileName()') -or
        -not $commonText.Contains('$script:TrustedCommandOutputRoot = $dotGit') -or
        -not $commonText.Contains('Assert-PathOutsideKnownSandboxWritableRoots')
    ) {
        throw "Trusted wrappers must keep command output and guard paths outside sandbox-writable temporary storage."
    }
    if (
        $installerText.Contains('"codex.cmd"') -or
        $installerText.Contains('"codex.ps1"') -or
        $commonText.Contains('"codex.cmd"') -or
        $commonText.Contains('"codex.ps1"') -or
        -not $installerText.Contains('-ExpectedFileNames @("codex.exe")') -or
        -not $commonText.Contains('-ExpectedFileNames @("codex.exe")')
    ) {
        throw "Trusted Codex execution must be bound to native codex.exe, never a Node launcher shim."
    }

    $startTaskText = Get-Content -LiteralPath "scripts/agent/start-task.ps1" -Raw
    $saveStateIndex = $startTaskText.LastIndexOf("Save-TaskState")
    $createBranchIndex = $startTaskText.LastIndexOf('Invoke-Git @("switch", "--create"')
    $completeStartIndex = $startTaskText.LastIndexOf('pendingOperation = $null')
    if (
        $saveStateIndex -lt 0 -or
        $createBranchIndex -le $saveStateIndex -or
        $completeStartIndex -le $createBranchIndex
    ) {
        throw "Task start no longer records a recoverable intent before creating its branch."
    }

    $commitTaskText = Get-Content -LiteralPath "scripts/agent/commit-task.ps1" -Raw
    foreach ($commitRecoveryControl in @(
        'pendingCommitPhase     = "staging"',
        'pendingCommitPhase   = "committing"',
        'Assert-PendingCommitResult',
        '-AllowPendingOperation "commit"'
    )) {
        if (-not $commitTaskText.Contains($commitRecoveryControl)) {
            throw "Commit recovery control is missing: $commitRecoveryControl"
        }
    }

    $ciText = Get-Content -LiteralPath ".github/workflows/ci.yml" -Raw
    foreach ($ciCompatibilityControl in @(
        'foreach ($version in $versions)',
        'pwsh.exe -NoProfile -File',
        'WindowsPowerShell/v1.0/powershell.exe',
        '-CodexExecutablePath $nativeCodex[0].FullName'
    )) {
        if (-not $ciText.Contains($ciCompatibilityControl)) {
            throw "CI compatibility coverage is missing: $ciCompatibilityControl"
        }
    }
    if ($ciText.Contains('Select-Object -First 1')) {
        throw "CI validates only the first allowed Codex CLI version."
    }

    foreach ($wrapperContract in @(
        [pscustomobject]@{
            path = "scripts/agent/wait-ci.ps1"
            text = "ExpectedHeadSha"
        },
        [pscustomobject]@{
            path = "scripts/agent/inspect-pr.ps1"
            text = "Get-ImmutableCommitDiff"
        },
        [pscustomobject]@{
            path = "scripts/agent/inspect-ci.ps1"
            text = '"--commit", $ExpectedHeadSha'
        },
        [pscustomobject]@{
            path = "scripts/agent/merge-ready.ps1"
            text = "Assert-MainProtectionVerified"
        },
        [pscustomobject]@{
            path = "scripts/agent/merge-task.ps1"
            text = "Assert-MergedPrMatchesTask"
        },
        [pscustomobject]@{
            path = "scripts/agent/merge-task.ps1"
            text = "Assert-MainProtectionVerified"
        },
        [pscustomobject]@{
            path = "scripts/agent/merge-task.ps1"
            text = "Assert-MergeAttemptMatchesTask"
        },
        [pscustomobject]@{
            path = "scripts/agent/merge-task.ps1"
            text = "mergeReadyPrNumber"
        },
        [pscustomobject]@{
            path = "scripts/agent/create-pr.ps1"
            text = '$fields.mergeReadyPrNumber = $null'
        },
        [pscustomobject]@{
            path = "scripts/agent/merge-task.ps1"
            text = "cleanupComplete"
        }
    )) {
        $wrapperText = Get-Content -LiteralPath $wrapperContract.path -Raw
        if (-not $wrapperText.Contains([string]$wrapperContract.text)) {
            throw "Guarded wrapper contract is missing '$($wrapperContract.text)': $($wrapperContract.path)"
        }
    }

    Write-Output "Guard trust-boundary regression validation passed."
}
finally {
    Set-Location -LiteralPath $originalLocation
}
