# Automatically start fixed-iteration campaigns from the installed skill

Use only for **explicit N**, in an outer Codex CLI agent with a shell and `python` available. A worker running with `RR_SUPERVISED=1` must not start this. The user only invokes `/reflective-refinement ... 30 iterations`; the agent launches the controller itself.

1. Inspect the project and identify the Git root, precise source folder/file and exact user goal. Do not guess a source path from examples. Record/commit a safe checkpoint on a development branch before launching, without sweeping up unrelated work.
2. Invoke the terminal tool. Use the actual installed skill location resolved from `SKILL.md`, not a copy in the project:

   ```bash
   python /actual/skill/path/scripts/auto_start.py launch \
     --workspace /actual/project/root \
     --artifact path/to/actual/source \
     --goal "The exact user goal" \
     --iterations 30 --evidence-kind visual
   ```

3. Read the JSON response. `LAUNCHED` is **not** `COMPLETE`. Use `python /actual/skill/path/scripts/auto_start.py status --state-dir /actual/project/root/.refinement/loop-contract` to inspect the count. Logs: `.refinement/loop-contract/controller.log`, `turns/NNNN.events.jsonl`; records: `contract.json`.
4. If the launcher returns `AUTO_ENFORCEMENT_BLOCKED`, inspect and fix a real environment/permission/scope issue, then retry when safe. Never fall back silently to a non-supervised 30/30 promise. If support cannot be established, work with the inline guard while reporting the limited ability to enforce future turns.
5. Do not start another supervisor if an identical campaign is running. If a stopped campaign needs resuming, inspect process/log/state/pending first; then the agent, not the user, may call `auto_start.py launch ... --resume` with identical arguments. Never erase the contract or force-reset a live lock.

The controller uses `codex exec` with a fresh worker invocation per candidate, and the worker prompt explicitly reads this skill and disables nested auto-launch. Individual trials are verified by `loop_guard.py`. Workers preserve candidate/evidence receipts, with keep/discard/outcome distinction. A structurally valid screenshot is not aesthetic proof; the actual game still needs inspection.

## Limits and portability

This is an **agent-initiated external supervisor**, not a magical hook into the parent model runtime. The initial tool call is not enforceable if the outer model refuses to follow `SKILL.md`, nor can a sandbox always spawn nested authenticated Codex processes. The script starts a detached process so it may survive the initial turn if the host permits; some hosts terminate child processes on session exit. A genuinely unconditional start/stop guarantee requires integration with the host itself (for instance a built-in lifecycle feature). **Do not falsely claim such integration.** Other hosts without a compatible CLI simply use the portable skill and in-turn guard; they are not required to support Codex.

No implicit overall campaign deadline or cap of four trials exists; the per-turn timeout is a hang guard. Never trade genuine visual/behavioral quality for a fabricated iteration count. Stop with INCOMPLETE and evidence when actual access or safe experimentation is impossible.
