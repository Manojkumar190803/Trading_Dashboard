# Functional Requirements Document: 21 EMA Strategy

## 1. Document Control

| Field | Value |
|---|---|
| Document status | Buy-first implementation specification |
| Version | 1.0 |
| Strategy name | 21 EMA Strategy |
| Market timezone | Asia/Kolkata (IST) |
| Signal timeframe | 3-minute candles |
| Signal instrument | Nifty ATM CE and ATM PE option premiums |
| Execution instrument | Nifty ATM CE and ATM PE options for the current weekly expiry; next weekly expiry when today is expiry day |
| Initial implementation scope | Buy setup |
| Deferred scope | Sell setup is documented in Section 11 but is not part of the first implementation |
| Maximum filled trades | 3 per trading day, with trading also locked after 3 stop-loss exits |
| Default position size | 1 lot = 65 quantity |

This document is the behavioral contract for backtesting, paper trading, and
live trading. Any behavior not defined here must be made configurable and
recorded before release.

## 2. Executive Summary

The strategy calculates a separate 21-period Exponential Moving Average (EMA)
from the close of each completed 3-minute ATM CE and ATM PE option candle. A
buy setup begins independently for each option when its price crosses from
below the EMA and a candle closes above it. That first candle is the setup
candle. Its low, less a 1-point protective buffer, defines the initial
stop-loss.

The next three completed candles are confirmation candles. Every one must close
above the 21 EMA, and at least one must be red (`close < open`). The pending
entry order is placed immediately after the first red confirmation candle
closes, at 1 point above that candle's high. If a later confirmation candle
closes at or below the EMA, any pending order is cancelled and any already-filled
position is exited. The setup is discarded when the resulting initial risk
exceeds 25 option-premium points.

After entry, the position remains open through the first 1R milestone. At 1R,
the stop moves to entry price. Thereafter, the stop advances by 0.5R for every
additional 0.5R milestone. The position exits when its stop is hit, when a
3-minute option candle closes below its EMA, or at the mandatory 15:10 IST
square-off. Stop, milestone, and trailing triggers use live option-premium
ticks.

## 3. Scope and Assumptions

1. All timestamps are interpreted in IST. Candle timestamps represent the
   candle close time used by the strategy.
2. EMA-21 is calculated independently from the closing prices of the ATM CE and
   ATM PE option contracts.
3. A buy cross for either option requires its previous completed candle close to
   be at or below its EMA-21 and its setup candle close to be strictly above its
   EMA-21.
4. The setup candle is excluded from the three-candle confirmation window.
5. “Red candle” means `close < open`. Doji candles are not red candles.
6. The first red candle in the confirmation window is the entry-reference
   candle. If more than one red candle forms, later red candles do not replace
   the first valid reference.
7. A candle that closes exactly on the EMA fails the above-EMA requirement.
8. The 1-point buffer is applied in the adverse direction: entry is red-candle
   high plus 1 point, and the initial stop is setup-candle low minus 1 point.
9. Prices are rounded to the execution instrument's valid tick size before an
   order is submitted. The rounded entry trigger and rounded initial stop are
   also used to calculate and validate initial risk.
10. The strategy shall use both ATM CE and ATM PE contracts for the current
   weekly expiry. If the trading day is the expiry day, it shall use the next
   available weekly expiry. The selected expiry shall be locked and recorded
   for the session.
11. A filled entry consumes one daily trade allowance. A cancelled or rejected
    pending entry does not consume an allowance.

## 4. Configuration Parameters

| Parameter | Default | Requirement |
|---|---:|---|
| `timeframe_minutes` | 3 | Signal candle interval |
| `ema_period` | 21 | EMA period, calculated on close |
| `atm_lock_time` | 09:20 IST | Time when the ATM strike and CE/PE contracts are calculated and locked |
| `expiry_policy` | Current weekly | Use current weekly expiry; use the immediately following weekly expiry when today is expiry day |
| `entry_start` | 09:20 IST | Earliest time the strategy may scan for a new setup or trigger an entry |
| `entry_cutoff` | 14:45 IST | No new entry may be accepted at or after this time |
| `force_square_off` | 15:10 IST | Mandatory exit time for every open position |
| `entry_buffer_points` | 1.0 | Added above the red candle high for buys |
| `stop_buffer_points` | 1.0 | Subtracted below the setup candle low for buys |
| `entry_limit_buffer_points` | 0.5 | Added to the stop-limit trigger to calculate the limit price |
| `max_initial_risk_points` | 25.0 | Discard setup when initial risk is greater than this value |
| `breakeven_rr` | 1.0 | Move stop to cost at 1R |
| `trail_step_rr` | 0.5 | Advance stop at each additional 0.5R |
| `max_trades_per_day` | 3 | Maximum filled entries per trading day |
| `lots` | 1 | Initial lot count |
| `option_lot_size` | 65 | Quantity per Nifty lot |
| `quantity` | 65 | `lots * option_lot_size` per filled CE or PE entry |

