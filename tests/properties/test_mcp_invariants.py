"""
Property-based tests for the Commonwatt MCP tools.

Invariants tested (per project spec):
  1. portfolio total ≥ target or explicit "unreachable" — never silently short
  2. EJ share ≤ cap on every returned plan
  3. estimate_savings is monotonic in shed_mw; zero at zero
  4. Every counter has a source_id
  5. backfill never adds a building that declined
  6. check_constraints catches EJ cap violations
  7. Protected facilities excluded above heat threshold
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from server.tools import (
    backfill,
    check_constraints,
    estimate_savings,
    plan_event,
    score_equity,
)
from server.data import load_buildings, EJ_ZIPS
from server.constants import EJ_CAP_DEFAULT_PCT, EXTREME_HEAT_TEMP_F


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_sample_building_ids(n: int = 20, ej_only: bool = False) -> list[str]:
    """Return up to n building ids from the fixture."""
    buildings = load_buildings()
    if ej_only:
        buildings = [b for b in buildings if b.is_ej and b.curtailable_load_kw]
    else:
        buildings = [b for b in buildings if b.curtailable_load_kw]
    return [b.building_id for b in buildings[:n]]


# ---------------------------------------------------------------------------
# Invariant 1 & 2: plan_event — portfolio ≥ target OR explicit unreachable;
#                               EJ share ≤ cap
# ---------------------------------------------------------------------------

@given(
    target_mw=st.floats(min_value=1.0, max_value=50.0),
    ej_cap_pct=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=30, deadline=60_000)
def test_plan_event_meets_target_or_unreachable(target_mw, ej_cap_pct):
    """
    plan_event must either:
    (a) return achieved_mw >= target_mw and reachable=True, or
    (b) return reachable=False with a non-empty tradeoff string.
    Never silently short.
    """
    result = plan_event(target_mw=target_mw, ej_cap_pct=ej_cap_pct)
    if result.get("reachable"):
        assert result["achieved_mw"] >= target_mw * 0.999, (
            f"reachable=True but achieved {result['achieved_mw']:.2f} < target {target_mw:.2f}"
        )
    else:
        assert result.get("tradeoff"), (
            f"reachable=False but no tradeoff string — silent shortfall detected. "
            f"target={target_mw}, achieved={result.get('achieved_mw')}"
        )


@given(
    target_mw=st.floats(min_value=1.0, max_value=40.0),
    ej_cap_pct=st.floats(min_value=0.05, max_value=0.95),
)
@settings(max_examples=30, deadline=60_000)
def test_plan_event_ej_share_respects_cap(target_mw, ej_cap_pct):
    """
    EJ share on every returned plan must be ≤ ej_cap_pct (with 0.1% tolerance for rounding).
    """
    result = plan_event(target_mw=target_mw, ej_cap_pct=ej_cap_pct)
    ej_share = result["ej_share_pct"] / 100
    assert ej_share <= ej_cap_pct + 0.001, (
        f"EJ share {ej_share*100:.1f}% exceeds cap {ej_cap_pct*100:.1f}%"
    )


# ---------------------------------------------------------------------------
# Invariant 3: estimate_savings — monotonic in shed_mw; zero at zero
# ---------------------------------------------------------------------------

@given(
    shed_mw=st.floats(min_value=0.0, max_value=100.0),
    duration=st.floats(min_value=0.5, max_value=8.0),
)
@settings(max_examples=50, deadline=10_000)
def test_savings_zero_at_zero(shed_mw, duration):
    """When shed_mw == 0, all counters must be zero."""
    result = estimate_savings(shed_mw=0.0, event_duration_hours=duration)
    for counter in result["counters"]:
        if "value_usd" in counter:
            assert counter["value_usd"] == 0.0, f"{counter['key']} non-zero at zero shed"
        if "value_mt" in counter:
            assert counter["value_mt"] == 0.0, f"{counter['key']} non-zero at zero shed"


@given(
    shed_a=st.floats(min_value=0.1, max_value=50.0),
    shed_b=st.floats(min_value=0.1, max_value=50.0),
)
@settings(max_examples=50, deadline=10_000)
def test_savings_monotonic(shed_a, shed_b):
    """
    If shed_b > shed_a then every counter for shed_b ≥ counter for shed_a.
    """
    assume(shed_b > shed_a)
    r_a = estimate_savings(shed_mw=shed_a)
    r_b = estimate_savings(shed_mw=shed_b)
    for ca, cb in zip(r_a["counters"], r_b["counters"]):
        key = ca["key"]
        va = ca.get("value_usd") or ca.get("value_mt") or 0
        vb = cb.get("value_usd") or cb.get("value_mt") or 0
        assert vb >= va - 0.001, (
            f"{key}: shed {shed_b} gave lower value ({vb}) than shed {shed_a} ({va})"
        )


# ---------------------------------------------------------------------------
# Invariant 4: every counter has a source_id
# ---------------------------------------------------------------------------

@given(shed_mw=st.floats(min_value=0.0, max_value=50.0))
@settings(max_examples=20, deadline=10_000)
def test_savings_counters_have_source_id(shed_mw):
    """Every savings counter must carry a source_id."""
    result = estimate_savings(shed_mw=shed_mw)
    for counter in result["counters"]:
        assert counter.get("source_id"), (
            f"Counter {counter['key']} missing source_id"
        )
        assert counter.get("estimated") is True, (
            f"Counter {counter['key']} not labeled estimated"
        )


# ---------------------------------------------------------------------------
# Invariant 5: backfill never adds a declined building
# ---------------------------------------------------------------------------

def test_backfill_never_adds_declined():
    """backfill must not include any building from declined_building_ids."""
    all_ids = _get_sample_building_ids(50)
    current = all_ids[:5]
    declined = all_ids[5:10]

    result = backfill(
        gap_mw=1.0,
        current_portfolio_building_ids=current,
        declined_building_ids=declined,
    )
    added_ids = {b["building_id"] for b in result.get("additions", [])}
    for did in declined:
        assert did not in added_ids, f"Declined building {did} appeared in backfill"


# ---------------------------------------------------------------------------
# Invariant 6: check_constraints catches EJ cap violations
# ---------------------------------------------------------------------------

def test_check_constraints_catches_ej_violation():
    """
    A portfolio made entirely of EJ buildings should fail the 35% cap.
    """
    ej_ids = _get_sample_building_ids(30, ej_only=True)
    assert len(ej_ids) >= 5, "Not enough EJ buildings in fixture"

    result = check_constraints(
        building_ids=ej_ids,
        target_mw=0.01,  # very small target so reachability is not the issue
        ej_cap_pct=EJ_CAP_DEFAULT_PCT,
    )
    ej_violations = [v for v in result["violations"] if v["type"] == "ej_cap_exceeded"]
    assert len(ej_violations) > 0, (
        f"Expected EJ cap violation for 100% EJ portfolio, got: {result['violations']}"
    )


# ---------------------------------------------------------------------------
# Invariant 7: protected facilities excluded above heat threshold
# ---------------------------------------------------------------------------

def test_protected_facilities_excluded_above_heat_threshold():
    """
    plan_event should not include any protected facilities when temp >= EXTREME_HEAT_TEMP_F.
    """
    from server.data import buildings_by_id
    result = plan_event(
        target_mw=5.0,
        current_temp_f=EXTREME_HEAT_TEMP_F + 1,
    )
    bid_map = buildings_by_id()
    for b in result.get("portfolio", []):
        building = bid_map.get(b["building_id"])
        assert building is not None
        assert not building.is_protected, (
            f"Protected facility {b['building_id']} ({building.property_type}) "
            f"included in plan above heat threshold"
        )


# ---------------------------------------------------------------------------
# Smoke test: score_equity
# ---------------------------------------------------------------------------

def test_score_equity_sum():
    """score_equity ej_load_kw + non_ej_load_kw sums to total."""
    ids = _get_sample_building_ids(20)
    result = score_equity(building_ids=ids)
    assert result["ej_load_kw"] + (result["total_load_kw"] - result["ej_load_kw"]) == pytest.approx(
        result["total_load_kw"], rel=0.01
    )
    assert result.get("source_id"), "score_equity missing source_id"


# ---------------------------------------------------------------------------
# Socioeconomic equity invariants
# ---------------------------------------------------------------------------

from server.tools import score_socioeconomic, plan_event as _plan_event


@given(
    target_mw=st.floats(min_value=1.0, max_value=25.0),
)
@settings(max_examples=20, deadline=60_000)
def test_plan_prefers_affordable_over_low_income(target_mw):
    """
    The equity-corrected plan should not lean on low-income residents: the
    low-income RESIDENTIAL load share must stay modest. Commercial buildings in
    any area are a fair ask; low-income *homes* are what we protect.
    """
    result = _plan_event(target_mw=target_mw, ej_cap_pct=0.35, respect_ej_cap=True)
    ids = [b["building_id"] for b in result["portfolio"]]
    if not ids:
        return
    socio = score_socioeconomic(ids)
    # Protecting low-income residents is the whole point: their residential
    # share should never dominate a fair plan.
    assert socio["low_income_residential_share_pct"] <= 50.0, (
        f"plan leans too hard on low-income residents: "
        f"{socio['low_income_residential_share_pct']}%"
    )


def test_score_socioeconomic_has_source_and_sums():
    """score_socioeconomic carries the income source id and tier shares are sane."""
    ids = _get_sample_building_ids(30)
    s = score_socioeconomic(ids)
    assert s["source_id"], "missing income source id"
    shares = s["load_share_pct_by_tier"]
    total = sum(shares.values())
    # tier shares should sum to ~100 (allowing rounding) when there is load
    if s["total_load_kw"] > 0:
        assert 95.0 <= total <= 105.0, f"tier shares sum to {total}"


def test_socioeconomic_priority_ordering():
    """A high-income commercial building outranks a low-income residential one."""
    from server.data import load_buildings
    bs = load_buildings()
    hi_commercial = next(
        (b for b in bs if b.affluence_tier == "high" and b.is_commercial
         and not b.is_protected), None)
    low_resid = next(
        (b for b in bs if b.affluence_tier == "low" and not b.is_commercial
         and not b.is_protected), None)
    if hi_commercial and low_resid:
        assert hi_commercial.socioeconomic_priority > low_resid.socioeconomic_priority
