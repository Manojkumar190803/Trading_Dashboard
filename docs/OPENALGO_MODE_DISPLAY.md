# OpenAlgo Mode Display & Real-Time Sync

## Overview

The React dashboard now displays the current OpenAlgo mode (**LIVE** or **ANALYZER**) with real-time synchronization. When you change the mode in OpenAlgo, the React dashboard automatically reflects the change within 1 second.

**Key Features:**
- 🔴 **LIVE Mode Badge** - Displayed prominently in red when trading live
- 🔵 **ANALYZER Mode Badge** - Displayed in blue for paper trading/analysis
- ⚡ **Real-Time Updates** - Mode changes detected every 1 second
- 🎯 **Visual Indicator** - Pulsing radio icon shows active monitoring
- 📊 **Integrated Display** - Located in dashboard header alongside engine status

## Mode Definitions

### LIVE Mode (🔴 Red)
- Real money is at stake
- Actual trades are being executed
- All orders go to the broker
- **Risk Level:** HIGH
- **Environment Variable:** `OPENALGO_MODE=live` or `STRATEGY_MODE=live`

### ANALYZER Mode (🔵 Blue)
- Paper trading / simulation
- Orders are not executed
- Used for backtesting and analysis
- **Risk Level:** LOW / SAFE
- **Environment Variable:** `OPENALGO_MODE=analyzer` or `STRATEGY_MODE=paper|backtest|smoke`

## Dashboard Display

The mode indicator appears in the dashboard header:

```
┌─────────────────────────────────────────────────────────────────┐
│  Trading Dashboard                                              │
│  Live overview of your trading account and market positions     │
│                                                                 │
│  [🎙️ OpenAlgo: LIVE]  [✅ Engine: Ready]                       │
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- `LIVE` badge shows in red with pulsing radio icon
- `ANALYZER` badge shows in blue with pulsing radio icon
- Updates every 1 second automatically
- No page refresh needed

## How to Change Mode

### Method 1: Using the Management Script (Recommended)

```bash
# Check current mode
python3 set_openalgo_mode.py --get

# Switch to LIVE mode
python3 set_openalgo_mode.py --set live

# Switch to ANALYZER mode
python3 set_openalgo_mode.py --set analyzer
```

### Method 2: Direct .env Configuration

Edit `.env` file:
```env
OPENALGO_MODE=live      # Switch to live mode
OPENALGO_MODE=analyzer  # Switch to analyzer mode
```

Restart containers for full effect:
```bash
docker-compose restart react_dashboard
```

### Method 3: Environment Variable

Set before running:
```bash
export OPENALGO_MODE=live
python3 run_strategy.py --mode live --strategy st
```

## Mode Detection Logic

The system automatically detects mode in this priority order:

1. **OPENALGO_MODE env variable** (highest priority)
   - `OPENALGO_MODE=live` → LIVE mode
   - `OPENALGO_MODE=analyzer` → ANALYZER mode

2. **STRATEGY_MODE env variable**
   - `STRATEGY_MODE=live` → LIVE mode
   - `STRATEGY_MODE=paper|backtest|smoke` → ANALYZER mode

3. **Account State**
   - Has active positions → LIVE mode (inferred)
   - Otherwise → ANALYZER mode

4. **Default** → ANALYZER mode (safe default)

## Real-Time Synchronization

### How It Works

```
OpenAlgo Backend (.env)
         ↓
   Mode Detection Service
         ↓
   Dashboard JSON API
         ↓
   React Frontend (Polls every 1s)
         ↓
   Display Update (instant)
```

### Update Frequency

- **Python Backend:** Detects mode on every data fetch
- **React Frontend:** Polls dashboard data every 1 second
- **Display Update:** Instant upon detection

### Network Flow

```
1. React fetches: GET /logs/dashboard_data.json
2. JSON contains:
   {
     "timestamp": "2024-01-15T10:30:45.123",
     "mode": "live",  // or "analyzer"
     "account": {...},
     "positions": [...],
     "orders": [...]
   }
3. Component renders mode badge
4. Repeats every 1 second
```

## API Changes

### Python Backend (dashboard_data.py)

**New Methods:**
- `_detect_mode()` → Returns current mode ("live" or "analyzer")

**Updated Response:**
```python
{
    "timestamp": "2024-01-15T10:30:45.123",
    "mode": "live",  # NEW FIELD
    "account": {...},
    "positions": [...],
    "orders": [...]
}
```

### React Frontend (Dashboard.tsx)

**New State Variables:**
```typescript
const [openalgoMode, setOpenalgoMode] = useState<'live' | 'analyzer'>('analyzer')
```

**New UI Component:**
```jsx
<div className={clsx(
  'flex items-center gap-3 px-4 py-3 rounded-lg border-2 font-semibold',
  openalgoMode === 'live'
    ? 'bg-accent-red/10 border-accent-red text-accent-red'
    : 'bg-accent-blue/10 border-accent-blue text-accent-blue'
)}>
  <Radio size={16} className="animate-pulse" />
  <span>OpenAlgo: <strong>{openalgoMode}</strong></span>
