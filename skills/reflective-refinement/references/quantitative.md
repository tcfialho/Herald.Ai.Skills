# Quantitative evaluation and workload-dependent gains

Use for numerical/noisy goals or resource trade-offs; see [shared acceptance](evaluation.md).

## Measure comparably

Fix workload, environment, inputs, seeds, protocol and units. Record raw samples, warmup, center and spread. Use independent launches, paired inputs/seeds or interleaving to control drift; avoid shared-resource contention unless part of the workload. For variable results repeat the same baseline (e.g. 3–5 initial samples, not universal sufficiency). Estimate noise from repeats of the **same version**, never different candidates. Use median and median absolute deviation or another justified estimator; zero observed spread is not zero uncertainty.

If gain is near variability, repeat incumbent/candidate under matched conditions or mark uncertain if budget cannot resolve it. Report variation, not unsupported significance. Screening many candidates amplifies false positives; do not select the best noisy observation as confirmation. Separate setup, diagnostic and acceptance measures.

## Inspect variation before optimizing one case

When applicability or workload varies materially, define regimes **before search** from usage, required cases, failure paths and constraints: size/density, concurrency, cold/warm start, empty/tiny inputs, processing states or preparation vs use. Use the smallest meaningful matrix and actual frequencies when known.

- Measure end-to-end user outcome and relevant stage costs. For a cache or index, separate setup/build, lookup, reuse, memory and eviction/invalidation if relevant; a better inner loop can worsen a complete workflow.
- Identify which group matters most, what must not regress, and tolerable costs or trade-offs for other groups. If the distribution is unknown, report effects by group instead of a weighted average with invented weights. Use tail/worst cases when they matter. Protect required correctness and resource bounds independently of speed.
- Probe at least one relevant cheap/adverse or boundary case early when plausible costs differ. A cheap search signal that cannot represent a new approach's expected benefit is not enough to eliminate it; run a small informative prototype or representative probe if justified.
- Record each group's result, evidence and scope; don't rank using just a favorable group. Use [evaluation.md](evaluation.md) for promotion. A candidate meeting only a local target stays a scoped gain or alternative, not a globally verified winner.

## When different approaches win in different conditions

Do not assume one mechanism is universally best. Compare the incumbent and relevant specialists on common workload groups. If the costs cross, test whether a hybrid is warranted. First identify the cost that changes with the condition, measure it where useful, and state a rule using information available at execution time (e.g. request count or size, not the correct answer or measured future runtime). Record its expected crossover, fallback and additional cost/complexity before building the candidate. Use an existing simple mechanism when differences are not meaningful.

Treat the hybrid as a new experiment. Measure both parents, incumbent and new candidate under the same conditions, including dispatch cost and protected behavior. Test just below, at and above each switching boundary, plus typical and adverse cases. Include fallback, empty input and high-density cases when applicable, and check stability of the threshold across plausible inputs. Attribute a gain to its measured scope, not a universal cutoff. Compare complete costs and complexity; don't combine merely because each parent had an isolated gain.

If confirmation reveals a failing regime, diagnose it as new search evidence; another threshold needs fresh equivalent confirmation. Otherwise keep the admissible result or explicitly narrow the verified scope.

## Test economy

One valid deterministic check may suffice. Replicate as randomness, rare failures, drift and budget warrant, not by rigid count. Secondary metrics are diagnostic unless contracted as acceptance/trade-off conditions.
