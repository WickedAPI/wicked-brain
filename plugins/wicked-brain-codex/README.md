# Wicked Brain for Codex

A plain-markdown memory vault your agents share. This is the Codex plugin build.

- **Skills:** `$brain-find`, `$brain-save`, `$brain-capture`, `$brain-health`, `$brain-sync`, `$brain-init`, `$brain-setup` and more. Codex has no slash commands, so each command is a skill.
- **MCP server:** local `wicked-brain` stdio server (ranked vault search and reads), started with `uv`.
- **Setup:** run `$brain-setup` once; it records your vault path in `~/.config/wicked-brain/.env`.
- **Needs:** `uv` on your PATH (https://docs.astral.sh/uv/).
- **Not included on Codex:** automatic recall and auto-sync hooks. Those run on Claude Code only; on Codex use `$brain-find` and `$brain-sync`.

Project home: https://github.com/choaticpixels/wicked-brain
