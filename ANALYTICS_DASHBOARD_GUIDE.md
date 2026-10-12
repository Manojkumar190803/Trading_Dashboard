# Analytics Dashboard Guide - Daily P&L Calendar & Monthly Summary

**Last Updated:** 2026-10-09  
**Status:** ✅ Production Ready  
**Docker Build:** Persisted (api_server.py + DailyPnLCalendar.tsx included in container)

---

## 📊 Overview

The Analytics Dashboard provides real-time trading performance metrics with a new Daily P&L Calendar visualization showing:
- Live P&L and trade metrics (top cards)
- Equity curve and performance charts
- **NEW: Daily P&L Calendar with color-coded cells**
- **NEW: Monthly Summary metrics card**

All data flows from the strategy engine → JSON files → Flask API → React Dashboard.

---

## 🎨 Visual Components

### 1. Daily P&L Calendar

**Location:** Analytics page, scroll down → left side of 2-column grid

**Features:**
- Full month calendar grid (7 columns for Sun-Sat)
- Color-coded day cells based on P&L thresholds:
  - 🟩 **Dark Green** (bg-green-900): P&L ≥ ₹2,000 profit
  - 🟩 **Green** (bg-green-600): ₹0 - ₹2,000 profit
  - 🟥 **Red** (bg-red-600): P&L < ₹0 (loss)
  - 🟥 **Dark Red** (bg-red-900): P&L < -₹2,000 (large loss)
  - ⬜ **Gray** (bg-gray-700): No trades that day

**Day Cell Display:**
```
┌─────────────────┐
│       9         │  ← Day number
│   -₹1,086       │  ← P&L amount (if trades exist)
│    (2 trades)   │  ← Trade count
└─────────────────┘
```

**Interactions:**
- **Hover:** Scale up (105%) with shadow effect, shows tooltip: "Day 9: -₹1,086 (2 trades)"
- **Export Button:** Downloads CSV file with columns: `Day,P&L,Trades`
  - Filename: `daily_pnl_October_2026.csv`
  - Example content:
    ```
    Day,P&L,Trades
    1,0,0
    2,0,0
    ...
    9,-1085.5,2
    ...
    ```
- **Reset Button:** Clears current month data (red button with ⟳ icon)
  - POSTs to `/api/analytics/daily/reset`
  - Preserves historical months for trend analysis

**Legend (Bottom):**
```
🟥 Dark Red: < -₹2,000  |  🟥 Red: < ₹0  |  🟩 Green: < ₹2,000  |  🟩 Dark Green: ≥ ₹2,000
```

**Responsive Design:**
- Desktop (lg screens): 2-column grid (calendar left, summary right)
- Tablet/Mobile: Stacked vertically

---

### 2. Monthly Summary Metrics

**Location:** Analytics page, scroll down → right side of 2-column grid

**Components:**

#### Main Card - Total P&L
```
┌─────────────────────────┐
│   MONTH P&L             │
│   -₹1,086.50            │  ← text-3xl, bold
│   (Red if negative)     │
└─────────────────────────┘
```

#### 2×2 Grid - Key Metrics
| Metric | Icon | Example Value |
|--------|------|---|
| Best Day | 📈 | Day 9: -₹1,086 |
| Worst Day | 📉 | Day 9: -₹1,086 |
| Winning Days | ✅ | 0% (0 winning) |
| Losing Days | ❌ | 100% (1 losing) |

#### Bottom Card - Trading Activity
```
┌────────────────────────┐
│  📅 Trading Days       │
│  1 day                 │
│  (cyan colored)        │
└────────────────────────┘
```

**State Handling:**
- Shows **"N/A"** if no best_day/worst_day data
- Calculates percentages: `(winning_days / total_trading_days) × 100`
- Color coding: Green for positive metrics, Red for losses, Cyan for counts

---

## 🔌 API Endpoints

All endpoints run on **Flask server** (port 5003 inside Docker, proxied through port 3000).

### 1. Get Summary Metrics
```bash
GET /api/analytics/summary
```

**Response:**
```json
{
  "net_pnl": -1085.5,
  "gross_loss": 1085.5,
  "gross_profit": 0,
  "losing_trades": 1,
  "winning_trades": 0,
  "trades_completed": 2,
  "win_rate": 0.0,
  "profit_factor": 0.0,
  "expectancy": -542.75,
  "timestamp": "2026-10-09T16:45:23.123456",
  "orders": [...],
  "positions": [...]
}
```

**Used By:** Top metric cards (NET PROFIT/LOSS, TRADES COMPLETED, WIN RATE, PROFIT FACTOR)

