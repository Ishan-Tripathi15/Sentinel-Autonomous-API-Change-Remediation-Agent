# Delivery idempotency

Phase 5 delivery must distinguish durable delivery identity from mutable workflow state.

`PostgresDeliveryIdempotency.delivery_key()` hashes the immutable remediation identity together with provider, repository, and base branch. Re-running the same job after a status transition therefore resolves to the same key.

The `remediation_delivery_attempts` table persists the provider result and terminal delivery state. The unique `delivery_key` constraint prevents a second durable attempt from being recorded for the same delivery identity.

This layer is deliberately separate from GitHub authorization. A delivery still requires a verified, non-dry-run remediation and explicit write authorization.

The next integration step is to place acquisition and provider-result recording around the existing GitHub delivery adapter, with recovery logic for the external-provider gap between creating a branch/PR and recording its durable result.
