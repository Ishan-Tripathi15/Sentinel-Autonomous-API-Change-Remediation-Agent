# Sentinel architecture

Sentinel is organized as a shared core engine with provider adapters around it. Model A (hosted neutral service) and Model B (embedded vendor agent) must call the same domain interfaces.

## Pipeline

1. **Ingestion** receives OpenAPI documents or vendor events.
2. **Diff/classification** creates a structured `ChangeEvent` without an LLM.
3. **Repository matching** builds deterministic evidence for imports/call sites, then optionally escalates ambiguous cases to an agent.
4. **Blast radius** ranks affected call sites and records evidence.
5. **Remediation** produces a minimal patch for each affected site.
6. **Verification** runs lint/typecheck/tests only inside an isolated sandbox.
7. **Delivery** creates a dry-run comment first; PR creation is enabled only after verification and explicit installation policy permits it.
8. **Audit** records tenant, source, change, model/prompt version, patch, verification and delivery outcome.

## Trust boundaries

- API processes never execute customer code.
- Sandbox workers receive only the repository snapshot needed for a job and have no ambient credentials.
- GitHub credentials are installation-scoped and should be short-lived where possible.
- Every remediation is reversible through the normal Git branch/PR lifecycle; auto-merge is explicitly out of scope.

## Interfaces

- `VendorAdapter`: source-specific retrieval and normalization.
- `ChangeDetector`: spec-to-spec or package surface diffing.
- `Matcher`: deterministic call-site discovery with an optional ambiguity resolver.
- `RemediationAgent`: tool-using patch generation.
- `Sandbox`: isolated verification boundary.
- `DeliveryProvider`: GitHub App operations.

The current MVP implements the first four deterministic boundaries plus the sandbox contract. Persistent storage, Temporal/queue orchestration, GitHub App OAuth, and the real microVM adapter are subsequent production slices.
