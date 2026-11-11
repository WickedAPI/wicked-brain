---
name: brain-init
description: "Bootstrap a new memory vault - fixed folder structure, operating manuals for both Claude Code and Codex CLI, index.md, CRITICAL_FACTS.md Triggers: init memory, bootstrap vault, set up my memory, create a new vault. Use only when the user explicitly asks for it."
---

> **Plugin root.** This skill ships inside the Wicked Brain plugin. `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`). Resolve every `<plugin-root>/...` path below from this file's own location. The vault itself is wherever `WICKED_BRAIN_VAULT_PATH` (or `~/.config/wicked-brain/.env`) points; if neither is set, run `$brain-setup` first.


Use the wicked-brain skill. Execute `$brain-init`:

1. Ask the user for the vault path if not already known (check for a `WICKED_BRAIN_VAULT_PATH` env var first).
2. Create the fixed folder structure if any part is missing: `projects/`, `entities/`, `decisions/`, `sessions/`, `concepts/`, `_trash/`. Do not invent additional top-level folders - this schema is intentionally fixed (see `<plugin-root>/references/vault-schema.md`).
3. Generate `_CLAUDE.md` (Claude Code) and `AGENTS.md` (Codex CLI) from `<plugin-root>/references/claude-md-template.md`, filling in `{{VAULT_NAME}}` from the folder name (or ask the user). The two files carry the same content; neutralize Claude-specific tool names (`read files` -> `read files`, etc.) in `AGENTS.md` only.
4. Create `CRITICAL_FACTS.md` at the vault root if it doesn't exist: a short (~100-150 token) file for things worth loading every session (timezone, current focus). Leave it mostly empty with a comment explaining its purpose - do not fabricate content.
5. Generate `index.md`: a catalog of every existing note grouped by folder, one line each (`- [[Note Name]] - brief description` from frontmatter or the first line of body). If the vault is new and empty, write a stub explaining the format.
6. Create today's `sessions/YYYY-MM-DD.md` with an init entry: `**HH:MM** - init | Vault initialized with _CLAUDE.md, AGENTS.md, index.md, CRITICAL_FACTS.md`.
7. **Ask** whether to enable version history (Phase 2): a git repo local to the vault, giving free diff/rollback/blame with no server involved. This is the one place that turns it on - everything else (the write-time git hook on Claude Code, the commit-if-git-repo step in `$brain-save`/`$brain-capture`/`$brain-reconcile`, the MCP write path) only ever checks for `.git/` and stays silent if it's absent. If the user says yes and the vault is not already a git repo: `uv run --directory "<plugin-root>" scripts/vault_git.py --path <vault> --init --json`, which runs `git init`, writes a vault `.gitignore` (`.claude-runs/`, `*.semantic-index.json`, `.claude-lock`) if one doesn't already exist, and makes one initial commit covering everything just created. If the vault is already a git repo, say so and skip - never re-init.
8. Confirm what was written and tell the user to restart their Claude Code / Codex CLI session so the new files take effect. **Also check whether the platform-level install has actually been done** - this command only writes vault content; it does not symlink Claude Code's commands, copy Codex CLI's skill tree, or register the MCP server. If `/brain-*` or `$brain-*` don't already work in the user's current session, point them at `dist/claude-code/INSTALL.md` and/or `dist/codex-cli/INSTALL.md` (the latter has a global option, recommended for using the vault across more than one project folder) - a freshly-initialized vault does nothing on its own without that separate, one-time, per-machine step.

If `_CLAUDE.md` already exists: show a diff of what would change and ask before overwriting - never silently clobber a hand-edited operating manual. If `index.md` already exists, regenerate it (it's always meant to be a fresh catalog of current state).

---

**AI-first rule:** Every note created or updated by this command MUST follow `<plugin-root>/references/ai-first-rules.md`.

**Anti-fabrication:** Do not invent vault content, entity names, or project names that don't already exist in the vault when generating `index.md` - list only what's really there.
