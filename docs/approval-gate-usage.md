# Approval gate usage

Call `approve_remediation()` only after presenting the remediation plan to an authorized human operator. Persist the returned `RemediationApproval` with the existing audit trail before allowing the queued job to run.
