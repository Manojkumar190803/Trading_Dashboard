This revised **Functional Requirements Document (FRD) V1.1** for the **TC (Trend Continuation) Strategy** incorporates your specific candle-geometry and volume requirements.

### Summary of Logic Updates:
1.  **The "High-Volume Shakeout":** The Red candle must have higher volume than the preceding green candle.
2.  **The "Structure" Rule:** The Red candle must break the **High** of the previous strong green candle (indicating an attempt to continue) but must **not** break its **Low** (indicating the support of the trend is still intact).
3.  **Entry/Exit:** Based strictly on the Red Candle's boundaries.

---

# Functional Requirements Document (FRD): TC Option Strategy (V1.1)

## 1. Project Overview
The **TC Strategy** is an automated trend-following system. It identifies a "Bullish Continuation" pattern where, after a strong move, a high-volume red candle forms that tests the previous high but fails to break the previous support (low), creating a high-probability entry for the next leg up.

## 2. Instrument Selection & Initialization
*   **Base Index:** NIFTY (NSE_INDEX).
*   **Strike Selection (09:20 IST):** ATM Strike (Nearest 50 points) for CE and PE.

## 3. Technical Indicators (3-Min Candles)
1.  **EMA 13, 20, 50:** To confirm trend direction.
2.  **Volume:** Vertical volume for every 3-min candle.
3.  **VWAP:** Daily reset.

## 4. Signal Generation Logic (The "Four-Gate" Entry)

### Gate 1: Trend Context
*   **EMA Alignment:** (EMA 13 > EMA 20) AND (EMA 20 > EMA 50).
*   **LTP Position:** The current candle must be trading above EMA 13.

### Gate 2: Momentum (The "Green Run")
*   There must be at least **two consecutive Strong Green candles** immediately preceding the signal candle.
*   **Strong Green Definition:** Body $\ge$ 80% of total range OR Hammer (Lower wick $\ge$ 2 $\times$ Body).
*   The most recent green candle is referred to as the **"Previous Green Strong" (PGS)** candle.

### Gate 3: The Signal Candle (Red Pullback)
The candle immediately following the PGS must be **Red (Close < Open)** and meet these three criteria:
1.  **Volume Spike:** $Volume_{Red} > Volume_{PGS}$ (Increasing volume on the pullback).
2.  **High Break:** $High_{Red} > High_{PGS}$ (Must breach the previous high).
3.  **Low Support:** $Low_{Red} \ge Low_{PGS}$ (Must **not** break the low of the PGS).

### Gate 4: Risk & Entry Setup
*   **Entry Price:** $High_{Red} + 1.0$.
*   **Initial SL:** $Low_{Red} - 1.0$.
*   **Initial Risk (IR):** Entry Price - Initial SL.
*   **Risk Cap:** Discard trade if $IR > 20$ points.

## 5. Execution & WebSocket Integration

### 5.1 Order Placement
*   **Position Sizing:** 2 Lots if Close > VWAP; 1 Lot if Close < VWAP.
*   **Order Type:** STOP_LIMIT (Trigger: Entry Price, Limit: Trigger + 0.5).
*   **WebSocket Activation:** Activated immediately upon placing the order.

### 5.2 Monitoring
*   **Pending State:** If $LTP \le Initial\_SL$ before entry is triggered, cancel order.
*   **Entry Deadline:** If the entry is not triggered within **3 candles** (9 minutes) of the Red Candle close, cancel the order.

## 6. Multi-Stage Exit & Trailing SL (TSL) Logic
Managed tick-by-tick via WebSocket based on **Initial Risk (IR)**.

*   **Phase 1: Initial (Under 1.5 RR)**
    *   SL remains at `Initial SL`.
*   **Phase 2: Breakeven (At 1.5 RR)**
    *   Once $LTP \ge Entry + (1.5 \times IR)$: Move SL to Entry Price.
    *   If total quantity is 1 Lot: Exit Full.
*   **Phase 3: Step-Trailing (Every 0.5 RR thereafter)**
    *   **At 2.0 RR:** Move SL to $Entry + (0.5 \times IR)$ AND Exit 1 Lot (if 2 lots held).
    *   **At 2.5 RR:** Move SL to $Entry + (1.0 \times IR)$.
    *   **At 3.0 RR:** Move SL to $Entry + (1.5 \times IR)$.
    *   (Continue trailing every 0.5 RR).

## 7. Operational Management
*   **Daily SL Cap:** 3 Hard SL hits across all strategies.
*   **Time Constraints:**
    *   No new signals after **15:00 IST**.
    *   Square-off at **15:15 IST**.

## 8. Data Architecture (Logging)
*   **Candle Comparison:** Log $(High_{Red} \text{ vs } High_{PGS})$ and $(Low_{Red} \text{ vs } Low_{PGS})$.
*   **Volume Log:** Log $Volume_{Red}$ and $Volume_{PGS}$ to verify the "Increasing Volume" rule.
*   **Slippage Log:** Track difference between Milestone triggers and actual fills.

---
**END OF FRD V1.1 (TC Strategy)**