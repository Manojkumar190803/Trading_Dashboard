from __future__ import annotations

import logging
import re
import time as time_module
from datetime import date, datetime, time, timedelta
from typing import Optional

import pandas as pd

from core.models import OrderSide

logger = logging.getLogger("core.broker")


class BrokerInterface:
    """Abstract broker — subclass and implement for your broker API."""

    is_replay = False

    def get_ltp(self, symbol: str) -> float:
        raise NotImplementedError

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        raise NotImplementedError

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        raise NotImplementedError

    def simulate_stop_limit_fill(
        self,
        symbol: str,
        trigger_price: float,
        limit_price: float,
    ) -> Optional[float]:
        """Return a simulated fill price for replay, or None when unfilled."""
        return None

    def resolve_nearest_expiry(
        self,
        index_symbol: str,
        trade_day: date,
        atm_strike: int,
        strike_step: int,
        preferred_weekday: Optional[int] = None,
    ) -> Optional[date]:
        """Return nearest tradable expiry date for an option root, if available."""
        return None


class ConsoleBroker(BrokerInterface):
    """Prints orders to stdout; useful for dry-run verification."""

    def __init__(self, ltp_fallback: float = 100.0) -> None:
        self.ltp_fallback = ltp_fallback

    def get_ltp(self, symbol: str) -> float:
        print(f"[BROKER] get_ltp {symbol} -> {self.ltp_fallback}")
        return self.ltp_fallback

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        oid = f"SL-L-{symbol}-{side}-{quantity}"
        print(
            f"[BROKER] place_stop_limit_order "
            f"symbol={symbol} side={side} qty={quantity} "
            f"trigger={trigger_price:.2f} limit={limit_price:.2f} id={oid}"
        )
        return oid

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        oid = f"MKT-{symbol}-{side}-{quantity}"
        print(f"[BROKER] place_market_order symbol={symbol} side={side} qty={quantity} id={oid}")
        return oid


