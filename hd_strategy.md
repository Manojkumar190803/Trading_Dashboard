This revised Functional Requirements Document (FRD) V3.0 incorporates real-time
WebSocket monitoring and the specific Step-Trailing Stop Loss (TSL) logic you
requested.

Functional Requirements Document (FRD): HD Option Strategy (V3.0)

1. Project Overview

The HD Strategy is an automated system for Nifty weekly options. It uses a
3-minute candle interval for signal generation (RSI Divergence + EMA filters)
and switches to Real-time WebSocket (Tick-by-Tick) monitoring once an order is
placed or executed to manage a dynamic Trailing Stop Loss (TSL).

2. Instrument Selection & Initialization

  - Base Index: NIFTY (NSE_INDEX).
  - Strike Selection (09:20 IST):
      - Fetch Nifty Spot LTP at 09:20:00.
      - Round to nearest 50-point step to find ATM Strike.
      - Lock the corresponding CE and PE symbols for the current weekly expiry.

3. Technical Indicators (Calculated on 3-Min Candles)

1.  EMA 13, 20, 50.
2.  RSI (3 period): Applied to Close price.
3.  VWAP: Daily reset.

4. Signal Generation Logic (The "Four-Gate" Entry)

  - Gate 1 (Divergence): Fractal Lows P1 and P2 (3–20 candles apart).
      - Low_{P2} > Low_{P1} AND RSI_{P2} < RSI_{P1}.
      - Both RSI points must be < 20.
  - Gate 2 (Trend): (EMA13 > EMA20) OR (EMA20 > EMA50).
  - Gate 3 (Trigger): Current candle must be Strong Green (Body \ge 85%) OR
    Hammer (Lower wick \ge 2\times Body).
  - Gate 4 (Risk):
      - \text{Initial SL} = \text{Lowest Low of (P1, P2, and Trigger)} - 1.0.
      - \text{Entry Price} = \text{Trigger Candle High} + 1.0.
      - Discard if (\text{Entry} - \text{SL}) > 20 \text{ points}.

5. Execution & WebSocket Integration

5.1 Order Placement

  - Position Sizing: 2 Lots if Close > VWAP; 1 Lot if Close < VWAP.
  - Order Type: STOP_LIMIT (Trigger: High + 1.0, Limit: Trigger + 0.5).
  - WebSocket Activation: As soon as the STOP_LIMIT order is successfully placed
    with the broker, the system must subscribe to the Tick-by-Tick WebSocket
    feed for that specific symbol.

5.2 Real-Time Monitoring

The system transitions from "Candle-based" to "Tick-based" logic:

1.  Pending State: Monitor WebSocket LTP to confirm entry.
2.  Executed State: Once the entry order is filled, immediately place the Hard
    Stop Loss order at the calculated Swing Low.

6. Multi-Stage Exit & Trailing SL (TSL) Logic

Exits are managed tick-by-tick via WebSocket based on the Initial Risk (IR).
Formula: IR = \text{Entry Price} - \text{Initial SL}

6.1 The RR Milestones

  - Phase 1: Initial (Before 1.5 RR)
      - SL remains at Swing Low - 1.0.
  - Phase 2: Breakeven (At 1.5 RR)
      - Once LTP hits Entry + (1.5 \times IR):
      - Action: Move SL to Entry Price (Cost).
      - If total quantity is 1 Lot: Strategy closes here (Exit Full).
  - Phase 3: Step-Trailing (Every 0.5 RR thereafter)
      - The SL trails the price in "steps" of 0.5 RR.
      - At 2.0 RR: Move SL to Entry + (0.5 \times IR).
      - At 2.0 RR (Partial Exit): If 2 Lots were taken, Exit 1 Lot (50%) at
        Market.
      - At 2.5 RR: Move SL to Entry + (1.0 \times IR).
      - At 3.0 RR: Move SL to Entry + (1.5 \times IR).
      - (Continue trailing the remaining 1 lot every 0.5 RR indefinitely until
        hit).

7. Risk & Operational Management

  - Daily SL Cap: System stops after 3 Hard SL hits (Initial SLs hit). TSL hits
    do not count towards the cap.
  - Time Constraints:
      - No new signals/orders after 15:00 IST.
      - Mandatory square-off of all positions at 15:15 IST.
  - Order Cleanup: If an entry STOP_LIMIT is not filled by the time the
    next 3-minute candle closes, the order must be Cancelled via API.

8. Data Architecture

8.1 State Machine

The system must track the TradeState for each instrument:

1.  SEARCHING: Scanning 3-min candles for divergence.
2.  PENDING: Order placed, waiting for WebSocket LTP > Trigger.
3.  ACTIVE: Order filled, WebSocket tracking TSL milestones.
4.  COMPLETED/CANCELLED: Trade over.

8.2 Logging

Detailed logs required for:

  - Indicator values at every 3-min close.
  - The exact IR (Initial Risk) calculation.
  - WebSocket "Price Hit" events for every 0.5 RR milestone.
  - Order fill prices vs. requested prices (Slippage tracking).

END OF FRD V3.0
