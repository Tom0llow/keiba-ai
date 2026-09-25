Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "_path-security.ps1")

$script:AgentBranchPrefix = "agent/"
$script:DefaultBaseBranch = "main"
$script:TaskStateFileName = "codex-task.json"
$script:WorkflowLockFileName = "codex-workflow.lock"
$script:RequiredCheckNames = @("Quality", "Test")
$script:GitHubApiVersion = "2026-03-10"
$script:GuardManifestFileName = "guard-manifest.json"
$script:GuardRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$script:DisabledHooksPath = Join-Path $script:GuardRoot "empty-hooks"
$script:GitHubRepositoryBinding = $null
$script:WorkflowLock = $null
$script:GitPath = $null
$script:GhPath = $null
$script:CodexPath = $null
$script:TrustedCommandOutputRoot = $null
$script:GuardedSourcePaths = @(
    "scripts/agent/_common.ps1",
    "scripts/agent/_path-security.ps1",
    "scripts/agent/commit-task.ps1",
    "scripts/agent/create-pr.ps1",
    "scripts/agent/github-preflight.ps1",
    "scripts/agent/inspect-ci.ps1",
    "scripts/agent/inspect-pr.ps1",
    "scripts/agent/merge-ready.ps1",
    "scripts/agent/merge-task.ps1",
    "scripts/agent/push-task.ps1",
    "scripts/agent/start-task.ps1",
    "scripts/agent/wait-ci.ps1",
    "scripts/guard-tests/codex-cli-version.txt",
    "scripts/github/verify-main-protection.ps1"
)

# Never let ambient GitHub CLI repository selection override the repository
# proven from this checkout's origin remote.
Remove-Item Env:GH_REPO -ErrorAction SilentlyContinue
Remove-Item Env:GH_HOST -ErrorAction SilentlyContinue

