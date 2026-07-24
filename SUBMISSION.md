# Evaluation submission

## Object

- Entry: `GPT-5.6 Sol + TRACE + REVAL + ORO v0.1`
- Frozen manifest: `frozen/trace-reval-oro-v0.1.json`
- Manifest SHA-256: `383339f18bd5e421e82c8bac40bd416dbb91be836ae22cec6197a3ce8b2551da`
- Network: disabled
- Rollouts: five independent runs per task and reasoning budget
- Completion rule: every required REVAL gate passes
- Failure rule: unresolved verification failure is an abstention/zero, never completion

## Benchmark-owner interface

Python:

```python
from tro_frontier import run_task

result = run_task(
    {
        "task_id": "private-id",
        "prompt": "private task prompt",
        "repo": "/workspace/repo",
        "check_commands": ["benchmark-provided-check"],
        "allowed_paths": [],
    },
    manifest_path="frozen/trace-reval-oro-v0.1.json",
    output_dir="runs",
)
```

CLI:

```bash
tro-frontier task.json --output-dir runs
```

## Required handoff from the benchmark owner

The private task repositories, prompts, grader, container contract, authoritative model API identifier, credentials, and billing data remain external. This package records them but does not fabricate them.
