# publish-release

This folder contains a GitHub Copilot-compatible skill scaffold for publishing `release-assessment.md` into a remote GitHub repository.

## Files

- `SKILL.md` — skill definition consumed by GitHub Copilot.
- `scripts/publish_release.py` — helper script that clones/pulls the remote repo, copies the assessment file into place, commits, and pushes.

## Environment variables

- `REMOTE_REPO_URL`: remote Git repository clone URL.
- `REMOTE_BRANCH`: target branch to push to (default: `main`).
- `COMMIT_MESSAGE`: commit message (default: `Publish release assessment`).
- `GITHUB_TOKEN`: optional token if the remote requires authentication.

## Usage

python scripts/publish_release.py --file release-assessment.md --remote-url "$REMOTE_REPO_URL" --branch "$REMOTE_BRANCH"