**Update Frequency:** Real-time (polled every 3 seconds by React hook)

---

### 2. Get Daily P&L Calendar
```bash
GET /api/analytics/daily
```

**Response:**
```json
{
  "month": "October 2026",
  "year": 2026,
  "month_num": 10,
  "days": {
    "1": {"pnl": 0, "trades": 0, "color": "gray"},
    "2": {"pnl": 0, "trades": 0, "color": "gray"},
    "9": {"pnl": -1085.5, "trades": 2, "color": "red"},
    "10": {"pnl": 0, "trades": 0, "color": "gray"}
  },
  "month_summary": {
    "total_pnl": -1085.5,
    "best_day": {"day": 9, "pnl": -1085.5},
    "worst_day": {"day": 9, "pnl": -1085.5},
    "winning_days": 0,
    "losing_days": 1,
    "total_trading_days": 1
  }
}
```

**Used By:** DailyPnLCalendar component (calendar grid) + MonthlySummary component (metric cards)

**Update Frequency:** Polled every 5 seconds by React hook

**Color Logic (in Python backend):**
```python
if pnl < -2000:
    color = "dark-red"      # bg-red-900
elif pnl < 0:
    color = "red"           # bg-red-600
elif pnl < 2000:
    color = "green"         # bg-green-600
elif pnl >= 2000:
    color = "dark-green"    # bg-green-900
else:
    color = "gray"          # bg-gray-700 (no trades)
```

---

### 3. Reset Current Month
```bash
POST /api/analytics/daily/reset
```

**Request:** Empty body

**Response:**
```json
{
  "status": "success",
  "message": "October 2026 data cleared",
  "timestamp": "2026-10-09T16:50:00.000000"
}
```

**Effect:**
- Clears all days in current month (YYYY-MM) from `logs/daily_pnl.json`
- Preserves previous months for historical analysis
- Resets calendar to all gray cells with 0 trades
- Monthly summary shows 0 values

**Used By:** Reset button in DailyPnLCalendar component

---

### 4. Search Symbols (Bonus)
```bash
GET /api/symbols/search?q=NI&strategy=21EMA
```

**Response:**
```json
["NIFTY"]
```

---

### 5. Validate Symbol (Bonus)
```bash
POST /api/symbols/validate
Content-Type: application/json

{"symbol": "NIFTY"}
```

**Response:**
```json
{
  "valid": true,
  "symbol": "NIFTY",
  "message": "Symbol is valid",
  "available_symbols": ["NIFTY", "BANKNIFTY", "SENSEX"]
}
```

---

## 📂 Data Storage

### Daily P&L JSON File
**Path:** `logs/daily_pnl.json`

**Structure:**
```json
{
  "2026-09": {
    "1": {"pnl": 500.0, "trades": 1},
    "15": {"pnl": -2500.0, "trades": 3}
  },
  "2026-10": {
    "9": {"pnl": -1085.5, "trades": 2}
  }
}
```

**Format:** `{YYYY-MM: {day: {pnl, trades}, ...}, ...}`

**Maintenance:**
- Automatically updated by strategy engine after each trade
- Preserved across Docker restarts (volume mount: `./logs → /app/logs`)
- Historical months never deleted (support 12+ month trends)
- Only current month cleared by `/api/analytics/daily/reset`

### Dashboard Data JSON
**Path:** `logs/dashboard_data.json`

Contains:
- Current open positions
- Recent closed orders
- Live account metrics (net_mtm, margins, etc.)

**Updated:** Every 5 seconds by dashboard_exporter service

---

## 🚀 Docker Architecture

### Container Coordination
```
┌─────────────────────────────────────────────┐
│  react_dashboard (Node.js)                  │
│  ├─ server.js (port 4000)                   │
│  │  └─ Proxy: /api/analytics/* → port 5003  │
│  └─ vite dev server (port 3000)             │
│     └─ React app loads components           │
└──────────────────────────────────────────────┘
              ↓ (fetch requests)
┌──────────────────────────────────────────────┐
│  strategy_worker (Python)                    │
│  ├─ api_server.py (port 5003)                │
│  │  ├─ /api/analytics/summary                │
│  │  ├─ /api/analytics/daily                  │
│  │  └─ /api/analytics/daily/reset            │
│  └─ run_strategy.py (strategy engine)        │
│     └─ Writes to logs/daily_pnl.json         │
└──────────────────────────────────────────────┘
```

### File Sharing
Both services mount same volume:
```yaml
volumes:
  - ./logs:/app/logs
  - ./data:/app/data
```

**Benefit:** Strategy writes daily_pnl.json → API reads same file → React displays instantly

---

## 💻 React Components