## 5. Functional Requirements

### 5.1 Session and Data Initialization

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The system shall create one strategy session per Nifty trading day and reset the filled-trade counter at session start. | Must |
| FR-02 | The system shall use completed 3-minute candles and shall not evaluate a partially formed candle as a signal candle. | Must |
| FR-03 | The system shall calculate EMA-21 from candle closes in chronological order. | Must |
| FR-04 | The system shall block new entries when the signal data is missing, malformed, stale, or not sufficiently initialized to calculate EMA-21. | Must |
| FR-05 | At `atm_lock_time` (09:20 IST), the system shall calculate and lock the Nifty ATM strike and resolve the ATM CE and ATM PE contracts for the current weekly expiry. If today is expiry day, it shall select the immediately following tradable weekly expiry. Missing expiry or contract metadata shall prevent live order placement. | Must |

### 5.2 Buy Setup Detection

| ID | Requirement | Priority |
|---|---|---|
| FR-06 | A buy setup shall begin only when the previous candle close is at or below the previous EMA-21 and the current candle close is strictly above the current EMA-21. | Must |
| FR-07 | The current candle shall be recorded as the setup candle, including open, high, low, close, EMA-21, and timestamp. | Must |
| FR-08 | The initial stop level shall be `setup_candle_low - 1.0`. | Must |
| FR-09 | The system shall evaluate only the next three completed candles after the setup candle as the confirmation window. | Must |
| FR-10 | Each confirmation candle shall close strictly above its EMA-21. A close at or below EMA-21 shall cancel the setup immediately. | Must |
| FR-11 | At least one confirmation candle shall be red (`close < open`). | Must |
| FR-12 | The first red confirmation candle shall define the entry trigger as `red_candle_high + 1.0`, and the system shall place the pending entry immediately after that candle closes. | Must |
| FR-13 | The setup shall be cancelled if no red candle occurs in the three-candle window. | Must |
| FR-14 | The system shall cancel the pending entry if it is not filled by the end of the three-candle confirmation window. | Must |
| FR-15 | The system shall discard the setup when `entry_trigger - initial_stop > 25.0` option-premium points. | Must |
| FR-16 | A setup shall be cancelled when its entry window or trigger time reaches 14:45 IST without a filled entry. | Must |

### 5.3 Entry Execution

| ID | Requirement | Priority |
|---|---|---|
| FR-17 | The system shall scan for new 21 EMA setups and accept new entries only from 09:20:00 IST through 14:44:59 IST. | Must |
| FR-18 | The system shall submit a BUY stop-limit order for the relevant ATM CE or ATM PE option, triggered at `red_candle_high + 1.0`, using `lots * 65` quantity by default. | Must |
| FR-19 | The stop-limit order's limit price shall be the trigger price plus a configurable positive limit buffer. The default limit buffer shall be `0.5` option-premium points. | Must |
| FR-20 | The system shall use the broker-confirmed average option-premium fill price as the actual entry price for all risk and reward calculations. | Must |
| FR-21 | The system shall calculate `R = actual_entry_price - initial_stop`. A non-positive R shall invalidate the trade and trigger protective cleanup. | Must |
| FR-22 | The system shall reserve and increment the daily trade count only for a broker-confirmed filled entry. | Must |
| FR-23 | The system shall permit no more than three filled entries per trading day, including entries that later exit during the same day. | Must |
| FR-24 | Only one position may be active globally at a time. If CE is active, any PE signal or pending entry shall be rejected or cancelled; if PE is active, any CE signal or pending entry shall be rejected or cancelled. A new setup may be considered after the prior position is confirmed closed, subject to the daily limit. | Must |
| FR-25 | The system shall cancel an unfilled pending entry when its setup is invalidated, its confirmation window expires, its entry cutoff is reached, or the opposite side has an active position. | Must |

### 5.4 Initial Risk and Stop Management

