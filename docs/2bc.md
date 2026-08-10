This incorporates your detailed research on market regimes into the **2BC Strategy**. Based on your recommendation of a "multi-factor filter," I have updated **Gate 1** to use a combination of the **Choppiness Index (CHOP)** and the **Average Directional Index (ADX)**. This ensures the strategy only triggers when the market is transitioning from a "High Compression" state to a "Momentum" state.

---

# Functional Requirements Document (FRD): 2BC Option Strategy (V1.1)

## 1. Project Overview
The **2BC Strategy** is an automated momentum breakout system. It is designed to identify "volatility expansion" events. By filtering for high-choppiness/low-trend environments (Gate 1) and requiring a specific two-candle price action with an RSI surge, the strategy captures the beginning of a fresh trend.

## 2. Instrument Selection & Initialization
*   **Base Index:** NIFTY (NSE_INDEX).
*   **Strike Selection (09:20 IST):** Round Nifty Spot to the nearest 50-point step to lock the **ATM CE and PE** symbols.

## 3. Technical Indicators (3-Min Candles)
1.  **Choppiness Index (14 period):** To identify sideways movement.
2.  **ADX (14 period):** To identify low trend strength.
3.  **RSI (3 period):** Applied to the Close price for momentum surge detection.
4.  **VWAP:** Daily reset (used for position sizing).

## 4. Signal Generation Logic (The "Four-Gate" Entry)

### Gate 1: Multi-Factor Consolidation Filter
The strategy only proceeds if the market is programmatically "sideways" in the period immediately preceding the signal.
*   **Condition A (Choppiness):** $CHOP > 61.8$ (Indicates the market is efficient/sideways).
*   **Condition B (Trend Strength):** $ADX < 25$ (Indicates a lack of a directional trend).
*   *Both conditions must be true for at least 3 of the 5 candles preceding the 2BC pattern.*

### Gate 2: The Two-Candle Breakout (2BC)
Two consecutive **Strong Green** candles must form:
*   **Candle 1 (C1):** Body $\ge$ 85% of total range OR Hammer.
*   **Candle 2 (C2):** Body $\ge$ 85% of total range.
*   **Structural Confirm:** $Close_{C2} > High_{C1}$ (Price must be making higher highs).

### Gate 3: RSI Momentum Surge
*   **Momentum Shift:**
    *   $RSI_{C1} < 80$ (Market still within "normal" momentum).
    *   $RSI_{C2} > 80$ (Market enters "extreme" momentum/surge).

### Gate 4: Risk & Entry Setup
*   **Entry Price:** $High_{C2} + 1.0$.
*   **Initial SL:** $Low_{C1} - 1.0$.
*   **Initial Risk (IR):** Entry Price - Initial SL.
*   **Risk Cap:** Discard trade if $IR > 20$ points (prevents entering late on "exhaustion" spikes).

## 5. Execution & WebSocket Integration

### 5.1 Order Placement
*   **Position Sizing:** 2 Lots if C2 Close > VWAP; 1 Lot if C2 Close < VWAP.
*   **Order Type:** STOP_LIMIT (Trigger: Entry Price, Limit: Trigger + 0.5).
*   **WebSocket Activation:** Activated immediately upon placing the order.

### 5.2 Real-Time Monitoring
*   **Pending State:** Monitor WebSocket LTP. If $LTP \le Initial\_SL$ before entry is triggered, **Cancel Entry Order**.
*   **Entry Deadline:** If the entry is not triggered within the **very next candle** (3 minutes), cancel the order.

## 6. Multi-Stage Exit & Trailing SL (TSL) Logic
Exits are managed tick-by-tick via WebSocket based on **Initial Risk (IR)**.

*   **Phase 1: Initial (Under 1.5 RR)**
    *   SL remains at `Initial SL`.
*   **Phase 2: Breakeven (At 1.5 RR)**
    *   Once $LTP \ge Entry + (1.5 \times IR)$: Move SL to Entry Price (Cost).
    *   If total quantity is 1 Lot: Exit Position Full.
*   **Phase 3: Step-Trailing (Every 0.5 RR thereafter)**
    *   **At 2.0 RR:** Move SL to $Entry + (0.5 \times IR)$ AND Exit 1 Lot (if 2 lots held).
    *   **At 2.5 RR:** Move SL to $Entry + (1.0 \times IR)$.
    *   **At 3.0 RR:** Move SL to $Entry + (1.5 \times IR)$.
    *   (Continue trailing every 0.5 RR step).

## 7. Operational Management
*   **Daily SL Cap:** 3 Hard SL hits across all strategies.
*   **Time Constraints:** No new signals after 15:00 IST. Square-off at 15:15 IST.
*   **Cleanup Rule:** If a CD or HD signal occurs during a 2BC trade, the active TSL manages the position; no new overlapping entries are taken.

## 8. Data Architecture (Logging)
*   **Regime Logs:** Log the specific CHOP and ADX values that triggered the Gate 1 "Consolidation" status.
*   **Momentum Logs:** Log the RSI transition (e.g., "RSI jumped from 65 to 88").
*   **Execution Logs:** Detailed WebSocket timestamps for each 0.5 RR milestone hit.

---
**END OF FRD V1.1 (2BC Strategy)**