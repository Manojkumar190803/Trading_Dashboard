"""Flask API server for React dashboard and symbol search."""

import os
import json
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from pathlib import Path

logger = logging.getLogger("api_server")

app = Flask(__name__)
CORS(app)
DAILY_PNL_FILE = Path("logs") / "daily_pnl.json"
DASHBOARD_DATA_FILE = Path("logs") / "dashboard_data.json"

# Initialize database connection
try:
    from core.db_connection import init_db_connection
    init_db_connection()
    logger.info("✅ Database initialized successfully")
except Exception as e:
    logger.warning(f"⚠️  Database initialization skipped: {e}")

# OpenAlgo credentials from environment
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "default_key")
OPENALGO_HOST = os.getenv("OPENALGO_HOST", "http://localhost:5000")

# Initialize OpenAlgo client
try:
    from openalgo import api
    openalgo_client = api(api_key=OPENALGO_API_KEY, host=OPENALGO_HOST)
    logger.info(f"OpenAlgo connected to {OPENALGO_HOST}")
except Exception as e:
    logger.warning(f"OpenAlgo not available: {e}")
    openalgo_client = None


# ==================== Symbol Search ====================

# Base indices - ALL strategies use SPOT symbols for initial setup
# At 9:20 IST, the system checks SPOT price and determines ATM strike for CE/PE
BASE_INDICES = [
    "NIFTY",        # Main index for 21EMA, HD, CD, TC, 2BC, BO
    "BANKNIFTY",    # Bank sector index
    "SENSEX",       # BSE index
]


@app.route("/api/symbols/search", methods=["GET"])
def search_symbols():
    """
    Search for symbols based on strategy.
    
    Query Parameters:
        q (str): Search query (required)
        strategy (str): Trading strategy - '21EMA' for spot symbols, others for options
    
    For ALL strategies:
    1. User selects base symbol (NIFTY, BANKNIFTY, etc.) during setup
    2. At 9:20 IST ATM lock, system checks SPOT price at that time
    3. System determines ATM strike based on SPOT price
    4. Execution uses CE/PE of the calculated ATM strike
    
    Returns: SPOT symbols (NIFTY, BANKNIFTY, SENSEX)
    """
    query = request.args.get("q", "").upper().strip()
    strategy = request.args.get("strategy", "21EMA").upper().strip()
    
    if not query:
        return jsonify({"symbols": []})
    
    results = []
    
    # All strategies use SPOT symbols for base selection
    # The strategy parameter is for future enhancement (options chain lookup)
    # Currently, all strategies work with spot symbols
    for index in BASE_INDICES:
        if index.startswith(query):
            results.append(index)
    
    # Log the search
    if results:
        logger.info(f"Symbol search '{query}' (strategy: {strategy}) returned: {results}")
    else:
        logger.debug(f"No symbols found for query: {query} (strategy: {strategy})")
    
    # Sort and remove duplicates
    results = sorted(list(set(results)))
    
    return jsonify({
        "symbols": results[:20],  # Limit to 20 results
        "query": query,
        "strategy": strategy,
        "count": len(results)
    })




@app.route("/api/symbols/validate", methods=["POST"])
def validate_symbol():
    """
    Validate if a symbol is available in OpenAlgo.
    
    Request body:
        {"symbol": "NIFTY"}
    
    Returns info about whether the symbol is valid and available in OpenAlgo.
    """
    data = request.get_json() or {}
    symbol = str(data.get("symbol", "")).upper().strip()
    
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400
    
    # Check against base indices
    is_valid = symbol in BASE_INDICES
    
    response = {
        "symbol": symbol,
        "valid": is_valid,
        "available_symbols": BASE_INDICES,
    }
    
    if is_valid:
        response["message"] = f"✅ '{symbol}' is a valid symbol"
        response["details"] = {
            "symbol": symbol,
            "type": "SPOT INDEX",
            "strategy": "All strategies (21EMA, HD, CD, TC, 2BC, BO)",
            "how_it_works": "At 9:20 IST, system checks SPOT price and determines ATM strike for options trading"
        }
        logger.info(f"Symbol validation: '{symbol}' is VALID")
        return jsonify(response), 200
    else:
        response["message"] = f"❌ '{symbol}' is NOT a valid symbol. Please choose from: {', '.join(BASE_INDICES)}"
        response["suggestion"] = "Use one of the available symbols above"
        logger.warning(f"Symbol validation: '{symbol}' is INVALID")
        return jsonify(response), 400


