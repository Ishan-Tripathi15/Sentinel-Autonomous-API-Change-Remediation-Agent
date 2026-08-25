# MVP cut line

The first end-to-end proof is intentionally narrow:

- Stripe as the first provider.
- TypeScript/JavaScript as the first customer language.
- OpenAPI/spec changes as the first source of truth.
- A documented breaking field/contract change as the first remediation target.
- Detect -> match -> patch -> isolated verification -> dry-run delivery.

## Safety gates

A job must not create an autonomous PR when:

- no high-confidence call site was found;
- the proposed patch is not minimal and machine-readable;
- the verification sandbox is unavailable;
- lint/typecheck/tests fail after the retry budget;
- the repository policy requires human review before delivery;
- the installation is in dry-run mode.

A failed remediation should become a diagnostic artifact rather than a broken PR.
