---
description: Quick capture - zero friction, saves a fact, pattern, or idea to concepts/ and links it from today's session note
category: vault
trigger-mode: proactive
triggers_en: ["remember that", "capture this", "note this down", "keep this in mind"]
---

Use the wicked-brain skill. Execute `/brain-capture $ARGUMENTS`:

The optional argument is the text to capture. If not provided, pull the most recent worthwhile fact or idea from the conversation.

1. Read `_CLAUDE.md` (or `AGENTS.md`) first if it exists in the vault root.
2. Take the argument as the capture, or pull it from recent conversation context.
3. Search `concepts/` for a related existing note. If found, append to it (with today's date) rather than creating a near-duplicate.
4. If new: create `concepts/Title.md` with the minimal capture schema (`type: concept`, `date`, `tags: [concept]`, `ai-first: true`, `status: captured`, one-line body) - the documented capture exception in `references/ai-first-rules.md`: full enrichment happens later, not at capture time.
5. Add a brief link to it from today's session note (`sessions/YYYY-MM-DD.md`), creating that note if it doesn't exist yet.

Each write in steps 3-5 (the concept note, the session note) is a separate note - wrap each one individually with the shared vault lock per `references/write-rules.md`'s "Concurrent-safe writes" section, not the whole command.
6. **Version history (if enabled):** if `.git/` exists at the vault root, `git -C <vault> add -A && git -C <vault> commit -q -m "capture: <title>"`. Skip silently if there is no `.git/` directory. (Claude Code users get this automatically via `hooks/validate-ai-first.sh` - this step is the Codex CLI / no-hook-system path.)

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md`. The capture exception applies: minimal schema now, full enrichment later - but the preamble, `ai-first: true`, and a `date` are never optional even at capture time.

**Anti-fabrication:** Never invent context that wasn't actually said. If the source is ambiguous, capture it as stated and mark confidence `speculation` rather than upgrading it to `stated`.
