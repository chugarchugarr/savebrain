# GPT + TRACE + REVAL + ORO v0.1

This repository freezes a runnable coding-agent package for private FrontierCode-style evaluation:

**GPT-5.6 Sol + TRACE + REVAL + ORO v0.1**

The package does not claim a FrontierCode score. FrontierCode Main tasks and graders are private, so only the benchmark owner can produce the chart coordinate. This repository fixes the agent policy, model slot, verification gates, routing budget, tool permissions, and immutable run ledger required for an external evaluation.

## Frozen mechanism

TRACE controls the path:

1. **Target** — lock the requested repository state and success conditions.
2. **Rip** — inspect the repository and expose assumptions, constraints, and regression surfaces.
3. **Assemble** — make the smallest complete implementation.
4. **Contain** — run checks, repair failures, prevent scope drift, and preserve unrelated behavior.
5. **Exit** — return verified completion or an explicit blocker.

REVAL controls truth:

- Every required check must pass.
- `git diff --check` always runs.
- Changed files must remain inside any task-supplied path boundary.
- Final factual claims must cite evidence IDs emitted by repository reads, commands, writes, or verification checks.
- Unresolved verification failure cannot be reported as completion.

ORO controls spend:

- Reasoning starts at low effort and escalates after failed verification.
- The agent stops on verified completion.
- Step, repair, wall-time, and optional USD ceilings are frozen in the manifest.
- Input tokens, output tokens, tool calls, command outputs, and optional cost are written to the run ledger.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
export OPENAI_API_KEY="..."
```

Set `OPENAI_MODEL` to the exact API model identifier supplied for the evaluation. `gpt-5.6-sol` is the frozen label used by this package; the API identifier must be confirmed by the model provider or benchmark owner.

## Task contract

Create `task.json`:

```json
{
  "task_id": "frontiercode-private-task-id",
  "prompt": "Implement the requested change exactly as described by the benchmark.",
  "repo": "/absolute/path/to/the/task/repository",
  "check_commands": [
    "python -m pytest -q",
    "ruff check ."
  ],
  "allowed_paths": [
    "src",
    "tests"
  ]
}
```

Run one rollout:

```bash
tro-frontier task.json --output-dir runs
```

The command returns either:

- `verified` — every REVAL gate passed;
- `abstained` — the frozen budget ended or the agent submitted an explicit blocker.

Each rollout writes an immutable JSON ledger containing the manifest hash, TRACE transitions, model effort, tool calls, command output, verification report, token use, and optional USD accounting.

## Benchmark run protocol

For each benchmark task and each reasoning budget:

1. Reset the repository to the benchmark-provided commit.
2. Disable network access at the container level.
3. Run five independent rollouts with the same frozen manifest.
4. Preserve each run ledger and final repository diff.
5. Let the benchmark owner apply its private grader and cost accounting.
6. Report both benchmark score and REVAL-certified completion rate.

The plotted point belongs to the complete system, not the base model alone:

`GPT model + TRACE path control + REVAL verification + ORO budget control`

## Freeze

The evaluation object is `frozen/trace-reval-oro-v0.1.json`. Its SHA-256 is embedded into every run ledger. Any change creates a new version and a new benchmark entry.

## Submission boundary

This package is ready to hand to the FrontierCode benchmark owner. It cannot submit itself or execute the private Main suite without benchmark access. The benchmark owner must supply:

- private task repositories and prompts;
- required container/tool interface;
- exact model API identifier and credentials;
- private graders and score aggregation;
- authoritative rollout-cost accounting.
