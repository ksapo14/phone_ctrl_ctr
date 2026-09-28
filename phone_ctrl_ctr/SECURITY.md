# Security review

Reviewed September 27, 2026, through commit `3348742`.

## Results

The local pre-push check completed with no findings across 64 working files,
64 Git index entries, 92 history blobs reachable from local branches, tags,
and remote-tracking refs, and four built frontend files. It also checked for
the configured local secret without printing its value. A temporary synthetic
credential was correctly rejected and the test file was removed.

The dependency audits reported no known vulnerabilities: `npm audit` for Node
and `pip_audit` for the commands virtual environment. The Python environment's
pip was upgraded from 26.1.2 to 26.2.1 to resolve its reported advisory.
The application build, lint, and all 15 tests passed during this review.

## Changes applied

- Moved the active environment file out of the repository and OneDrive into
  `%USERPROFILE%\.phone-control\.env`. Its permissions, and those of the private
  HTTPS keys, are restricted to the current user, SYSTEM, and Administrators.
- Load server credentials from the process environment first, then the private
  environment file, then the ignored project environment file as a fallback.
- Remove `DEEPGRAM_API_KEY` from environments passed to child processes.
- Recheck both the authenticated session and controller connection before
  executing each inferred command. A controller replacement regression test
  covers commands awaiting inference.
- Ignore local credentials, certificates, model weights, virtual environments,
  and generated training artifacts. Keep sanitized smoke-test data in fixtures.
- Add a secret and artifact scanner and enable the local pre-push hook.

The checked-in `server/fixtures/audio-test-key.pem` is a public, disposable
test-only key. The scanner exemption requires its exact path and content hash.
It must never be used by a live server.

## Before pushing

From the application directory:

```powershell
npm run security:check
npm audit
.venv-commands\Scripts\python.exe -m pip_audit --progress-spinner off
```

Enable the hook for each new clone, from the repository root:

```powershell
git config core.hooksPath .githooks
git hook run pre-push
```

The hook runs locally and does not push. Git hooks are not installed
automatically by cloning, and can be bypassed; this is not a server-side gate.
The scanner checks eligible working files, index contents, branch/tag history,
and the built frontend. Findings contain locations and rule names, not values.

## Scope and limitations

This review found no production credentials in the scanned files. Pattern
matching and comparison with configured secrets cannot prove all credentials
are absent, particularly unknown or encoded credentials.

Local Codex recovery refs contain large model artifacts. They are outside the
ordinary branch/tag scan and are not sent by a normal branch push. They remain
available for recovery; do not mirror all refs to publish this repository.
Use `node scripts/security-check.mjs --history --all-refs` to inventory those
refs as well. Files above 10 MB are flagged for separate review rather than
content-scanned. Local ignored model binaries were not content-audited.

GitHub settings, Actions secrets/artifacts, forks, unreachable remote objects,
and OneDrive version history were not audited. Moving the environment file
does not erase any earlier cloud or backup copies. No Git history was rewritten
and this review did not push changes.

Restart the companion server manually to apply the server-side changes.