### DailyPnLCalendar.tsx
**Path:** `frontend-react/src/components/DailyPnLCalendar.tsx`
**Size:** 156 lines
**Props:**
```typescript
{
  dailyData: {
    month: string,
    year: number,
    month_num: number,
    days: Record<string, {pnl: number, trades: number, color: string}>,
    month_summary: {...}
  },
  onExport: () => void,
  onReset: () => void
}
```

**Key Functions:**
- `getColorStyles()`: Maps color string → Tailwind CSS classes
- `useMemo`: Builds 7-column calendar grid
- `DayCell`: Subcomponent for each day cell with hover effects

---

### MonthlySummary.tsx
**Path:** `frontend-react/src/components/MonthlySummary.tsx`
**Size:** 138 lines
**Props:**
```typescript
{
  monthSummary: {
    total_pnl: number,
    best_day: {day: number, pnl: number},
    worst_day: {day: number, pnl: number},
    winning_days: number,
    losing_days: number,
    total_trading_days: number
  }
}
```

**Subcomponents:**
- `MetricCard`: Reusable styled card with icon + label + value

---

### Analytics.tsx (Updated)
**Path:** `frontend-react/src/pages/Analytics.tsx`

**New Hooks:**
```typescript
// Fetch daily P&L data every 5 seconds
const dailyData = useDailyPnL();

// Export handler
const handleExport = () => {
  // Creates CSV from dailyData.days
  // Downloads as daily_pnl_${month}.csv
};

// Reset handler
const handleReset = async () => {
  // Calls resetDaily() from useDailyPnL hook
  // POSTs to /api/analytics/daily/reset
};
```

**New JSX:**
```tsx
<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
  <DailyPnLCalendar
    dailyData={dailyData}
    onExport={handleExport}
    onReset={handleReset}
  />
  <MonthlySummary monthSummary={dailyData?.month_summary || null} />
</div>
```

---

### useData.ts (Updated Hook)
**Path:** `frontend-react/src/hooks/useData.ts`

**New Hook - useDailyPnL():**
```typescript
function useDailyPnL() {
  const [dailyData, setDailyData] = useState<DailyPnLData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Poll every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetch('/api/analytics/daily')
        .then(res => res.json())
        .then(data => setDailyData(data))
        .catch(err => setError(err.message));
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Reset function
  const reset = async () => {
    const res = await fetch('/api/analytics/daily/reset', {method: 'POST'});
    if (res.ok) setDailyData(null); // Trigger refetch
  };

  return {dailyData, loading, error, reset: reset()};
}
```

**Update Frequency:** 5 seconds (adjustable via interval constant)

---

## 🔄 Data Flow

### When Strategy Makes a Trade

```
1. Strategy Engine (run_strategy.py)
   └─> Closes position → logs to CSV

2. Dashboard Exporter (background)
   └─> Reads CSV → Aggregates to daily_pnl.json
   └─> Updated file at logs/daily_pnl.json

3. React Hook (useDailyPnL)
   └─> Polls every 5 seconds
   └─> fetch('/api/analytics/daily')

4. Flask API (api_server.py)
   └─> Reads logs/daily_pnl.json
   └─> Applies color coding logic
   └─> Returns JSON with days + month_summary

5. React Components
   └─> DailyPnLCalendar renders grid
   └─> MonthlySummary renders metrics
   └─> User sees updated calendar with new day colored
```

**Total Latency:** < 10 seconds (aggregation + poll + render)

---

## ✅ Deployment Checklist

### ✅ Docker Build (Persisted)
- [x] `api_server.py` in Dockerfile COPY
- [x] `start_with_api.sh` in Dockerfile COPY
- [x] CMD updated to `./start_with_api.sh`
- [x] DailyPnLCalendar.tsx in React build
- [x] MonthlySummary.tsx in React build
- [x] useData.ts hook updated with useDailyPnL()
- [x] Containers rebuilt with `docker-compose up --build -d`

### ✅ Runtime Verification
- [x] Flask API running on port 5003
- [x] `/api/analytics/daily` returns calendar data
- [x] `/api/analytics/summary` returns metrics
- [x] React dashboard loads at localhost:3000
- [x] DailyPnLCalendar component visible
- [x] MonthlySummary component visible
- [x] Export button downloads CSV
- [x] Reset button clears calendar

### ✅ Persistence
- [x] `logs/daily_pnl.json` survives container restart
- [x] Volume mount `./logs:/app/logs` configured
- [x] Docker desktop stores volumes locally
- [x] Data persists next day without rebuild

---

## 📋 Testing Procedures

