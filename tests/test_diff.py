from sentinel.diff import classify_openapi_changes, diff_openapi
from sentinel.models import ChangeSeverity, ChangeType


def test_removed_openapi_property_is_breaking() -> None:
    before = {"paths": {"/v1/payments": {"post": {"responses": {"200": {}}}}}}
    after = {"paths": {}}
    changes = diff_openapi(before, after)
    change_type, severity, endpoints, _ = classify_openapi_changes(changes)
    assert change_type == ChangeType.BREAKING
    assert severity == ChangeSeverity.HIGH
    assert "/v1/payments" in endpoints


def test_added_endpoint_is_new_feature() -> None:
    before = {"paths": {}}
    after = {"paths": {"/v1/payments": {"get": {"responses": {"200": {}}}}}}
    changes = diff_openapi(before, after)
    change_type, severity, endpoints, _ = classify_openapi_changes(changes)
    assert change_type == ChangeType.NEW_FEATURE
    assert severity == ChangeSeverity.LOW
    assert "/v1/payments" in endpoints


def test_nested_endpoint_change_keeps_full_endpoint_path() -> None:
    before = {"paths": {"/v1/payments/{payment_id}": {"get": {"responses": {"200": {}}}}}}
    after = {"paths": {"/v1/payments/{payment_id}": {"get": {"responses": {"200": {"description": "ok"}}}}}}
    changes = diff_openapi(before, after)
    _, _, endpoints, _ = classify_openapi_changes(changes)
    assert "/v1/payments/{payment_id}" in endpoints


def test_deprecation_is_classified() -> None:
    before = {"paths": {"/v1/payments": {"get": {"deprecated": False}}}}
    after = {"paths": {"/v1/payments": {"get": {"deprecated": True}}}}
    changes = diff_openapi(before, after)
    change_type, _, _, _ = classify_openapi_changes(changes)
    assert change_type == ChangeType.DEPRECATION
