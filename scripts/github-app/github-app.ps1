#Requires -Version 7.2
<#
.SYNOPSIS
Issues short-lived GitHub App installation tokens for agent Git/GitHub operations.

.DESCRIPTION
The private key never leaves this process and tokens are never written to disk.
Each invocation signs a fresh App JWT (RS256), exchanges it for an installation
token limited to the configured repository, and uses that token only for the
requested operation. Installation tokens expire after one hour.

Configuration is read from $env:KEIBA_GITHUB_APP_CONFIG when set, otherwise from
~/.config/keiba-ai-agent/app.json:

    {
      "appId": 123456,
      "installationId": 7890123,
      "privateKeyPath": "C:/Users/<user>/.config/keiba-ai-agent/<key>.pem",
      "repository": "keiba-ai"
    }

Optional keys: "apiBaseUrl" (default https://api.github.com; plain http is
accepted only for loopback test servers), "gitHost" (default github.com), and
"ghPath" (default: gh on PATH).

.EXAMPLE
pwsh -NoProfile -File scripts/github-app/github-app.ps1 check
Verifies that a token can be issued, without printing it, and fails unless the
token reports contents, pull_requests, and issues as write and no workflows.

.EXAMPLE
pwsh -NoProfile -File scripts/github-app/github-app.ps1 credential get
Git credential-helper protocol. Configure it only for the x-access-token push URL.

.EXAMPLE
pwsh -NoProfile -File scripts/github-app/github-app.ps1 gh pr view 12
Runs an allow-listed gh command with the token in the child environment only.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandArgumentPassing = 'Standard'

# gh subcommands agents may run with the App identity. Merging, reviewing,
# repository administration, raw API access, and authentication changes are
# intentionally absent. GitHub itself enforces the main-branch rulesets (merge
# and approval counting) and the App's missing workflows permission; this
# allow-list is local defense in depth on top of them. Issues can be filed,
# read, commented on, and edited, but never closed, reopened, deleted,
# transferred, locked, or pinned (ADR-033). This allow-list blocks all six.
# GitHub does not stop close, reopen, lock, or pin, which the Issues permission
# allows; it may also refuse delete and transfer (not verified).
$AllowedGhCommands = @{
    'pr'    = @('create', 'view', 'list', 'diff', 'checks', 'comment', 'edit', 'ready', 'status', 'update-branch')
    'run'   = @('list', 'view', 'watch', 'rerun')
    'issue' = @('create', 'view', 'list', 'comment', 'edit')
}

function Write-Failure([string]$Message) {
    [Console]::Error.WriteLine("github-app: $Message")
    exit 1
}

function Read-AppConfig {
    $path = if ($env:KEIBA_GITHUB_APP_CONFIG) {
        $env:KEIBA_GITHUB_APP_CONFIG
    }
    else {
        Join-Path $HOME '.config/keiba-ai-agent/app.json'
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Write-Failure "configuration file not found: $path"
    }
    $config = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in @('appId', 'installationId', 'privateKeyPath', 'repository')) {
        if (-not $config.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$config[$key])) {
            Write-Failure "configuration key '$key' is required in $path"
        }
    }
    if ([string]$config['installationId'] -notmatch '^[0-9]+$') {
        Write-Failure 'installationId must be numeric'
    }
    if ([string]$config['repository'] -notmatch '^[A-Za-z0-9._-]+$') {
        Write-Failure 'repository must be a repository name without owner'
    }
    if (-not $config.ContainsKey('apiBaseUrl')) { $config['apiBaseUrl'] = 'https://api.github.com' }
    if (-not $config.ContainsKey('gitHost')) { $config['gitHost'] = 'github.com' }
    if (-not $config.ContainsKey('ghPath')) { $config['ghPath'] = 'gh' }

    $api = [Uri][string]$config['apiBaseUrl']
    if ($api.Scheme -ne 'https' -and -not ($api.Scheme -eq 'http' -and $api.IsLoopback)) {
        Write-Failure 'apiBaseUrl must use https (plain http is allowed only for loopback)'
    }
    $config['apiBaseUrl'] = ([string]$config['apiBaseUrl']).TrimEnd('/')
    return $config
}

function ConvertTo-Base64Url([byte[]]$Bytes) {
    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-AppJwt([hashtable]$Config) {
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    # Backdate iat for clock skew; GitHub rejects lifetimes above ten minutes.
    $header = '{"alg":"RS256","typ":"JWT"}'
    $payload = [ordered]@{ iat = $now - 60; exp = $now + 540; iss = $Config['appId'] } |
        ConvertTo-Json -Compress
    $utf8 = [Text.Encoding]::UTF8
    $signingInput = (ConvertTo-Base64Url $utf8.GetBytes($header)) + '.' +
        (ConvertTo-Base64Url $utf8.GetBytes($payload))

    $keyPath = [string]$Config['privateKeyPath']
    if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
        Write-Failure "private key not found: $keyPath"
    }
    $rsa = [Security.Cryptography.RSA]::Create()
    try {
        $rsa.ImportFromPem((Get-Content -LiteralPath $keyPath -Raw))
        $signature = $rsa.SignData(
            [Text.Encoding]::ASCII.GetBytes($signingInput),
            [Security.Cryptography.HashAlgorithmName]::SHA256,
            [Security.Cryptography.RSASignaturePadding]::Pkcs1)
    }
    finally {
        $rsa.Dispose()
    }
    return $signingInput + '.' + (ConvertTo-Base64Url $signature)
}