function Assert-CommandExists {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-ExternalText {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$ArgumentList = @(),
        [Parameter()][switch]$RawOutput
    )

    if ([string]::IsNullOrWhiteSpace([string]$script:TrustedCommandOutputRoot)) {
        throw "Trusted command output directory is not initialized."
    }
    $outputId = [guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path $script:TrustedCommandOutputRoot ".codex-command-$outputId.stdout"
    $stderrPath = Join-Path $script:TrustedCommandOutputRoot ".codex-command-$outputId.stderr"

    try {
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $FilePath @ArgumentList 1> $stdoutPath 2> $stderrPath
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorAction
        }
        $stdout = Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue

        if ($exitCode -ne 0) {
            $detail = @($stdout, $stderr) | Where-Object {
                -not [string]::IsNullOrWhiteSpace([string]$_)
            }
            throw "Command failed ($exitCode): $FilePath $($ArgumentList -join ' ')`n$($detail -join "`n")"
        }

        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            Write-Verbose $stderr.Trim()
        }
        if ($null -eq $stdout) {
            return ""
        }
        if ($RawOutput) {
            return $stdout
        }
        return $stdout.Trim()
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-CurrentPowerShellPath {
    $process = Get-Process -Id $PID
    $path = [System.IO.Path]::GetFullPath([string]$process.Path)
    $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if (
        $item.PSIsContainer -or
        ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
        $item.Name -notin @("pwsh.exe", "powershell.exe")
    ) {
        throw "Guarded wrappers require a regular pwsh.exe or powershell.exe host."
    }
    Assert-NoReparsePointInPath -Path $path -Role "PowerShell executable"
    Assert-CanonicalPhysicalPath -Path $path -Role "PowerShell executable"
    return $path
}

function Test-ExternalSuccess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$ArgumentList = @()
    )
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @ArgumentList *> $null
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Invoke-Git {
    param(
        [Parameter()][string[]]$Arguments = @(),
        [Parameter()][switch]$RawOutput
    )

    if ([string]::IsNullOrWhiteSpace([string]$script:GitPath)) {
        throw "Trusted Git executable is not initialized. Validate the installed guard first."
    }

    # Guarded wrappers run outside the sandbox only to reach Git/GitHub state.
    # Disable every repository hook and external fsmonitor so branch-controlled
    # files cannot turn a guarded Git operation into arbitrary host execution.
    $guardedArguments = @(
        "-c", "core.hooksPath=$script:DisabledHooksPath",
        "-c", "core.fsmonitor=false",
        "-c", "core.pager="
    ) + $Arguments

    return Invoke-ExternalText `
        -FilePath $script:GitPath `
        -ArgumentList $guardedArguments `
        -RawOutput:$RawOutput
}

function Get-GitPathList {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    if ($Arguments -notcontains "-z") {
        throw "Git path listings must use NUL separators."
    }
    $raw = Invoke-Git -Arguments $Arguments -RawOutput
    if ([string]::IsNullOrEmpty($raw)) {
        return @()
    }
    # Windows PowerShell 5.1 can append a line ending while redirecting
    # native stdout; it is outside Git's terminal NUL record separator.
    $raw = $raw.TrimEnd([char[]]@([char]13, [char]10))
    if (-not $raw.EndsWith([string][char]0, [System.StringComparison]::Ordinal)) {
        $lastCodepoint = [int][char]$raw[$raw.Length - 1]
        throw "Git $($Arguments[0]) path listing was not NUL-terminated (last codepoint $lastCodepoint)."
    }
    foreach ($path in $raw.Split([char]0)) {
        if ($path.Length -gt 0) {
            $path.Replace("\", "/")
        }
    }
}

function Test-GitSuccess {
    param([Parameter()][string[]]$Arguments = @())

    if ([string]::IsNullOrWhiteSpace([string]$script:GitPath)) {
        throw "Trusted Git executable is not initialized. Validate the installed guard first."
    }
    $guardedArguments = @(
        "-c", "core.hooksPath=$script:DisabledHooksPath",
        "-c", "core.fsmonitor=false",
        "-c", "core.pager="
    ) + $Arguments
    return Test-ExternalSuccess -FilePath $script:GitPath -ArgumentList $guardedArguments
}

function Invoke-Gh {
    param([Parameter()][string[]]$Arguments = @())
    if ([string]::IsNullOrWhiteSpace([string]$script:GhPath)) {
        throw "Trusted GitHub CLI executable is not initialized. Validate the installed guard first."
    }
    return Invoke-ExternalText -FilePath $script:GhPath -ArgumentList $Arguments
}

function Invoke-GhRepo {
    param([Parameter()][string[]]$Arguments = @())

    $binding = Get-GitHubRepositoryBinding
    return Invoke-Gh -Arguments ($Arguments + @("--repo", [string]$binding.nameWithOwner))
}

function Invoke-GhRepositoryApi {
    param(
        [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Endpoint,
        [Parameter()][ValidateNotNullOrEmpty()][string]$Accept = "application/vnd.github+json"
    )

    if ($Endpoint.StartsWith("/", [System.StringComparison]::Ordinal)) {
        throw "GitHub API endpoint must be repository-relative without a leading slash."
    }
    $binding = Get-GitHubRepositoryBinding
    return Invoke-Gh @(
        "api",
        "--hostname", [string]$binding.host,
        "--method", "GET",
        "--header", "Accept: $Accept",
        "--header", "X-GitHub-Api-Version: $($script:GitHubApiVersion)",
        $Endpoint
    )
}

function Get-RepoRoot {
    $workspaceDotGit = Join-Path $script:GuardRoot ".git"
    if (Test-Path -LiteralPath $workspaceDotGit -PathType Container) {
        if ([string]::IsNullOrWhiteSpace([string]$script:GitPath)) {
            $script:GitPath = Resolve-TrustedCommandPath `
                -Name "git" `
                -ExpectedFileNames @("git.exe") `
                -RepoRoot $script:GuardRoot `
                -Role "Workspace verifier Git executable"
        }
        if ([string]::IsNullOrWhiteSpace([string]$script:GhPath)) {
            $script:GhPath = Resolve-TrustedCommandPath `
                -Name "gh" `
                -ExpectedFileNames @("gh.exe") `
                -RepoRoot $script:GuardRoot `
                -Role "Workspace verifier GitHub CLI executable"
        }
        return $script:GuardRoot
    }

    $manifestPath = Join-Path $script:GuardRoot $script:GuardManifestFileName
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Installed guard manifest is missing: $manifestPath"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $repoRootProperty = $manifest.PSObject.Properties["repoRoot"]
    if ($null -eq $repoRootProperty -or [string]::IsNullOrWhiteSpace([string]$repoRootProperty.Value)) {
        throw "Installed guard manifest is missing its repository checkout binding."
    }
    return [System.IO.Path]::GetFullPath([string]$repoRootProperty.Value)
}

function Set-RepoRoot {
    $root = Get-RepoRoot
    Set-Location -LiteralPath $root
    return $root
}

function Enter-GuardedWorkflowLock {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    if ($null -ne $script:WorkflowLock) {
        throw "This process already holds the guarded workflow lock."
    }

    $gitDirectory = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot ".git"))
    if (-not (Test-Path -LiteralPath $gitDirectory -PathType Container)) {
        throw "Guarded workflow locking requires a standard checkout with a .git directory."
    }

    $lockPath = Join-Path $gitDirectory $script:WorkflowLockFileName
    if (Test-Path -LiteralPath $lockPath) {
        $lockItem = Get-Item -LiteralPath $lockPath -Force -ErrorAction Stop
        if (
            $lockItem.PSIsContainer -or
            ($lockItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        ) {
            throw "Guarded workflow lock must be a regular file: $lockPath"
        }
    }

    try {
        $stream = [System.IO.File]::Open(
            $lockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch [System.IO.IOException] {
        throw @"
Another guarded workflow operation is active, or the workflow lock cannot be
acquired exclusively:
$lockPath

Refusing to continue concurrently.
"@
    }

    $script:WorkflowLock = [pscustomobject]@{
        path   = $lockPath
        stream = $stream
    }
    return $script:WorkflowLock
}

function Exit-GuardedWorkflowLock {
    param([Parameter(Mandatory = $true)]$Lock)

    if (-not [object]::ReferenceEquals($script:WorkflowLock, $Lock)) {
        throw "Refusing to release a workflow lock that this process does not hold."
    }

    try {
        if ($null -ne $Lock.stream) {
            $Lock.stream.Dispose()
        }
    }
    finally {
        $script:WorkflowLock = $null
    }
}

function Invoke-WithGuardedWorkflowLock {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    $lock = Enter-GuardedWorkflowLock -RepoRoot $RepoRoot
    try {
        & $Action
    }
    finally {
        Exit-GuardedWorkflowLock -Lock $lock
    }
}

function Assert-GuardedWorkflowLockHeld {
    if ($null -eq $script:WorkflowLock) {
        throw "Task state may be changed only while the guarded workflow lock is held."
    }
}

function Assert-TrustedGuardInstallation {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $dotGit = Join-Path $RepoRoot ".git"
    if (-not (Test-Path -LiteralPath $dotGit -PathType Container)) {
        throw "Guarded wrappers require a standard checkout with a .git directory."
    }
    Assert-NoReparsePointInPath -Path $RepoRoot -Role "Repository checkout"
    Assert-CanonicalPhysicalPath -Path $RepoRoot -Role "Repository checkout"
    Assert-NoReparsePointInPath -Path $dotGit -Role "Repository Git directory"
    Assert-CanonicalPhysicalPath -Path $dotGit -Role "Repository Git directory"
    $script:TrustedCommandOutputRoot = $dotGit
    $currentShellPath = Get-CurrentPowerShellPath
    Assert-TrustedPowerShellHostPath `
        -ShellPath $currentShellPath `
        -RepoRoot $RepoRoot

    $repoPrefix = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    if (
        [string]::Equals(
            $script:GuardRoot,
            [System.IO.Path]::GetFullPath($RepoRoot),
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        $script:GuardRoot.StartsWith(
            $repoPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw @"
Refusing to run a mutable workspace wrapper.

Run the reviewed absolute path recorded in:
$(Join-Path $dotGit "codex-guard\guard-invocation.json")
"@
    }

    $guardRootItem = Get-Item -LiteralPath $script:GuardRoot -Force
    if (-not $guardRootItem.PSIsContainer) {
        throw "Guard installation root must be a directory."
    }
    Assert-NoReparsePointInPath -Path $script:GuardRoot -Role "Guard installation"
    Assert-CanonicalPhysicalPath -Path $script:GuardRoot -Role "Guard installation"
    Assert-PathOutsideKnownSandboxWritableRoots `
        -Path $script:GuardRoot `
        -RepoRoot $RepoRoot `
        -Role "Guard installation"

    $emptyHooksItem = Get-Item -LiteralPath $script:DisabledHooksPath -Force -ErrorAction Stop
    if (
        -not $emptyHooksItem.PSIsContainer -or
        ($emptyHooksItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
        @(Get-ChildItem -LiteralPath $script:DisabledHooksPath -Force).Count -ne 0
    ) {
        throw "Guarded Git hooks directory must exist, be empty, and not be a reparse point."
    }
    Assert-NoReparsePointInPath -Path $script:DisabledHooksPath -Role "Guarded Git hooks directory"
    Assert-CanonicalPhysicalPath -Path $script:DisabledHooksPath -Role "Guarded Git hooks directory"

    $manifestPath = Join-Path $script:GuardRoot $script:GuardManifestFileName
    $manifestItem = Get-Item -LiteralPath $manifestPath -Force -ErrorAction Stop
    if ($manifestItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Guard manifest must not be a symbolic link."
    }
    Assert-NoReparsePointInPath -Path $manifestPath -Role "Guard manifest"
    Assert-CanonicalPhysicalPath -Path $manifestPath -Role "Guard manifest"

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $versionProperty = $manifest.PSObject.Properties["version"]
    if ($null -eq $versionProperty -or [int]$versionProperty.Value -ne 4) {
        throw "Unsupported or missing guard manifest version."
    }

    $manifestRepoRootProperty = $manifest.PSObject.Properties["repoRoot"]
    $manifestGuardRootProperty = $manifest.PSObject.Properties["guardRoot"]
    $manifestRepositoryProperty = $manifest.PSObject.Properties["repository"]
    $manifestRepositoryPolicyIdProperty = $manifest.PSObject.Properties["repositoryPolicyId"]
    $manifestInstallationIdProperty = $manifest.PSObject.Properties["installationId"]
    $manifestSourceShaProperty = $manifest.PSObject.Properties["sourceSha"]
    $manifestShellPathProperty = $manifest.PSObject.Properties["shellPath"]
    $manifestGitPathProperty = $manifest.PSObject.Properties["gitPath"]
    $manifestGhPathProperty = $manifest.PSObject.Properties["ghPath"]
    $manifestCodexPathProperty = $manifest.PSObject.Properties["codexPath"]
    $manifestCodexVersionProperty = $manifest.PSObject.Properties["codexVersion"]
    if (
        $null -eq $manifestRepoRootProperty -or
        $null -eq $manifestGuardRootProperty -or
        $null -eq $manifestRepositoryProperty -or
        $null -eq $manifestRepositoryPolicyIdProperty -or
        $null -eq $manifestInstallationIdProperty -or
        $null -eq $manifestSourceShaProperty -or
        $null -eq $manifestShellPathProperty -or
        $null -eq $manifestGitPathProperty -or
        $null -eq $manifestGhPathProperty -or
        $null -eq $manifestCodexPathProperty -or
        $null -eq $manifestCodexVersionProperty
    ) {
        throw "Guard manifest is missing its repository or installation binding."
    }
    if (-not [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$manifestRepoRootProperty.Value),
        [System.IO.Path]::GetFullPath($RepoRoot),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Installed guard belongs to a different repository checkout."
    }
    if (-not [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$manifestGuardRootProperty.Value),
        $script:GuardRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Guard manifest installation path does not match the running guard."
    }
    if (-not [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$manifestShellPathProperty.Value),
        $currentShellPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Installed guard belongs to a different PowerShell executable."
    }

    $expectedRepositoryPolicyId = Get-GuardRepositoryPolicyId `
        -Repository ([string]$manifestRepositoryProperty.Value) `
        -RepoRoot $RepoRoot
    if (-not [string]::Equals(
        [string]$manifestRepositoryPolicyIdProperty.Value,
        $expectedRepositoryPolicyId,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Guard manifest repository policy identity is invalid."
    }
    $expectedGuardDirectoryName = Get-GuardInstallationDirectoryName `
        -RepositoryPolicyId $expectedRepositoryPolicyId `
        -SourceSha ([string]$manifestSourceShaProperty.Value) `
        -InstallationId ([string]$manifestInstallationIdProperty.Value)
    if (-not [string]::Equals(
        (Split-Path -Leaf $script:GuardRoot),
        $expectedGuardDirectoryName,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Guard installation directory does not match its immutable identity."
    }

    $validatedGitPath = Assert-TrustedCommandPath `
        -CommandPath ([string]$manifestGitPathProperty.Value) `
        -ExpectedFileNames @("git.exe") `
        -RepoRoot $RepoRoot `
        -Role "Installed Git executable"
    $validatedGhPath = Assert-TrustedCommandPath `
        -CommandPath ([string]$manifestGhPathProperty.Value) `
        -ExpectedFileNames @("gh.exe") `
        -RepoRoot $RepoRoot `
        -Role "Installed GitHub CLI executable"
    $validatedCodexPath = Assert-TrustedCommandPath `
        -CommandPath ([string]$manifestCodexPathProperty.Value) `
        -ExpectedFileNames @("codex.exe") `
        -RepoRoot $RepoRoot `
        -Role "Installed native Codex CLI executable"

    $entries = @($manifest.files)
    if ($entries.Count -ne $script:GuardedSourcePaths.Count) {
        throw "Guard manifest does not contain the required file set."
    }

    $guardPrefix = $script:GuardRoot + [System.IO.Path]::DirectorySeparatorChar
    foreach ($sourcePath in $script:GuardedSourcePaths) {
        $entry = @($entries | Where-Object { [string]$_.sourcePath -eq $sourcePath })
        if ($entry.Count -ne 1) {
            throw "Guard manifest entry is missing or duplicated: $sourcePath"
        }

        $installedPath = [System.IO.Path]::GetFullPath((Join-Path $script:GuardRoot $sourcePath))
        if (-not $installedPath.StartsWith($guardPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Guard manifest path escaped its installation root: $sourcePath"
        }

        $installedItem = Get-Item -LiteralPath $installedPath -Force -ErrorAction Stop
        if ($installedItem.PSIsContainer) {
            throw "Guarded source must be a regular file: $sourcePath"
        }
        Assert-NoReparsePointInPath -Path $installedPath -Role "Guarded source '$sourcePath'"
        Assert-CanonicalPhysicalPath -Path $installedPath -Role "Guarded source '$sourcePath'"

        $actualHash = (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash
        if (-not [string]::Equals(
            $actualHash,
            [string]$entry[0].sha256,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Guarded file hash mismatch: $sourcePath"
        }
    }

    $codexVersionOutput = Invoke-ExternalText `
        -FilePath $validatedCodexPath `
        -ArgumentList @("--version")
    $actualCodexVersion = Get-CodexCliVersionFromOutput -VersionOutput $codexVersionOutput
    $codexVersionPolicyPath = Join-Path `
        $script:GuardRoot `
        "scripts\guard-tests\codex-cli-version.txt"
    Assert-CodexCliVersionAllowed `
        -Version ([string]$manifestCodexVersionProperty.Value) `
        -VersionFile $codexVersionPolicyPath
    if (-not [string]::Equals(
        $actualCodexVersion,
        [string]$manifestCodexVersionProperty.Value,
        [System.StringComparison]::Ordinal
    )) {
        throw "Installed Codex CLI version changed; reinstall the guarded wrappers."
    }

    $script:GitPath = $validatedGitPath
    $script:GhPath = $validatedGhPath
    $script:CodexPath = $validatedCodexPath

    $originCoordinates = Get-OriginGitHubCoordinates
    if (-not [string]::Equals(
        [string]$manifestRepositoryProperty.Value,
        [string]$originCoordinates.nameWithOwner,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Installed guard repository does not match the current origin."
    }

    return $manifest
}

function Assert-GuardSourcesMatchCommit {
    param(
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$Commit,
        [Parameter(Mandatory = $true)]$Manifest
    )

    $entries = @($Manifest.files)
    foreach ($sourcePath in $script:GuardedSourcePaths) {
        $entry = @($entries | Where-Object { [string]$_.sourcePath -eq $sourcePath })
        if ($entry.Count -ne 1) {
            throw "Guard manifest entry is missing or duplicated: $sourcePath"
        }

        $sourceBlob = Invoke-Git @("rev-parse", "$Commit`:$sourcePath")
        if (-not [string]::Equals(
            $sourceBlob,
            [string]$entry[0].sourceBlob,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw @"
The guarded workflow source changed on origin/main: $sourcePath
Reinstall the reviewed guard from protected main before starting another task.
"@
        }
    }
}

function Assert-MainProtectionVerified {
    $verifyScript = [System.IO.Path]::GetFullPath((Join-Path `
        $script:GuardRoot "scripts\github\verify-main-protection.ps1"
    ))
    if (-not (Test-Path -LiteralPath $verifyScript -PathType Leaf)) {
        throw "Missing installed branch-protection verifier: $verifyScript"
    }

    try {
        $verificationText = Invoke-ExternalText `
            -FilePath (Get-CurrentPowerShellPath) `
            -ArgumentList @("-NoProfile", "-File", $verifyScript)
        $verification = $verificationText | ConvertFrom-Json
    }
    catch {
        throw "GitHub repository/main policy verification failed:`n$($_.Exception.Message)"
    }

    $binding = Get-GitHubRepositoryBinding
    if (
        -not [string]::Equals(
            [string]$verification.repository,
            [string]$binding.nameWithOwner,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        [string]$verification.branch -ne $script:DefaultBaseBranch -or
        -not [bool]$verification.requiredChecksConfigured -or
        -not [bool]$verification.strictStatusChecks -or
        [long]$verification.githubActionsAppId -le 0
    ) {
        throw "Installed branch-protection verifier returned an invalid success result."
    }
    return $verification
}

function Get-CurrentBranch {
    $branch = Invoke-Git @("branch", "--show-current")
    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw "Detached HEAD is not allowed for guarded agent Git operations."
    }
    return $branch.Trim()
}

function Assert-AgentBranch {
    param([Parameter(Mandatory = $true)][string]$Branch)
    if (-not $Branch.StartsWith($script:AgentBranchPrefix, [System.StringComparison]::Ordinal)) {
        throw "Operation refused: '$Branch' is not an agent/* task branch."
    }
    if ($Branch -eq $script:DefaultBaseBranch) {
        throw "Operation refused on protected base branch '$($script:DefaultBaseBranch)'."
    }
}

function Assert-ValidAgentBranchName {
    param([Parameter(Mandatory = $true)][string]$Branch)

    Assert-AgentBranch -Branch $Branch

    if ($Branch.Length -gt 100 -or $Branch -notmatch '^agent/[a-z0-9][a-z0-9._/-]*$') {
        throw "Invalid agent branch name '$Branch'."
    }
    if ($Branch.Contains("..") -or $Branch.Contains("//") -or $Branch.EndsWith("/") -or $Branch.EndsWith(".")) {
        throw "Invalid agent branch name '$Branch'."
    }
    if (-not (Test-GitSuccess -Arguments @("check-ref-format", "--branch", $Branch))) {
        throw "Git rejected branch name '$Branch'."
    }
}

function New-AgentBranchName {
    param([Parameter(Mandatory = $true)][string]$TaskName)

    $slug = $TaskName.ToLowerInvariant()
    $slug = [regex]::Replace($slug, '[^a-z0-9]+', '-')
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) { $slug = "task" }
    if ($slug.Length -gt 40) { $slug = $slug.Substring(0, 40).TrimEnd('-') }

    return "$($script:AgentBranchPrefix)$slug-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}

function Get-IgnoredProtectedPaths {
    $protectedPathspecs = @(
        ":(icase).pre-commit-config.yaml",
        ":(icase)docs/AUTONOMOUS_DEVELOPMENT.md",
        ":(icase)docs/rules/git-workflow.md",
        ":(icase)docs/decisions/ADR-001-trusted-guarded-wrappers.md",
        ":(icase,glob).agents/**",
        ":(icase,glob).codex/**",
        ":(icase,glob).github/**",
        ":(icase,glob)scripts/agent/**",
        ":(icase,glob)scripts/guard-tests/**",
        ":(icase,glob)scripts/github/**",
        ":(icase,glob)scripts/setup/**",
        ":(icase)AGENTS.md",
        ":(icase)AGENTS.override.md",
        ":(icase,glob)**/AGENTS.md",
        ":(icase,glob)**/AGENTS.override.md",
        ":(icase).gitattributes",
        ":(icase).gitmodules",
        ":(icase).lfsconfig",
        ":(icase,glob)**/.gitattributes",
        ":(icase,glob)**/.gitmodules",
        ":(icase,glob)**/.lfsconfig"
    )
    $ignored = @(Get-GitPathList -Arguments (
        @("ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--") +
        $protectedPathspecs
    ))
    return @($ignored | Sort-Object -Unique)
}

function Assert-CleanWorkingTree {
    $ignoredProtected = @(Get-IgnoredProtectedPaths)
    if ($ignoredProtected.Count -gt 0) {
        throw "Ignored workflow trust-boundary paths are present:`n- $($ignoredProtected -join "`n- ")"
    }
    $status = Invoke-Git @("status", "--porcelain=v1", "--untracked-files=all")
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Working tree is not clean. Autonomous startup/publish refuses to touch existing changes.`n$status"
    }
}

function Assert-NoProtectedTaskChanges {
    param(
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$BaseSha,
        [Parameter()][switch]$IncludeWorktree
    )

    $changedPaths = New-Object System.Collections.Generic.List[string]
    $committed = @(Get-GitPathList -Arguments @(
        "diff", "--name-only", "-z", "--no-ext-diff", "--no-textconv", "--no-renames",
        "$BaseSha..HEAD", "--"
    ))
    foreach ($path in $committed) {
        $changedPaths.Add($path)
    }

    if ($IncludeWorktree) {
        $worktree = @(Get-GitPathList -Arguments @(
            "diff", "--name-only", "-z", "--no-ext-diff", "--no-textconv", "--no-renames",
            "HEAD", "--"
        ))
        foreach ($path in $worktree) {
            $changedPaths.Add($path)
        }

        $untracked = @(Get-GitPathList -Arguments @(
            "ls-files", "-z", "--others", "--exclude-standard", "--"
        ))
        foreach ($path in $untracked) {
            $changedPaths.Add($path)
        }

        $ignoredProtected = @(Get-IgnoredProtectedPaths)
        foreach ($path in $ignoredProtected) {
            $changedPaths.Add($path)
        }
    }

    $protectedPaths = @($changedPaths.ToArray() | Sort-Object -Unique | Where-Object {
        $path = $_
        $leaf = @($path -split '/')[-1]
        [string]::Equals($leaf, "AGENTS.md", [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]::Equals($leaf, "AGENTS.override.md", [System.StringComparison]::OrdinalIgnoreCase) -or
        ($path -eq ".pre-commit-config.yaml") -or
        ($path -eq "docs/AUTONOMOUS_DEVELOPMENT.md") -or
        ($path -eq "docs/rules/git-workflow.md") -or
        ($path -eq "docs/decisions/ADR-001-trusted-guarded-wrappers.md") -or
        $path.StartsWith(".agents/", [System.StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith(".codex/", [System.StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith(".github/", [System.StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("scripts/agent/", [System.StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("scripts/guard-tests/", [System.StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("scripts/github/", [System.StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("scripts/setup/", [System.StringComparison]::OrdinalIgnoreCase) -or
        ($leaf -in @(".gitattributes", ".gitmodules", ".lfsconfig"))
    })

    if ($protectedPaths.Count -gt 0) {
        throw @"
Autonomous changes to the workflow trust boundary are forbidden:
- $($protectedPaths -join "`n- ")

Prepare these changes through an explicitly authorized manual security bootstrap.
"@
    }
}

function Assert-OriginExists {
    if (-not (Test-GitSuccess -Arguments @("remote", "get-url", "origin"))) {
        throw "Remote 'origin' is not configured."
    }
}

function ConvertTo-GitHubRemoteCoordinates {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Role
    )

    $remoteUrl = $Url.Trim()
    $path = $null

    if ($remoteUrl -match '^https://github\.com/(?<path>[^?#]+?)(?:\.git)?/?$') {
        $path = [string]$Matches.path
    }
    elseif ($remoteUrl -match '^ssh://git@github\.com/(?<path>[^?#]+?)(?:\.git)?/?$') {
        $path = [string]$Matches.path
    }
    elseif ($remoteUrl -match '^git@github\.com:(?<path>[^?#]+?)(?:\.git)?/?$') {
        $path = [string]$Matches.path
    }
    else {
        throw "Guarded GitHub operations require a github.com $Role URL; found '$remoteUrl'."
    }

    $path = $path.Trim('/').TrimEnd('/')
    if ($path.EndsWith('.git', [System.StringComparison]::OrdinalIgnoreCase)) {
        $path = $path.Substring(0, $path.Length - 4)
    }

    $parts = @($path -split '/')
    if (
        $parts.Count -ne 2 -or
        $parts[0] -notmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,38}$' -or
        $parts[1] -notmatch '^[A-Za-z0-9_.-]+$'
    ) {
        throw "Could not derive a safe GitHub owner/repository identity from $Role URL '$remoteUrl'."
    }

    return [pscustomobject]@{
        host          = "github.com"
        owner         = [string]$parts[0]
        repository    = [string]$parts[1]
        nameWithOwner = "$($parts[0])/$($parts[1])"
        url            = $remoteUrl
    }
}

function Get-OriginGitHubCoordinates {
    Assert-OriginExists

    $fetchUrlText = Invoke-Git @("remote", "get-url", "--all", "origin")
    $pushUrlText = Invoke-Git @("remote", "get-url", "--push", "--all", "origin")
    $fetchUrls = @($fetchUrlText -split "`r?`n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })
    $pushUrls = @($pushUrlText -split "`r?`n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })

    if ($fetchUrls.Count -ne 1) {
        throw "Remote 'origin' must have exactly one fetch URL; found $($fetchUrls.Count)."
    }
    if ($pushUrls.Count -ne 1) {
        throw "Remote 'origin' must resolve to exactly one push URL; found $($pushUrls.Count)."
    }

    $fetch = ConvertTo-GitHubRemoteCoordinates -Url ([string]$fetchUrls[0]) -Role "fetch"
    $push = ConvertTo-GitHubRemoteCoordinates -Url ([string]$pushUrls[0]) -Role "push"
    if (-not [string]::Equals(
        [string]$fetch.nameWithOwner,
        [string]$push.nameWithOwner,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Remote 'origin' push URL '$($push.url)' does not match fetch repository '$($fetch.nameWithOwner)'."
    }

    return [pscustomobject]@{
        host          = [string]$fetch.host
        owner         = [string]$fetch.owner
        repository    = [string]$fetch.repository
        nameWithOwner = [string]$fetch.nameWithOwner
        origin        = [string]$fetch.url
        pushUrl       = [string]$push.url
    }
}

function Get-TaskOriginCoordinates {
    param([Parameter(Mandatory = $true)]$State)

    $coordinates = Get-OriginGitHubCoordinates
    if (-not [string]::Equals(
        [string]$coordinates.nameWithOwner,
        [string]$State.repository,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Current origin repository '$($coordinates.nameWithOwner)' does not match task repository '$($State.repository)'."
    }
    if (-not [string]::Equals(
        [string]$coordinates.owner,
        [string]$State.repositoryOwner,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Current origin owner '$($coordinates.owner)' does not match task owner '$($State.repositoryOwner)'."
    }
    return $coordinates
}

function Get-GitHubRepositoryBinding {
    if ($null -ne $script:GitHubRepositoryBinding) {
        return $script:GitHubRepositoryBinding
    }

    $coordinates = Get-OriginGitHubCoordinates
    $repoJson = Invoke-Gh @(
        "repo", "view", [string]$coordinates.nameWithOwner,
        "--json", "nameWithOwner"
    )
    $resolved = [string](($repoJson | ConvertFrom-Json).nameWithOwner)
    if (-not [string]::Equals(
        $resolved,
        [string]$coordinates.nameWithOwner,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "GitHub CLI resolved '$resolved', not origin repository '$($coordinates.nameWithOwner)'."
    }

    $script:GitHubRepositoryBinding = $coordinates
    return $script:GitHubRepositoryBinding
}

function Get-GhLogin {
    $coordinates = Get-OriginGitHubCoordinates

    try {
        $login = Invoke-Gh @(
            "api", "--hostname", [string]$coordinates.host,
            "user", "--jq", ".login"
        )
    }
    catch {
        $detail = $_.Exception.Message

        if ($detail -match 'proxyconnect' -or $detail -match '127\.0\.0\.1:9') {
            throw @"
GitHub access is still running inside the network-disabled Codex sandbox.

The GitHub command must be executed through an allow-listed host-side rule.
Confirm the user-layer policy recorded by
.git/codex-guard/guard-invocation.json exists, then restart Codex and retry the
absolute github-preflight.ps1 path recorded in that metadata. Reinstall the
guard manually from protected main if the policy is missing or stale.

Actual error:
$detail
"@
        }

        throw @"
GitHub API authentication/access failed.

Do not diagnose this solely with sandboxed 'gh auth status'.
Verify the host terminal can run 'gh api user --jq .login'.

Actual error:
$detail
"@
    }

    if ([string]::IsNullOrWhiteSpace($login)) {
        throw "GitHub API succeeded but no login was returned."
    }

    return $login.Trim()
}

function Assert-GhAuthenticated {
    $null = Get-GhLogin
    $null = Get-GitHubRepositoryBinding
}

function Get-TaskStatePath {
    $gitPath = Invoke-Git @("rev-parse", "--git-path", $script:TaskStateFileName)
    if ([System.IO.Path]::IsPathRooted($gitPath)) {
        return [System.IO.Path]::GetFullPath($gitPath)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $gitPath))
}

function Assert-NoActiveTaskState {
    $path = Get-TaskStatePath
    if (Test-Path -LiteralPath $path) {
        $raw = Get-Content -LiteralPath $path -Raw
        throw @"
An active/stale guarded task state already exists:
$path

Do not overwrite another task's identity. Finish/merge the existing task first.
If the state is known to be stale, remove it manually only after confirming that
no active autonomous task depends on it.

State:
$raw
"@
    }
}

function Read-TaskStateRaw {
    $path = Get-TaskStatePath
    if (-not (Test-Path -LiteralPath $path)) {
        throw "No guarded task state. Use the absolute start-task.ps1 path recorded in .git/codex-guard/guard-invocation.json."
    }
    $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if (
        $item.PSIsContainer -or
        ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
    ) {
        throw "Guarded task state must be a regular file: $path"
    }
    return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Write-TaskStateObject {
    param([Parameter(Mandatory = $true)]$State)
    Assert-GuardedWorkflowLockHeld
    $path = Get-TaskStatePath
    $parent = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
        if (
            $item.PSIsContainer -or
            ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        ) {
            throw "Guarded task state must be a regular file: $path"
        }
    }

    $temporaryPath = Join-Path $parent (".$($script:TaskStateFileName).$([guid]::NewGuid().ToString('N')).tmp")
    $replacementBackupPath = Join-Path $parent (".$($script:TaskStateFileName).$([guid]::NewGuid().ToString('N')).bak")
    $json = $State | ConvertTo-Json -Depth 10
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream = $null
    try {
        $stream = [System.IO.FileStream]::new(
            $temporaryPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        $stream.Dispose()
        $stream = $null

        if (Test-Path -LiteralPath $path) {
            [System.IO.File]::Replace($temporaryPath, $path, $replacementBackupPath)
        }
        else {
            [System.IO.File]::Move($temporaryPath, $path)
        }
    }
    finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $replacementBackupPath -Force -ErrorAction SilentlyContinue
    }
}

function Save-TaskState {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Branch,
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][string]$StartSha,
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string]$RepositoryOwner
    )

    $state = [ordered]@{
        version       = 6
        repoRoot      = $RepoRoot
        repository    = $Repository
        repositoryOwner = $RepositoryOwner
        branch        = $Branch
        base          = $Base
        startSha      = $StartSha
        headSha       = $StartSha
        taskName      = $TaskName
        createdAt     = (Get-Date).ToUniversalTime().ToString("o")
        prNumber      = $null
        prUrl         = $null
        mergeReadyPrNumber = $null
        mergeReadySha = $null
        mergeReadyAt  = $null
        mergeAttemptPrNumber = $null
        mergeAttemptHeadSha  = $null
        mergeAttemptMethod   = $null
        mergeAttemptAt       = $null
        pendingOperation       = "start"
        pendingCommitPhase     = $null
        pendingCommitParentSha = $null
        pendingCommitTreeSha   = $null
        pendingCommitMessage   = $null
    }

    Write-TaskStateObject -State $state
}

function Load-TaskState {
    param(
        [Parameter()][switch]$AllowDefaultBranch,
        [Parameter()][ValidateSet("start", "commit")][string]$AllowPendingOperation
    )

    $state = Read-TaskStateRaw
    $repoRoot = Get-RepoRoot

    if ([int]$state.version -ne 6) {
        throw "Unsupported guarded task state version '$($state.version)'."
    }

    if (-not [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$state.repoRoot),
        [System.IO.Path]::GetFullPath($repoRoot),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Task state belongs to a different repository."
    }

    Assert-AgentBranch -Branch ([string]$state.branch)
    if ([string]$state.startSha -notmatch '^[0-9a-fA-F]{40,64}$') {
        throw "Guarded task state contains an invalid starting SHA."
    }
    if ([string]$state.headSha -notmatch '^[0-9a-fA-F]{40,64}$') {
        throw "Guarded task state contains an invalid HEAD SHA."
    }

    $requiredStateFields = @(
        "mergeReadyPrNumber",
        "pendingOperation",
        "pendingCommitPhase",
        "pendingCommitParentSha",
        "pendingCommitTreeSha",
        "pendingCommitMessage"
    )
    foreach ($field in $requiredStateFields) {
        if ($state.PSObject.Properties.Name -notcontains $field) {
            throw "Guarded task state is missing required field '$field'."
        }
    }

    $readyFields = @("mergeReadyPrNumber", "mergeReadySha", "mergeReadyAt")
    $populatedReadyFields = @($readyFields | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$state.$_)
    })
    if ($populatedReadyFields.Count -notin @(0, $readyFields.Count)) {
        throw "Guarded task state contains a partial MERGE_READY record."
    }
    if ($populatedReadyFields.Count -eq $readyFields.Count) {
        if ([int]$state.mergeReadyPrNumber -lt 1) {
            throw "Guarded task state contains an invalid MERGE_READY PR number."
        }
        if ([int]$state.prNumber -ne [int]$state.mergeReadyPrNumber) {
            throw "MERGE_READY belongs to a different PR than the recorded task PR."
        }
        if ([string]$state.mergeReadySha -notmatch '^[0-9a-fA-F]{40,64}$') {
            throw "Guarded task state contains an invalid MERGE_READY HEAD SHA."
        }
        $readyTimestamp = [System.DateTimeOffset]::MinValue
        if (-not [System.DateTimeOffset]::TryParse(
            [string]$state.mergeReadyAt,
            [ref]$readyTimestamp
        )) {
            throw "Guarded task state contains an invalid MERGE_READY timestamp."
        }
    }

    $pendingOperation = [string]$state.pendingOperation
    $pendingCommitFields = @(
        "pendingCommitPhase",
        "pendingCommitParentSha",
        "pendingCommitTreeSha",
        "pendingCommitMessage"
    )
    if ([string]::IsNullOrWhiteSpace($pendingOperation)) {
        $unexpectedPendingFields = @($pendingCommitFields | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$state.$_)
        })
        if ($unexpectedPendingFields.Count -ne 0) {
            throw "Guarded task state contains commit recovery data without a pending operation."
        }
    }
    elseif ($pendingOperation -eq "start") {
        $unexpectedPendingFields = @($pendingCommitFields | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$state.$_)
        })
        if ($unexpectedPendingFields.Count -ne 0) {
            throw "A pending start operation contains unrelated commit recovery data."
        }
    }
    elseif ($pendingOperation -eq "commit") {
        if ([string]$state.pendingCommitPhase -notin @("staging", "committing")) {
            throw "Guarded task state contains an invalid pending commit phase."
        }
        if ([string]$state.pendingCommitParentSha -notmatch '^[0-9a-fA-F]{40,64}$') {
            throw "Guarded task state contains an invalid pending commit parent SHA."
        }
        if (
            [string]::IsNullOrWhiteSpace([string]$state.pendingCommitMessage) -or
            [string]$state.pendingCommitMessage -match '[\r\n]'
        ) {
            throw "Guarded task state contains an invalid pending commit message."
        }
        if (
            [string]$state.pendingCommitPhase -eq "staging" -and
            -not [string]::IsNullOrWhiteSpace([string]$state.pendingCommitTreeSha)
        ) {
            throw "A staging commit must not have a finalized tree SHA."
        }
        if (
            [string]$state.pendingCommitPhase -eq "committing" -and
            [string]$state.pendingCommitTreeSha -notmatch '^[0-9a-fA-F]{40,64}$'
        ) {
            throw "A committing operation requires a valid tree SHA."
        }
    }
    else {
        throw "Guarded task state contains unsupported pending operation '$pendingOperation'."
    }

    if (
        -not [string]::IsNullOrWhiteSpace($pendingOperation) -and
        $pendingOperation -ne $AllowPendingOperation
    ) {
        throw "Guarded task has an incomplete '$pendingOperation' operation. Retry its original wrapper."
    }

    $attemptFields = @(
        "mergeAttemptPrNumber",
        "mergeAttemptHeadSha",
        "mergeAttemptMethod",
        "mergeAttemptAt"
    )
    foreach ($field in $attemptFields) {
        if ($state.PSObject.Properties.Name -notcontains $field) {
            throw "Guarded task state is missing merge-attempt field '$field'."
        }
    }
    $populatedAttemptFields = @($attemptFields | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$state.$_)
    })
    if ($populatedAttemptFields.Count -notin @(0, $attemptFields.Count)) {
        throw "Guarded task state contains a partial merge-attempt record."
    }
    if ($populatedAttemptFields.Count -eq $attemptFields.Count) {
        if ([int]$state.mergeAttemptPrNumber -lt 1) {
            throw "Guarded task state contains an invalid merge-attempt PR number."
        }
        if ([string]$state.mergeAttemptHeadSha -notmatch '^[0-9a-fA-F]{40,64}$') {
            throw "Guarded task state contains an invalid merge-attempt HEAD SHA."
        }
        if ([string]$state.mergeAttemptMethod -ne "squash") {
            throw "Guarded task state contains an unsupported merge-attempt method."
        }
        $attemptTimestamp = [System.DateTimeOffset]::MinValue
        if (-not [System.DateTimeOffset]::TryParse(
            [string]$state.mergeAttemptAt,
            [ref]$attemptTimestamp
        )) {
            throw "Guarded task state contains an invalid merge-attempt timestamp."
        }
        if (
            $populatedReadyFields.Count -ne $readyFields.Count -or
            [int]$state.mergeAttemptPrNumber -ne [int]$state.mergeReadyPrNumber -or
            -not [string]::Equals(
                [string]$state.mergeAttemptHeadSha,
                [string]$state.mergeReadySha,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        ) {
            throw "Merge-attempt state is not bound to the recorded MERGE_READY decision."
        }
    }

    $branch = Get-CurrentBranch
    if ($branch -ne [string]$state.branch) {
        if (-not $AllowDefaultBranch -or $branch -ne [string]$state.base) {
            throw "Current branch '$branch' does not match guarded task '$($state.branch)'."
        }
    }

    $coordinates = Get-OriginGitHubCoordinates
    if (-not [string]::Equals(
        [string]$state.repository,
        [string]$coordinates.nameWithOwner,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Task state repository '$($state.repository)' does not match origin '$($coordinates.nameWithOwner)'."
    }
    if (-not [string]::Equals(
        [string]$state.repositoryOwner,
        [string]$coordinates.owner,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Task state owner '$($state.repositoryOwner)' does not match origin owner '$($coordinates.owner)'."
    }

    return $state
}

function Set-TaskStateFields {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Fields,
        [Parameter()][switch]$AllowDefaultBranch,
        [Parameter()][ValidateSet("start", "commit")][string]$AllowPendingOperation
    )
    $loadArguments = @{}
    if ($AllowDefaultBranch) {
        $loadArguments.AllowDefaultBranch = $true
    }
    if (-not [string]::IsNullOrWhiteSpace($AllowPendingOperation)) {
        $loadArguments.AllowPendingOperation = $AllowPendingOperation
    }
    $state = Load-TaskState @loadArguments
    foreach ($key in $Fields.Keys) {
        if ($state.PSObject.Properties.Name -contains $key) {
            $state.$key = $Fields[$key]
        }
        else {
            $state | Add-Member -NotePropertyName $key -NotePropertyValue $Fields[$key]
        }
    }
    Write-TaskStateObject -State $state
    return $state
}

function Remove-TaskState {
    Assert-GuardedWorkflowLockHeld
    $path = Get-TaskStatePath
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

function Assert-ConventionalCommitMessage {
    param([Parameter(Mandatory = $true)][string]$Message)
    if ($Message -match '[\r\n]') {
        throw "Commit message must be a single-line subject."
    }
    if (-not [string]::Equals(
        $Message,
        $Message.Trim(),
        [System.StringComparison]::Ordinal
    )) {
        throw "Commit message must not have leading or trailing whitespace."
    }
    $pattern = '^(feat|fix|refactor|test|docs|perf|build|ci|chore)(\([a-z0-9._/-]+\))?!?: .+'
    if ($Message -notmatch $pattern) {
        throw "Commit message must follow Conventional Commits."
    }
    if ($Message.Length -gt 200) {
        throw "Commit subject is too long."
    }
}

function Assert-NoSensitiveStagedPaths {
    $names = @(Get-GitPathList -Arguments @(
        "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"
    ))
    if ($names.Count -eq 0) { return }

    $blocked = New-Object System.Collections.Generic.List[string]

    foreach ($path in $names) {
        $n = $path.Replace("\", "/").ToLowerInvariant()
        $isEnv = $n -match '(^|/)\.env($|\.)'
        $safeEnv = $n -match '\.env\.(example|sample|template)$'

        $isBlocked =
            ($isEnv -and -not $safeEnv) -or
            ($n -match '\.(pem|key|p12|pfx)$') -or
            ($n -match '(^|/)(id_rsa|id_ed25519)(\.pub)?$') -or
            ($n -match '(^|/)(credentials|service[-_]?account)[^/]*\.json$') -or
            ($n -match '(^|/)(\.npmrc|\.pypirc|\.netrc)$')

        if ($isBlocked) { $blocked.Add($path) }
    }

    if ($blocked.Count -gt 0) {
        Invoke-Git @("restore", "--staged", "--", ".") | Out-Null
        throw "Commit refused: likely-sensitive paths staged:`n- $($blocked -join "`n- ")"
    }
}

function Get-PrObject {
    param([Parameter(Mandatory = $true)][int]$PrNumber)

    Assert-GhAuthenticated
    $json = Invoke-GhRepo @(
        "pr", "view", "$PrNumber",
        "--json",
        "number,title,url,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner,mergeable,mergeStateStatus,reviewDecision,mergedAt"
    )
    return $json | ConvertFrom-Json
}

function Get-CheckBucket {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter()][AllowEmptyString()][string]$Conclusion = ""
    )

    if ($Status -ne "completed") {
        return "pending"
    }
    switch ($Conclusion) {
        "success" { return "pass" }
        "neutral" { return "pass" }
        "skipped" { return "skipping" }
        "cancelled" { return "cancel" }
        default { return "fail" }
    }
}

function Get-CommitChecks {
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
        [string]$HeadSha
    )

    $binding = Get-GitHubRepositoryBinding
    $repository = [string]$binding.nameWithOwner
    $checkRunsText = Invoke-GhRepositoryApi `
        -Endpoint "repos/$repository/commits/$HeadSha/check-runs?filter=latest&per_page=100"
    $checkRunsResponse = $checkRunsText | ConvertFrom-Json
    $checkRuns = @($checkRunsResponse.check_runs)
    if ([int]$checkRunsResponse.total_count -gt $checkRuns.Count) {
        throw "More than 100 check runs exist for '$HeadSha'; fail closed until pagination is reviewed."
    }

    $checks = New-Object System.Collections.Generic.List[object]
    foreach ($run in $checkRuns) {
        if (-not [string]::Equals(
            [string]$run.head_sha,
            $HeadSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "GitHub returned a check run for a different HEAD SHA."
        }
        $appSlug = if ($null -eq $run.app) { "" } else { [string]$run.app.slug }
        $bucket = Get-CheckBucket `
            -Status ([string]$run.status) `
            -Conclusion ([string]$run.conclusion)
        $stateText = if ([string]$run.status -eq "completed") {
            [string]$run.conclusion
        }
        else {
            [string]$run.status
        }
        $checks.Add([pscustomobject]@{
            bucket                = $bucket
            name                  = [string]$run.name
            state                 = $stateText
            workflow              = $appSlug
            link                  = [string]$run.details_url
            trustedForRequirement = ($appSlug -eq "github-actions")
        })
    }

    $statusesText = Invoke-GhRepositoryApi `
        -Endpoint "repos/$repository/commits/$HeadSha/status?per_page=100"
    $statusesResponse = $statusesText | ConvertFrom-Json
    if (-not [string]::Equals(
        [string]$statusesResponse.sha,
        $HeadSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "GitHub returned combined status for a different HEAD SHA."
    }
    $statuses = @($statusesResponse.statuses)
    if ([int]$statusesResponse.total_count -gt $statuses.Count) {
        throw "More than 100 commit statuses exist for '$HeadSha'; fail closed until pagination is reviewed."
    }
    foreach ($status in $statuses) {
        $bucket = switch ([string]$status.state) {
            "success" { "pass" }
            "pending" { "pending" }
            "error" { "fail" }
            "failure" { "fail" }
            default { "fail" }
        }
        $checks.Add([pscustomobject]@{
            bucket                = $bucket
            name                  = [string]$status.context
            state                 = [string]$status.state
            workflow              = "commit-status"
            link                  = [string]$status.target_url
            trustedForRequirement = $false
        })
    }

    return $checks.ToArray()
}

function Get-ImmutableCommitDiff {
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
        [string]$BaseSha,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
        [string]$HeadSha
    )

    Invoke-Git @("cat-file", "-e", "$BaseSha^{commit}") | Out-Null
    Invoke-Git @("cat-file", "-e", "$HeadSha^{commit}") | Out-Null
    $mergeBase = (Invoke-Git @("merge-base", $BaseSha, $HeadSha)).Trim()
    if (-not [string]::Equals(
        $mergeBase,
        $BaseSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Guarded task HEAD is no longer descended from its recorded diff base."
    }

    # Exact object IDs make the evidence immutable. Disable external diff and
    # text-conversion drivers so repository-controlled configuration cannot
    # execute host commands while producing the complete local diff.
    return Invoke-Git @(
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--binary",
        "--full-index",
        "$BaseSha...$HeadSha",
        "--"
    )
}

function Get-MissingRequiredCheckNames {
    param([Parameter(Mandatory = $true)]$Checks)

    $present = @($Checks | Where-Object {
        $property = $_.PSObject.Properties["trustedForRequirement"]
        $null -ne $property -and [bool]$property.Value
    } | ForEach-Object { [string]$_.name })
    return @($script:RequiredCheckNames | Where-Object { $_ -notin $present })
}

function Assert-ChecksReady {
    param([Parameter(Mandatory = $true)]$Checks)

    $checksArray = @($Checks)
    if ($checksArray.Count -eq 0) {
        throw "No CI/status checks found."
    }

    $missing = @(Get-MissingRequiredCheckNames -Checks $checksArray)
    if ($missing.Count -gt 0) {
        throw "Required checks have not appeared: $($missing -join ', ')."
    }

    $blocking = @($checksArray | Where-Object {
        $bucket = [string]$_.bucket
        $name = [string]$_.name
        ($bucket -ne "pass") -and (
            ($name -in $script:RequiredCheckNames) -or
            ($bucket -ne "skipping")
        )
    })

    if ($blocking.Count -gt 0) {
        $summary = $blocking | ForEach-Object {
            "$($_.workflow) / $($_.name): $($_.state) [$($_.bucket)]"
        }
        throw "Non-passing checks remain:`n- $($summary -join "`n- ")"
    }
}

function Get-PrHeadIdentity {
    param([Parameter(Mandatory = $true)]$Pr)

    $headOwner = ""
    if ($Pr.headRepositoryOwner -is [string]) {
        $headOwner = [string]$Pr.headRepositoryOwner
    }
    elseif ($null -ne $Pr.headRepositoryOwner) {
        $loginProperty = $Pr.headRepositoryOwner.PSObject.Properties["login"]
        if ($null -ne $loginProperty) {
            $headOwner = [string]$loginProperty.Value
        }
    }

    $headRepository = ""
    if ($Pr.headRepository -is [string]) {
        $headRepository = [string]$Pr.headRepository
    }
    elseif ($null -ne $Pr.headRepository) {
        $nameWithOwnerProperty = $Pr.headRepository.PSObject.Properties["nameWithOwner"]
        if ($null -ne $nameWithOwnerProperty) {
            $headRepository = [string]$nameWithOwnerProperty.Value
        }
        if ([string]::IsNullOrWhiteSpace($headRepository)) {
            $nameProperty = $Pr.headRepository.PSObject.Properties["name"]
            $headRepositoryName = if ($null -eq $nameProperty) {
                ""
            }
            else {
                [string]$nameProperty.Value
            }
            if (
                -not [string]::IsNullOrWhiteSpace($headOwner) -and
                -not [string]::IsNullOrWhiteSpace($headRepositoryName)
            ) {
                $headRepository = "$headOwner/$headRepositoryName"
            }
        }
    }

    return [pscustomobject]@{
        owner      = $headOwner
        repository = $headRepository
    }
}

function Test-PrHeadMatchesTask {
    param(
        [Parameter(Mandatory = $true)]$Pr,
        [Parameter(Mandatory = $true)]$State
    )

    $identity = Get-PrHeadIdentity -Pr $Pr
    return (
        [string]$Pr.baseRefName -eq [string]$State.base -and
        [string]$Pr.headRefName -eq [string]$State.branch -and
        [string]::Equals(
            [string]$identity.owner,
            [string]$State.repositoryOwner,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -and
        [string]::Equals(
            [string]$identity.repository,
            [string]$State.repository,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    )
}

function Assert-PrMatchesTask {
    param(
        [Parameter(Mandatory = $true)]$Pr,
        [Parameter(Mandatory = $true)]$State,
        [Parameter()][switch]$AllowPrRebinding
    )

    if (
        -not $AllowPrRebinding -and
        $null -ne $State.prNumber -and
        [int]$State.prNumber -gt 0 -and
        [int]$Pr.number -ne [int]$State.prNumber
    ) {
        throw "PR #$($Pr.number) != recorded task PR #$($State.prNumber)."
    }
    if ([string]$Pr.baseRefName -ne [string]$State.base) {
        throw "PR base '$($Pr.baseRefName)' != recorded base '$($State.base)'."
    }
    if ([string]$Pr.headRefName -ne [string]$State.branch) {
        throw "PR head '$($Pr.headRefName)' != recorded branch '$($State.branch)'."
    }

    $identity = Get-PrHeadIdentity -Pr $Pr

    if (-not [string]::Equals(
        [string]$identity.owner,
        [string]$State.repositoryOwner,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "PR head owner '$($identity.owner)' != recorded origin owner '$($State.repositoryOwner)'."
    }
    if (-not [string]::Equals(
        [string]$identity.repository,
        [string]$State.repository,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "PR head repository '$($identity.repository)' != recorded origin repository '$($State.repository)'."
    }
}

function Get-VerifiedTaskHeadSnapshot {
    param(
        [Parameter(Mandatory = $true)][int]$PrNumber,
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$ExpectedHeadSha
    )

    $pr = Get-PrObject -PrNumber $PrNumber
    Assert-PrMatchesTask -Pr $pr -State $State

    $localSha = (Invoke-Git @("rev-parse", "HEAD")).Trim()
    $coordinates = Get-TaskOriginCoordinates -State $State
    $fetchUrl = [string]$coordinates.origin
    $pushUrl = [string]$coordinates.pushUrl
    $remoteText = Invoke-Git @(
        "ls-remote", "--heads", $pushUrl, "refs/heads/$($State.branch)"
    )
    $remoteLines = @($remoteText -split "`r?`n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })
    if ($remoteLines.Count -ne 1) {
        throw "Expected exactly one remote task ref; found $($remoteLines.Count)."
    }
    $remoteSha = ([string]$remoteLines[0] -split "\s+")[0]

    $baseSha = [string]$pr.baseRefOid
    if ($baseSha -notmatch '^[0-9a-fA-F]{40,64}$') {
        throw "PR base resolved to an invalid commit ID."
    }
    $baseRemoteText = Invoke-Git @(
        "ls-remote", "--heads", $fetchUrl, "refs/heads/$($State.base)"
    )
    $baseRemoteLines = @($baseRemoteText -split "`r?`n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })
    if ($baseRemoteLines.Count -ne 1) {
        throw "Expected exactly one remote base ref; found $($baseRemoteLines.Count)."
    }
    $baseRemoteSha = ([string]$baseRemoteLines[0] -split "\s+")[0]
    if (-not [string]::Equals(
        $baseRemoteSha,
        $baseSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "PR base SHA changed while collecting the guarded snapshot."
    }

    $observed = [ordered]@{
        "task state HEAD" = [string]$State.headSha
        "PR HEAD"     = [string]$pr.headRefOid
        "local HEAD"  = $localSha
        "remote HEAD" = $remoteSha
    }
    foreach ($entry in $observed.GetEnumerator()) {
        if (-not [string]::Equals(
            [string]$entry.Value,
            $ExpectedHeadSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "$($entry.Key) '$($entry.Value)' changed while checking '$ExpectedHeadSha'. Retry review and CI for the current HEAD."
        }
    }

    return [pscustomobject]@{
        pr        = $pr
        baseSha   = $baseSha
        localSha  = $localSha
        remoteSha = $remoteSha
        fetchUrl  = $fetchUrl
        pushUrl   = $pushUrl
    }
}

function Assert-MergedPrMatchesTask {
    param(
        [Parameter(Mandatory = $true)]$Pr,
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
        [string]$ExpectedHeadSha
    )

    Assert-PrMatchesTask -Pr $Pr -State $State
    if ([string]$Pr.state -ne "MERGED") {
        throw "PR is not in the MERGED state required for recovery."
    }
    if ([string]::IsNullOrWhiteSpace([string]$Pr.mergedAt)) {
        throw "Merged PR recovery requires a recorded mergedAt timestamp."
    }
    foreach ($observed in @(
        [pscustomobject]@{ role = "PR HEAD"; value = [string]$Pr.headRefOid },
        [pscustomobject]@{ role = "task state HEAD"; value = [string]$State.headSha },
        [pscustomobject]@{ role = "MERGE_READY HEAD"; value = [string]$State.mergeReadySha }
    )) {
        if (-not [string]::Equals(
            [string]$observed.value,
            $ExpectedHeadSha,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "$($observed.role) '$($observed.value)' does not match approved HEAD '$ExpectedHeadSha'."
        }
    }
}

function Assert-MergeAttemptMatchesTask {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-fA-F]{40,64}$')]
        [string]$ExpectedHeadSha
    )

    if ([int]$State.mergeAttemptPrNumber -ne $PrNumber) {
        throw "Merged PR recovery requires a matching recorded merge-attempt PR number."
    }
    if (-not [string]::Equals(
        [string]$State.mergeAttemptHeadSha,
        $ExpectedHeadSha,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Merged PR recovery requires a matching recorded merge-attempt HEAD SHA."
    }
    if ([string]$State.mergeAttemptMethod -ne "squash") {
        throw "Merged PR recovery requires a recorded squash merge attempt."
    }
    if ([string]::IsNullOrWhiteSpace([string]$State.mergeAttemptAt)) {
        throw "Merged PR recovery requires a recorded merge-attempt timestamp."
    }
}

function Assert-PrReadyForMerge {
    param([Parameter(Mandatory = $true)]$Pr)

    if ([string]$Pr.state -ne "OPEN") { throw "PR is not open." }
    if ([bool]$Pr.isDraft) { throw "PR is still a draft." }
    if ([string]$Pr.mergeable -ne "MERGEABLE") {
        throw "PR is not mergeable: $($Pr.mergeable)."
    }
    if ([string]$Pr.mergeStateStatus -ne "CLEAN") {
        throw "PR merge state is '$($Pr.mergeStateStatus)', not CLEAN."
    }

    $decision = [string]$Pr.reviewDecision
    if ($decision -eq "CHANGES_REQUESTED" -or $decision -eq "REVIEW_REQUIRED") {
        throw "PR review decision blocks merge: '$decision'."
    }
    return $decision
}

function Write-GuardedResult {
    param([Parameter(Mandatory = $true)][hashtable]$Data)

    $result = [ordered]@{ status = "ok" }
    foreach ($key in $Data.Keys) { $result[$key] = $Data[$key] }
    $result | ConvertTo-Json -Depth 10
}
