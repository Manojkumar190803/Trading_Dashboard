from datetime import date

from core.option_contracts import select_option_contract_pair


def _contract(symbol: str, strike: int, option_type: str, expiry: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": "NIFTY",
        "strike": strike,
        "instrumenttype": option_type,
        "expiry": expiry,
    }


def test_selects_same_day_expiry_pair_before_next_expiry():
    calls = [
        _contract("TODAY-CE", 25450, "CE", "23-Nov-26"),
        _contract("NEXT-CE", 25450, "CE", "01-Dec-26"),
    ]
    puts = [
        _contract("TODAY-PE", 25550, "PE", "23-Nov-26"),
        _contract("NEXT-PE", 25550, "PE", "01-Dec-26"),
    ]

    expiry, call, put = select_option_contract_pair(
        calls,
        puts,
        "NIFTY",
        atm_strike=25500,
        strike_step=50,
        trading_day=date(2026, 11, 23),
    )

    assert expiry == date(2026, 11, 23)
    assert call["symbol"] == "TODAY-CE"
    assert put["symbol"] == "TODAY-PE"


def test_falls_back_to_next_pair_when_same_day_pair_is_incomplete():
    calls = [
        _contract("TODAY-CE", 25450, "CE", "23-Nov-26"),
        _contract("NEXT-CE", 25450, "CE", "01-Dec-26"),
    ]
    puts = [_contract("NEXT-PE", 25550, "PE", "01-Dec-26")]

    expiry, call, put = select_option_contract_pair(
        calls,
        puts,
        "NIFTY",
        atm_strike=25500,
        strike_step=50,
        trading_day=date(2026, 11, 23),
    )

    assert expiry == date(2026, 12, 1)
    assert call["symbol"] == "NEXT-CE"
    assert put["symbol"] == "NEXT-PE"


def test_non_expiry_day_selects_nearest_future_pair():
    calls = [
        _contract("NEXT-CE", 25450, "CE", "01-Dec-26"),
        _contract("LATER-CE", 25450, "CE", "08-Dec-26"),
    ]
    puts = [
        _contract("NEXT-PE", 25550, "PE", "01-Dec-26"),
        _contract("LATER-PE", 25550, "PE", "08-Dec-26"),
    ]

    expiry, call, put = select_option_contract_pair(
        calls,
        puts,
        "NIFTY",
        atm_strike=25500,
        strike_step=50,
        trading_day=date(2026, 11, 24),
    )

    assert expiry == date(2026, 12, 1)
    assert call["symbol"] == "NEXT-CE"
    assert put["symbol"] == "NEXT-PE"


def test_selects_requested_deeper_itm_strike_step():
    calls = [_contract("DEEP-CE", 25400, "CE", "01-Dec-26")]
    puts = [_contract("DEEP-PE", 25600, "PE", "01-Dec-26")]

    expiry, call, put = select_option_contract_pair(
        calls,
        puts,
        "NIFTY",
        atm_strike=25500,
        strike_step=50,
        trading_day=date(2026, 11, 24),
        itm_steps=2,
    )

    assert expiry == date(2026, 12, 1)
    assert call["symbol"] == "DEEP-CE"
    assert put["symbol"] == "DEEP-PE"
