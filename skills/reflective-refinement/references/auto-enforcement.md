# Automatically start fixed-iteration or verifiable-goal campaigns

Use for **explicit N** or an **unmet, testable goal** on any compatible agent CLI with a shell and Python. A worker running with `RR_SUPERVISED=1` must not start this. The user invokes only `/reflective-refinement ...`; the outer agent launches the controller itself.

1. Inspect the project and identify the Git root, precise source folder/file and exact user goal. Do not guess a source path from examples. Record/commit a safe checkpoint on a development branch before launching, without sweeping up unrelated work.
2. Invoke the terminal tool. Use the actual installed skill location resolved from `SKILL.md`, not a copy in the project:

   ```bash
   python /actual/skill/path/scripts/auto_start.py launch \
     --workspace /actual/project/root \
     --artifact path/to/actual/source \
     --goal "The exact user goal" \
     --iterations 30 --evidence-kind visual
   ```

   For a goal such as "make real page rendering at least 50% faster", first freeze a verified evaluation contract and then launch:

   ```bash
   python /actual/skill/path/scripts/auto_start.py launch \
     --workspace /actual/project/root --artifact source/ \
     --goal "Make real page rendering at least 50% faster" \
     --evaluation-contract evaluation.json --until-target
   ```

   A performance goal needs `primary_metrics[].target_value` (or executable target checks),
   `case_requirements` and benchmark `case_facts` proving representative user content was loaded.
   The supervisor verifies baseline fidelity before the first worker. `KEEP` with `NOT_MET`
   continues the loop; only externally verified `MET` closes goal mode.

3. Read the JSON response. `LAUNCHED` is **not** `COMPLETE`. Use `python /actual/skill/path/scripts/auto_start.py status --state-dir /actual/project/root/.refinement/loop-contract` to inspect the count. Logs: `.refinement/loop-contract/controller.log`, `turns/NNNN.events.jsonl`; records: `contract.json`.
4. If the launcher returns `AUTO_ENFORCEMENT_BLOCKED`, inspect and fix a real environment/permission/scope issue, then retry when safe. Never fall back silently to a non-supervised 30/30 promise. If support cannot be established, work with the inline guard while reporting the limited ability to enforce future turns.
5. Do not start another supervisor if an identical campaign is running. The launcher automatically restarts an identical stopped campaign when its prior receipt is resolved and source is safe. Inspect prior process/log/state first. Never erase the contract, skip pending reconciliation, or force-reset a live lock.

The controller uses a fresh worker CLI invocation per candidate (Codex, Claude, or a configured argv adapter). Individual trials are verified by `loop_guard.py`. An independent, report-only diagnostic agent can suggest a different next test after repeated stalls; this adviser does not approve changes or rewrite acceptance. A structurally valid screenshot is not aesthetic proof; the actual game still needs inspection.

## Limits and portability

This is an **agent-initiated external supervisor**, not a magical hook into the parent model runtime. The initial tool call is not enforceable if the outer model refuses to follow `SKILL.md`, nor can a sandbox always spawn nested authenticated Codex processes. The script starts a detached process so it may survive the initial turn if the host permits; some hosts terminate child processes on session exit. A genuinely unconditional start/stop guarantee requires integration with the host itself (for instance a built-in lifecycle feature). **Do not falsely claim such integration.** Other hosts without a compatible CLI simply use the portable skill and in-turn guard; they are not required to support Codex.

No implicit overall campaign deadline or cap of four trials exists; the per-turn timeout is a hang guard. Goal mode has no arbitrary iteration cap; repeated worker failures still have a configurable retry limit to prevent infinite paid failures. A stopped/blocked run is INCOMPLETE and can be resumed when safe. Do not claim that the skill can survive computer shutdown, model entitlement exhaustion, revoked permissions, or an outer model that ignores the initial tool call without host-level lifecycle integration.
