---
description: Sync the vault across your devices - push local changes, pull remote ones, and report any genuine conflicts
category: vault
triggers_en: ["sync my memory", "sync the vault", "push my notes", "pull my notes"]
---

Use the wicked-brain skill. Execute `/brain-sync $ARGUMENTS`:

The optional argument is `push`, `pull`, or nothing (default: full bidirectional `sync`).

1. Check that sync is configured: `WICKED_BRAIN_SYNC_URL`, `WICKED_BRAIN_SYNC_TOKEN`, and `WICKED_BRAIN_SYNC_PASSPHRASE` must all be set in the environment. If any are missing, say so plainly and stop - do not guess a URL or invent a passphrase. Point the user at `sync_server/README.md` for how to stand up (or find) the sync server, and at this command's own frontmatter for the env var names.
2. Read `_CLAUDE.md` (or `AGENTS.md`) first to find the vault path. The skill root was given at session start as **Skill root**; substitute it for `SKILL_ROOT` below.
3. If this vault has never synced before (no `.sync-state.json` at the vault root) AND the vault currently has few or no notes, ask whether this is a brand-new device joining an existing synced vault - if so, use `--bootstrap` instead of `sync` so it fetches everything rather than diffing against nothing:
   ```bash
   uv run --directory "SKILL_ROOT" python scripts/vault_sync.py bootstrap --path <vault> --url "$WICKED_BRAIN_SYNC_URL" --token "$WICKED_BRAIN_SYNC_TOKEN" --passphrase "$WICKED_BRAIN_SYNC_PASSPHRASE" --device "<a stable name for this machine>" --json
   ```
   Bootstrap does NOT blindly overwrite this device's own vault: every device's own `/brain-init` creates local `_CLAUDE.md`/`index.md`/`CRITICAL_FACTS.md` before it ever syncs, so bootstrap checks each path first - a local file that already exists and differs from what's about to be pulled is saved as a conflict copy (`preserved` in the result), never silently discarded. Report those the same way you'd report a sync conflict (step 5 below).
4. Otherwise, run the requested mode (default `sync`):
   ```bash
   uv run --directory "SKILL_ROOT" python scripts/vault_sync.py <push|pull|sync> --path <vault> --url "$WICKED_BRAIN_SYNC_URL" --token "$WICKED_BRAIN_SYNC_TOKEN" --passphrase "$WICKED_BRAIN_SYNC_PASSPHRASE" --device "<a stable name for this machine>" --json
   ```
   Use a stable, human-readable `--device` value (e.g. the machine's hostname) - it's what conflict-copy filenames and pull commit messages will reference, so a consistent name makes history readable across devices.
5. Report back plainly from the JSON result: what was pushed, what was pulled, what got trashed locally (a note someone else deleted), and - most important - any conflicts (`sync`'s `conflicts` list, or bootstrap's `preserved` list). For each one, say which version won and where the losing version was saved (`conflict_copy`), and suggest the user review it and fold in anything worth keeping, the same way `/brain-merge` output is reviewed.
6. If the command fails outright (network error, wrong passphrase, auth rejected), relay the actual error - do not report success, and do not retry silently with different credentials.

Version history from git-backed local commits does **not** sync between devices - only current note content does. A pulled note lands in this device's own local git history (if this vault has one) via the same commit path `/brain-save` uses, but each device's history starts from wherever it joined.

---

**Anti-fabrication:** Report exactly what `vault_sync.py` returned - never claim a clean sync when the command reported conflicts or errors, and never invent a device name, URL, or token value that wasn't actually configured.
