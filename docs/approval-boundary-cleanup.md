# Approval boundary cleanup

`sentinel.approval_gate` is the canonical human-approval boundary. The repository previously contained a duplicate `sentinel.approval` implementation with overlapping tests.

The duplicate is removed so there is one authoritative approval API and one test surface. Approval remains separate from repository-write authorization.
