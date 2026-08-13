"""Story 2.13: the five-step Data Resolver order and the success-feedback
demotion loop. Pure unit tests — no Playwright/DB needed.
"""

from discovery_worker.data_resolver import PoolEntry, ResolutionLog, field_key, resolve


def test_pool_is_tried_before_synthesis() -> None:
    pool = {field_key("Policy Number", "text"): PoolEntry(value="ABC-123")}
    result = resolve(
        field_name="Policy Number",
        input_type="text",
        route_family="/orders/{id}",
        pool=pool,
        log=ResolutionLog(),
        generic_value="Test value",
    )
    assert result is not None
    assert result.value == "ABC-123"
    assert result.source == "pool"


def test_route_specific_pool_entry_beats_the_wildcard() -> None:
    from domain import aggregation_key

    pool = {
        aggregation_key("Policy Number", "text", "*"): PoolEntry(value="wildcard-value"),
        aggregation_key("Policy Number", "text", "/orders/{id}"): PoolEntry(value="route-value"),
    }
    result = resolve(
        field_name="Policy Number",
        input_type="text",
        route_family="/orders/{id}",
        pool=pool,
        log=ResolutionLog(),
        generic_value="Test value",
    )
    assert result.value == "route-value"


def test_generic_field_gets_synthetic_value_when_pool_is_empty() -> None:
    result = resolve(
        field_name="email",
        input_type="email",
        route_family="/signup",
        pool={},
        log=ResolutionLog(),
        generic_value="test@example.com",
    )
    assert result is not None
    assert result.source == "synthetic"
    assert result.value == "test@example.com"


def test_business_specific_field_with_no_pool_entry_is_unresolved() -> None:
    result = resolve(
        field_name="Claim Number",
        input_type="text",
        route_family="/claims/{id}",
        pool={},
        log=ResolutionLog(),
        generic_value="Test value",
    )
    assert result is None


def test_rejected_value_is_demoted_and_not_reused() -> None:
    log = ResolutionLog()
    key = field_key("Coupon Code", "text")
    log.record_outcome(key, "SAVE10", "rejected")

    pool = {key: PoolEntry(value="SAVE10")}
    result = resolve(
        field_name="Coupon Code",
        input_type="text",
        route_family="/checkout",
        pool=pool,
        log=log,
        generic_value="Test value",
    )
    # The pool value was demoted; nothing else resolves it (not
    # business-specific, but the generic fallback is a different value).
    assert result is not None
    assert result.value == "Test value"
    assert result.source == "synthetic"


def test_successful_value_is_reused_on_a_later_field_with_the_same_key() -> None:
    log = ResolutionLog()
    key = field_key("Coupon Code", "text")
    log.record_outcome(key, "WELCOME5", "success")

    result = resolve(
        field_name="Coupon Code",
        input_type="text",
        route_family="/checkout",
        pool={},
        log=log,
        generic_value="Test value",
    )
    assert result is not None
    assert result.value == "WELCOME5"
    assert result.source == "reused"


def test_demoted_synthetic_value_is_never_reoffered() -> None:
    log = ResolutionLog()
    key = field_key("Quantity", "number")
    log.record_outcome(key, "1", "rejected")

    result = resolve(
        field_name="Quantity",
        input_type="number",
        route_family="/cart",
        pool={},
        log=log,
        generic_value="1",
    )
    assert result is None


def test_unknown_outcome_leaves_state_alone() -> None:
    log = ResolutionLog()
    key = field_key("Coupon Code", "text")
    log.record_outcome(key, "WELCOME5", "success")
    log.record_outcome(key, "WELCOME5", "unknown")

    assert log.reused_value(key) == "WELCOME5"
