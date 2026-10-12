# Phase 6: Backend API + Manual Stop-Loss Overrides

## Overview

This phase adds three critical features to enable flexible instrument configuration with backend support:

1. **Flask API Server** - Backend service for broker symbol search
2. **Searchable Autocomplete** - Type to find broker symbols from OpenAlgo
3. **Manual Stop-Loss Overrides** - Override auto-calculated trailing mechanism values
4. **Improved Lot Display** - Shows "1 × 65" format instead of "1 units"

## Architecture

### Deployment Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    React Dashboard (Port 3000)              │
│  - Vite dev server with /api proxy → localhost:4000         │
│  - TypeScript form with searchable autocomplete             │
│  - Manual override fields for SL/TSL configuration          │
└─────────────────────────────────────────────────────────────┘
                            ↓ (Fetch requests)
┌─────────────────────────────────────────────────────────────┐
│                  Flask API Server (Port 4000)               │
│  - /api/symbols/search?q=NIFTY → Symbol autocomplete        │
│  - /api/logs/*.json → Dashboard data & configuration        │
│  - OpenAlgo integration for live symbol lookup              │
└─────────────────────────────────────────────────────────────┘
                            ↓ (OpenAlgo SDK)
┌─────────────────────────────────────────────────────────────┐
│              OpenAlgo Broker API (External)                 │
│  - quotes() → Get symbol prices & validate existence        │
│  - positionbook() → Active positions                        │
│  - orderbook() → Order status                              │
└─────────────────────────────────────────────────────────────┘
```

## Running the System

### Step 1: Start Flask API Server

```bash
# From project root
./start_api_server.sh

# OR manually:
python api_server.py
```

Expected output:
```
🚀 Starting OpenAlgo API Server on port 4000...
WARNING in app.run(): This is a development server. Do not use it in production.
Running on http://0.0.0.0:4000
```

### Step 2: Start Docker Containers (React + Strategy Worker)

```bash
docker-compose up -d
```

Or with fresh build:
```bash
docker-compose build react_dashboard strategy_worker --no-cache
docker-compose up -d react_dashboard strategy_worker
```

### Step 3: Access React Dashboard

Open browser: `http://localhost:3000`

Navigate to: **Instruments** page

## Form Features

### 1. Searchable Broker Symbol (NEW)

**Field**: "Broker Symbol * (Searchable)"

```
┌─ NIFTY25DEC26000CE
├─ NIFTY25DEC26000PE
├─ NIFTY25DEC26050CE
└─ ...
```

**How it works**:
- Type 2+ characters to trigger search
- Queries Flask `/api/symbols/search?q=YOUR_QUERY`
- Debounced (300ms) to avoid excessive API calls
- Click a suggestion to auto-fill the field
- Symbol must exist in OpenAlgo

**Example**:
```
User types: "NI"
Search hits: /api/symbols/search?q=NI
Suggestions show: ["NIFTY25DEC26000CE", "NIFTY25DEC26000PE", ...]
```

### 2. Lot Size Display Format (IMPROVED)

**Before**: "1 units"  
**After**: "1 × 65"

**Formula Display**:
```
Calculated Trade Quantity: 1 × 65
1 × 65 = 65 contracts
```

Where:
- First number = `lotSizeAdjustment` (user input, default 1)
- Second number = `calculateLotSize()` (from LOT_SIZE_MAP: NIFTY=65, BANKNIFTY=30, SENSEX=20)
- Result = total contracts for this trade

### 3. Manual Stop-Loss Overrides (NEW)

**Section**: "Manual Stop-Loss Overrides (Optional)"

Located below Premium Price fields, before Calculated Trade Quantity

#### 3a. Initial SL Override (points)

```
Field: initialSLOverride
Type:  Number (0 to unlimited)
Step:  1 point
Default: Empty (use auto-calculated from setup_candle_low)
```

**Example**: Enter `45` to override initial stop at 45 points below entry

**When used**:
- If filled: Strategy uses this SL instead of setup_candle_low
- If empty: Strategy auto-calculates from setup_candle_low

#### 3b. Breakeven RR Override

```
Field: breakevenRROverride
Type:  Number (0.1 to 5)
Step:  0.1 Risk Ratio unit
Default: Empty (use 1.0 from 21EMA spec)
```

**Example**: Enter `1.5` to move stop to breakeven at 1.5R instead of 1.0R

**21EMA Specification** (from docs/21EMA.md):
- FR-27: At 1R milestone → stop moves to entry (breakeven)
- Override to 1.5R → stop moves to breakeven at 1.5R instead
- Override to 0.8R → stop moves to breakeven earlier (0.8R)

**Risk Ratio (RR)**: `R = entry_price - initial_stop`

#### 3c. Trailing Step RR Override

```
Field: trailingStepRROverride
Type:  Number (0.05 to 2)
Step:  0.05 RR unit
Default: Empty (use trailingStepRR field above)
```

**Example**: Enter `1.0` to trail in 1.0R steps instead of default 0.5R

**21EMA Specification** (from docs/21EMA.md):
- FR-28: At each 0.5R → advance stop by 0.5R (milestones: 1.5R, 2.0R, 2.5R)
- Override to 1.0R → milestones become: 2.0R, 3.0R, 4.0R
- More aggressive (larger steps) = higher trailing distance

**Milestones Example** (trailingStepRR=0.5, R=50 points, entry=1000):
```
Entry: 1000, Initial SL: 950 (R=50)
  
At 1.0R (1050):  SL moves to 1000 (entry/breakeven)
At 1.5R (1075):  SL moves to 1025 (+0.5R steps start)
At 2.0R (1100):  SL moves to 1050 (+0.5R)
At 2.5R (1125):  SL moves to 1075 (+0.5R)
```

## Integration with Strategy Engine

### Current Status
✅ Form fields are defined and saved to Zustand store  
✅ Instrument interface includes override fields  
⚠️ Strategy engine not yet using manual overrides  

### What Needs to Happen

The engine (core/engine.py) should check for these overrides:

```python
# Pseudo-code for engine integration
instrument = get_instrument_config()  # Has manual override fields

# Use manual SL if provided, else calculate from setup_candle_low
initial_sl = (
    instrument.initialSLOverride 
    if instrument.initialSLOverride is not None
    else calculate_from_setup_candle_low()
)

# Use manual breakeven RR if provided, else default 1.0
breakeven_rr = (
    instrument.breakevenRROverride 
    if instrument.breakevenRROverride is not None
    else 1.0
)

# Use manual trailing step if provided, else use form value
trailing_step = (
    instrument.trailingStepRROverride 
    if instrument.trailingStepRROverride is not None
    else instrument.trailingStepRR
)

# Apply 3-phase mechanism with manual values
# Phase 1: Initial stop = initial_sl
# Phase 2: At breakeven_rr milestone → move to breakeven
# Phase 3: At each trailing_step → advance stop
```

## Testing the Implementation

### Test Case 1: Form Saves All Fields

1. Open Instruments page
2. Fill in form:
   - Name: NIFTY
   - Broker Symbol: Type "NIF" → Select "NIFTY25DEC26000CE"
   - Monitoring Times: 09:15 to 15:30
   - Lot Size Adjustment: 2
   - Strategy: 21EMA
   - Trailing Step RR: 0.75
3. **Scroll down** to "Manual Stop-Loss Overrides"
4. Fill in:
   - Initial SL Override: 50
   - Breakeven RR Override: 1.2
   - Trailing Step RR Override: 0.75
5. Submit form
6. Verify:
   - Instrument appears in table
   - Lot display shows: "2 × 65"
   - Form resets to defaults

### Test Case 2: Searchable Symbol Autocomplete

1. On form, click "Broker Symbol" field
2. Type "BAN" (3+ characters to start search)
3. Verify suggestions dropdown appears with BANKNIFTY symbols
4. Click a suggestion (e.g., "BANKNIFTY25DEC26000CE")
5. Verify field auto-fills with full symbol

### Test Case 3: Edit Instrument with Overrides

1. Click Edit (pencil icon) on existing instrument
2. Verify all fields are pre-populated:
   - Broker symbol shows previous value
   - Manual overrides show saved values
3. Modify a value:
   - Change Initial SL Override from 50 to 60
4. Submit form
5. Verify update succeeded (table shows new values)

### Test Case 4: Optional Overrides

1. Create instrument WITHOUT filling manual override fields
2. Leave all three override fields empty
3. Submit form
4. Verify:
   - Form accepted (no validation error)
   - Instrument created successfully
   - Engine will use auto-calculated values

## API Endpoints Reference

### Symbol Search
```
GET /api/symbols/search?q=NIFTY
```

**Query Parameters**:
- `q` (string, min 2 chars): Symbol search term

**Response**:
```json
{
  "symbols": [
    "NIFTY25DEC26000CE",
    "NIFTY25DEC26000PE",
    "NIFTY25DEC26050CE"
  ],
  "query": "NIFTY",
  "count": 3
}
```

**Behavior**:
- Less than 2 characters: Returns empty list
- Found in cache: Returns cached symbols (NIFTY, BANKNIFTY, SENSEX)
- Found in OpenAlgo: Queries live API
- Not found: Returns empty list (no error)

### Dashboard Data
```
GET /api/logs/dashboard_data.json
GET /api/logs/wallet_data.json
```

**Purpose**: Serve cached JSON from logs directory

### Health Check
```
GET /api/health
```

**Response**:
```json
{
  "status": "healthy",
  "openalgo": "connected|disconnected"
}
```

## Configuration

### Environment Variables

**For Flask API**:
```bash
export OPENALGO_API_KEY="your_api_key"
export OPENALGO_HOST="http://your_broker_host:5000"
```

**For React** (Vite proxy in vite.config.ts):
```typescript
proxy: {
  '/api': {
    target: 'http://localhost:4000',  // Flask API server
    changeOrigin: true,
  }
}
```

### Lot Size Mapping

Located in: `frontend-react/src/pages/Instruments.tsx`

```typescript
const LOT_SIZE_MAP: Record<string, number> = {
  'NIFTY': 65,
  'NIFTY50': 65,
  'BANKNIFTY': 30,
  'SENSEX': 20,
}
```

Update this map if lot sizes change per instrument.

## File Changes Summary

### New Files
- `api_server.py` - Flask API server
- `start_api_server.sh` - Startup script for Flask

### Modified Files
- `requirements.txt` - Added flask, flask-cors
- `frontend-react/src/pages/Instruments.tsx` - Form with autocomplete + overrides
- `frontend-react/src/types/index.ts` - Instrument interface with new fields

### No Changes Needed (But Ready for Integration)
- `core/engine.py` - Will consume manual override values (future)
- `core/broker.py` - Already has OpenAlgo client available
- `docker-compose.yml` - Could add Flask service (optional, run separately now)

## Troubleshooting

### Symbol search returns empty?

1. Verify Flask API is running on port 4000:
   ```bash
   curl http://localhost:4000/api/health
   ```
   Should return: `{"status":"healthy","openalgo":"connected"}`

2. Check OpenAlgo connection:
   - Verify `OPENALGO_API_KEY` and `OPENALGO_HOST` environment variables
   - Test with curl:
   ```bash
   curl "http://localhost:4000/api/symbols/search?q=NIFTY"
   ```

3. Check browser console (F12) for network errors

### Form not saving manual overrides?

1. Check browser console for JavaScript errors
2. Verify TypeScript compilation succeeded (0 errors)
3. Try refreshing the page: Ctrl+R
4. Check Zustand store in Redux DevTools (if installed)

### React can't connect to Flask API?

1. Verify Flask is running: `ps aux | grep api_server`
2. Verify port 4000 is listening: `lsof -i :4000`
3. Check Vite proxy config (vite.config.ts line 59)
4. Clear React cache: `rm -rf node_modules/.vite && npm run dev`

## Next Phase: Engine Integration

After this form is working, the strategy engine needs to:

1. **Load instrument config** from Zustand store
2. **Check for manual overrides** before calculating stops
3. **Apply 3-phase mechanism** with manual values:
   - Phase 1: Initial SL (manual or auto)
   - Phase 2: Breakeven at RR milestone (manual or 1.0)
   - Phase 3: Trailing by step RR (manual or 0.5)
4. **Pass to signal provider** (strategies/21ema.py, etc.)
5. **Execute live trading** with manual flexibility

This enables traders to:
- ✅ Override conservative defaults for aggressive testing
- ✅ Use manual SL for specific market conditions
- ✅ Adjust trailing mechanism per trade
- ✅ A/B test different stop-loss strategies

---

**Status**: Form complete and ready for live market integration  
**Docker**: Both services running (rebuild completed)  
**Next**: Start Flask API server + integration with core/engine.py
