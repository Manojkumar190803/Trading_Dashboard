"""Unified CLI entry point — runs any registered strategy via --strategy flag."""

from __future__ import annotations

import argparse
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.broker import OpenAlgoBroker
from core.engine import BaseStrategyEngine
from core.indicators import add_indicators
from core.models import RiskConfig, StrategyConfig
from core.runner import LiveFeedRunner, MultiEngineLiveFeedRunner, _normalize_history_df, run_historical_replay, run_multi_historical_replay
from strategies.base import SignalProvider

logger = logging.getLogger("run_strategy")

SCRIPT_CHOICES = ("NIFTY", "BANKNIFTY", "SENSEX")

# ── Strategy registry ────────────────────────────────────────────────────────
# Add new strategies here: key = CLI name, value = factory function.

STRATEGY_REGISTRY: dict[str, callable] = {}


def _register_hd() -> SignalProvider:
    from strategies.hd import HDConfig, HDSignalProvider
    return HDSignalProvider(HDConfig())


def _register_cd() -> SignalProvider:
    from strategies.cd import CDConfig, CDSignalProvider
    return CDSignalProvider(CDConfig())


def _register_tc() -> SignalProvider:
    from strategies.tc import TCConfig, TCSignalProvider
    return TCSignalProvider(TCConfig())


def _register_ema21() -> SignalProvider:
    from strategies.ema21 import EMA21SignalProvider
    return EMA21SignalProvider()


STRATEGY_REGISTRY["hd"] = _register_hd
STRATEGY_REGISTRY["cd"] = _register_cd
STRATEGY_REGISTRY["tc"] = _register_tc
STRATEGY_REGISTRY["ema21"] = _register_ema21
STRATEGY_REGISTRY["opt_buy_930"] = lambda: None


def get_signal_provider(name: str, args: argparse.Namespace) -> SignalProvider:
    """Instantiate the named strategy, applying any strategy-specific CLI overrides."""
    if name == "opt_buy_930":
        raise SystemExit("opt_buy_930 is routed through its dedicated live/backtest runner")

    if name == "hd":
        from strategies.hd import HDConfig, HDSignalProvider
        hd_cfg = HDConfig()
        if args.body_threshold is not None:
            hd_cfg.strong_body_threshold = args.body_threshold
        return HDSignalProvider(hd_cfg)

    if name == "cd":
        from strategies.cd import CDConfig, CDSignalProvider
        cd_cfg = CDConfig()
        if args.body_threshold is not None:
            cd_cfg.strong_body_threshold = args.body_threshold
        return CDSignalProvider(cd_cfg)

    if name == "tc":
        from strategies.tc import TCConfig, TCSignalProvider
        tc_cfg = TCConfig()
        if args.body_threshold is not None:
            tc_cfg.strong_body_threshold = args.body_threshold
        return TCSignalProvider(tc_cfg)

    if name == "ema21":
        from strategies.ema21 import EMA21SignalProvider
        return EMA21SignalProvider()

    factory = STRATEGY_REGISTRY.get(name)
    if factory is None:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise SystemExit(f"Unknown strategy '{name}'. Available: {available}")
    return factory()


# ── CLI ──────────────────────────────────────────────────────────────────────


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified strategy runner")
    parser.add_argument(
        "--script", type=str, default="NIFTY",
        help="Underlying script: NIFTY | BANKNIFTY | SENSEX (auto-discovers lot/strike/expiry from OpenAlgo)",
    )
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
                        help="Print full candle summary every bar (live + backtest)")
    parser.add_argument(
        "--verbose-csv",
        type=str,
        default=None,
        help="Backtest only: save candle-by-candle verbose trace to CSV path",
    )
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


def _apply_discovered_script_profile(cfg: StrategyConfig, script: str) -> dict[str, object]:
    """Discover and apply script-specific instrument metadata via OpenAlgo."""
    probe_broker = _build_broker(cfg, dry_run=True)
    profile = probe_broker.discover_index_profile(script)
    cfg.spot_symbol = str(profile["spot_symbol"])
    cfg.option_index_symbol = str(profile["option_index_symbol"])
    cfg.exchange_spot = str(profile["exchange_spot"])
    cfg.exchange_options = str(profile["exchange_options"])
    cfg.strike_step = int(profile["strike_step"])
    cfg.option_lot_size = int(profile["option_lot_size"])
    cfg.weekly_expiry_weekday = int(profile["weekly_expiry_weekday"])

    logger.info(
        "script profile discovered: script=%s spot=%s opt_root=%s exch=%s/%s strike_step=%s lot_size=%s expiry_weekday=%s",
        script,
        cfg.spot_symbol,
        cfg.option_index_symbol,
        cfg.exchange_spot,
        cfg.exchange_options,
        cfg.strike_step,
        cfg.option_lot_size,
        cfg.weekly_expiry_weekday,
    )
    return profile


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


def _run_multi_live(
    cfg: StrategyConfig,
    risk: RiskConfig,
    strategy_names: list[str],
    args: argparse.Namespace,
    dry_run: bool,
    diagnose: bool,
    verbose: bool,
) -> None:
    broker = _build_broker(cfg, dry_run=dry_run)
    engines: list[tuple[str, BaseStrategyEngine]] = []
    for name in strategy_names:
        provider = get_signal_provider(name, args)
        engine = BaseStrategyEngine(cfg, risk, broker, provider)
        engine.diagnose = diagnose
        engine.verbose = verbose
        engines.append((name, engine))
    runner = MultiEngineLiveFeedRunner(engines, broker, cfg)
    try:
        runner.run_forever()
    except KeyboardInterrupt:
        logger.info("interrupted; stopping runner")
        runner.stop()


