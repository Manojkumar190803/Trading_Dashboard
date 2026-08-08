This is the **Functional Requirements Document (FRD) V6.0**, specifically tailored for **Classic Divergence (CD)**. 

While Hidden Divergence (HD) is a *trend continuation* signal, Classic Divergence is a **trend reversal** signal. This FRD adjusts the mathematical "Gates" to identify when a falling option premium has bottomed and is ready for a trend reversal.

---

# Functional Requirements Document (FRD): CD Option Strategy (V6.0)

## 1. Project Overview
The CD Strategy is an automated system for Nifty weekly options that identifies **Classic Bullish RSI Divergence** (Price Reversal) on a 3-minute chart. It uses a hybrid approach: candle-based signal generation and **Tick-by-Tick WebSocket management** for high-precision exits, with all states persisted in **PostgreSQL**.

## 2. Master Guardrail: The "3-SL Rule"
*   **Daily Quota:** Maximum **3 Hard SL hits** allowed per trading session.
*   **Persistence:** The system must check the `daily_state` PostgreSQL table at 09:15 IST. If `sl_count` is already $\ge 3$ (due to a mid-day crash/restart), the system must remain idle.
*   **Action:** On the 3rd Hard SL hit, the system must immediately trigger a `KillSwitch`—closing all positions, cancelling orders, and updating the database to `HALTED`.

## 3. Instrument Selection (09:20 IST)
*   **ATM Locking:** Round Nifty Spot LTP to the nearest 50 points at **09:20:00**.
*   **Symbols:** Lock the ATM CE and PE for the current weekly expiry.
*   **Persistence:** Write the locked symbols to `daily_state`. All logic from 09:20 to 15:00 applies only to these two symbols.

## 4. Signal Generation (The "CD Reversal" Gates)

### Gate 1: Classic Bullish Divergence (Reversal)
*   **Point Identification:** P1 (Older) and P2 (Recent) must be **Fractal Lows** (5-candle structure).
*   **Lookback:** P1 must be found within 3 to 20 candles of P2.
*   **Price Rule:** $Low_{P2} < Low_{P1}$ (Price is making a **Lower Low**).
*   **RSI Rule:** $RSI_{P2} > RSI_{P1}$ (RSI is making a **Higher Low**).
*   **Threshold:** $RSI_{P1}$ must have been **< 20** (extreme oversold), and $RSI_{P2}$ must be **< 35**.

### Gate 2: Trend Reversal Filter
Since CD is a reversal strategy, we look for the *start* of bullish momentum:
*   **Condition:** $(\text{LTP} > \text{EMA 13})$ AND $(\text{EMA 13} \ge \text{EMA 20})$.

### Gate 3: Trigger Candle
*   **Strong Green:** Body $\ge$ 85% of total range.
*   **Hammer:** Lower Wick $\ge 2\times$ Body; Body in the upper 33% of the range.

### Gate 4: Risk Filter
*   **Stop Loss (SL):** $\text{Lowest Low of the entire CD pattern (P1, P2, and Trigger)} - 1.0$.
*   **Initial Risk (IR):** $\text{Trigger High} + 1.0 - \text{SL}$.
*   **Cap:** If $IR > 20 \text{ points}$, the signal is **Discarded**.

---

## 5. Execution & WebSocket Integration
1.  **Entry Order:** Place `STOP_LIMIT` at `Trigger High + 1.0`.
2.  **WebSocket Kick-in:** Immediately upon order placement, subscribe to the tick-stream.
3.  **Active State:** Once WebSocket LTP $\ge$ Trigger, update PostgreSQL trade status to `OPEN`. 
4.  **SL Placement:** Simultaneously place the Hard SL order at the broker.

## 6. Real-Time Exit & Step-Trailing Logic
Managed tick-by-tick via WebSocket. *IR = Initial Risk.*

| Milestone | LTP Target | Action | SL Movement (TSL) |
| :--- | :--- | :--- | :--- |
| **Start** | - | - | Initial SL (Swing Low - 1.0) |
| **Target 1** | $Entry + (1.5 \times IR)$ | If 1 Lot: Exit Full. | Move SL to **Entry Price (Cost)** |
| **Target 2** | $Entry + (2.0 \times IR)$ | If 2 Lots: **Exit 1 Lot** | Move SL to $Entry + (0.5 \times IR)$ |
| **Target 3** | $Entry + (2.5 \times IR)$ | Hold remaining | Move SL to $Entry + (1.0 \times IR)$ |
| **Step-Trail** | Every $+0.5 \text{ RR}$ | Hold | Trail SL up by $0.5 \times IR$ |

---

## 7. Database Persistence (PostgreSQL)

The system must use an **asynchronous DB handler** to prevent blocking the WebSocket thread.

*   **`daily_state`:** Records `sl_count`, `realized_pnl`, and `active_symbols`.
*   **`trades`:** Records every entry/exit, `current_sl_price`, and `highest_rr_reached`.
*   **`audit_logs`:** Every internal decision (e.g., *"LTP hit 1.5RR; moving SL to BE"*).

## 8. Recovery Logic (Fault Tolerance)
If the system crashes and restarts:
1.  Fetch `active_symbols` and `sl_count` from `daily_state`.
2.  Check `trades` for any row where `status = 'OPEN'`.
3.  If a trade is open:
    *   Subscribe to WebSocket for that symbol.
    *   Calculate current RR milestone based on `highest_rr_reached` in the DB.
    *   Resume Trailing SL logic immediately.

## 9. Operational Constraints
*   **Signal Cutoff:** 15:00 IST.
*   **EOD Square-off:** 15:15 IST (Market order for all).
*   **Clean-up:** If a `STOP_LIMIT` isn't filled by the next candle close, cancel it and update DB to `CANCELLED`.

---
**END OF FRD V6.0 (Classic Divergence)**