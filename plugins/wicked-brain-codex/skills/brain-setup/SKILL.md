---
name: brain-setup
description: "Connect the Wicked Brain plugin to a memory vault: records the vault location for the MCP server and skills, checks that search works, and offers to create the vault. Run once after installing, or whenever brain search says the vault is not configured. Triggers: set up wicked brain, connect my vault, brain setup."
---

> **Plugin root.** `<plugin-root>` means the folder two levels above this `SKILL.md` (the folder that contains `skills/`, `references/` and `scripts/`).

Connect this plugin to the user's vault.

1. **Find the vault.** Check, in order: the `WICKED_BRAIN_VAULT_PATH` environment variable, then a `WICKED_BRAIN_VAULT_PATH=` line in `~/.config/wicked-brain/.env`. If one is set and the folder exists, say where it points and skip to step 4.
2. **Ask where the vault is (or should be).** Accept an existing folder of markdown notes or a new empty path, such as `~/Vault`. Never guess a path and never pick one for the user.
3. **Record it.** Create `~/.config/wicked-brain/` if needed and write (or update, keeping any other lines) `~/.config/wicked-brain/.env` containing exactly `WICKED_BRAIN_VAULT_PATH=<absolute path, forward slashes>`. On Windows `~` is the user profile folder. Tell the user the file location; it holds a path only, no secrets.
4. **Check it.** Confirm the folder exists. If it has none of `projects/`, `entities/`, `decisions/`, `sessions/`, `concepts/`, it is new: offer to run `$brain-init` to create the structure, and run it only if the user says yes.
5. **Verify search.** Call the `wicked-brain` MCP search tool with a simple query. If the tool is missing, tell the user to restart Codex so the plugin's MCP server restarts and to confirm `uv` is installed (https://docs.astral.sh/uv/); do not try to work around it.
6. **Finish.** Summarise: vault path, whether it is new or existing, whether search works, and the skills now available (`$brain-find`, `$brain-save`, `$brain-capture`, `$brain-health`, `$brain-sync` and the rest).

Optional sync: `$brain-sync` needs `WICKED_BRAIN_SYNC_URL`, `WICKED_BRAIN_SYNC_TOKEN` and `WICKED_BRAIN_SYNC_PASSPHRASE` in the environment. Mention this only if the user asks about syncing across devices; never ask for or write those secrets yourself.
