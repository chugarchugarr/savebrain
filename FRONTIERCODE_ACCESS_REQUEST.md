# FrontierCode 1.1 evaluation access request

**Subject:** FrontierCode 1.1 evaluation request — GPT-5.6 Sol + TRACE + REVAL + ORO

Cognition FrontierCode team,

I built a frozen agent system around the official OpenAI model ID `gpt-5.6-sol`:

**GPT-5.6 Sol + TRACE + REVAL + ORO**

Repository: https://github.com/chugarchugarr/savebrain

The system separates three functions:

- **TRACE** controls the work path: target, inspect, implement, contain, exit.
- **REVAL** prevents unsupported completion by requiring repository evidence and passing verification gates.
- **ORO** controls reasoning effort, repair escalation, stopping, and cost.

The repository includes an immutable run ledger, evidence-linked final claims, abstention on unresolved verification failure, five-rollout support, and explicit token/tool/cost accounting.

I am requesting one of the following:

1. Access to submit this complete model–harness system for private FrontierCode 1.1 Main evaluation; or
2. The adapter contract required to run TRACE–REVAL–ORO inside Cognition's standardized OpenAI evaluation harness.

Important compatibility disclosure: the frozen v0.1 package currently uses a closed-network policy. FrontierCode 1.1 allows legitimate internet use while detecting and zeroing solution-bearing retrieval. I therefore do **not** claim that v0.1 is already an exact FrontierCode 1.1 harness match. I need Cognition's tool and internet-verifier contract before freezing the compatible evaluation version.

The requested evaluation object will remain fixed after that compatibility boundary is supplied. I will report the complete configuration, reasoning effort, retries, wall time, token use, tool use, and average USD cost per rollout. No FrontierCode score is claimed before Cognition runs the private suite.

— Joseph Lerma