function Get-InstallationToken([hashtable]$Config) {
    $jwt = New-AppJwt $Config
    $uri = "$($Config['apiBaseUrl'])/app/installations/$($Config['installationId'])/access_tokens"
    $body = @{ repositories = @([string]$Config['repository']) } | ConvertTo-Json -Compress
    try {
        $response = Invoke-RestMethod -Method Post -Uri $uri -Body $body `
            -ContentType 'application/json' `
            -Headers @{
                Authorization          = "Bearer $jwt"
                Accept                 = 'application/vnd.github+json'
                'X-GitHub-Api-Version' = '2022-11-28'
            }
    }
    catch {
        Write-Failure "installation token request failed: $($_.Exception.Message)"
    }
    $tokenProperty = if ($response) { $response.PSObject.Properties['token'] } else { $null }
    if (-not $tokenProperty -or [string]::IsNullOrWhiteSpace([string]$tokenProperty.Value)) {
        Write-Failure 'installation token response did not contain a token'
    }
    return $response
}

# Permissions the agent workflow needs (ADR-031, ADR-033) and ones it must not have.
$RequiredPermissions = @{ contents = 'write'; pull_requests = 'write'; issues = 'write' }
$ForbiddenPermissions = @('workflows')

function Assert-TokenPermissions($Response) {
    # Fail closed: the installation token response must report its permissions.
    $property = $Response.PSObject.Properties['permissions']
    if (-not $property -or $null -eq $property.Value) {
        Write-Failure 'installation token response did not report permissions'
    }
    $granted = $property.Value
    foreach ($name in $RequiredPermissions.Keys) {
        $value = $granted.PSObject.Properties[$name]
        if (-not $value -or [string]$value.Value -ne $RequiredPermissions[$name]) {
            Write-Failure "App permission $name must be $($RequiredPermissions[$name])"
        }
    }
    foreach ($name in $ForbiddenPermissions) {
        if ($granted.PSObject.Properties[$name]) {
            Write-Failure "App must not have the $name permission"
        }
    }
}

function Read-CredentialRequest {
    $fields = @{}
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ($line -eq '') { break }
        $separator = $line.IndexOf('=')
        if ($separator -gt 0) {
            $fields[$line.Substring(0, $separator)] = $line.Substring($separator + 1)
        }
    }
    return $fields
}

function Invoke-Credential([string]$Operation) {
    # store/erase are no-ops: tokens are short-lived and never persisted.
    if ($Operation -ne 'get') { return }
    $request = Read-CredentialRequest
    $config = Read-AppConfig
    if ($request['protocol'] -ne 'https' -or $request['host'] -ne $config['gitHost']) {
        # Not ours; answer nothing so Git falls back to its normal behavior.
        return
    }
    $token = (Get-InstallationToken $config).token
    [Console]::Out.Write(
        "protocol=https`nhost=$($config['gitHost'])`nusername=x-access-token`npassword=$token`n")
}

function Invoke-Gh([string[]]$GhArgs) {
    if ($GhArgs.Count -lt 2 -or -not $AllowedGhCommands.ContainsKey($GhArgs[0]) -or
        $AllowedGhCommands[$GhArgs[0]] -notcontains $GhArgs[1]) {
        Write-Failure "gh command not allowed for the agent identity: gh $($GhArgs -join ' ')"
    }
    $config = Read-AppConfig
    $env:GH_TOKEN = (Get-InstallationToken $config).token
    $env:GH_HOST = [string]$config['gitHost']
    Remove-Item Env:GITHUB_TOKEN, Env:GH_ENTERPRISE_TOKEN -ErrorAction SilentlyContinue
    & ([string]$config['ghPath']) @GhArgs
    exit $LASTEXITCODE
}

if ($args.Count -eq 0) {
    Write-Failure 'usage: github-app.ps1 check | credential <get|store|erase> | gh <args...>'
}
$command = [string]$args[0]
$rest = @($args | Select-Object -Skip 1 | ForEach-Object { [string]$_ })

switch ($command) {
    'check' {
        $config = Read-AppConfig
        $response = Get-InstallationToken $config
        Assert-TokenPermissions $response
        $expires = $response.PSObject.Properties['expires_at']
        [Console]::Out.WriteLine(
            "ok: installation $($config['installationId']) repository $($config['repository']) " +
            "permissions verified; " +
            "token expires $(if ($expires) { $expires.Value } else { 'unknown' })")
    }
    'credential' {
        if ($rest.Count -ne 1) { Write-Failure 'usage: github-app.ps1 credential <get|store|erase>' }
        Invoke-Credential $rest[0]
    }
    'gh' { Invoke-Gh $rest }
    default { Write-Failure "unknown command: $command" }
}
exit 0
