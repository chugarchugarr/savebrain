# TRACE + REVAL + ORO possibilities

## What exists now

This repository is an agent harness around a frontier model, not a newly trained foundation-model checkpoint. Its current value is the control architecture: path discipline, evidence-linked verification, budget escalation, abstention, and immutable trajectory logging.

## Immediate public evaluations

1. **SWE-bench Verified and Lite** — generate repository patches, convert results to the official prediction format, evaluate through `sb-cli`, and submit the model–agent combination to the public leaderboard.
2. **Terminal-Bench 2.1** — adapt the task contract to Harbor containers and test general terminal execution under a public, current agent benchmark.
3. **RE-Bench** — replace the repository-only task adapter with METR Task Standard support and evaluate autonomous AI-research engineering work.
4. **EVMbench** — add Solidity/Anvil task adapters for defensive smart-contract detection and patch evaluation.
5. **PaperBench** — use TRACE to decompose paper replication, REVAL to bind claims to experimental artifacts, and ORO to allocate compute across replication branches.
6. **Private workflow evals** — use the ledger and verification gates to build organization-specific golden sets and trace-level graders.

## Product paths

### Verified software engineer

Turn an issue into a reviewable PR, but expose `verified`, `abstained`, and `blocked` as distinct outcomes. Sell reliability and evidence, not autonomous-completion theater.

### PR verification and repair layer

Run after Codex, Devin, Claude Code, or another coding agent. REVAL audits the produced diff, TRACE contains repairs, and ORO decides whether to repair locally, escalate models, or stop.

### Model-routing Pareto engine

Route work among GPT-5.6 Luna, Terra, and Sol. Begin with the cheapest substrate, escalate only when verification survives, and learn a score/cost frontier from actual trajectories.

### Independent agent-evaluation lab

Evaluate complete model–harness systems rather than model names alone. Publish configuration, budgets, tools, verified completion, failure modes, and cost per successful result.

### Research and due-diligence agent

Replace repository commands with search, files, code execution, datasets, and external adjudication. REVAL becomes a claim ledger; unsupported conclusions remain unresolved rather than becoming prose.

### Security and smart-contract audit agent

Use TRACE for exhaustive attack-surface exploration, REVAL for reproducible findings and patch checks, and ORO for parallel threat hypotheses and compute allocation.

### GatePass engineering operator

Use the system internally to implement GatePass changes, inspect repository state, run required checks, preserve product doctrine, and produce an evidence-backed permanent engineering record.

## Research program

1. Run component ablations: GPT alone, +TRACE, +REVAL, +ORO, and the complete stack.
2. Measure raw benchmark score, verified-completion rate, false-completion rate, cost, latency, and repair count.
3. Test fixed-model routing versus Luna→Terra→Sol escalation.
4. Compare closed-network operation with fair-internet operation plus contamination detection.
5. Test whether the same frozen control mechanism transfers across coding, research, forecasting, and professional-work tasks without hand-placing domain intelligence.
6. Use trajectories to identify recurrent failure classes and improve the controller without changing the underlying task grader.

## Required next architecture changes

- Add the complete GPT-5.6 reasoning range: `none`, `low`, `medium`, `high`, `xhigh`, and `max`.
- Add first-class hosted shell, apply-patch, web-search, file-search, and programmatic-tool-calling adapters.
- Add URL and artifact lineage logging for fair-internet evaluation.
- Separate the agent policy from benchmark-specific task adapters.
- Add multi-agent execution for independent inspection, implementation, adversarial review, and synthesis.
- Add authoritative tool fees, long-context multipliers, cache accounting, and cost per verified success.
- Add task reset, container lifecycle, prediction export, and leaderboard submission adapters.

## Priority

The strongest sequence is:

1. Correct FrontierCode 1.1 compatibility.
2. Run SWE-bench Verified and Terminal-Bench 2.1 publicly.
3. Build Luna→Terra→Sol ORO routing and publish the resulting Pareto curve.
4. Add RE-Bench and EVMbench adapters.
5. Productize the system as a verification and repair layer that can sit behind any coding agent.
