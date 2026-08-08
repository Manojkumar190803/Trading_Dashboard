from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

import pandas as pd

from core.models import OrderSide

logger = logging.getLogger("core.broker")


class BrokerInterface:
    """Abstract broker — subclass and implement for your broker API."""

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
        logger.info(
            "OpenAlgoBroker initialized host=%s ws_url=%s product=%s dry_run=%s",
            host, ws_url, product, dry_run,
        )

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

    def _infer_exchange(self, symbol: str) -> str:
        if symbol.endswith("CE") or symbol.endswith("PE"):
            return self.exchange_options
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

    def __init__(self) -> None:
        self._bars: dict[str, pd.Series] = {}

    def set_current_bar(self, symbol: str, row: pd.Series) -> None:
        self._bars[symbol] = row

    def get_ltp(self, symbol: str) -> float:
        row = self._bars.get(symbol)
        if row is None:
            return 0.0
        return float(row["close"])

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
