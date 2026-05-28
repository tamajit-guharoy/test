# Dummy caller for push-file-to-repo.ps1
# Replace these values with real ones to test or run the script.

$scriptDir = Split-Path $PSCommandPath -Parent
$pushScript = Join-Path $scriptDir "push-file-to-repo.ps1"

& $pushScript `
    -RepoUrl        "https://github.com/your-org/your-repo.git" `
    -BranchName     "test-branch" `
    -InputFilePath  "C:\Users\guhar\ws\test\sample.txt" `
    -TargetPath     "data/uploaded"