### Manual Test 1: View Calendar
```bash
# 1. Open browser
http://localhost:3000/analytics

# 2. Scroll down
# Should see 2-column layout:
# Left: Daily P&L Calendar with October 2026 grid
# Right: Monthly Summary metrics

# 3. Verify day 9 shows:
# - P&L: -₹1,086
# - Trades: 2
# - Color: Red (bg-red-600)
```

### Manual Test 2: Export CSV
```bash
# 1. Click "Export" button on calendar
# 2. File downloads: daily_pnl_October_2026.csv
# 3. Open file, verify contents:
#    Day,P&L,Trades
#    9,-1085.5,2
```

### Manual Test 3: Reset Month
```bash
# 1. Click "Reset" button
# 2. Calendar grid turns all gray
# 3. Monthly summary shows 0 values
# 4. Verify logs/daily_pnl.json updated
#    (October 2026 cleared, Sept preserved)
```

### API Test: Verify Endpoints
```bash
# Test summary endpoint
curl http://localhost:3000/api/analytics/summary | jq .net_pnl
# Should output: -1085.5

# Test daily endpoint
curl http://localhost:3000/api/analytics/daily | jq '.days."9"'
# Should output: {"pnl": -1085.5, "trades": 2, "color": "red"}

# Test reset endpoint
curl -X POST http://localhost:3000/api/analytics/daily/reset
# Should output: {"status": "success", ...}
```

---

## 🐛 Troubleshooting

### Issue: Calendar Shows "Loading..." Indefinitely

**Cause:** React hook fetch failing to reach API

**Solutions:**
1. Check Docker containers running:
   ```bash
   docker-compose ps
   ```
   Verify `strategy_worker` and `react_dashboard` show "Up"

2. Test API directly:
   ```bash
   curl http://localhost:5003/api/analytics/daily
   ```
   Should return JSON (not error)

3. Check browser console (F12):
   - Look for network errors (red requests)
   - Verify `/api/analytics/daily` request shows 200 status

4. Restart containers:
   ```bash
   docker-compose down && docker-compose up -d
   ```

---

### Issue: Export Button Downloads Empty File

**Cause:** `dailyData.days` undefined or empty

**Solutions:**
1. Verify daily API returns data:
   ```bash
   curl http://localhost:3000/api/analytics/daily | jq .days
   ```
   Should show day entries like `"9": {...}`

2. Check `logs/daily_pnl.json` exists and has content:
   ```bash
   cat logs/daily_pnl.json | jq '.["2026-10"]'
   ```

3. Hard-refresh browser (Cmd+Shift+R) to clear cache

---

### Issue: Reset Button Doesn't Clear Calendar

**Cause:** POST request failing or hook not refetching

**Solutions:**
1. Verify reset endpoint works:
   ```bash
   curl -X POST http://localhost:3000/api/analytics/daily/reset
   ```
   Should return `{"status": "success", ...}`

2. Check `logs/daily_pnl.json` was updated:
   ```bash
   cat logs/daily_pnl.json | jq '.["2026-10"]'
   ```
   October 2026 should be empty `{}`

3. If calendar still shows data, hard-refresh browser

---

## 📚 Related Files

| File | Purpose |
|------|---------|
| `api_server.py` | Flask API server with analytics endpoints |
| `core/dashboard_data.py` | Daily P&L aggregation logic |
| `frontend-react/src/components/DailyPnLCalendar.tsx` | Calendar grid component |
| `frontend-react/src/components/MonthlySummary.tsx` | Summary metrics component |
| `frontend-react/src/pages/Analytics.tsx` | Main analytics page |
| `frontend-react/src/hooks/useData.ts` | Data fetching hooks |
| `frontend-react/vite.config.ts` | Vite proxy config for API |
| `frontend-react/server.js` | Node.js proxy for analytics endpoints |
| `Dockerfile` | Strategy worker container setup |
| `docker-compose.yml` | Multi-container orchestration |
| `logs/daily_pnl.json` | Daily P&L data storage |
| `logs/dashboard_data.json` | Live positions & orders |

---

## 🎯 Next Steps (Optional Enhancements)

- [ ] Add year/month picker to view historical months
- [ ] Add daily P&L trend line chart
- [ ] Add win rate heatmap (30-day rolling window)
- [ ] Add export options (PDF, Excel)
- [ ] Add monthly comparison (MoM growth %)
- [ ] Add trading hours filter
- [ ] Add strategy-specific P&L breakdown

---

**Questions?** Check `/memories/repo/progress.md` for implementation details or review the source files above.

**Last verified:** 2026-10-09 22:25 IST  
**Docker status:** ✅ All containers running with persisted changes
