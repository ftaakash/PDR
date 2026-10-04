---
description: Pick the next unchecked task in TASKS.md and work it per the project rules
---
1. Read `CLAUDE.md` and `TASKS.md`. Find the first unchecked task.
2. If it is marked HUMAN-GATE, stop: state exactly what the human must do or
   decide, what you have prepared, and what you will do after.
3. If it is AUTO: write or amend the design section in `docs/` FIRST, before
   running anything expensive. Then implement, add tests for decision logic,
   run `/verify`, update `docs/claims.json` and every doc quoting changed
   numbers in the same commit, tick the task with a dated note, and commit
   (small commit, clear message).
4. Obey the autonomy boundaries in `CLAUDE.md`. If a result contradicts the
   working thesis, present the data and options; do not choose a story.
5. End with a short report: what changed, what the data say (negatives
   included), what is still unverified, and the next task.