</div>
```

### Type Definition (types/index.ts)

```typescript
export interface DashboardMetrics {
  // ... existing fields ...
  openalgo_mode?: 'live' | 'analyzer'
}
```

## Testing

### Test 1: Verify Current Mode Display

```bash
# Check current mode in terminal
python3 set_openalgo_mode.py --get

# Expected output:
# ✅ Current Mode: ANALYZER
# 📊 Status: ANALYZER MODE (Paper trading / Analysis)

# Visit dashboard: http://localhost:3000
# Should show blue "OpenAlgo: ANALYZER" badge
```

### Test 2: Switch Mode and Verify Update

```bash
# Terminal 1: Monitor mode changes
watch -n 1 'python3 set_openalgo_mode.py --get'

# Terminal 2: Change mode
python3 set_openalgo_mode.py --set live

# Expected:
# - .env file updated with OPENALGO_MODE=live
# - Terminal 1 shows mode change within 1 second
# - Dashboard badge changes to red "OpenAlgo: LIVE" within 1 second
```

### Test 3: Verify JSON API Response

```bash
# Check dashboard data includes mode
curl -s http://localhost:3000/logs/dashboard_data.json | jq '.mode'

# Expected output:
# "analyzer"
# or
# "live"
```

### Test 4: Verify Real-Time Updates

1. Open React Dashboard: http://localhost:3000
2. Open browser DevTools (F12)
3. Go to Network tab
4. Filter for "dashboard_data.json"
5. Run: `python3 set_openalgo_mode.py --set live`
6. Watch network requests show mode change
7. Badge updates instantly (no page refresh)

## Troubleshooting

### Mode Not Updating in Dashboard

**Check 1:** Verify backend is serving mode
```bash
curl -s http://localhost:3000/logs/dashboard_data.json | jq '.mode'
```

**Check 2:** Verify React dashboard is accessing correct endpoint
- Open browser DevTools (F12)
- Go to Network tab
- Look for `dashboard_data.json` requests
- Verify response includes `"mode": "..."` field

**Check 3:** Restart containers
```bash
docker-compose restart react_dashboard
```

### .env Changes Not Recognized

Make sure you:
1. Edit `.env` file in the project root
2. Restart containers: `docker-compose restart react_dashboard`
3. Wait 3-5 seconds for container to start
4. Refresh browser

### Environment Variable Not Working

```bash
# Verify env var is set
echo $OPENALGO_MODE

# Try setting explicitly
export OPENALGO_MODE=live
python3 run_strategy.py ...
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│        OPENALGO CONFIG                              │
│  .env or Environment Variable                       │
│  OPENALGO_MODE=live|analyzer                        │
└────────────────┬──────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────┐
│      PYTHON BACKEND (core/dashboard_data.py)        │
│  DashboardDataProvider._detect_mode()               │
│  - Reads OPENALGO_MODE                              │
│  - Reads STRATEGY_MODE                              │
│  - Infers from account state                        │
│  - Returns 'live' or 'analyzer'                     │
└────────────────┬──────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────┐
│   JSON API (logs/dashboard_data.json)               │
│  {                                                   │
│    "mode": "live",                                  │
│    "timestamp": "...",                              │
│    "account": {...},                                │
│    "positions": [...]                               │
│  }                                                   │
└────────────────┬──────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────┐
│     REACT DASHBOARD (src/pages/Dashboard.tsx)       │
│  useRealAccountData() polls JSON every 1s           │
│  Sets openalgoMode state                           │
│  Renders mode badge with color & icon              │
│                                                     │
│  [🎙️ OpenAlgo: LIVE]  (updates in real-time)       │
└─────────────────────────────────────────────────────┘
```

## Performance Impact

- **Backend:** Negligible - mode detection is ~1ms
- **Frontend:** Minimal - adds single state variable
- **Network:** Already polling dashboard data (no extra requests)
- **UI Rendering:** Instant (React hooks handle updates)

## Files Modified

1. **core/dashboard_data.py**
   - Added `_detect_mode()` method
   - Updated `get_account_summary()` to include mode
   - Updated `_mock_account_summary()` to include mode

2. **frontend-react/src/pages/Dashboard.tsx**
   - Added Radio icon import
   - Added `openalgoMode` state
   - Added mode detection useEffect
   - Added mode badge UI component
   - Updated sync status message

3. **frontend-react/src/types/index.ts**
   - Added `openalgo_mode` field to DashboardMetrics

4. **set_openalgo_mode.py** (NEW)
   - Utility script to change mode
   - Reads/writes .env file
   - Displays current mode status

## Future Enhancements

- [ ] Add mode change history/audit log
- [ ] Add webhook notifications on mode change
- [ ] Add mode scheduling (e.g., auto-switch to analyzer after market hours)
- [ ] Add mode confirmation dialog before switching to LIVE
- [ ] Add mode switch protection (require password for LIVE)
- [ ] Add mode statistics (time in LIVE vs ANALYZER)

## Support & Questions

For issues or questions:
1. Check logs: `docker-compose logs -f react_dashboard`
2. Run troubleshooting tests above
3. Verify .env file exists in project root
4. Ensure containers are running: `docker-compose ps`
