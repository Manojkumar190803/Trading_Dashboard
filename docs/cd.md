This Functional Requirements Document (FRD) for the **CD (Classic Divergence) Strategy** is modeled after your HD Strategy V3.0. 

While the HD (Hidden Divergence) strategy focuses on trend continuation, the **CD (Classic Divergence)** strategy focuses on **reversals**—identifying when price momentum is fading despite making new price extremes.

---

# Functional Requirements Document (FRD): CD Option Strategy (V1.0)

### 1. Project Overview
The CD Strategy is an automated reversal system for Nifty weekly options. It identifies "Classic Bullish Divergence" on a 3-minute timeframe and uses a high-frequency WebSocket engine to manage a multi-stage trailing stop loss.

### 2. Instrument Selection & Initialization
*   **Base Index:** NIFTY (NSE_INDEX).
*   **Strike Selection (09:20 IST):**
    *   Fetch Nifty Spot LTP at 09:20:00.
    *   Round to nearest 50-point step to find ATM Strike.
    *   Lock the corresponding **CE and PE** symbols for the current weekly expiry.

### 3. Technical Indicators (3-Min Candles)
1.  **EMA 13, 20, 50.**
2.  **RSI (3 period):** Applied to Close price (Standard for Classic Divergence).
3.  **VWAP:** Daily reset.

### 4. Signal Generation Logic (The "Four-Gate" Entry)
*   **Gate 1 (Classic Bullish Divergence):** Fractal Lows P1 and P2.
    *   **Price:** $Low_{P2} < Low_{P1}$ (Price makes a Lower Low).
    *   **RSI:** $RSI_{P2} > RSI_{P1}$ (RSI makes a Higher Low).
    *   **Zone:** At least one RSI point ($P1$ or $P2$) must be $< 30$ (Oversold).
    *   **Window:** $P2$ must occur within 15 candles of $P1$.
*   **Gate 2 (Trend Filter):** 
    *   Price must be within 0.20% of the **EMA 50** OR **EMA 50** must be flattening (Slope analysis). 
    *   *(Rationale: Reversals work best when the existing trend is exhausted near a major EMA).*
*   **Gate 3 (Trigger):** 
    *   Current candle must be **Strong Green** (Body $\ge$ 80%) OR **Bullish Engulfing** OR **Hammer**.
*   **Gate 4 (Risk):**
    *   $\text{Initial SL} = \text{Lowest Low of (P2 and Trigger Candle)} - 1.0$.
    *   $\text{Entry Price} = \text{Trigger Candle High} + 1.0$.
    *   Discard if $(\text{Entry} - \text{SL}) > 20$ points.

### 5. Execution & WebSocket Integration
#### 5.1 Order Placement
*   **Position Sizing:** 
    *   2 Lots if $Close > VWAP$.
    *   1 Lot if $Close < VWAP$.
*   **Order Type:** STOP_LIMIT (Trigger: High + 1.0, Limit: Trigger + 0.5).
*   **WebSocket Activation:** Upon order placement, subscribe to the **Tick-by-Tick** feed for the option symbol.

#### 5.2 Real-Time Monitoring
*   **Pending State:** Monitor WebSocket LTP. If $LTP \le \text{Initial SL}$ before entry is triggered, **Cancel Entry Order**.
*   **Executed State:** Once filled, immediately place a **Hard Stop Loss** order at the broker.

### 6. Multi-Stage Exit & Trailing SL (TSL) Logic
Exits are managed tick-by-tick via WebSocket based on **Initial Risk (IR)**.
$IR = \text{Entry Price} - \text{Initial SL}$

*   **Phase 1: Initial (Under 1.5 RR)**
    *   SL remains at $Initial SL$.
*   **Phase 2: Breakeven (At 1.5 RR)**
    *   Once $LTP \ge Entry + (1.5 \times IR)$:
    *   **Action:** Move SL to Entry Price (Cost).
    *   If total quantity is 1 Lot: Exit Full.
*   **Phase 3: Step-Trailing (Every 0.5 RR thereafter)**
    *   **At 2.0 RR:** Move SL to $Entry + (0.5 \times IR)$.
    *   **At 2.0 RR (Partial):** If 2 Lots, Exit 1 Lot (50%) at Market.
    *   **At 2.5 RR:** Move SL to $Entry + (1.0 \times IR)$.
    *   **At 3.0 RR:** Move SL to $Entry + (1.5 \times IR)$.
    *   Continue trailing the remaining 1 lot every 0.5 RR step.

### 7. Risk & Operational Management
*   **Daily SL Cap:** System stops after **2 Hard SL hits** (CD strategies have lower win rates than HD, so the cap is tighter).
*   **Time Constraints:**
    *   No new signals after 14:45 IST (Reversals late in the day are often "bull traps").
    *   Mandatory square-off at 15:15 IST.
*   **Conflict Rule:** If an HD signal and a CD signal occur simultaneously on the same symbol, the **HD signal takes priority**.

### 8. Data Architecture
#### 8.1 Trade States
1.  **SCANNING:** Looking for $P1$ and $P2$ (Lower Low in Price, Higher Low in RSI).
2.  **TRIGGERED:** Gate 1, 2, and 3 met; Order placed.
3.  **MONITORING:** WebSocket active, tracking IR milestones.
4.  **CLOSED:** Trade exited via TSL or Manual Square-off.

#### 8.2 Logging Requirements
*   **Divergence Coordinates:** Log Price and RSI values for both $P1$ and $P2$.
*   **IR Calculation:** Clear log of the mathematical IR value used for the TSL steps.
*   **Slippage Log:** Difference between the 1.5 RR Target Price and the actual Execution Price.

---

### Key Differences from your HD Strategy:
1.  **Divergence Direction:** CD looks for **Price Lower Low** vs **RSI Higher Low** (Reversal), whereas HD looks for **Price Higher Low** vs **RSI Lower Low** (Continuation).
2.  **RSI Period:** Changed to **14** for CD (Standard) vs **3** for HD (Aggressive).
3.  **Lookback Window:** CD requires a window (usually 15 candles) because reversal patterns lose validity if the "divergence" takes too long to form.
4.  **Daily Cap:** Reduced to **2 Hard SLs** to preserve capital during strong trending days where reversals fail repeatedly.