class OpenAlgoBroker(BrokerInterface):
    """BrokerInterface backed by the OpenAlgo REST client."""

    def __init__(
        self,
        api_key: str,
        host: str,
        ws_url: Optional[str] = None,
        strategy_tag: str = "HD_Strategy",
        product: str = "MIS",
        exchange_options: str = "NFO",
        dry_run: bool = True,
    ) -> None:
        try:
            from openalgo import api  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "openalgo package not installed. Install with `pip install openalgo`."
            ) from exc

        kwargs = {"api_key": api_key, "host": host}
        self.client = api(**kwargs)
        self.ws_url = ws_url
        self.strategy_tag = strategy_tag
        self.product = product
        self.exchange_options = exchange_options
        self.dry_run = dry_run
        self._nearest_expiry_cache: dict[tuple[str, str, int, int, str], Optional[date]] = {}
        logger.info(
            "OpenAlgoBroker initialized host=%s ws_url=%s product=%s dry_run=%s",
            host, ws_url, product, dry_run,
        )

    def resolve_nearest_expiry(
        self,
        index_symbol: str,
        trade_day: date,
        atm_strike: int,
        strike_step: int,
        preferred_weekday: Optional[int] = None,
    ) -> Optional[date]:
        """Probe option symbols to find the nearest tradable expiry.

        This handles broker feeds that don't expose explicit weekly/monthly expiry metadata.
        """
        root = (index_symbol or "").upper().strip()
        key = (
            root,
            trade_day.isoformat(),
            int(atm_strike),
            int(strike_step),
            self.exchange_options,
            int(preferred_weekday) if preferred_weekday is not None else -1,
        )
        if key in self._nearest_expiry_cache:
            return self._nearest_expiry_cache[key]

        strikes = [atm_strike - strike_step, atm_strike, atm_strike + strike_step]
        strikes = sorted({s for s in strikes if s > 0})

        candidate_days: list[date] = []

        # Prioritize the configured/script-specific expiry weekday first.
        if preferred_weekday is not None and 0 <= preferred_weekday <= 6:
            for day_offset in range(0, 70):
                d = trade_day + timedelta(days=day_offset)
                if d.weekday() == preferred_weekday:
                    candidate_days.append(d)
                if len(candidate_days) >= 10:
                    break

        # Add the remaining weekdays as backups with short horizon.
        for wd in range(0, 5):
            if preferred_weekday is not None and wd == preferred_weekday:
                continue
            count = 0
            for day_offset in range(0, 35):
                d = trade_day + timedelta(days=day_offset)
                if d.weekday() == wd:
                    if d not in candidate_days:
                        candidate_days.append(d)
                    count += 1
                if count >= 2:
                    break

        candidate_days.sort()
        for candidate_day in candidate_days:
            expiry_code = candidate_day.strftime("%d%b%y").upper()
            for strike in strikes:
                for option_type in ("CE", "PE"):
                    symbol = f"{root}{expiry_code}{strike}{option_type}"
                    if self._quote_symbol_exists(symbol):
                        self._nearest_expiry_cache[key] = candidate_day
                        logger.info(
                            "nearest expiry resolved for %s: %s (symbol=%s)",
                            root,
                            candidate_day,
                            symbol,
                        )
                        return candidate_day

        logger.warning(
            "Could not resolve nearest expiry for %s around strike=%s; using fallback expiry logic",
            root,
            atm_strike,
        )
        self._nearest_expiry_cache[key] = None
        return None

    def _quote_symbol_exists(self, symbol: str) -> bool:
        """Check symbol existence via quotes with gentle throttling and 429 retry."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                resp = self.client.quotes(symbol=symbol, exchange=self.exchange_options)
            except Exception:
                resp = None

            if isinstance(resp, dict):
                if resp.get("status") == "success":
                    time_module.sleep(0.03)
                    return True
                message = str(resp.get("message") or "")
                if "429" in message and attempt < max_attempts - 1:
                    # Back off slightly when OpenAlgo rate-limits requests.
                    time_module.sleep(0.25 * (attempt + 1))
                    continue
            break

        time_module.sleep(0.03)
        return False

    def get_ltp(self, symbol: str) -> float:
        exchange = self._infer_exchange(symbol)
        try:
            resp = self.client.quotes(symbol=symbol, exchange=exchange)
        except Exception as exc:
            logger.warning("quotes(%s) error: %s", symbol, exc)
            return 0.0

        if isinstance(resp, dict) and resp.get("status") == "success":
            data = resp.get("data") or {}
            ltp = data.get("ltp") or resp.get("ltp")
            if ltp is not None:
                return round(float(ltp), 2)
        logger.warning("quotes(%s) unexpected response: %s", symbol, resp)
        return 0.0

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        exchange = self._infer_exchange(symbol)
        if self.dry_run:
            oid = f"DRY-SL-L-{symbol}-{side.value}-{quantity}"
            logger.info(
                "[DRY_RUN] place_stop_limit_order %s %s qty=%s trigger=%.2f limit=%.2f -> %s",
                symbol, side.value, quantity, trigger_price, limit_price, oid,
            )
            return oid
        try:
            resp = self.client.placeorder(
                strategy=self.strategy_tag,
                symbol=symbol,
                action=side.value,
                exchange=exchange,
                price_type="SL",
                product=self.product,
                quantity=int(quantity),
                price=round(float(limit_price), 2),
                trigger_price=round(float(trigger_price), 2),
            )
        except Exception as exc:
            logger.error("placeorder SL error for %s: %s", symbol, exc)
            raise
        return self._extract_order_id(resp)

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        exchange = self._infer_exchange(symbol)
        if self.dry_run:
            oid = f"DRY-MKT-{symbol}-{side.value}-{quantity}"
            logger.info(
                "[DRY_RUN] place_market_order %s %s qty=%s -> %s",
                symbol, side.value, quantity, oid,
            )
            return oid
        try:
            resp = self.client.placeorder(
                strategy=self.strategy_tag,
                symbol=symbol,
                action=side.value,
                exchange=exchange,
                price_type="MARKET",
                product=self.product,
                quantity=int(quantity),
            )
        except Exception as exc:
            logger.error("placeorder MARKET error for %s: %s", symbol, exc)
            raise
        return self._extract_order_id(resp)

    def fetch_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        df = self.client.history(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
        if isinstance(df, dict):
            raise RuntimeError(f"history returned error for {symbol}: {df}")
        if df is None or df.empty:
            raise RuntimeError(f"No history data for {symbol}")
        return df

    def discover_index_profile(self, script: str) -> dict[str, object]:
        """Discover instrument metadata for index option trading from OpenAlgo.

        Returns keys used by StrategyConfig:
        - spot_symbol
        - option_index_symbol
        - exchange_spot
        - exchange_options
        - strike_step
        - option_lot_size
        - weekly_expiry_weekday
        """
        canonical = self._normalize_script_name(script)
        default_exchanges = {
            "NIFTY": ("NSE_INDEX", "NFO"),
            "BANKNIFTY": ("NSE_INDEX", "NFO"),
            "SENSEX": ("BSE_INDEX", "BFO"),
        }
        fallback_metadata = {
            "NIFTY": {"strike_step": 50, "option_lot_size": 65, "weekly_expiry_weekday": 1},
            "BANKNIFTY": {"strike_step": 100, "option_lot_size": 30, "weekly_expiry_weekday": 1},
            "SENSEX": {"strike_step": 100, "option_lot_size": 20, "weekly_expiry_weekday": 3},
        }
        spot_exch, opt_exch = default_exchanges.get(canonical, ("NSE_INDEX", self.exchange_options))

        payload, discovery_error = self._discover_payload(canonical, spot_exch, opt_exch)
        if payload is None:
            raise RuntimeError(
                f"Could not discover instrument metadata for '{script}' from OpenAlgo"
                + (f": {discovery_error}" if discovery_error else "")
            )

        numeric = self._extract_numeric_fields(payload)
        discovered_root = self._extract_option_root(payload)
        if canonical in fallback_metadata and discovered_root not in (None, canonical):
            numeric = {}
        strike_step = self._extract_strike_step(payload)
        if canonical in fallback_metadata and discovered_root not in (None, canonical):
            strike_step = None
        lot_size = numeric.get("lot_size")
        if lot_size is None:
            lot_size = numeric.get("market_lot")
        missing_both = strike_step is None and lot_size is None
        if strike_step is None or lot_size is None:
            fallback = fallback_metadata.get(canonical)
            if fallback is not None:
                if strike_step is None:
                    strike_step = int(fallback["strike_step"])
                if lot_size is None:
                    lot_size = int(fallback["option_lot_size"])
                log_fn = logger.info if missing_both else logger.warning
                log_fn(
                    "OpenAlgo discovery missing strike/lot metadata for %s; using fallback strike_step=%s lot_size=%s",
                    canonical,
                    strike_step,
                    lot_size,
                )
            else:
                if strike_step is None:
                    raise RuntimeError(
                        f"OpenAlgo discovery for '{script}' did not return strike-step metadata"
                    )
                if lot_size is None:
                    raise RuntimeError(
                        f"OpenAlgo discovery for '{script}' did not return lot-size metadata"
                    )

        symbol_guess = self._extract_symbol(payload) or canonical
        option_root = canonical if canonical in fallback_metadata else (
            discovered_root or symbol_guess or canonical
        )
        weekly_expiry_weekday = self._extract_weekly_expiry_weekday(payload)

        return {
            "spot_symbol": canonical,
            "option_index_symbol": option_root,
            "exchange_spot": spot_exch,
            "exchange_options": opt_exch,
            "strike_step": int(strike_step),
            "option_lot_size": int(lot_size),
            "weekly_expiry_weekday": int(weekly_expiry_weekday),
        }

    def _discover_payload(
        self,
        canonical: str,
        spot_exchange: str,
        options_exchange: str,
    ) -> tuple[object | None, str | None]:
        aliases = self._symbol_aliases(canonical)
        last_error: Optional[str] = None
        first_usable_payload = None
        expiry_dates_by_alias: dict[str, list[str]] = {}

        expiry_method = getattr(self.client, "expiry", None)
        if expiry_method is not None:
            for alias in aliases:
                discovered_dates: list[str] = []
                expiry_kwargs_candidates = [
                    {"exchange": options_exchange, "symbol": alias, "instrumenttype": "OPTIDX"},
                    {"exchange": options_exchange, "underlying": alias, "instrumenttype": "OPTIDX"},
                    {"exchange": options_exchange, "symbol": alias},
                ]
                for kwargs in expiry_kwargs_candidates:
                    try:
                        resp = expiry_method(**kwargs)
                    except Exception:
                        continue
                    if isinstance(resp, dict) and resp.get("status") == "error":
                        msg = resp.get("message")
                        if isinstance(msg, str) and msg.strip():
                            last_error = msg.strip()
                    discovered_dates.extend(self._extract_expiry_dates(resp))
                if discovered_dates:
                    # Keep first-seen order while de-duplicating.
                    expiry_dates_by_alias[alias] = list(dict.fromkeys(discovered_dates))

        method_candidates: list[tuple[str, list[dict[str, object]]]] = []
        for alias in aliases:
            optionchain_kwargs: list[dict[str, object]] = [
                {"underlying": alias, "exchange": options_exchange},
                {"underlying": alias, "exchange": spot_exchange},
            ]
            for expiry_date in expiry_dates_by_alias.get(alias, []):
                optionchain_kwargs.append(
                    {"underlying": alias, "exchange": options_exchange, "expiry_date": expiry_date}
                )
                optionchain_kwargs.append(
                    {"underlying": alias, "exchange": spot_exchange, "expiry_date": expiry_date}
                )

            method_candidates.extend(
                [
                    (
                        "optionchain",
                        optionchain_kwargs,
                    ),
                    (
                        "search",
                        [
                            {"exchange": options_exchange, "query": alias},
                            {"exchange": spot_exchange, "query": alias},
                        ],
                    ),
                    (
                        "symbol",
                        [
                            {"exchange": spot_exchange, "symbol": alias},
                            {"exchange": options_exchange, "symbol": alias},
                        ],
                    ),
                    (
                        "instruments",
                        [
                            {"exchange": options_exchange},
                            {"exchange": spot_exchange},
                        ],
                    ),
                    (
                        "expiry",
                        [
                            {"exchange": options_exchange, "symbol": alias, "instrumenttype": "OPTIDX"},
                        ],
                    ),
                ]
            )

        for method_name, kwargs_list in method_candidates:
            method = getattr(self.client, method_name, None)
            if method is None:
                continue
            for kwargs in kwargs_list:
                try:
                    resp = method(**kwargs)
                except Exception:
                    continue
                if isinstance(resp, dict) and resp.get("status") == "error":
                    msg = resp.get("message")
                    if isinstance(msg, str) and msg.strip():
                        last_error = msg.strip()
                if self._is_usable_payload(resp):
                    if first_usable_payload is None:
                        first_usable_payload = resp
                    has_step = self._extract_strike_step(resp) is not None
                    numeric = self._extract_numeric_fields(resp)
                    has_lot = (
                        numeric.get("lot_size") is not None
                        or numeric.get("market_lot") is not None
                    )
                    if has_step and has_lot:
                        return resp, None
        if first_usable_payload is not None:
            return first_usable_payload, None
        return None, last_error

    @staticmethod
    def _normalize_script_name(script: str) -> str:
        key = re.sub(r"[^A-Za-z0-9]", "", script or "").upper()
        alias_map = {
            "NIFTY": "NIFTY",
            "NIFTY50": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "NIFTYBANK": "BANKNIFTY",
            "SENSEX": "SENSEX",
            "BSESENSEX": "SENSEX",
        }
        return alias_map.get(key, key)

    @staticmethod
    def _symbol_aliases(canonical: str) -> list[str]:
        aliases = {
            "NIFTY": ["NIFTY", "NIFTY 50"],
            "BANKNIFTY": ["BANKNIFTY", "NIFTY BANK"],
            "SENSEX": ["SENSEX", "BSE SENSEX"],
        }
        return aliases.get(canonical, [canonical])

    @staticmethod
    def _is_usable_payload(payload) -> bool:
        if payload is None:
            return False
        if isinstance(payload, dict) and payload.get("status") == "error":
            return False
        return True

    @staticmethod
    def _walk_objects(payload):
        stack = [payload]
        while stack:
            cur = stack.pop()
            yield cur
            if isinstance(cur, dict):
                for v in cur.values():
                    if isinstance(v, (dict, list, tuple)):
                        stack.append(v)
            elif isinstance(cur, (list, tuple)):
                for v in cur:
                    if isinstance(v, (dict, list, tuple)):
                        stack.append(v)

    @staticmethod
    def _coerce_number(value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            try:
                return float(text)
            except ValueError:
                return None
        return None

    @classmethod
    def _extract_numeric_fields(cls, payload) -> dict[str, int]:
        out: dict[str, int] = {}
        key_map = {
            "lot_size": "lot_size",
            "lotsize": "lot_size",
            "market_lot": "market_lot",
            "marketlot": "market_lot",
        }
        for item in cls._walk_objects(payload):
            if not isinstance(item, dict):
                continue
            normalized = {str(k).lower(): v for k, v in item.items()}
            for raw_key, target in key_map.items():
                if raw_key not in normalized:
                    continue
                val = cls._coerce_number(normalized.get(raw_key))
                if val is None:
                    continue
                if val > 0:
                    out[target] = int(round(val))
        return out

    @classmethod
    def _extract_strike_step(cls, payload) -> Optional[int]:
        direct_keys = ("strike_step", "strikestep", "strike_interval", "strikeinterval")
        for item in cls._walk_objects(payload):
            if not isinstance(item, dict):
                continue
            normalized = {str(k).lower(): v for k, v in item.items()}
            for key in direct_keys:
                if key not in normalized:
                    continue
                val = cls._coerce_number(normalized.get(key))
                if val and val > 0:
                    return int(round(val))

        strikes: list[float] = []
        for item in cls._walk_objects(payload):
            if isinstance(item, dict):
                normalized = {str(k).lower(): v for k, v in item.items()}
                for key in ("strike", "strike_price", "strikeprice"):
                    if key in normalized:
                        val = cls._coerce_number(normalized.get(key))
                        if val is not None:
                            strikes.append(val)
            elif isinstance(item, (list, tuple)):
                for v in item:
                    val = cls._coerce_number(v)
                    if val is not None:
                        strikes.append(val)

        unique = sorted({int(round(s)) for s in strikes if s > 0})
        if len(unique) < 2:
            return None
        diffs = [b - a for a, b in zip(unique, unique[1:]) if (b - a) > 0]
        return min(diffs)

    @classmethod
    def _extract_symbol(cls, payload) -> Optional[str]:
        keys = ("brsymbol", "name", "symbol", "tradingsymbol", "index")
        for item in cls._walk_objects(payload):
            if not isinstance(item, dict):
                continue
            normalized = {str(k).lower(): v for k, v in item.items()}
            for key in keys:
                value = normalized.get(key)
                if isinstance(value, str) and value.strip():
                    root = cls._infer_index_root(value)
                    if root is not None:
                        return root
        return None

    @classmethod
    def _extract_option_root(cls, payload) -> Optional[str]:
        keys = (
            "underlying",
            "underlying_symbol",
            "index_symbol",
            "option_root",
            "brsymbol",
            "name",
            "symbol",
        )
        for item in cls._walk_objects(payload):
            if not isinstance(item, dict):
                continue
            normalized = {str(k).lower(): v for k, v in item.items()}
            for key in keys:
                value = normalized.get(key)
                if isinstance(value, str) and value.strip():
                    root = cls._infer_index_root(value)
                    if root is not None:
                        return root
        return None

    @staticmethod
    def _infer_index_root(value: str) -> Optional[str]:
        text = value.strip().upper().replace(" ", "")
        if not text:
            return None
        if "BANKNIFTY" in text or "NIFTYBANK" in text:
            return "BANKNIFTY"
        if "SENSEX" in text:
            return "SENSEX"
        if "NIFTY" in text:
            return "NIFTY"
        return None

    @classmethod
    def _extract_weekly_expiry_weekday(cls, payload) -> int:
        # Default to Tuesday for backward compatibility with existing config.
        default_weekday = 1
        for item in cls._walk_objects(payload):
            if not isinstance(item, dict):
                continue
            normalized = {str(k).lower(): v for k, v in item.items()}
            for key in ("weekly_expiry_weekday", "expiry_weekday"):
                if key in normalized:
                    val = cls._coerce_number(normalized.get(key))
                    if val is not None and 0 <= int(val) <= 6:
                        return int(val)

        dates: list[date] = []
        for item in cls._walk_objects(payload):
            if isinstance(item, dict):
                normalized = {str(k).lower(): v for k, v in item.items()}
                for key in ("expiry", "expiry_date", "expdate", "exp"):
                    if key not in normalized:
                        continue
                    parsed = cls._parse_date(normalized.get(key))
                    if parsed is not None:
                        dates.append(parsed)
            elif isinstance(item, (list, tuple)):
                for value in item:
                    parsed = cls._parse_date(value)
                    if parsed is not None:
                        dates.append(parsed)

        if not dates:
            return default_weekday
        # Weekly expiries tend to dominate chain payloads; pick most frequent weekday.
        counts: dict[int, int] = {}
        for d in dates:
            wd = d.weekday()
            counts[wd] = counts.get(wd, 0) + 1
        return max(counts.items(), key=lambda kv: kv[1])[0]

    @staticmethod
    def _parse_date(value: object) -> Optional[date]:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d-%b-%y",
            "%d-%b-%Y",
            "%d%b%y",
            "%d%b%Y",
            "%d %b %Y",
        ):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def _extract_expiry_dates(cls, payload) -> list[str]:
        """Collect all parseable expiry values in ISO format (YYYY-MM-DD)."""
        out: list[str] = []
        for item in cls._walk_objects(payload):
            if isinstance(item, dict):
                normalized = {str(k).lower(): v for k, v in item.items()}
                for key in ("expiry", "expiry_date", "expdate", "exp"):
                    if key not in normalized:
                        continue
                    parsed = cls._parse_date(normalized.get(key))
                    if parsed is not None:
                        out.append(parsed.isoformat())
            elif isinstance(item, (list, tuple)):
                for value in item:
                    parsed = cls._parse_date(value)
                    if parsed is not None:
                        out.append(parsed.isoformat())
        return out

    def _infer_exchange(self, symbol: str) -> str:
        if symbol.endswith("CE") or symbol.endswith("PE"):
            return self.exchange_options
        upper = symbol.upper()
        if "SENSEX" in upper:
            return "BSE_INDEX"
        return "NSE_INDEX"

    @staticmethod
    def _extract_order_id(resp) -> str:
        if isinstance(resp, dict):
            if resp.get("status") == "success":
                return str(
                    resp.get("orderid")
                    or (resp.get("data") or {}).get("orderid")
                    or ""
                )
            raise RuntimeError(f"Order rejected: {resp}")
        return str(resp)


class HistoricalReplayBroker(BrokerInterface):
    """Backtest broker driven by pre-loaded per-symbol bars."""

    is_replay = True

    def __init__(self) -> None:
        self._bars: dict[str, pd.Series] = {}

    def set_current_bar(self, symbol: str, row: pd.Series) -> None:
        self._bars[symbol] = row

    def get_ltp(self, symbol: str) -> float:
        row = self._bars.get(symbol)
        if row is None:
            return 0.0
        return float(row["close"])

    def simulate_stop_limit_fill(
        self,
        symbol: str,
        trigger_price: float,
        limit_price: float,
    ) -> Optional[float]:
        row = self._bars.get(symbol)
        if row is None or float(row["high"]) < trigger_price:
            return None
        if float(row["high"]) > limit_price:
            return None
        return float(trigger_price)

    def place_market_order(self, symbol: str, side: OrderSide, quantity: int) -> str:
        return f"BT-MKT-{symbol}-{side.value}-{quantity}"

    def place_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        trigger_price: float,
        limit_price: float,
    ) -> str:
        return f"BT-SL-L-{symbol}-{side.value}-{quantity}"
