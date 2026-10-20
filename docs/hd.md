This revised Functional Requirements Document (FRD) V3.3 defines the HD trend,
instrument selection, entry, risk, order, and dashboard-controlled trailing rules.

Functional Requirements Document (FRD): HD Option Strategy (V3.3)

1. Project Overview

The HD Strategy is an automated system for Nifty weekly options. It uses
3-minute NIFTY spot candles to determine direction and 3-minute candles from a
selected CE or PE contract to identify the RSI pullback and alert candle. The
React dashboard is the source of truth for per-instrument monitoring start/end,
entry cutoff, premium range, lot-size adjustment, and maximum initial risk.
Changes to an active instrument's settings restart its strategy process so the
new values take effect. Global dashboard trailing settings control breakeven
and trailing steps. Stop and milestone monitoring uses live option ticks.

The configured monitoring start/end times define the runner's active window.
HD locks contracts no earlier than 09:20; if monitoring starts later, contract
selection happens at the configured start. Monitoring end also triggers
square-off. Entry cutoff must fall within the monitoring window.

2. Instrument Selection & Initialization

  - Base Index: NIFTY (NSE_INDEX).
  - At the later of 09:20 IST or the instrument's configured monitoring start,
    inspect current-weekly-expiry CE and PE contracts.
  - Derive the ATM reference strike from the spot price using the configured
    strike step. Select the CE exactly one strike step below ATM and the PE
    exactly one strike step above ATM (one strike ITM for each side).
  - For each one-step ITM contract, require premium to be within that
    instrument's configured React dashboard range. If multiple chain rows
    exist for the target strike, select the premium closest to the range
    midpoint. Lock the selected symbols for the session.
  - Do not fall back to ATM, farther ITM, or OTM contracts if a one-step ITM
    contract is missing or outside the premium range; leave that side disabled
    and record the reason.

3. Technical Indicators (Calculated on 3-Min Candles)

1. EMA 13, 20, 50, 100, and 200, calculated on NIFTY spot close. EMA 100 and
  EMA 200 are informational only; they do not gate entries.
2. RSI (3 period): Applied to close price of the selected option. A setup begins
  when RSI crosses from at/above 20 to below 20 on a completed 3-minute candle.
3. VWAP: Daily reset, calculated on the selected option. Log it for monitoring;
  it does not gate entries or determine position size.

4. Signal Generation Logic

  - Determine direction using NIFTY spot EMA13, EMA20, and EMA50:
      - Bullish condition: EMA13 > EMA20 OR EMA20 > EMA50.
      - Bearish condition: EMA13 < EMA20 OR EMA20 < EMA50.
      - If both conditions are true or both are false, treat direction as
        ambiguous and do not generate a signal.
      - Bullish direction scans the locked CE contract; bearish direction scans
        the locked PE contract.
  - A setup begins when the selected option's completed-candle RSI(3) crosses
    from at/above 20 to below 20.
  - Evaluate only the immediately following completed 3-minute option candle
    for an alert. If it does not qualify, expire the setup. A new setup requires
    a new RSI cross below 20.
  - The alert candle must be green and meet either condition:
      - Body is at least 85% of its full high-low range; or
      - Hammer: lower wick is at least 2 times the body and upper wick is no
        greater than the body.
    The previous-high breakout is not a required condition.
  - The previous fractal-divergence requirement is removed.
  - Entry trigger: High of the alert candle.
  - Initial stop-loss: Low of the alert candle.
  - Initial risk: Planned trigger price minus alert candle low. Skip the trade
    if this exceeds the instrument's configured maximum initial risk. The
    per-instrument React setting defaults to 20 option-premium points.
  - The previous fractal-based risk calculation and VWAP-room filter are
    removed.

5. Execution & WebSocket Integration

5.1 Order Placement

  - Position size is read from the selected instrument's React dashboard
    configuration; it is not determined by VWAP.
  - Order Type: BUY STOP_LIMIT. Trigger and limit are both one valid instrument
    tick above the alert candle high. Do not add a further limit-price buffer.
  - Initial Stop-Loss: Alert candle low.
  - Risk Check: Calculate planned trigger price minus alert candle low before
    order placement; skip if greater than the configured per-instrument maximum.
  - WebSocket Activation: As soon as the STOP_LIMIT order is successfully placed
    with the broker, the system must subscribe to the Tick-by-Tick WebSocket
    feed for that specific symbol.

5.2 Real-Time Monitoring

The system transitions from "Candle-based" to "Tick-based" logic:

1.  Pending State: Monitor WebSocket LTP to confirm entry.
2.  Executed State: Once the entry order is filled, immediately place the Hard
    Stop Loss order at the alert candle low.

6. Multi-Stage Exit & Trailing SL (TSL) Logic

Trailing parameters are read from the React dashboard's global trailing-stop
configuration (`breakEvenRR` and `trailStepRR`). For HD, initial risk is:
IR = broker-confirmed entry price - alert candle low.

  - Stop-loss starts at the alert candle low.
  - At `breakEvenRR`, move the stop to the broker-confirmed entry price.
  - At each additional `trailStepRR` milestone, advance the stop by
    `trailStepRR * IR`. For example, with break-even at 1.25R and a 0.5R step,
    at 1.75R the stop is entry + 0.5R; at 2.25R it is entry + 1.0R.
  - Evaluate stop, milestone, and trailing conditions using live option-premium
    ticks. The stop must never move backward.

7. Risk & Operational Management

  - Daily SL Cap: System stops after 3 Hard SL hits (Initial SLs hit). TSL hits
    do not count towards the cap.
  - Time Constraints:
      - No new signals/orders after the entry cutoff configured for the instrument
        in the React dashboard.
      - Monitoring end time in the React dashboard stops the runner and triggers
        square-off of open positions.
  - Order Cleanup: A pending STOP_LIMIT entry order is cancelled only if
    the option's stop-loss level is breached (candle low ≤ option SL)
    before the order triggers.

8. Data Architecture

8.1 State Machine

The system must track the TradeState for each instrument:

1.  SEARCHING: Scanning 3-min candles for trend, pullback, RSI, and alert-candle
  conditions. If market direction is ambiguous, remain in SEARCHING without
  selecting a side.
2.  PENDING: Order placed, waiting for WebSocket LTP > Trigger.
3.  ACTIVE: Order filled, WebSocket tracking TSL milestones.
4.  COMPLETED/CANCELLED: Trade over.

8.2 Logging

Detailed logs required for:

  - Indicator values at every 3-min close.
  - The exact IR (Initial Risk) calculation.
  - WebSocket "Price Hit" events for every 0.5 RR milestone.
  - Order fill prices vs. requested prices (Slippage tracking).

END OF FRD V3.3

9. Runtime Deployment and Strategy Isolation

  - The single `strategy_daemon` Compose service polls the dashboard instrument
    API and starts one child process for each active supported strategy
    instrument (21EMA, HD, CD, TC, 2BC, or BO). A filesystem lock prevents a
    second manager using the shared logs volume from starting duplicate workers.
  - HD uses its own ATM-lock file, daily hard-stop counter, and OpenAlgo
    strategy tag. HD position/order recovery must not claim or cancel EMA21
    orders for the same option symbol.
  - The Logs dashboard reads the per-strategy ATM-lock file to show the
    selected contract side(s) and strike. Setup-status rows must use the
    strategy provider's name so HD candles appear under HD rather than EMA21.
    Before a qualifying contract is locked, the dashboard reports that it is
    waiting for a contract; setup candles are unavailable until then.
  - Live price monitoring in the current runner is broker quote polling (about
    once per second), not the WebSocket tick subscription specified above.