| ID | Requirement | Priority |
|---|---|---|
| FR-26 | Immediately after entry confirmation, the system shall place or maintain the initial stop at the already-calculated tick-rounded `initial_stop` (`setup_candle_low - 1.0`). The 1-point stop buffer shall be applied exactly once. | Must |
| FR-27 | At 1R, where a live option-premium tick reaches `entry + R`, the system shall move the stop to the actual entry price, creating a loss-free trade before fees and slippage. | Must |
| FR-28 | At every additional 0.5R milestone based on live option-premium ticks, the system shall advance the stop by 0.5R. For example, at 1.5R the stop is `entry + 0.5R`; at 2R it is `entry + 1R`; at 2.5R it is `entry + 1.5R`. | Must |
| FR-29 | The stop shall never move backward. Repeated observations of the same milestone shall be idempotent. | Must |
| FR-30 | The position shall be exited when the active stop is hit. | Must |
| FR-31 | An already-filled position shall be exited when its completed 3-minute option-premium candle closes strictly below its EMA-21. | Must |
| FR-32 | Stop-loss, trailing-stop, and milestone conditions shall be evaluated from ticks. The EMA-close exit shall be evaluated when the completed 3-minute option candle closes. If a later confirmation candle closes at or below EMA before entry, the pending order shall be cancelled; if the entry has already filled, the position shall also be exited. If multiple tick events have the same timestamp, the engine shall process them in feed order and record that ordering. | Must |

### 5.5 Time-Based Exit and Cleanup

| ID | Requirement | Priority |
|---|---|---|
| FR-33 | At or after 15:10 IST, the system shall cancel all outstanding CE and PE strategy orders and submit an exit for every remaining position quantity. | Must |
| FR-34 | The 15:10 IST exit shall apply regardless of profit, loss, EMA position, or trailing-stop state. | Must |
| FR-35 | The system shall not submit a new entry at or after 14:45 IST, including an entry trigger observed after the cutoff. | Must |
| FR-36 | The system shall persist the final option-premium exit price, exit timestamp, exit reason, realized P&L, order IDs, and cleanup result. | Must |
| FR-37 | If a stop-limit trigger is reached but the market price exceeds the limit and no fill occurs, the system shall cancel the stop-limit order immediately and record the missed-fill reason. | Must |
| FR-38 | If a stop-limit order is partially filled, the system shall cancel the unfilled remainder, protect the filled quantity, and manage the filled position using the confirmed average fill price. | Must |
| FR-39 | If actual fill risk, calculated as `actual_entry_price - initial_stop`, is greater than 25 option-premium points, the system shall exit the filled quantity immediately and record the risk breach. | Must |
| FR-40 | The system shall lock new trading for the day after three filled trades exit at their initial or active stop-loss, regardless of the remaining filled-entry allowance. | Must |

## 6. State Machine

The strategy shall track one global session state and one setup/position state:

| State | Meaning |
|---|---|
| `WAITING` | No active setup and no active position |
| `CONFIRMING` | Setup candle completed; evaluating the next three candles |
| `ENTRY_PENDING` | Valid red candle found; entry order is waiting for trigger/fill |
| `ACTIVE` | Entry filled and position is protected by an active stop |
| `BREAKEVEN` | 1R reached; stop moved to entry |
| `TRAILING` | One or more 0.5R trailing milestones reached |
| `CLOSED` | Position exited; may return to `WAITING` if daily limit remains |
| `CANCELLED` | Setup or pending entry invalidated without a fill |
| `DAY_LOCKED` | Three filled entries recorded, three stop-loss exits recorded, or session is past the entry cutoff |
| `FORCE_EXIT` | Mandatory 15:10 cleanup is in progress |

## 7. Invalidation and Exception Handling

| Case | Required behavior |
|---|---|
| Setup candle does not close above EMA-21 | No setup is created |
| A confirmation candle closes at or below EMA-21 | Cancel the setup/pending entry |
| No red candle in three confirmations | Cancel the setup |
| More than 25 points initial risk | Discard the setup without placing an entry |
| Entry trigger is not reached in the window | Cancel the pending entry |
| Stop-limit trigger is reached but price exceeds the limit | Cancel the order immediately and record a missed fill |
| Stop-limit entry is partially filled | Cancel the remainder and protect the filled quantity |
| Entry cutoff reached with pending order | Cancel the pending order |
| Entry order rejected or cancelled | Do not increment the filled-trade count; record the broker reason |
| Stop order placement fails after fill | Attempt immediate market exit and mark the trade operationally unresolved until broker quantity is zero |
| WebSocket or live price feed unavailable | Block new entries; retain broker-side protection and use fallback order/position reconciliation for active trades |
| Process restarts with an open position | Reconcile broker position and stop orders before accepting any new setup |
| Three filled entries reached | Cancel pending entries and lock new entries for the day |
| Three trades exit at their stop-loss | Cancel pending entries and lock new entries for the day |
| Actual fill risk exceeds 25 points | Exit the filled quantity immediately and record the risk breach |
| Later confirmation candle closes at or below EMA | Cancel pending entry; exit any already-filled position |
| Exit order fails at 15:10 | Retry and alert until the broker confirms zero remaining quantity |

## 8. Audit and Reporting Requirements

