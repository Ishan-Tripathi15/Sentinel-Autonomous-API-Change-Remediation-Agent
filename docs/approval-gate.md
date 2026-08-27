# Remediation approval gate

Jobs in `awaiting-approval` require an explicit human decision before returning to `queued`.

The approval record captures job, organization, installation, approver, and a timezone-aware timestamp. Approval only releases the workflow hold; it does not authorize repository writes. GitHub delivery remains independently gated by verified status, dry-run policy, and explicit write authorization.
