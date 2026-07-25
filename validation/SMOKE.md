# Adapter smoke validation

This branch exists only to trigger the repository's pull-request CI against the frozen TRACE + REVAL + ORO v0.1 adapter.

Validation gate:

- install package with development dependencies;
- run Ruff;
- run the full pytest suite;
- do not invoke a model API;
- do not modify the frozen manifest.

A passing run validates packaging, imports, static checks, and the deterministic unit suite. It does not produce a FrontierCode score.