The system shall record:

- Trading date, strategy version, timezone, configuration, and execution symbol.
- Every completed candle's close, EMA-21, and signal-evaluation result.
- Setup candle OHLC, EMA-21, initial stop, confirmation candles, and cancellation reason.
- Red reference candle OHLC and calculated entry trigger.
- Initial risk in points and the reason for any 25-point risk rejection.
- Entry order request, acknowledgement, fill quantity, average fill price, and slippage.
- Every 1R and 0.5R milestone, including the resulting stop level.
- Stop modifications, EMA-close exits, force exits, order IDs, and final P&L.
- Filled-trade count and final session status: `NO_TRADE`, `CANCELLED`,
  `TRADE_CLOSED`, `DAY_LOCKED`, or `OPERATIONAL_FAILURE`.

## 9. Acceptance Test Scenarios

| ID | Scenario | Expected result |
|---|---|---|
| TC-01 | Previous close is below EMA-21 and setup candle closes above it | Buy setup begins and setup low is recorded |
| TC-02 | First confirmation candle is red and closes above EMA-21 | Entry trigger is red high + 1 point |
| TC-03 | All three confirmation candles close above EMA-21 and none is red | Setup is cancelled |
| TC-04 | A confirmation candle closes at EMA-21 | Setup is cancelled |
| TC-05 | Tick-rounded entry trigger minus tick-rounded initial stop is 25 points | Setup remains eligible |
| TC-06 | Initial risk is 25.01 points | Setup is discarded |
| TC-07 | Entry fills at 100 and initial stop is 80 | R is 20; 1R is 120 and initial stop remains 80 before milestone |
| TC-08 | Price reaches 1R | Stop moves to 100 |
| TC-09 | Price reaches 1.5R | Stop moves to 110 for the TC-07 example |
| TC-10 | A candle closes below EMA-21 while position is active | Position exits |
| TC-11 | Three filled trades have already occurred | No fourth entry is accepted |
| TC-12 | A pending trigger appears at 14:45 | It is rejected and no entry is placed |
| TC-13 | Position remains active at 15:10 | All remaining quantity is force-exited |
| TC-14 | Trading day is the current weekly expiry day | Next available weekly expiry is selected for both ATM options |
| TC-15 | First red candle closes with high 100 | BUY stop-limit trigger is 101 and default limit price is 101.5 |
| TC-16 | CE position is active and a PE signal is generated | PE signal/order is rejected and CE remains the only active position |
| TC-17 | PE position is active and a CE signal is generated | CE signal/order is rejected and PE remains the only active position |
| TC-18 | Stop-limit trigger is reached but price exceeds the limit | Order is cancelled immediately with a missed-fill result |
| TC-19 | Stop-limit order is partially filled | Remainder is cancelled and the filled quantity receives protection |
| TC-20 | Actual fill risk is greater than 25 points | Filled quantity is exited immediately |
| TC-21 | Later confirmation candle closes at or below EMA | Pending order is cancelled; any filled position is exited |
| TC-22 | Three filled trades exit at their stop-loss | All pending entries are cancelled and trading is locked for the day |

## 10. Implementation Notes

1. Backtests must define how intrabar trigger, stop, and milestone ordering is
   resolved when OHLC data alone cannot establish chronology.
2. The ATM strike, expiry, order type, and tick-size metadata remain
   configuration or broker inputs. They must not be silently changed after the
   CE and PE contracts are locked for the session.
3. “1 point” is an option-premium price-point buffer, not a percentage or tick count. The
   implementation shall round the resulting trigger and stop to the execution
   instrument's valid tick size before validating risk or submitting orders.
4. The requested 65 quantity per lot is the current Nifty lot-size assumption;
   broker metadata and configured fallback values must be reconciled before
   live orders.

## 11. Deferred Sell Setup

The sell setup is documented for future implementation and shall remain
disabled while buy behavior is validated.

The intended inverse is:

1. Price crosses from above to below EMA-21; the first candle closing below the
   EMA becomes the sell setup candle for the relevant ATM option premium.
2. The initial stop is the setup candle high plus a 1-point buffer.
3. Within the next three candles, every close must remain below EMA-21 and at
   least one candle must be green (`close > open`).
4. Entry is triggered 1 point below the first qualifying green candle's low.
5. Discard the setup when initial risk exceeds 25 points.
6. Apply the same 1R breakeven, 0.5R step-trailing, three-trade daily cap,
   entry window, EMA-close exit, and 15:10 force-exit rules in the inverse
   direction.

Sell implementation remains disabled until buy behavior is validated. Its
inverse rules use the corresponding ATM option premium, option-premium risk,
and live option-premium ticks.

**END OF FRD V1.0**