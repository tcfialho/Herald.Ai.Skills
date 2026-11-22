# Explicit N experiment contract — use this when the user requests a number

## First resolve what a genuine iteration is

**One credited trial** = a new falsifiable hypothesis, a genuinely changed source/artifact variant, an actual test/render/inspection of that variant, saved evidence, and a decision (keep, discard, inconclusive or crash). Failures count as attempted experiments if a real candidate was built and evaluated; repetitions of the same candidate, baseline measurement, thinking aloud, a plan, one A/B test of unchanged source, a screenshot not taken from an actual output, or tests passing without an attempted modification **do not count**. Do not equate '30 trials' with '30 accepted improvements'.

The user-defined count overrides the default limit of 12. Set a contract for the exact requested number and do not change N in response to model preference. Progress is `verified_attempts / required`. A verified quality target achieved early changes the **research direction** (challenge edge cases, compare materials/layouts, verify alternative mechanisms), not the obligation to execute genuine experiments. If no defensible experiment remains, report a blocked **partial** run, never make a cosmetic change merely for a receipt.

## When Python and a terminal are available

Find `scripts/loop_guard.py` next to this skill's `SKILL.md`; run it against the project root and the **source file/directory**, not the generated screenshots. Choose an artifact directory small enough to avoid unrelated files. Use the exact goal and N from the user; for visual improvements use `--evidence-kind visual`.

```bash
python /path/to/reflective-refinement/scripts/loop_guard.py init \
  --workspace /path/to/project --artifact src/track \
  --state-dir /path/to/project/.refinement/loop-contract \
  --iterations 30 --evidence-kind visual --goal "Improve track edges in actual gameplay"

python /path/to/reflective-refinement/scripts/loop_guard.py begin \
  --state-dir /path/to/project/.refinement/loop-contract \
  --hypothesis "Add grounded variation to the flat verge silhouette" \
  --planned-check "Compare gameplay screenshots at three camera locations"

# Edit source, build and inspect the result, save a REAL screenshot from the application.
python /path/to/reflective-refinement/scripts/loop_guard.py finish \
  --state-dir /path/to/project/.refinement/loop-contract \
  --outcome keep \
  --finding "Different edge heights improve depth while native tracks stay unchanged" \
  --evidence .refinement/screenshots/candidate-01.png

python /path/to/reflective-refinement/scripts/loop_guard.py status \
  --state-dir /path/to/project/.refinement/loop-contract --gate
```

`status --gate` returns nonzero while incomplete. The tool captures timestamps, parent/candidate SHA-256, evidence SHA-256, attempt count, and rejects duplicate candidate source, no-op attempts and missing/old evidence. Identical fresh screenshots are valid negative evidence for *different* candidates; they cannot alone justify a visual `keep`. It does **not** certify semantic novelty, actual aesthetic quality or truthful performance claims. These require exercising the artifact and independent evaluation when consequential.

An already pending trial must be reconciled rather than silently restarted; `abandon --reason "..."` frees its slot without adding a count. After a rejection, preserve evidence and restore only experiment-owned changes. Preserve Git history frequently and never reset unrelated work.

## Host enforcement, beyond a prompt

A skill is instructions; a single interactive agent can still end its reply at 2/30. The bundled `scripts/auto_start.py` starts a detached `scripts/codex_supervisor.py`, which invokes Codex non-interactively for one attempt, checks the guard ledger, and invokes it again until N verified attempts. **The skill itself instructs the outer Codex agent to invoke the launcher via its terminal tool; do not ask the user to run a command.** The controller installs no hooks, changes no global configuration, and is not needed for normal work without explicit N. A clean, recoverable Git branch is required. A supervised worker identified by `RR_SUPERVISED=1` must never launch another controller. The supervisor only claims COMPLETE at N/N; if permissions, timeouts, safety or a stubborn model block progress, it reports INCOMPLETE with logs. A markdown instruction cannot guarantee that a noncompliant outer agent invokes the launcher; this needs host-native lifecycle enforcement for an unconditional guarantee. Never hide an operational ceiling.

If Python is unavailable, keep the same attempt ledger manually in a project file and report honest progress; no mechanical guarantee exists without a host-side controller. Never imply that `SKILL.md` alone can force another model invocation after an agent returns.
