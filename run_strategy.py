"""Unified CLI entry point — runs any registered strategy via --strategy flag."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.broker import OpenAlgoBroker
from core.engine import BaseStrategyEngine
from core.indicators import add_indicators
from core.models import RiskConfig, StrategyConfig
from core.runner import LiveFeedRunner, _normalize_history_df, run_historical_replay
from strategies.base import SignalProvider

logger = logging.getLogger("run_strategy")

# ── Strategy registry ────────────────────────────────────────────────────────
# Add new strategies here: key = CLI name, value = factory function.

STRATEGY_REGISTRY: dict[str, callable] = {}


def _register_hd() -> SignalProvider:
    from strategies.hd import HDConfig, HDSignalProvider
    return HDSignalProvider(HDConfig())


STRATEGY_REGISTRY["hd"] = _register_hd


def get_signal_provider(name: str, args: argparse.Namespace) -> SignalProvider:
    """Instantiate the named strategy, applying any strategy-specific CLI overrides."""
    if name == "hd":
        from strategies.hd import HDConfig, HDSignalProvider
        hd_cfg = HDConfig()
        if args.body_threshold is not None:
            hd_cfg.strong_body_threshold = args.body_threshold
        return HDSignalProvider(hd_cfg)

    factory = STRATEGY_REGISTRY.get(name)
    if factory is None:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise SystemExit(f"Unknown strategy '{name}'. Available: {available}")
    return factory()


# ── CLI ──────────────────────────────────────────────────────────────────────


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified strategy runner")
    parser.add_argument(
        "--strategy", type=str, default="hd",
        help=f"Strategy to run (available: {', '.join(sorted(STRATEGY_REGISTRY.keys()))})",
    )
    parser.add_argument(
        "--mode", choices=("backtest", "smoke", "paper", "live"), default="smoke",
        help="backtest | smoke | paper | live",
    )
    parser.add_argument("--start", type=str, default=None,
                        help="Backtest start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None,
                        help="Backtest end date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Override spot_symbol (default NIFTY)")
    parser.add_argument("--exchange", type=str, default=None,
                        help="Override exchange_spot (default NSE_INDEX)")
    parser.add_argument("--timeframe", type=int, default=None,
                        help="Override timeframe_minutes (default 3)")
    parser.add_argument("--max-risk", type=float, default=None,
                        help="Override max_option_risk_points")
    parser.add_argument("--max-sl", type=int, default=None,
                        help="Override max_sl_per_day")
    # Strategy-specific params (shared namespace; each strategy picks what it needs).
    parser.add_argument("--body-threshold", type=float, default=None,
                        help="[HD] Override strong_body_threshold (default 0.85)")
    parser.add_argument("--diagnose", action="store_true",
                        help="Print per-candle diagnostic when no signal fires")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full candle summary every bar")
    parser.add_argument("--log-level", type=str, default="INFO")
    return parser.parse_args(argv)


def _load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    script_dir = Path(__file__).resolve().parent
    env_path = script_dir / ".env"
    if not env_path.exists():
        env_path = script_dir.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _build_broker(cfg: StrategyConfig, dry_run: bool) -> OpenAlgoBroker:
    api_key = os.getenv("OPENALGO_API_KEY")
    if not api_key:
        raise SystemExit("OPENALGO_API_KEY not set (check .env)")
    host = os.getenv("OPENALGO_HOST") or os.getenv("OPENALGO_URL") or "http://127.0.0.1:5002"
    ws_url = os.getenv("OPENALGO_WS_URL") or (
        f"ws://{os.getenv('WEBSOCKET_HOST', '127.0.0.1')}:"
        f"{os.getenv('WEBSOCKET_PORT', '8765')}"
    )
    return OpenAlgoBroker(
        api_key=api_key,
        host=host,
        ws_url=ws_url,
        strategy_tag=os.getenv("STRATEGY_NAME", "Strategy"),
        product=os.getenv("PRODUCT", "MIS"),
        exchange_options=cfg.exchange_options,
        dry_run=dry_run,
    )


def _run_smoke(cfg: StrategyConfig) -> None:
    broker = _build_broker(cfg, dry_run=True)
    today = datetime.now().date()
    start = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    interval = f"{cfg.timeframe_minutes}m"
    logger.info("smoke: fetching %s %s %s [%s -> %s]", cfg.spot_symbol, cfg.exchange_spot, interval, start, end)
    raw = broker.fetch_history(symbol=cfg.spot_symbol, exchange=cfg.exchange_spot, interval=interval, start_date=start, end_date=end)
    prepared = add_indicators(_normalize_history_df(raw), cfg)
    print(prepared.tail(5).to_string(index=False))
    ltp = broker.get_ltp(cfg.spot_symbol)
    print(f"\nLive LTP for {cfg.spot_symbol}: {ltp}")


def _run_live(cfg: StrategyConfig, risk: RiskConfig, signal_provider: SignalProvider, dry_run: bool, diagnose: bool, verbose: bool) -> None:
    broker = _build_broker(cfg, dry_run=dry_run)
    engine = BaseStrategyEngine(cfg, risk, broker, signal_provider)
    engine.diagnose = diagnose
    engine.verbose = verbose
    runner = LiveFeedRunner(engine, broker, cfg)
    try:
        runner.run_forever()
    except KeyboardInterrupt:
        logger.info("interrupted; stopping runner")
        runner.stop()


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    _setup_logging(args.log_level)
    _load_dotenv_if_present()

    cfg = StrategyConfig()
    if args.symbol:
        cfg.spot_symbol = args.symbol
        cfg.option_index_symbol = args.symbol
    if args.exchange:
        cfg.exchange_spot = args.exchange
    if args.timeframe:
        cfg.timeframe_minutes = args.timeframe
    if args.max_risk is not None:
        cfg.max_option_risk_points = args.max_risk

    risk = RiskConfig()
    if args.max_sl is not None:
        risk.max_sl_per_day = args.max_sl

    signal_provider = get_signal_provider(args.strategy, args)

    if args.mode == "backtest":
        if not args.start:
            raise SystemExit("backtest mode requires --start YYYY-MM-DD")
        end_date = args.end or datetime.now().date().strftime("%Y-%m-%d")
        run_historical_replay(cfg, risk, signal_provider, args.start, end_date, diagnose=args.diagnose)
        return

    if args.mode == "smoke":
        _run_smoke(cfg)
        return

    dry_run = args.mode == "paper"
    _run_live(cfg, risk, signal_provider, dry_run=dry_run, diagnose=args.diagnose, verbose=args.verbose)


if __name__ == "__main__":
    main()