# ==================== Logs & Dashboard Data ====================

@app.route("/api/logs/<filename>", methods=["GET"])
def get_log_file(filename):
    """Serve JSON files from logs directory."""
    # Security: only allow .json files and prevent path traversal
    if not filename.endswith(".json") or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400
    
    filepath = Path("logs") / filename
    
    try:
        if filepath.exists():
            with open(filepath, "r") as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs/dashboard_data.json", methods=["GET"])
def get_dashboard_data():
    """Get cached dashboard data from logs."""
    return get_log_file("dashboard_data.json")


@app.route("/api/logs/wallet_data.json", methods=["GET"])
def get_wallet_data():
    """Get cached wallet data from logs."""
    return get_log_file("wallet_data.json")


@app.route("/api/analytics/summary", methods=["GET"])
def get_analytics_summary():
    """
    Extract analytics summary from dashboard_data.json.
    Synthesizes trade data from positions and orders for the Analytics page.
    
    Returns:
    {
        "total_pnl": float,
        "net_pnl": float,
        "gross_profit": float,
        "gross_loss": float,
        "trades_completed": int,
        "winning_trades": int,
        "losing_trades": int,
        "win_rate": float,
        "profit_factor": float,
        "expectancy": float,
        "positions": [...],
        "orders": [...]
    }
    """
    try:
        filepath = Path("logs") / "dashboard_data.json"
        
        if not filepath.exists():
            return jsonify({
                "total_pnl": 0,
                "net_pnl": 0,
                "gross_profit": 0,
                "gross_loss": 0,
                "trades_completed": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "expectancy": 0,
                "positions": [],
                "orders": [],
                "message": "No data available yet"
            })
        
        with open(filepath, "r") as f:
            data = json.load(f)
        
        positions = data.get("positions", [])
        orders_data = data.get("orders", {})
        all_orders = orders_data.get("orders", []) if isinstance(orders_data, dict) else []
        
        # Calculate P&L from positions
        total_pnl = sum(float(p.get("pnl", 0)) for p in positions)
        gross_profit = sum(float(p.get("pnl", 0)) for p in positions if float(p.get("pnl", 0)) > 0)
        gross_loss = abs(sum(float(p.get("pnl", 0)) for p in positions if float(p.get("pnl", 0)) < 0))
        
        # Count completed orders as trades
        completed_orders = [o for o in all_orders if o.get("order_status") == "complete"]
        trades_completed = len(completed_orders)
        
        # Winning and losing trades
        winning_trades = sum(1 for p in positions if float(p.get("pnl", 0)) > 0)
        losing_trades = sum(1 for p in positions if float(p.get("pnl", 0)) < 0)
        
        # Win rate
        win_rate = (winning_trades / trades_completed * 100) if trades_completed > 0 else 0
        
        # Profit factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (1 if gross_profit > 0 else 0)
        
        # Expectancy
        expectancy = (total_pnl / trades_completed) if trades_completed > 0 else 0
        
        logger.info(f"Analytics summary: PnL={total_pnl}, Trades={trades_completed}, WinRate={win_rate:.1f}%")
        
        return jsonify({
            "total_pnl": round(total_pnl, 2),
            "net_pnl": round(total_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "trades_completed": trades_completed,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 2),
            "positions": positions,
            "orders": completed_orders,
            "timestamp": data.get("timestamp", "")
        }), 200
        
    except Exception as e:
        logger.error(f"Error calculating analytics summary: {e}")
        return jsonify({"error": str(e)}), 500


