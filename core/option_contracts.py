from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def _expiry_date(value: object) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    for date_format in ("%d-%b-%y", "%d%b%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


def _matching_contracts(
    rows: list[dict[str, object]],
    underlying: str,
    strike: int,
    option_type: str,
    trading_day: date,
) -> dict[date, dict[str, object]]:
    root = underlying.upper()
    matches: dict[date, dict[str, object]] = {}
    for row in rows:
        normalized = {str(key).lower(): value for key, value in row.items()}
        symbol = normalized.get("symbol")
        try:
            row_strike = float(normalized.get("strike"))
        except (TypeError, ValueError):
            continue
        if (
            not isinstance(symbol, str)
            or row_strike != strike
            or str(normalized.get("instrumenttype") or "").upper() != option_type
        ):
            continue
        row_root = str(normalized.get("name") or normalized.get("underlying") or "").upper()
        if row_root and row_root != root:
            continue
        expiry = _expiry_date(normalized.get("expiry"))
        if expiry is None or expiry < trading_day:
            continue
        matches.setdefault(expiry, row)
    return matches


def _preferred_expiry(
    expiries: set[date],
    trading_day: date,
    expiry_policy: str,
) -> date:
    if trading_day in expiries:
        return trading_day
    if expiry_policy == "monthly":
        nearest_month = min(expiries).replace(day=1)
        month_expiries = {
            expiry
            for expiry in expiries
            if expiry.year == nearest_month.year and expiry.month == nearest_month.month
        }
        return max(month_expiries) if month_expiries else min(expiries)
    return min(expiries)


def select_option_contract(
    rows: list[dict[str, object]],
    underlying: str,
    strike: int,
    option_type: str,
    trading_day: date,
    expiry_policy: str = "weekly",
) -> tuple[Optional[date], Optional[dict[str, object]]]:
    """Choose one strike/type contract using the configured expiry policy."""
    contracts = _matching_contracts(
        rows,
        underlying,
        strike,
        option_type,
        trading_day,
    )
    if not contracts:
        return None, None
    selected_expiry = _preferred_expiry(
        set(contracts),
        trading_day,
        expiry_policy,
    )
    return selected_expiry, contracts[selected_expiry]


def select_option_contract_pair(
    call_rows: list[dict[str, object]],
    put_rows: list[dict[str, object]],
    underlying: str,
    atm_strike: int,
    strike_step: int,
    trading_day: date,
    expiry_policy: str = "weekly",
    itm_steps: int = 1,
) -> tuple[Optional[date], Optional[dict[str, object]], Optional[dict[str, object]]]:
    """Choose ITM CE/PE contracts at the requested strike depth."""
    if itm_steps < 1:
        raise ValueError("itm_steps must be a positive integer")
    calls = _matching_contracts(
        call_rows,
        underlying,
        atm_strike - strike_step * itm_steps,
        "CE",
        trading_day,
    )
    puts = _matching_contracts(
        put_rows,
        underlying,
        atm_strike + strike_step * itm_steps,
        "PE",
        trading_day,
    )
    if not calls and not puts:
        return None, None, None

    common_expiries = set(calls).intersection(puts)
    candidate_expiries = common_expiries or set(calls).union(puts)
    selected_expiry = _preferred_expiry(
        candidate_expiries,
        trading_day,
        expiry_policy,
    )

    return selected_expiry, calls.get(selected_expiry), puts.get(selected_expiry)