def _run_mixed_live(
    cfg: StrategyConfig,
    risk: RiskConfig,
    strategy_names: list[str],
    profile: dict[str, object],
    args: argparse.Namespace,
    dry_run: bool,
) -> None:
    """Run the dedicated tick strategy beside the candle-based strategies."""
    from scripts.run_opt_buy_930_openalgo_backtest import run_openalgo_live

    stop_event = threading.Event()
    opt_thread = threading.Thread(
        target=run_openalgo_live,
        args=(profile,),
        kwargs={"dry_run": dry_run, "stop_event": stop_event},
        name="opt-buy-930-live",
        daemon=True,
    )
    opt_thread.start()
    candle_names = [name for name in strategy_names if name != "opt_buy_930"]
    if not candle_names:
        try:
            opt_thread.join()
        except KeyboardInterrupt:
            stop_event.set()
            opt_thread.join()
        return

    try:
        _run_multi_live(
            cfg,
            risk,
            candle_names,
            args,
            dry_run=dry_run,
            diagnose=args.diagnose,
            verbose=args.verbose,
        )
    finally:
        stop_event.set()
        opt_thread.join(timeout=5)


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    _setup_logging(args.log_level)
    _load_dotenv_if_present()

    cfg = StrategyConfig()
    script = (args.script or "").upper().replace(" ", "")
    if script not in SCRIPT_CHOICES:
        allowed = ", ".join(SCRIPT_CHOICES)
        raise SystemExit(f"Invalid --script '{args.script}'. Allowed: {allowed}")
    profile = _apply_discovered_script_profile(cfg, script)

    # Manual overrides still win over discovered defaults.
    if args.symbol:
        cfg.spot_symbol = args.symbol
        cfg.option_index_symbol = args.symbol
    if args.exchange:
        cfg.exchange_spot = args.exchange
    if args.timeframe:
        cfg.timeframe_minutes = args.timeframe
    if args.max_risk is not None:
        cfg.max_option_risk_points = args.max_risk

    # Support comma-separated strategies: --strategy hd,cd
    strategy_names = [s.strip() for s in args.strategy.split(",")]

    if "ema21" in strategy_names:
        from datetime import time

        cfg.timeframe_minutes = 3
        cfg.market_open = time(9, 20)
        cfg.entry_start = time(9, 20)
        cfg.signal_cutoff = time(14, 45)
        cfg.entry_cutoff = time(14, 45)
        cfg.market_close = time(15, 10)
        cfg.force_square_off = time(15, 10)
        cfg.max_option_risk_points = 25.0 if args.max_risk is None else args.max_risk
        cfg.max_trades_per_day = 3

    risk = RiskConfig()
    if args.max_sl is not None:
        risk.max_sl_per_day = args.max_sl

    if args.mode == "backtest":
        if not args.start:
            raise SystemExit("backtest mode requires --start YYYY-MM-DD")
        end_date = args.end or datetime.now().date().strftime("%Y-%m-%d")
        if len(strategy_names) == 1 and strategy_names[0] == "opt_buy_930":
            from scripts.run_opt_buy_930_openalgo_backtest import run_openalgo_backtest

            results = run_openalgo_backtest(
                args.start,
                end_date,
                output_csv=None,
                output_txt=None,
                profile=profile,
            )
            fields = ["side", "symbol", "quantity", "entry_time", "entry_price", "stop_loss", "target", "exit_time", "exit_price", "exit_reason", "gross_pnl"]
            print("\t".join(fields))
            for trade in results:
                print("\t".join(str(getattr(trade, field) if field != "gross_pnl" else trade.gross_pnl) for field in fields))
            print(f"Trades: {len(results)}")
            print(f"Gross PnL (INR): {sum(trade.gross_pnl for trade in results):.2f}")
            return
        if len(strategy_names) > 1:
            if "opt_buy_930" in strategy_names:
                raise SystemExit("opt_buy_930 cannot be combined with candle strategies in backtest mode")
            providers = [(name, get_signal_provider(name, args)) for name in strategy_names]
            run_multi_historical_replay(
                cfg,
                risk,
                providers,
                args.start,
                end_date,
                diagnose=args.diagnose,
                verbose=args.verbose,
                verbose_csv_path=args.verbose_csv,
            )
        else:
            provider = get_signal_provider(strategy_names[0], args)
            run_historical_replay(
                cfg,
                risk,
                provider,
                args.start,
                end_date,
                diagnose=args.diagnose,
                verbose=args.verbose,
                verbose_csv_path=args.verbose_csv,
            )
        return

    if len(strategy_names) == 1 and strategy_names[0] == "opt_buy_930":
        if args.mode not in ("paper", "live"):
            raise SystemExit("opt_buy_930 supports only paper, live, and backtest modes")
        from scripts.run_opt_buy_930_openalgo_backtest import run_openalgo_live

        run_openalgo_live(profile, dry_run=args.mode == "paper")
        return

    if "opt_buy_930" in strategy_names:
        if args.mode not in ("paper", "live"):
            raise SystemExit("opt_buy_930 supports only paper and live modes")
        dry_run = args.mode == "paper"
        _run_mixed_live(cfg, risk, strategy_names, profile, args, dry_run=dry_run)
        return

    if args.mode == "smoke":
        _run_smoke(cfg)
        return

    dry_run = args.mode == "paper"
    if len(strategy_names) > 1:
        _run_multi_live(cfg, risk, strategy_names, args, dry_run=dry_run, diagnose=args.diagnose, verbose=args.verbose)
    else:
        signal_provider = get_signal_provider(strategy_names[0], args)
        _run_live(cfg, risk, signal_provider, dry_run=dry_run, diagnose=args.diagnose, verbose=args.verbose)


if __name__ == "__main__":
    main()
