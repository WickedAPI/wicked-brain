#!/usr/bin/env python3
"""auto_merge_exact_duplicates.py - the one upstream gap this fork closes for solo use.

Upstream's PostCompact background agent (hooks/bg-agent.sh) is add/update-only
by design, because an unattended agent choosing which of two notes to keep is a
judgment call, not mechanics (references/write-rules.md draws that line for
/brain-merge too: `merge_notes.py` does the mechanical half, a human or an
interactive agent composes the merged body).

For solo, single-vault use, one narrow case IS mechanical: two notes whose
bodies are near-byte-identical are not a judgment call, they are the same note
written twice. This script finds ONLY that case - similarity >= EXACT_THRESHOLD
(0.97, deliberately far above vault_health's 0.6 "likely duplicate" signal) -
and auto-applies the merge via merge_notes.compute_merge/apply_merge, reusing
the canonical note's own body verbatim (nothing to synthesize when the two
bodies already agree almost word-for-word).

Anything below the threshold is left for a human to run /brain-merge on. This
script never guesses on a real judgment call, and never touches a duplicate
group bigger than 2 (same ambiguity merge_notes.py itself refuses).

Usage:
    python scripts/auto_merge_exact_duplicates.py --path /vault [--apply] [--json]

Dry run (default) previews what would merge. --apply performs the merges.
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_notes import apply_merge, compute_merge  # noqa: E402
from note_io import read_exact  # noqa: E402
from vault_health import (  # noqa: E402
    FRONTMATTER_RE,
    _max_pairwise_similarity,
    check_duplicates,
    load_vault,
    load_vault_config,
)
from vault_lock import write_lock  # noqa: E402 - see its module docstring for why this is shared

EXACT_THRESHOLD = 0.97  # far above vault_health's 0.6 "likely duplicate" signal

# _max_pairwise_similarity only compares each note's first 1000 chars (it's a
# cheap human-facing signal for /brain-health, not a safety gate - a person
# reads both full notes before deciding to merge). This script is the one
# place that merges WITHOUT a human composing/reviewing the result, reusing
# the canonical note's body verbatim on the assumption the two bodies "already
# agree almost word-for-word" - so it needs its own full-body check. Without
# this, two notes with matching introductions but a different ending (e.g. two
# decision notes that agree on context but reached opposite conclusions) can
# score ~1.0 on the capped check purely because the difference falls past
# character 1000, and the losing decision is gone with no backup outside git
# (found 2026-09-10 via Codex Astra's report; reproduced with two notes over
# 1000 identical chars followed by opposite "we chose X" / "we chose Y").
# Capped (not fully unbounded) to bound difflib's cost on a pathologically
# large note - 50000 chars covers the overwhelming majority of real notes
# completely, which is what actually matters here.
_FULL_CHECK_CAP = 50_000


def _full_prose(text: str) -> str:
    """Same stripping _max_pairwise_similarity's _prose() does (frontmatter,
    the '## For future agent' preamble heading, whitespace collapse) but over
    the whole note instead of the first 1000 chars - see module docstring."""
    text = FRONTMATTER_RE.sub("", text, count=1)
    text = re.sub(
        r"(?:##|>[ \t]*\[![A-Za-z][\w-]*\][-+]?)[ \t]+For future (?:agent|AI|Claude|Codex)",
        "", text,
    )
    return re.sub(r"\s+", " ", text).strip()[:_FULL_CHECK_CAP]


def find_exact_pairs(vault: Path) -> list[dict]:
    excludes = load_vault_config(vault)
    notes = load_vault(vault, excludes)
    pairs = []
    for issue in check_duplicates(notes):
        files = issue["files"]
        if len(files) != 2:
            continue  # never guess a canonical note out of a 3+ group
        sim = _max_pairwise_similarity(notes, files)
        if sim < EXACT_THRESHOLD:
            continue
        a, b = files
        full_sim = difflib.SequenceMatcher(
            None, _full_prose(notes[a]["content"]), _full_prose(notes[b]["content"])
        ).ratio()
        if full_sim < EXACT_THRESHOLD:
            continue  # the capped check was fooled by a long shared prefix - leave it for a human
        # Canonical = the note with more frontmatter text (a cheap proxy for
        # "more fully filled in"), tie-broken by the earlier path so the
        # choice is deterministic and repeatable across runs.
        fm_len_a = len(notes[a]["frontmatter"] or "")
        fm_len_b = len(notes[b]["frontmatter"] or "")
        canonical, retire = (a, b) if (fm_len_a, a) >= (fm_len_b, b) else (b, a)
        pairs.append({"canonical": canonical, "retire": retire, "similarity": round(min(sim, full_sim), 4)})
    return pairs


def run(vault: Path, apply: bool, as_json: bool) -> int:
    pairs = find_exact_pairs(vault)
    if not pairs:
        if as_json:
            print(json.dumps({"merged": [], "checked": 0}))
        else:
            print("No near-identical duplicate pairs found.")
        return 0

    results = []
    for pair in pairs:
        canonical_rel, retire_rel = pair["canonical"], pair["retire"]
        # Reuse the canonical note's own body verbatim - the two bodies already
        # agree almost word-for-word at this similarity, so there is nothing to
        # synthesize or reconcile the way an interactive /brain-merge would.
        #
        # Locked for the whole read-compute-write span when actually applying:
        # a concurrent writer landing between the read above and the write in
        # apply_merge would have its edit silently discarded by a merge
        # computed from stale content - see vault_lock.py's module docstring.
        with write_lock(vault) if apply else contextlib.nullcontext():
            text = read_exact(vault / canonical_rel)
            if text is None:
                continue  # not valid UTF-8: refuse silently, same as merge_notes.py
            body = text.split("---", 2)[-1] if text.count("---") >= 2 else text
            result = compute_merge(vault, canonical_rel, retire_rel, body)
            if apply:
                apply_merge(vault, result)
        results.append({**pair, "applied": apply})

    if as_json:
        print(json.dumps({"merged": results, "checked": len(pairs)}))
    else:
        verb = "Merged" if apply else "Would merge"
        for r in results:
            print(f"{verb} (similarity {r['similarity']}): {r['retire']} -> {r['canonical']}")
        if not apply:
            print("\nDry run: nothing changed. Re-run with --apply to write.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return run(Path(args.path).expanduser(), args.apply, args.json)


if __name__ == "__main__":
    sys.exit(main())
