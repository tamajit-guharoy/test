<#
.SYNOPSIS
    Clones a GitHub repo, copies a file into it, commits, and pushes.
.PARAMETER RepoUrl
    GitHub repository URL (https://github.com/owner/repo.git)
.PARAMETER BranchName
    Branch to check out (created if it doesn't exist on remote)
.PARAMETER InputFilePath
    Local file to copy into the repo
.PARAMETER TargetPath
    Destination directory relative to the repo root; the input filename is preserved
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl,

    [Parameter(Mandatory = $true)]
    [string]$BranchName,

    [Parameter(Mandatory = $true)]
    [string]$InputFilePath,

    [Parameter(Mandatory = $true)]
    [string]$TargetPath
)

$ErrorActionPreference = 'Stop'

# --- Validation ---
$errors = @()

if (-not $RepoUrl) { $errors += "RepoUrl is required (GitHub repository URL)" }
if (-not $BranchName) { $errors += "BranchName is required" }
if (-not $InputFilePath) { $errors += "InputFilePath is required (local file to copy)" }
if (-not $TargetPath) { $errors += "TargetPath is required (destination directory relative to repo root)" }

if (-not (Test-Path $InputFilePath -PathType Leaf)) {
    $errors += "Input file not found: '$InputFilePath'"
}

$token = $env:GITHUB_TOKEN
if (-not $token) {
    $errors += "GITHUB_TOKEN environment variable is not set"
}

if ($errors.Count -gt 0) {
    Write-Host "ERROR: The following details are missing or invalid:" -ForegroundColor Red
    foreach ($e in $errors) {
        Write-Host "  - $e" -ForegroundColor Red
    }
    exit 1
}

$fileName = Split-Path $InputFilePath -Leaf
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("repo_" + [guid]::NewGuid().ToString('N').Substring(0, 8))

Write-Host "Temp directory: $tempDir"

# --- Build authenticated clone URL ---
try {
    $uri = [System.Uri]$RepoUrl
    $cloneUrl = "$($uri.Scheme)://oauth2:$token@$($uri.Host)$($uri.AbsolutePath)"
} catch {
    Write-Host "ERROR: Invalid RepoUrl '$RepoUrl' — $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$pushSucceeded = $false

try {
    # --- Clone ---
    Write-Host "Cloning $RepoUrl ..."
    git clone --quiet $cloneUrl $tempDir 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Git clone failed (exit code $LASTEXITCODE). Check the repo URL and token."
    }

    Push-Location $tempDir

    # --- Checkout / create branch ---
    Write-Host "Setting up branch '$BranchName' ..."
    $remoteBranch = git ls-remote --heads origin $BranchName 2>$null

    if ($remoteBranch) {
        git checkout $BranchName 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Git checkout '$BranchName' failed." }
    } else {
        git checkout --orphan $BranchName 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Git checkout --orphan '$BranchName' failed." }
        git rm -r --quiet --cached . 2>&1 | Out-Null
        git commit --allow-empty -m "Initial empty commit for $BranchName" 2>&1 | Out-Null
    }

    # --- Build target path: <TargetDir>/<filename> ---
    $targetFullPath = Join-Path (Join-Path $tempDir $TargetPath) $fileName
    $targetDir = Join-Path $tempDir $TargetPath
    $relativePath = "$TargetPath/$fileName".TrimStart('/')

    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Force $targetDir | Out-Null
        Write-Host "Created directory: $targetDir"
    }

    # --- Copy file ---
    Write-Host "Copying '$InputFilePath' -> '$relativePath' ..."
    Copy-Item -Path $InputFilePath -Destination $targetFullPath -Force

    # --- Add, commit, push ---
    Write-Host "Committing and pushing ..."
    git add $relativePath
    if ($LASTEXITCODE -ne 0) { throw "git add failed." }

    $commitMsg = "$fileName added"
    git commit -m $commitMsg 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # Capture output to check if it's "nothing to commit"
        $commitOutput = git commit -m $commitMsg 2>&1
        if ($commitOutput -notmatch "nothing to commit") {
            throw "git commit failed: $commitOutput"
        }
        Write-Host "No changes to commit (file already matches)."
    }

    git push -u origin $BranchName 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed. Check branch permissions and token scope."
    }

    $pushSucceeded = $true
    Write-Host "SUCCESS: '$fileName' pushed to '$RepoUrl' on branch '$BranchName'." -ForegroundColor Green

} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location -ErrorAction SilentlyContinue

    if ($pushSucceeded) {
        Write-Host "Cleaning up temp directory..."
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    } else {
        Write-Host "Push did not succeed — temp directory kept for inspection: $tempDir" -ForegroundColor Yellow
    }
}
