This is the fresh and complete **Functional Requirements Document (FRD) V1.2** for the **CD (Classic Divergence) Strategy**. 

It removes the restrictive EMA trend filter (Gate 2) to allow for pure reversal catching and incorporates the mandatory **Dual-Candle Confirmation** logic.

---

# Functional Requirements Document (FRD): CD Option Strategy (V1.2)

## 1. Project Overview
The **CD Strategy** is an automated reversal system for Nifty weekly options (both **CE and PE** sides, same as HD). It is designed to catch market reversals by identifying "Classic Bullish Divergence" on a 3-minute option premium candle interval. The strategy uses a high-sensitivity **RSI (3)** and requires two consecutive bullish candles for momentum confirmation. Post-entry, the system switches to **Real-time WebSocket (Tick-by-Tick)** monitoring to manage a Step-Trailing Stop Loss (TSL).

## 2. Instrument Selection & Initialization
*   **Base Index:** NIFTY (NSE_INDEX).
*   **Strike Selection (Daily at 09:20 IST):**
    *   Fetch Nifty Spot LTP at 09:20:00.
    *   Round to the nearest 50-point step to find the **ATM (At-The-Money) Strike**.
    *   Lock the corresponding **CE and PE** symbols for the current weekly expiry for the rest of the session.

## 3. Technical Indicators (Calculated on 3-Min Option Premium Candles)
All indicators are applied to the **option premium chart** (same as HD).
1.  **RSI (3 period):** Applied to the Close price of the option.
2.  **VWAP:** Daily reset (used for position sizing).
3.  **EMAs (13, 20, 50):** Tracked for logging and secondary analysis (No longer a hard entry gate).

## 4. Signal Generation Logic (The "Three-Gate" Entry)

### Gate 1: Classic Bullish Divergence ("The Alert")
P1 and P2 detection uses the **same swing-low state machine as HD** (RSI dips below 20, the lowest RSI during that sub-20 excursion marks the fractal low, confirmed when RSI crosses back above 20). No minimum or maximum candle-distance constraint between P1 and P2.

The system scans for two Fractal Lows (**P1** and **P2**) on both CE and PE option charts independently:
*   **Price Condition:** $Low_{P2} < Low_{P1}$ (Price makes a Lower Low).
*   **RSI Condition:** $RSI_{P2} > RSI_{P1}$ (RSI makes a Higher Low).
*   **Zone Constraint:** Both RSI points ($P1$ and $P2$) must be **< 20**.
*   The candle forming $P2$ is designated as the **Alert Candle**.

> **Note:** This is the inverse of HD's divergence condition (HD: Price HL + RSI LL → Hidden; CD: Price LL + RSI HL → Classic).

### Gate 2: Dual-Candle Confirmation
Immediately following the Alert Candle, the system requires **two consecutive** candles to confirm bullish momentum:
*   **Candle +1 and Candle +2** must both satisfy one of these conditions:
    *   **Strong Green:** Body $\ge$ 85% of the total candle range.
    *   **Hammer:** Lower wick $\ge$ 2 $\times$ Body.
*   **Invalidation:** If any candle in this 2-candle sequence is Red or a Doji, the signal is discarded.

### Gate 3: Risk Assessment
*   **Entry Price:** High of Confirmation Candle (+2) + 1.0.
*   **Initial SL:** Lowest Low of (P1, P2, and the two Confirmation Candles) - 1.0.
*   **Risk Cap:** If $(\text{Entry Price} - \text{Initial SL}) > 20$ points, the trade is **discarded**.

## 5. Execution & WebSocket Integration

### 5.1 Order Placement
*   **Position Sizing:** 
    *   **2 Lots** if Confirmation Candle (+2) Close > VWAP.
    *   **1 Lot** if Confirmation Candle (+2) Close < VWAP.
*   **Order Type:** STOP_LIMIT (Trigger: Entry Price, Limit: Trigger + 0.5).
*   **WebSocket Activation:** As soon as the STOP_LIMIT order is placed, subscribe to the **Tick-by-Tick WebSocket feed** for that specific option symbol.

### 5.2 Real-Time Monitoring
*   **Pending State:** Monitor WebSocket LTP. If the LTP hits the `Initial SL` level *before* the entry order is triggered, **Cancel the Entry Order** immediately.
*   **Executed State:** Once the entry order is filled, immediately place the **Hard Stop Loss** order at the broker.

## 6. Multi-Stage Exit & Trailing SL (TSL) Logic
Exits are managed tick-by-tick via WebSocket based on **Initial Risk (IR)**.
$\text{Formula: } IR = \text{Entry Price} - \text{Initial SL}$

*   **Phase 1: Initial (Before 1.5 RR)**
    *   SL remains at `Initial SL`.
*   **Phase 2: Breakeven (At 1.5 RR Milestone)**
    *   Once LTP hits $Entry + (1.5 \times IR)$:
    *   **Action:** Move SL to Entry Price (Cost).
    *   If total quantity is 1 Lot: Exit Position Full.
*   **Phase 3: Step-Trailing (Every 0.5 RR thereafter)**
    *   **At 2.0 RR:** Move SL to $Entry + (0.5 \times IR)$.
    *   **At 2.0 RR (Partial Exit):** If 2 Lots were taken, **Exit 1 Lot (50%)** at Market.
    *   **At 2.5 RR:** Move SL to $Entry + (1.0 \times IR)$.
    *   **At 3.0 RR:** Move SL to $Entry + (1.5 \times IR)$.
    *   **Indefinite Step:** Continue trailing the remaining 1 lot every 0.5 RR step until hit.

## 7. Risk & Operational Management
*   **Daily SL Cap:** System stops after **2 Hard SL hits** (Initial SLs hit).
*   **Time Constraints:**
    *   No new signals/orders after **14:45 IST**.
    *   Mandatory square-off of all positions at **15:15 IST**.
*   **Conflict Resolution:** If an HD (Hidden) signal and a CD (Classic) signal occur on the same symbol, the **HD signal takes priority**.

## 8. Data Architecture

### 8.1 State Machine
1.  **SCANNING:** Monitoring 3-min candles for Gate 1 (LL in Price, HL in RSI).
2.  **CONFIRMING:** Gate 1 met; checking the next two candles for Gate 2.
3.  **PENDING:** Order placed; WebSocket monitoring for entry or SL-invalidation.
4.  **ACTIVE:** Position open; WebSocket tracking TSL milestones.
5.  **CLOSED:** Trade completed.

### 8.2 Logging Requirements
*   **Indicator Values:** Log RSI 3 at P1 and P2.
*   **Confirmation Log:** Log the Body% and Wick/Body ratio for the two confirmation candles.
*   **Execution Log:** Log the exact IR value and every "Price Hit" event for the RR milestones.
*   **Slippage Tracking:** Difference between the Milestone Price and actual Execution Price.

---
**END OF FRD V1.2 (CD Strategy)**