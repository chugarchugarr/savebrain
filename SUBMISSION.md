# FrontierCode private evaluation submission

## Evaluation object

- **Entry:** `GPT-5.6 Sol + TRACE + REVAL + ORO v0.1`
- **Repository:** https://github.com/chugarchugarr/savebrain
- **Frozen evaluation commit:** `4f4eaaf05394415b43035350e1843d8728795afb`
- **Frozen manifest:** `frozen/trace-reval-oro-v0.1.json`
- **Manifest SHA-256:** `383339f18bd5e421e82c8bac40bd416dbb91be836ae22cec6197a3ce8b2551da`
- **Runner:** `tro-frontier`
- **Model slot:** `OPENAI_MODEL`; the benchmark owner must supply the authoritative GPT API model identifier.

The plotted object is the complete system: GPT substrate + TRACE path control + REVAL verification + ORO budget control. This submission does **not** claim a FrontierCode score before the private suite is executed by the benchmark owner.

## Install

```bash
git clone https://github.com/chugarchugarr/savebrain.git
cd savebrain
git checkout 4f4eaaf05394415b43035350e1843d8728795afb
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export OPENAI_API_KEY="..."
export OPENAI_MODEL="<benchmark-approved-model-id>"
```

Optional cost accounting:

```bash
export OPENAI_INPUT_USD_PER_MILLION="<rate>"
export OPENAI_OUTPUT_USD_PER_MILLION="<rate>"
```

## Task contract

Create one task file per private task:

```json
{
  "task_id": "frontiercode-private-task-id",
  "prompt": "Implement the benchmark request exactly as supplied.",
  "repo": "/absolute/path/to/the-reset-task-repository",
  "check_commands": [
    "<benchmark-provided-check>"
  ],
  "allowed_paths": []
}
```

Run one rollout:

```bash
tro-frontier task.json --output-dir runs
```

The Python interface is also available:

```python
from tro_frontier import run_task

result = run_task(
    {
        "task_id": "frontiercode-private-task-id",
        "prompt": "Implement the benchmark request exactly as supplied.",
        "repo": "/absolute/path/to/the-reset-task-repository",
        "check_commands": ["<benchmark-provided-check>"],
        "allowed_paths": [],
    },
    manifest_path="frozen/trace-reval-oro-v0.1.json",
    output_dir="runs",
)
```

## Frozen policy

TRACE must progress in order: `target -> rip -> assemble -> contain -> exit`. Writes are allowed only during `assemble` and `contain`. Completion is allowed only at `exit`.

REVAL always runs `git diff --check`, requires every benchmark-supplied check to pass, requires evidence IDs for final factual claims, and forbids unresolved verification failure from being reported as completion.

ORO begins at low reasoning effort, escalates after failed verification, permits at most 80 model steps and four repair cycles, stops on verified completion, and abstains when the frozen budget is exhausted.

Network access is disabled by policy. The adapter blocks common network-bearing commands, including `curl`, `wget`, SSH/SCP/SFTP, netcat, and remote Git clone/fetch/pull. The benchmark container should also disable network access externally so enforcement does not depend on the agent alone.

## Exact evaluation protocol

For every private task and every approved reasoning budget:

1. Reset the task repository to the benchmark-provided commit.
2. Disable network access at the container level.
3. Set the approved GPT model identifier and authoritative input/output prices.
4. Run five independent rollouts using the unchanged manifest and frozen evaluation commit.
5. Preserve every final repository diff and immutable JSON run ledger.
6. Apply the benchmark owner's private grader and score aggregation without modification.
7. Report both the official benchmark score and the REVAL-certified completion rate.
8. Plot score against measured average USD cost per rollout only after the private results exist.

## Run ledger

Each rollout records:

- run ID, task ID, manifest name, and manifest SHA-256;
- TRACE stage transitions;
- model response IDs and reasoning effort;
- prompts, tool calls, command outputs, and evidence IDs;
- input tokens, output tokens, and configured USD cost;
- verification checks, failures, repair transitions, final status, and final repository diff location.

Valid final statuses are `verified` or `abstained`. There is no unverified-success state.

## Benchmark-owner inputs required

The benchmark owner must supply the private task repositories and prompts, container/tool interface, private graders, score aggregation, approved GPT API model identifier and credentials, and authoritative cost accounting.

Compatibility changes required by the private harness must be isolated and documented. Any change to TRACE ordering, REVAL gates, ORO limits, network policy, model routing, or completion semantics creates a new version and a separate benchmark entry.