def _load_daily_pnl_from_database(year: int, month: int) -> dict[str, dict[str, float | int]]:
    """Aggregate database daily summaries by calendar day for the requested month."""
    from sqlalchemy import func
    from core.db_connection import DatabaseSession
    from core.db_models import DailyPnL

    with DatabaseSession() as session:
        records = session.query(DailyPnL).filter(
            func.extract("year", DailyPnL.trade_date) == year,
            func.extract("month", DailyPnL.trade_date) == month,
        ).all()

    daily_pnl = {}
    for record in records:
        day_key = str(record.trade_date.day)
        day_data = daily_pnl.setdefault(day_key, {"pnl": 0.0, "trades": 0})
        day_data["pnl"] += float(record.net_pnl or 0)
        day_data["trades"] += int(record.total_trades or 0)
    return daily_pnl


@app.route("/api/analytics/daily", methods=["GET"])
def get_daily_analytics():
    """Return a month of daily P&L from persistent snapshots and the database."""
    try:
        import calendar
        from datetime import datetime

        today = datetime.now()
        try:
            year = int(request.args.get("year", today.year))
            month = int(request.args.get("month", today.month))
        except (TypeError, ValueError):
            return jsonify({"error": "year and month must be integers"}), 400
        if year < 1900 or year > 2200 or month < 1 or month > 12:
            return jsonify({"error": "year or month is out of range"}), 400

        archive = {}
        if DAILY_PNL_FILE.exists():
            try:
                with DAILY_PNL_FILE.open("r", encoding="utf-8") as handle:
                    archive = json.load(handle)
            except (OSError, json.JSONDecodeError):
                pass

        month_key = f"{year}-{month:02d}"
        stored_daily_pnl = dict(archive.get(month_key, {}))

        # Database rows fill days that do not yet have an archive snapshot.
        try:
            database_daily_pnl = _load_daily_pnl_from_database(year, month)
            for day_key, day_data in database_daily_pnl.items():
                stored_daily_pnl.setdefault(day_key, day_data)
        except Exception as db_err:
            logger.debug("Could not load daily P&L from database: %s", db_err)

        current_day_data = None
        if (year, month) == (today.year, today.month) and DASHBOARD_DATA_FILE.exists():
            try:
                from core.dashboard_data import _extract_daily_pnl_snapshot_data

                with DASHBOARD_DATA_FILE.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                data_timestamp = datetime.fromisoformat(data.get("timestamp", ""))
                if data_timestamp.date() == today.date():
                    pnl, trades, has_daily_data = _extract_daily_pnl_snapshot_data(data, today.date())
                    if has_daily_data:
                        current_day_data = {"pnl": pnl, "trades": trades}
            except (OSError, ValueError, TypeError):
                pass

        days_in_month = calendar.monthrange(year, month)[1]
        days = {}
        for day in range(1, days_in_month + 1):
            day_key = str(day)
            day_data = stored_daily_pnl.get(day_key, {})
            if (
                day == today.day
                and (year, month) == (today.year, today.month)
                and current_day_data is not None
            ):
                day_data = current_day_data
            pnl = float(day_data.get("pnl", 0) or 0)
            trades = int(day_data.get("trades", 0) or 0)
            if trades == 0 and pnl == 0:
                color = "gray"
            elif pnl < -2000:
                color = "dark-red"
            elif pnl < 0:
                color = "red"
            elif pnl < 2000:
                color = "green"
            else:
                color = "dark-green"
            days[day_key] = {
                "pnl": round(pnl, 2),
                "trades": trades,
                "color": color
            }

        trading_days = [data for data in days.values() if data["trades"] > 0]
        total_pnl = sum(data["pnl"] for data in trading_days)
        winning_days = sum(1 for data in trading_days if data["pnl"] > 0)
        losing_days = sum(1 for data in trading_days if data["pnl"] < 0)
        best_day = None
        worst_day = None
        best_pnl = float('-inf')
        worst_pnl = float('inf')
        for day_str, day_data in days.items():
            if day_data["trades"] > 0:
                if day_data["pnl"] > best_pnl:
                    best_pnl = day_data["pnl"]
                    best_day = int(day_str)
                if day_data["pnl"] < worst_pnl:
                    worst_pnl = day_data["pnl"]
                    worst_day = int(day_str)

        return jsonify({
            "month": f"{calendar.month_name[month]} {year}",
            "year": year,
            "month_num": month,
            "days": days,
            "month_summary": {
                "total_pnl": round(total_pnl, 2),
                "best_day": {"day": best_day, "pnl": round(best_pnl, 2) if best_day else 0},
                "worst_day": {"day": worst_day, "pnl": round(worst_pnl, 2) if worst_day else 0},
                "winning_days": winning_days,
                "losing_days": losing_days,
                "total_trading_days": len(trading_days)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error calculating daily analytics: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics/daily/reset", methods=["POST"])
def reset_daily_analytics():
    """Reset daily P&L data for the selected month."""
    try:
        from datetime import datetime
        from sqlalchemy import func

        today = datetime.now()
        try:
            year = int(request.args.get("year", today.year))
            month = int(request.args.get("month", today.month))
        except (TypeError, ValueError):
            return jsonify({"error": "year and month must be integers"}), 400
        if year < 1900 or year > 2200 or month < 1 or month > 12:
            return jsonify({"error": "year or month is out of range"}), 400

        all_data = {}
        if DAILY_PNL_FILE.exists():
            with DAILY_PNL_FILE.open("r", encoding="utf-8") as handle:
                all_data = json.load(handle)
        month_key = f"{year}-{month:02d}"
        all_data[month_key] = {}
        temporary_path = DAILY_PNL_FILE.with_suffix(DAILY_PNL_FILE.suffix + ".tmp")
        temporary_path.write_text(json.dumps(all_data, indent=2), encoding="utf-8")
        os.replace(temporary_path, DAILY_PNL_FILE)

        try:
            from core.db_connection import DatabaseSession
            from core.db_models import DailyPnL
            with DatabaseSession() as session:
                session.query(DailyPnL).filter(
                    func.extract("year", DailyPnL.trade_date) == year,
                    func.extract("month", DailyPnL.trade_date) == month,
                ).delete(synchronize_session=False)
                session.commit()
        except Exception as db_err:
            logger.debug("Could not reset daily P&L database rows: %s", db_err)

        logger.info("Reset daily analytics for %s", month_key)
        return jsonify({"success": True, "message": f"Daily analytics reset for {month_key}"}), 200
    except Exception as e:
        logger.error(f"Error resetting daily analytics: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== Database Endpoints ====================

@app.route("/api/db/trades", methods=["GET"])
def get_trades():
    """Get all trades from database with optional filtering."""
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Trade
        from datetime import datetime, timedelta
        
        # Query parameters
        strategy = request.args.get("strategy")
        symbol = request.args.get("symbol")
        days = request.args.get("days", default=7, type=int)
        limit = request.args.get("limit", default=100, type=int)
        
        with DatabaseSession() as session:
            query = session.query(Trade)
            
            # Filter by strategy
            if strategy:
                query = query.filter(Trade.strategy_name == strategy)
            
            # Filter by symbol
            if symbol:
                query = query.filter(Trade.symbol == symbol)
            
            # Filter by date range
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            query = query.filter(Trade.trade_date >= cutoff_date)
            
            # Order by latest first
            trades = query.order_by(Trade.trade_date.desc()).limit(limit).all()
            
            return jsonify({
                "trades": [
                    {
                        "id": t.id,
                        "strategy": t.strategy_name,
                        "symbol": t.symbol,
                        "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                        "entry_price": float(t.entry_price),
                        "entry_qty": t.entry_qty,
                        "exit_price": float(t.exit_price) if t.exit_price else None,
                        "pnl": float(t.pnl) if t.pnl else None,
                        "pnl_percentage": t.pnl_percentage,
                        "status": t.status.value if t.status else None,
                    }
                    for t in trades
                ],
                "count": len(trades),
                "filters": {"strategy": strategy, "symbol": symbol, "days": days}
            }), 200
    
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/positions", methods=["GET"])
def get_positions():
    """Get current open positions from database."""
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Position
        
        strategy = request.args.get("strategy")
        
        with DatabaseSession() as session:
            query = session.query(Position).filter(Position.is_active == True)
            
            if strategy:
                query = query.filter(Position.strategy_name == strategy)
            
            positions = query.order_by(Position.opened_at.desc()).all()
            
            return jsonify({
                "positions": [
                    {
                        "id": p.id,
                        "strategy": p.strategy_name,
                        "symbol": p.symbol,
                        "qty": p.qty,
                        "side": p.side.value if p.side else None,
                        "entry_price": float(p.entry_price),
                        "current_price": float(p.current_price) if p.current_price else None,
                        "unrealized_pnl": float(p.unrealized_pnl) if p.unrealized_pnl else None,
                        "realized_pnl": float(p.realized_pnl),
                        "sl_price": float(p.sl_price) if p.sl_price else None,
                        "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                    }
                    for p in positions
                ],
                "count": len(positions),
            }), 200
    
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/daily-pnl", methods=["GET"])
def get_daily_pnl():
    """Get daily P&L summary from database."""
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import DailyPnL
        from datetime import datetime, timedelta
        
        strategy = request.args.get("strategy")
        days = request.args.get("days", default=30, type=int)
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with DatabaseSession() as session:
            query = session.query(DailyPnL)
            
            if strategy:
                query = query.filter(DailyPnL.strategy_name == strategy)
            
            query = query.filter(DailyPnL.trade_date >= cutoff_date)
            daily_pnls = query.order_by(DailyPnL.trade_date.desc()).all()
            
            return jsonify({
                "daily_pnl": [
                    {
                        "date": p.trade_date.strftime("%Y-%m-%d"),
                        "strategy": p.strategy_name,
                        "total_trades": p.total_trades,
                        "winning_trades": p.winning_trades,
                        "losing_trades": p.losing_trades,
                        "net_pnl": float(p.net_pnl),
                        "win_rate": p.win_rate,
                        "best_trade": float(p.best_trade) if p.best_trade else None,
                        "worst_trade": float(p.worst_trade) if p.worst_trade else None,
                    }
                    for p in daily_pnls
                ],
                "count": len(daily_pnls),
            }), 200
    
    except Exception as e:
        logger.error(f"Error fetching daily P&L: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/logs", methods=["GET"])
def get_logs():
    """Get logs from database with filtering."""
    try:
        from core.db_connection import DatabaseSession
        from core.db_models import Log
        from datetime import datetime, timedelta
        
        strategy = request.args.get("strategy")
        symbol = request.args.get("symbol")
        level = request.args.get("level")
        hours = request.args.get("hours", default=24, type=int)
        limit = request.args.get("limit", default=100, type=int)
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        with DatabaseSession() as session:
            query = session.query(Log).filter(Log.timestamp >= cutoff_time)
            
            if strategy:
                query = query.filter(Log.strategy_name == strategy)
            
            if symbol:
                query = query.filter(Log.symbol == symbol)
            
            if level:
                query = query.filter(Log.level == level)
            
            logs = query.order_by(Log.timestamp.desc()).limit(limit).all()
            
            return jsonify({
                "logs": [
                    {
                        "id": l.id,
                        "timestamp": l.timestamp.isoformat(),
                        "level": l.level,
                        "category": l.category,
                        "symbol": l.symbol,
                        "strategy": l.strategy_name,
                        "message": l.message,
                    }
                    for l in logs
                ],
                "count": len(logs),
                "filters": {"strategy": strategy, "symbol": symbol, "level": level, "hours": hours}
            }), 200
    
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== Instruments Management ====================

@app.route("/api/instruments", methods=["GET"])
def get_instruments():
    """Fetch all configured instruments from database."""
    try:
        from core.db_models import Instrument
        from core.db_connection import DatabaseConnection
        
        session = DatabaseConnection.get_session()
        query = session.query(Instrument)
        if request.args.get("includeArchived", "").lower() != "true":
            query = query.filter_by(status="ACTIVE")
        instruments = query.all()
        
        return jsonify({
            "instruments": [
                {
                    "id": i.id,
                    "name": i.name,
                    "brokerSymbol": i.broker_symbol,
                    "monitoringStartTime": i.monitoring_start_time,
                    "monitoringEndTime": i.monitoring_end_time,
                    "lotSizeAdjustment": i.lot_size_adjustment,
                    "calculatedLotSize": i.calculated_lot_size,
                    "strategy": i.strategy,
                    "productType": i.product_type,
                    "premiumMinPrice": i.premium_min_price,
                    "premiumMaxPrice": i.premium_max_price,
                    "premiumOptionStrike": i.premium_option_strike,
                    "status": i.status,
                    "createdAt": i.created_at.isoformat(),
                    "updatedAt": i.updated_at.isoformat(),
                }
                for i in instruments
            ],
            "count": len(instruments)
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching instruments: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/instruments", methods=["POST"])
def create_instrument():
    """Create a new instrument in database."""
    session = None
    try:
        from core.db_models import Instrument
        from core.db_connection import DatabaseConnection
        
        data = request.json
        session = DatabaseConnection.get_session()
        name = str(data.get("name") or "").strip()
        existing = session.query(Instrument).filter_by(name=name).first()

        if existing and existing.status == "ACTIVE":
            return jsonify({"error": f"Instrument '{name}' is already active"}), 409
        
        instrument = existing or Instrument(name=name)
        instrument.name = name
        instrument.broker_symbol = data.get("brokerSymbol")
        instrument.strategy = data.get("strategy")
        instrument.monitoring_start_time = data.get("monitoringStartTime")
        instrument.monitoring_end_time = data.get("monitoringEndTime")
        instrument.lot_size_adjustment = float(data.get("lotSizeAdjustment", 1.0))
        instrument.calculated_lot_size = int(data.get("calculatedLotSize"))
        instrument.premium_min_price = float(data.get("premiumMinPrice")) if data.get("premiumMinPrice") else None
        instrument.premium_max_price = float(data.get("premiumMaxPrice")) if data.get("premiumMaxPrice") else None
        instrument.product_type = data.get("productType", "SPOT")
        instrument.status = "ACTIVE"

        if existing:
            logger.info("Restoring archived instrument: %s", name)
        else:
            session.add(instrument)

        session.commit()

        logger.info("✅ Instrument created or restored: %s", instrument.name)

        return jsonify({
            "id": instrument.id,
            "name": instrument.name,
            "message": "Instrument restored successfully" if existing else "Instrument created successfully",
        }), 200 if existing else 201

    except Exception as e:
        if session is not None:
            session.rollback()
        error_message = str(e)
        if "uq_instrument_name" in error_message:
            return jsonify({"error": "An instrument with this name already exists"}), 409
        logger.error(f"Error creating instrument: {e}")
        return jsonify({"error": error_message}), 500


@app.route("/api/instruments/<int:instrument_id>", methods=["PUT"])
def update_instrument(instrument_id):
    """Update an existing instrument."""
    try:
        from core.db_models import Instrument
        from core.db_connection import DatabaseConnection
        
        data = request.json
        session = DatabaseConnection.get_session()
        
        instrument = session.query(Instrument).filter_by(id=instrument_id).first()
        if not instrument:
            return jsonify({"error": "Instrument not found"}), 404
        
        # Update fields
        if "name" in data:
            instrument.name = data["name"]
        if "brokerSymbol" in data:
            instrument.broker_symbol = data["brokerSymbol"]
        if "strategy" in data:
            instrument.strategy = data["strategy"]
        if "monitoringStartTime" in data:
            instrument.monitoring_start_time = data["monitoringStartTime"]
        if "monitoringEndTime" in data:
            instrument.monitoring_end_time = data["monitoringEndTime"]
        if "lotSizeAdjustment" in data:
            instrument.lot_size_adjustment = float(data["lotSizeAdjustment"])
        if "calculatedLotSize" in data:
            instrument.calculated_lot_size = int(data["calculatedLotSize"])
        if "premiumMinPrice" in data:
            instrument.premium_min_price = float(data["premiumMinPrice"]) if data["premiumMinPrice"] else None
        if "premiumMaxPrice" in data:
            instrument.premium_max_price = float(data["premiumMaxPrice"]) if data["premiumMaxPrice"] else None
        if "premiumOptionStrike" in data:
            instrument.premium_option_strike = int(data["premiumOptionStrike"]) if data["premiumOptionStrike"] else None
        if "status" in data:
            instrument.status = data["status"]
        
        session.commit()
        
        logger.info(f"✅ Instrument updated: {instrument.name}")
        
        return jsonify({
            "id": instrument.id,
            "name": instrument.name,
            "message": "Instrument updated successfully"
        }), 200
        
    except Exception as e:
        logger.error(f"Error updating instrument: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/instruments/<int:instrument_id>", methods=["DELETE"])
def delete_instrument(instrument_id):
    """Delete (archive) an instrument."""
    try:
        from core.db_models import Instrument
        from core.db_connection import DatabaseConnection
        
        session = DatabaseConnection.get_session()
        
        instrument = session.query(Instrument).filter_by(id=instrument_id).first()
        if not instrument:
            return jsonify({"error": "Instrument not found"}), 404
        
        # Mark as archived instead of hard delete
        instrument.status = "ARCHIVED"
        session.commit()
        
        logger.info(f"✅ Instrument archived: {instrument.name}")
        
        return jsonify({
            "message": "Instrument deleted successfully"
        }), 200
        
    except Exception as e:
        logger.error(f"Error deleting instrument: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/instruments/debug/all", methods=["GET"])
def get_all_instruments_debug():
    """Get all instruments including archived (debug endpoint)."""
    try:
        from core.db_models import Instrument
        from core.db_connection import DatabaseConnection
        
        session = DatabaseConnection.get_session()
        instruments = session.query(Instrument).all()  # No filter - get all
        
        return jsonify({
            "instruments": [
                {
                    "id": i.id,
                    "name": i.name,
                    "strategy": i.strategy,
                    "status": i.status,
                    "createdAt": i.created_at.isoformat(),
                }
                for i in instruments
            ],
            "count": len(instruments)
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching all instruments: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/instruments/debug/clear", methods=["POST"])
def clear_all_instruments():
    """Clear all instruments (debug endpoint)."""
    try:
        from core.db_models import Instrument
        from core.db_connection import DatabaseConnection
        
        session = DatabaseConnection.get_session()
        session.query(Instrument).delete()
        session.commit()
        
        logger.warning("🔴 CLEARED ALL INSTRUMENTS (DEBUG)")
        
        return jsonify({
            "message": "All instruments cleared"
        }), 200
        
    except Exception as e:
        logger.error(f"Error clearing instruments: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== Health Check ====================

@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    db_status = "connected"
    try:
        from core.db_connection import DatabaseConnection
        if not DatabaseConnection.is_initialized():
            db_status = "not_initialized"
    except Exception as e:
        db_status = f"error: {str(e)[:30]}"
    
    return jsonify({
        "status": "healthy",
        "openalgo": "connected" if openalgo_client else "disconnected",
        "database": db_status
    })


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    app.run(host="0.0.0.0", port=5003, debug=False)
