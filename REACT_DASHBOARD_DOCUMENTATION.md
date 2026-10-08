# React Trading Dashboard - Complete Documentation

## 📋 Table of Contents
1. [Overview](#overview)
2. [Purpose & Use Cases](#purpose--use-cases)
3. [Technology Stack](#technology-stack)
4. [Architecture](#architecture)
5. [Key Features](#key-features)
6. [Project Structure](#project-structure)
7. [Pages & Components](#pages--components)
8. [State Management](#state-management)
9. [API Endpoints](#api-endpoints)
10. [Data Flow](#data-flow)
11. [Strategy Linking](#strategy-linking)
12. [Setup & Installation](#setup--installation)
13. [Running the Dashboard](#running-the-dashboard)
14. [Configuration](#configuration)
15. [Integration with Python Backend](#integration-with-python-backend)

---

## Overview

The **React Trading Dashboard** is a modern, real-time professional trading control room built for automated options trading. It serves as the central interface for:

- **Instrument Management**: Configure and monitor trading instruments
- **Strategy Execution**: Select and run different trading strategies (21EMA, HD, CD, TC, 2BC, BO)
- **Live Monitoring**: Track running strategies, positions, and orders in real-time
- **Analytics & Reporting**: View P&L, equity curves, and trade analytics
- **Risk Management**: Monitor trailing stoploss, risk ratios, and breakeven levels

The dashboard bridges a **React TypeScript frontend** (port 3000) with:
- **Express.js backend** (port 4000) for API operations
- **Python strategy engine** (broker connection) via JSON file-based IPC
- **Python strategy daemon** for auto-starting/stopping strategies

---

## Purpose & Use Cases

### Primary Purpose
Provide a unified control panel for traders to:
1. Define trading instruments and their monitoring parameters
2. Select which strategy to apply to each instrument
3. Configure risk management parameters (stoploss, breakeven, trailing steps)
4. Monitor strategy execution status and P&L in real-time
5. View historical trades, orders, and performance analytics

### Key Use Cases

**Use Case 1: Strategy Selection & Configuration**
```
Trader Action: Add new NIFTY instrument with 2BC strategy
Dashboard Flow:
  → Trader fills form (name, symbol, strategy, hours)
  → Configures risk params (breakeven_rr, trail_step_rr, max_risk_points)
  → Clicks "Add" button
  → React stores in localStorage (Zustand) and exports to logs/instruments_config.json
  → Python daemon detects config change within 5 seconds
  → Daemon spawns: python3 run_strategy.py --strategy 2bc --script NIFTY --mode live
  → 2BC strategy core logic begins monitoring 3-min candles
```

**Use Case 2: Real-Time Strategy Monitoring**
```
Trader Action: Watch strategy execution status
Dashboard Flow:
  → Instruments page shows "Running (PID: 12345)" in green
  → Each 3 seconds, React polls /api/instruments/status
  → Dashboard updates with current process status
  → When signal fires, React fetches updated positions/trades
  → Charts and analytics update automatically
```

**Use Case 3: Risk Management & Stoploss Configuration**
```
Trader Action: Set trailing stoploss for a strategy
Dashboard Flow:
  → Trader sets breakeven_rr = 1.5 (e.g., "move SL to breakeven at 1.5x risk reward")
  → Trader sets trail_step_rr = 0.5 (e.g., "trail SL up by 0.5x risk every step")
  → Config auto-exports to instruments_config.json
  → Python strategy reads config and applies TSL logic during trade execution
  → React shows current strategy status and position info
```

---

## Technology Stack

### Frontend (React Application)

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Runtime** | Node.js | Latest | JavaScript runtime for development |
| **Framework** | React | 18.2.0 | UI component library and state management |
| **Language** | TypeScript | 5.3.3 | Type-safe JavaScript |
| **Routing** | React Router | 6.20.1 | Client-side navigation between pages |
| **State Management** | Zustand | 4.4.1 | Lightweight global state + localStorage persistence |
| **Styling** | Tailwind CSS | 3.4.1 | Utility-first CSS framework |
| **Charts & Graphs** | Recharts | 2.10.3 | React charting library for P&L curves |
| **Icons** | Lucide React | 0.408.0 | 300+ SVG icons for UI |
| **Date Handling** | date-fns | 2.30.0 | Date parsing, formatting, manipulation |
| **CSV Parsing** | PapaParse | 5.4.1 | CSV import/export for data |
| **Utilities** | clsx | 2.0.0 | Conditional className utility |

### Backend (Express.js Server)

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Server** | Express.js | 4.18.2 | HTTP API server on port 4000 |
| **Language** | JavaScript (ES Modules) | ES2020+ | Native async/await, modern syntax |
| **File I/O** | Node.js fs module | Built-in | Read/write JSON configs and logs |
| **Path Resolution** | Node.js path module | Built-in | Cross-platform file path handling |

### Build & Development Tools

| Tool | Version | Purpose |
|------|---------|---------|
| **Bundler** | Vite | 5.0.8 | Lightning-fast dev server and production builds |
| **React Plugin** | @vitejs/plugin-react | 4.2.1 | Fast Refresh for React in dev |
| **Linter** | ESLint | 8.56.0 | Code quality and style checking |
| **Type Checker** | TypeScript Compiler | 5.3.3 | Compile-time type validation |
| **CSS Processing** | PostCSS + Autoprefixer | 8.4.32 + 10.4.16 | CSS vendor prefixing |
| **Concurrency** | concurrently | Latest | Run server + Vite dev server together |

### Styling Framework Details

**Tailwind CSS 3.4.1** provides utility classes for:
- Dark mode trading theme (custom color palette)
- Responsive design (mobile to desktop)
- Animations and transitions
- Custom color variables (defined in globals.css)
  - Primary: `#0A1929` (dark navy)
  - Accent: Cyan (`#59D0FF`), Green (`#2BD48A`), Red (`#FF7180`)
  - Text: Secondary, Tertiary shades for hierarchy

---

## Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       REACT TRADING DASHBOARD                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐         ┌──────────────────────────────┐  │
│  │  React UI Pages  │         │  Components & Layout         │  │
│  │  ─────────────── │         │  ──────────────────────────   │  │
│  │ • Dashboard      │         │ • Sidebar Navigation         │  │
│  │ • Instruments    │ ◄──────►│ • Header with Status         │  │
│  │ • Positions      │         │ • Tables & Forms             │  │
│  │ • Orders         │         │ • Charts & Visualizations    │  │
│  │ • Trades         │         │ • Modals & Dialogs           │  │
│  │ • Analytics      │         │ • Status Indicators          │  │
│  │ • Logs           │         │                              │  │
│  └──────────────────┘         └──────────────────────────────┘  │
│         │                                                         │
│         │ useAppStore() → Zustand                               │
│         │ Redux-like state management with localStorage         │
│         │ Persists: instruments array, UI preferences           │
│         │                                                         │
│         ▼                                                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Zustand Global State Store                     │  │
│  │  ────────────────────────────────────────────────────    │  │
│  │  • metrics: DashboardMetrics (P&L, equity, stats)      │  │
│  │  • positions: Position[] (open trades)                 │  │
│  │  • trades: Trade[] (historical trades)                 │  │
│  │  • instruments: Instrument[] (trader config)           │  │
│  │  • orders: Order[] (active orders)                     │  │
│  │  • alerts: StrategyAlert[] (notifications)             │  │
│  │  • logs: LogEntry[] (system & strategy logs)           │  │
│  │  • equityCurve: EquityCurvePoint[] (P&L chart)         │  │
│  │                                                          │  │
│  │  Methods:                                               │  │
│  │  • exportInstruments() → POST /api/instruments/export   │  │
│  │  • getStrategyStatus() → GET /api/instruments/status    │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                   │
│                           ▼ (HTTP API Calls)                 │
│         ┌─────────────────────────────────────────────┐    │
│         │    Express.js Backend (port 4000)           │    │
│         │    ─────────────────────────────────────    │    │
│         │  ✓ /api/instruments/export (POST)           │    │
│         │  ✓ /api/instruments/status (GET)            │    │
│         │  ✓ /api/analytics/reset (POST)              │    │
│         │  ✓ /api/logs/:filename (GET)                │    │
│         │  ✓ /health (GET)                            │    │
│         └────────────┬────────────────────────────────┘    │
│                      │                                      │
└──────────────────────┼──────────────────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  Logs Directory (JSON)    │
         │  ──────────────────────   │
         │ • instruments_config.json │
         │ • strategies_status.json  │
         │ • analytics_trades.csv    │
         │ • monitoring_*.txt/.csv   │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────────────────────┐
         │  Python Strategy Daemon                   │
         │  ────────────────────────────────────────│
         │ • Monitors instruments_config.json        │
         │ • Spawns strategy subprocesses            │
         │ • Tracks running processes                │
         │ • Updates strategies_status.json          │
         └─────────────┬─────────────────────────────┘
                       │
         ┌─────────────▼─────────────────────────────┐
         │  Python Strategy Core Engines             │
         │  ────────────────────────────────────────│
         │ • 21EMA (EMA21SignalProvider)             │
         │ • HD (HDSignalProvider)                   │
         │ • CD (CDSignalProvider)                   │
         │ • TC (TCSignalProvider)                   │
         │ • 2BC (TwoBodyCandleSignalProvider) ✨    │
         │ • BO (BreakoutSignalProvider) ✨          │
         │ • Each connects to broker for live data   │
         └─────────────┬─────────────────────────────┘
                       │
                       ▼
              Broker API / WebSocket
           (Live candle data, order execution)
```

### Frontend Directory Structure

```
frontend-react/
├── index.html                 # HTML entry point
├── vite.config.ts            # Vite config with proxy & plugin
├── tailwind.config.js        # Tailwind CSS configuration
├── postcss.config.js         # PostCSS setup (for Tailwind)
├── tsconfig.json             # TypeScript configuration
├── tsconfig.node.json        # TypeScript config for Vite
├── package.json              # Dependencies & scripts
├── server.js                 # Express.js backend (port 4000)
│
├── public/                   # Static assets
│   └── favicon.svg
│
└── src/
    ├── main.tsx              # Vite entry point, renders to #root
    ├── App.tsx               # Main app component with routing
    │
    ├── components/           # Reusable React components
    │   ├── Layout.tsx        # Main layout wrapper
    │   ├── Sidebar.tsx       # Left navigation menu
    │   ├── Header.tsx        # Top header bar
    │   ├── StatusIndicator.tsx
    │   ├── Tables/           # Table components (Positions, Orderbook, etc.)
    │   ├── Charts/           # Chart components (EquityCurve, etc.)
    │   └── Forms/            # Form components (InstrumentForm, etc.)
    │
    ├── pages/                # Full-page components (one per route)
    │   ├── Dashboard.tsx     # Overview/home page
    │   ├── Instruments.tsx   # Strategy config & management
    │   ├── Positions.tsx     # Open positions
    │   ├── Orderbook.tsx     # Order history
    │   ├── Analytics.tsx     # P&L charts, statistics
    │   ├── Logs.tsx          # System and strategy logs
    │   └── Trades.tsx        # Trade history
    │
    ├── stores/               # Zustand state management
    │   └── app.ts            # Global app store (metrics, positions, instruments, etc.)
    │
    ├── types/                # TypeScript type definitions
    │   ├── index.ts          # All type definitions
    │   └── Instrument.ts     # Instrument interface
    │
    ├── hooks/                # Custom React hooks
    │   ├── useAPI.ts         # API calling logic
    │   ├── useWebSocket.ts   # WebSocket connection hook
    │   └── useAutoRefresh.ts # Auto-refresh intervals
    │
    ├── utils/                # Utility functions
    │   ├── api.ts            # API client functions
    │   ├── formatters.ts     # Number/date formatting
    │   ├── validators.ts     # Form validation
    │   └── constants.ts      # App-wide constants
    │
    └── styles/               # Global styles
        ├── globals.css       # Dark theme, CSS variables
        ├── tailwind.css      # Tailwind base imports
        └── animations.css    # Custom animations
```

---

## Key Features

### 1. **Instrument Management**
- ✅ Add new trading instruments (NIFTY, BANKNIFTY, SENSEX)
- ✅ Select strategy for each instrument (6 strategies available)
- ✅ Set monitoring hours (start/end time)
- ✅ Configure lot size adjustment multiplier
- ✅ Enable/disable instruments on the fly
- ✅ Edit existing instrument configurations
- ✅ Delete instruments from the list
- ✅ Search & filter by strategy or status

**Data Persisted:**
```typescript
interface Instrument {
  id: string                      // Unique identifier
  name: string                    // Display name (e.g., "NIFTY")
  brokerSymbol: string           // Broker API symbol
  strategy: string               // Selected strategy
  status: boolean                // Enabled/Disabled
  atmPrice: number               // Current ATM price
  minPremium: number             // Minimum premium filter
  maxPremium: number             // Maximum premium filter
  lotSizeAdjustment: number      // Position size multiplier
  monitoringStartTime: string    // "09:15"
  monitoringEndTime: string      // "15:30"
  breakeven_rr: number           // Risk-reward for breakeven
  trail_step_rr: number          // Risk-reward for trailing steps
  max_initial_risk_points: number // Max allowed initial risk
}
```

### 2. **Strategy Selection & Execution**
Available strategies:
1. **21EMA** - 21-period Exponential Moving Average crossover
2. **HD** - Hammer Divergence (RSI divergence detection)
3. **CD** - Candle Divergence (price divergence pattern)
4. **TC** - Trend Continuation (momentum-based)
5. **2BC** - Two Body Candle (consolidation + breakout) ✨ NEW
6. **BO** - Breakout (opening range breakout) ✨ NEW

Each strategy:
- Has its own Python core logic file (`strategies/*.py`)
- Is registered in `run_strategy.py` registry
- Can be dynamically selected per instrument
- Auto-starts when instrument is enabled
- Auto-stops when instrument is disabled

### 3. **Real-Time Monitoring**
- ✅ Display strategy execution status (Running, Crashed, Stopped)
- ✅ Show process ID (PID) for running strategies
- ✅ Pulse animation for active strategies
- ✅ Error indicators for crashed processes
- ✅ Auto-refresh status every 3 seconds
- ✅ Visual indicators (green dot, red alert, gray square)

### 4. **Risk Management Configuration**
Configure per-instrument stoploss behavior:

**Parameter 1: breakeven_rr (Breakeven Risk-Reward)**
- Default: 1.0
- Meaning: At what multiple of initial risk should SL move to breakeven?
- Example: If risk = 50 points, move SL to entry at 50 points profit

**Parameter 2: trail_step_rr (Trailing Step Risk-Reward)**
- Default: 0.5
- Meaning: How many points per risk multiple to trail SL up?
- Example: Every 50 points of additional profit, trail SL up by 25 points

**Parameter 3: max_initial_risk_points (Max Risk Cap)**
- Default: 20.0
- Meaning: Maximum points of risk for initial stop placement
- Example: If calculated risk > 20 points, skip this signal

### 5. **Real-Time Dashboard**
- ✅ P&L overview (daily, weekly, monthly)
- ✅ Equity curve chart (interactive Recharts)
- ✅ Win rate, profit factor, max drawdown
- ✅ Active positions count
- ✅ Active orders count
- ✅ Strategy alerts feed

### 6. **Positions & Orders Tracking**
- ✅ View all open positions with entry price, current P&L
- ✅ View closed trades with entry, exit, profit/loss
- ✅ Order history with timestamp and status
- ✅ Real-time order updates via polling
- ✅ Filter by strategy, status, or symbol

### 7. **Analytics & Reporting**
- ✅ Equity curve over time
- ✅ Daily P&L bars
- ✅ Strategy comparison
- ✅ Win/loss statistics
- ✅ Risk metrics (max drawdown, Sharpe ratio)
- ✅ Export data to CSV

### 8. **System Logs**
- ✅ Real-time strategy execution logs
- ✅ Order execution logs
- ✅ Error messages and alerts
- ✅ Filter by strategy, time range
- ✅ Search within logs
- ✅ Timestamp and severity levels

---

## Pages & Components

### Page 1: Dashboard (`/dashboard`)
**Purpose:** Home page showing trading overview

**Content:**
- Key metrics cards (Total P&L, Win Rate, Active Strategies)
- Equity curve chart
- Recent alerts feed
- Active positions summary
- Daily P&L bar chart

**Layout:**
```
┌─ Sidebar ─┬─────────────────────────────────┐
│ Nav       │ Header (Search, Refresh)       │
│ Links     ├─────────────────────────────────┤
│           │ 4 Metric Cards                  │
│           │ ┌──┐ ┌──┐ ┌──┐ ┌──┐           │
│           │ │P&│ │WR│ │MD│ │AS│           │
│           │ └──┘ └──┘ └──┘ └──┘           │
│           ├─────────────────────────────────┤
│           │ Equity Curve Chart (Recharts)  │
│           │ Line graph with tooltip         │
│           ├─────────────────────────────────┤
│           │ Recent Alerts (Feed)            │
│           │ • NIFTY 21EMA: BUY at 27500    │
│           │ • BANKNIFTY HD: SIGNAL         │
│           ├─────────────────────────────────┤
│           │ Active Positions (Mini Table)   │
└───────────┴─────────────────────────────────┘
```

### Page 2: Instruments (`/instruments`)
**Purpose:** Add/edit/manage trading instruments and configure strategies

**Content:**
- Search and filter bar
- "Add New Instrument" button
- Instruments table with columns:
  - Name, Strategy, Status, Monitoring Hours
  - Current Premium, Lot Size, Action buttons
- Modal form for adding/editing:
  - Name, Broker Symbol, Monitoring Hours
  - Strategy dropdown (6 options)
  - Risk config (breakeven_rr, trail_step_rr, max_risk)
  - Min/Max Premium filters
- Strategy status column (Running/Crashed/Stopped with PID)

**Features:**
- Real-time validation as user types
- Auto-export to backend when changes made
- Status polling every 3 seconds
- Delete confirmation dialog
- Edit mode for existing instruments
- Status indicators with colors

### Page 3: Positions (`/positions`)
**Purpose:** View all open positions and their P&L

**Columns:**
- Instrument, Strategy, Entry Time, Entry Price
- Current Price, Quantity, Unrealized P&L
- Unrealized %, Side (CE/PE), Stop Level
- Action (Close, Modify SL)

**Features:**
- Real-time P&L updates
- Color-coded rows (green profit, red loss)
- Click to view position details
- Quick actions (close, modify)

### Page 4: Orders (`/orderbook`)
**Purpose:** View order execution history

**Columns:**
- Time, Instrument, Strategy, Order Type
- Entry Price, Trigger Price, Status
- Filled Qty, Remaining Qty, Order ID

**Features:**
- Sort by any column
- Filter by status (Pending, Filled, Cancelled)
- Real-time status updates

### Page 5: Trades (`/trades`)
**Purpose:** View historical closed trades

**Columns:**
- Entry Time, Exit Time, Duration
- Strategy, Instrument, Entry Price, Exit Price
- Profit/Loss, P&L %, Win/Loss

**Features:**
- Search and filter
- Export to CSV
- Performance statistics
- Streak tracking (consecutive wins/losses)

### Page 6: Analytics (`/analytics`)
**Purpose:** Deep dive into strategy performance

**Visualizations:**
- Equity curve with drawdown area
- Daily P&L bar chart
- Strategy comparison (side-by-side performance)
- Win rate pie chart
- Monthly return heatmap

**Statistics:**
- Total trades, Wins, Losses
- Win rate %, Profit factor
- Average winning trade
- Average losing trade
- Max consecutive wins/losses
- Sharpe ratio, Sortino ratio
- Max drawdown, Recovery factor

**Actions:**
- Reset analytics
- Date range picker
- Export to CSV

### Page 7: Logs (`/logs`)
**Purpose:** Monitor real-time system and strategy logs

**Sections:**
1. Active Logs (real-time 3-minute candle data)
   - Shows live candle data by strategy and side
   - Updates as new candles arrive
2. System Logs
   - Strategy events (setup status, signals fired)
   - Order execution logs
   - Error messages

**Features:**
- Search within logs
- Filter by strategy or severity
- Time range picker
- Auto-scroll on new logs
- Tail mode (follow latest)
- Clear logs button

---

## State Management

### Zustand Store Architecture

**Location:** `src/stores/app.ts`

**Store Structure:**
```typescript
interface AppStore {
  // ===== Dashboard State =====
  metrics: DashboardMetrics | null
  setMetrics: (metrics: DashboardMetrics) => void

  // ===== Trading Data =====
  positions: Position[]
  setPositions: (positions: Position[]) => void
  
  trades: Trade[]
  setTrades: (trades: Trade[]) => void
  
  orders: Order[]
  setOrders: (orders: Order[]) => void
  
  equityCurve: EquityCurvePoint[]
  setEquityCurve: (curve: EquityCurvePoint[]) => void

  // ===== Alerts & Notifications =====
  alerts: StrategyAlert[]
  addAlert: (alert: StrategyAlert) => void
  clearAlerts: () => void
  maxAlertsDisplay: number

  // ===== Logs =====
  logs: LogEntry[]
  addLog: (log: LogEntry) => void
  setLogs: (logs: LogEntry[]) => void
  clearLogs: () => void
  maxLogsDisplay: number

  // ===== Instruments Management =====
  instruments: Instrument[]
  setInstruments: (instruments: Instrument[]) => void
  addInstrument: (instrument: Instrument) => void
  updateInstrument: (id: string, instrument: Partial<Instrument>) => void
  deleteInstrument: (id: string) => void
  toggleInstrument: (id: string) => void
  exportInstruments: () => Promise<void>        // POST to /api/instruments/export
  getStrategyStatus: () => Promise<any>        // GET from /api/instruments/status

  // ===== UI State =====
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
  theme: 'dark' | 'light'
  setTheme: (theme: 'dark' | 'light') => void
}
```

### Persistence with localStorage

**What Gets Persisted:**
- `instruments` array - All configured instruments
- UI preferences (theme, sidebar state)
- User preferences (default monitoring hours, lot sizes)

**Middleware:** `persist` from `zustand/middleware`
- Automatically saves store changes to localStorage key: `'app-store'`
- Loads from localStorage on app start
- Selective persistence via `partialize` option

**Example Usage in Components:**
```typescript
import { useAppStore } from '@/stores'

function MyComponent() {
  const instruments = useAppStore((state) => state.instruments)
  const addInstrument = useAppStore((state) => state.addInstrument)
  
  // Subscribe to only specific parts of state (performance optimization)
  // Changes to unrelated state won't re-render this component
}
```

### State Flow

```
User Action (e.g., Add Instrument)
    ↓
Component Handler (e.g., handleAddInstrument)
    ↓
addInstrument() method in Zustand store
    ↓
State updated in memory
    ↓
Component re-renders with new state
    ↓
localStorage automatically updated (via persist middleware)
    ↓
exportInstruments() API call triggered
    ↓
Express backend writes instruments_config.json
    ↓
Python daemon detects config change
    ↓
Strategy subprocess spawned
    ↓
Strategy status appears in UI
```

---

## API Endpoints

### Backend Server: `http://localhost:4000`

All requests/responses use JSON format with error handling.

#### 1. Health Check
```http
GET /health
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "timestamp": "2026-10-09T12:30:45.123Z"
}
```

---

#### 2. Export Instruments Configuration
```http
POST /api/instruments/export
Content-Type: application/json

{
  "instruments": [
    {
      "id": "inst-1",
      "name": "NIFTY",
      "brokerSymbol": "NIFTY50",
      "strategy": "21EMA",
      "status": true,
      "atmPrice": 27500,
      "minPremium": 10,
      "maxPremium": 500,
      "breakeven_rr": 1.0,
      "trail_step_rr": 0.5,
      "max_initial_risk_points": 20.0,
      "lotSizeAdjustment": 1,
      "monitoringStartTime": "09:15",
      "monitoringEndTime": "15:30"
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Instruments exported successfully",
  "count": 1,
  "timestamp": "2026-10-09T12:30:45.123Z"
}
```

**File Created:** `logs/instruments_config.json`
```json
{
  "exported_at": "2026-10-09T12:30:45.123Z",
  "instruments": [
    { ...instrument details... }
  ]
}
```

**Error Response (500):**
```json
{
  "success": false,
  "error": "Failed to export instruments"
}
```

---

#### 3. Get Strategy Execution Status
```http
GET /api/instruments/status
```

**Response (200 OK):**
```json
{
  "updated_at": "2026-10-09T12:35:12.456Z",
  "running_strategies": {
    "inst-1": {
      "pid": 12345,
      "status": "running",
      "started_at": "2026-10-09T12:30:00.000Z",
      "instrument_name": "NIFTY",
      "strategy": "21EMA",
      "error": null
    },
    "inst-2": {
      "pid": null,
      "status": "crashed",
      "started_at": "2026-10-09T12:31:00.000Z",
      "instrument_name": "BANKNIFTY",
      "strategy": "2BC",
      "error": "Process exited with code 1"
    }
  }
}
```

**Field Explanations:**
- `pid`: Process ID (null if stopped)
- `status`: "running", "crashed", or "stopped"
- `started_at`: ISO 8601 timestamp when process started
- `error`: Error message if crashed, null otherwise

---

#### 4. Reset Analytics
```http
POST /api/analytics/reset
```

**Action:** Clears analytics_trades.csv and writes reset timestamp

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Analytics data reset successfully",
  "timestamp": "2026-10-09T12:40:00.000Z"
}
```

**Files Modified:**
- `logs/analytics_trades.csv` - Cleared, header written
- `logs/analytics_reset.txt` - Updated with reset timestamp

---

#### 5. Fetch Log File
```http
GET /api/logs/:filename
```

**Example:**
```http
GET /api/logs/monitoring_20261009.txt
```

**Response (200 OK):**
```text
[file contents]
```

**Security:**
- Filename validation: only alphanumeric, dots, underscores, hyphens allowed
- Path traversal prevention (no `../` allowed)

**Error Response (400):**
```json
{
  "error": "Invalid filename"
}
```

**Error Response (404):**
```json
{
  "error": "File not found"
}
```

---

### Proxy Routing (via Vite)

In `vite.config.ts`, the dev server proxies requests:

```
/api/* → http://localhost:4000/api/*
/logs/* → http://localhost:4000/api/logs/*
```

This allows React code to call relative URLs in dev:
```typescript
// In React component:
fetch('/api/instruments/export')  // Dev proxy routes to :4000
// Production: URLs would be to same domain or configured backend
```

---

## Data Flow

### Complete Instrument Lifecycle

```
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: USER ADDS INSTRUMENT IN REACT                        │
└──────────────────────────────────────────────────────────────┘
    Trader opens Instruments page, clicks "Add New"
    Form appears with fields:
      - Name: "NIFTY"
      - Broker Symbol: "NIFTY50"
      - Strategy: "2BC" ← dropdown with 6 options
      - Monitoring Hours: "09:15" to "15:30"
      - Risk Config: breakeven_rr, trail_step_rr, max_risk
    
    Trader clicks "Add" button
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: REACT STATE UPDATE (Zustand Store)                  │
└──────────────────────────────────────────────────────────────┘
    addInstrument() called
      → instruments array updated
      → Component re-renders
      → localStorage auto-updated (persist middleware)
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: AUTO-EXPORT TO BACKEND                              │
└──────────────────────────────────────────────────────────────┘
    useEffect hook triggered (when instruments array changes)
      → exportInstruments() called
      → POST /api/instruments/export with all instruments
      → Express backend receives request
      → Writes logs/instruments_config.json
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 4: PYTHON DAEMON DETECTION (5-second poll)             │
└──────────────────────────────────────────────────────────────┘
    strategy_daemon.py continuous loop:
      → Reads logs/instruments_config.json every 5 seconds
      → Compares with previous config (change detection)
      → Finds new NIFTY instrument with 2BC strategy
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 5: STRATEGY NAME MAPPING                               │
└──────────────────────────────────────────────────────────────┘
    daemon._build_command() function:
      → Input: {"strategy": "2BC", ...}
      → STRATEGY_NAME_MAP: {"2BC": "2bc"}
      → Output: "2bc"
      → Final command: ['python3', 'run_strategy.py', '--strategy', '2bc', ...]
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 6: SUBPROCESS SPAWNED                                  │
└──────────────────────────────────────────────────────────────┘
    daemon._start_strategy() function:
      → subprocess.Popen(cmd, ...)
      → Process ID captured: e.g., 12345
      → Tracked in running_processes dict
      → Status written to running_status dict
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 7: RUN_STRATEGY.PY EXECUTES                            │
└──────────────────────────────────────────────────────────────┘
    run_strategy.py --strategy 2bc:
      → get_signal_provider("2bc", args) called
      → STRATEGY_REGISTRY["2bc"] lookup
      → _register_2bc() factory function
      → importlib.import_module('strategies.2bc')
      → TwoBodyCandleSignalProvider instantiated
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 8: STRATEGY CORE LOGIC RUNS                            │
└──────────────────────────────────────────────────────────────┘
    2BC strategy begins execution:
      → Connects to broker via OpenAlgo API
      → Subscribes to 3-minute NIFTY candles
      → Each candle: process_candle() called
      → Implements multi-gate entry logic:
        Gate 1: Consolidation filter (CHOP, ADX)
        Gate 2: Two-candle breakout pattern
        Gate 3: RSI momentum surge
        Gate 4: Risk cap validation
      → When all gates pass: Signal.BUY generated
      → Order placed via broker WebSocket
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 9: STATUS FILE UPDATED                                 │
└──────────────────────────────────────────────────────────────┘
    daemon._save_status() function:
      → running_status dict serialized to JSON
      → logs/strategies_status.json written
      → Contains: {
            "updated_at": "2026-10-09T12:35:12.456Z",
            "running_strategies": {
              "inst-1": {
                "pid": 12345,
                "status": "running",
                "started_at": "...",
                "strategy": "2BC"
              }
            }
          }
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 10: REACT POLLS STATUS (every 3 seconds)               │
└──────────────────────────────────────────────────────────────┘
    Instruments.tsx useEffect hook:
      → setInterval(getStrategyStatus, 3000)
      → GET /api/instruments/status
      → React receives status JSON
      → setStrategyStatus(status) called
      → Component re-renders
                ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 11: UI DISPLAYS RUNNING STATUS                         │
└──────────────────────────────────────────────────────────────┘
    Instruments table row shows:
      ✓ Name: "NIFTY"
      ✓ Strategy: "2BC"
      ✓ Status Column: 🟢 "Running (PID: 12345)"
      ✓ Pulsing green animation
      ✓ User can see strategy is active and monitoring
```

---

## Strategy Linking

### How Strategies Link from UI to Core Logic

**The Problem Solved:**
React dashboard has 6 strategies (21EMA, HD, CD, TC, 2BC, BO), but Python had only 4 registered. Strategy names didn't match either (React: "21EMA", Python: "ema21").

**The Solution:**
Three-layer mapping system ensures correct strategy is launched:

#### Layer 1: React UI → instruments_config.json
```typescript
// User selects "2BC" from dropdown
const formData = { strategy: "2BC", ... }
// Auto-exported to instruments_config.json
{
  "instruments": [
    { "strategy": "2BC", ... }
  ]
}
```

#### Layer 2: Daemon Strategy Name Mapping
```python
# strategy_daemon.py _build_command()
STRATEGY_NAME_MAP = {
    '21EMA': 'ema21',
    'HD': 'hd',
    'CD': 'cd',
    'TC': 'tc',
    '2BC': '2bc',     # NEW - Maps to registry name
    'BO': 'bo',       # NEW - Maps to registry name
}

strategy_name = instrument.get('strategy', '21EMA')  # "2BC"
strategy = STRATEGY_NAME_MAP.get(strategy_name, strategy_name.lower())  # "2bc"

cmd = ['python3', 'run_strategy.py', '--strategy', '2bc', ...]
```

#### Layer 3: run_strategy.py Registry Lookup
```python
# run_strategy.py
STRATEGY_REGISTRY = {
    'ema21': _register_ema21,
    'hd': _register_hd,
    'cd': _register_cd,
    'tc': _register_tc,
    '2bc': _register_2bc,      # NEW
    'bo': _register_bo,        # NEW
}

def get_signal_provider(name: str, args):
    if name == "2bc":
        import importlib
        module = importlib.import_module('strategies.2bc')
        return module.TwoBodyCandleSignalProvider(module.TwoBodyCandleConfig())
    # ... other strategies
```

#### Layer 4: Core Strategy Execution
```python
# strategies/2bc.py
class TwoBodyCandleSignalProvider(SignalProvider):
    def __init__(self, config: TwoBodyCandleConfig):
        self.config = config
    
    def process_candle(self, ...):
        # Multi-gate entry logic:
        # - Gate 1: Consolidation filter (CHOP > 61.8, ADX < 25)
        # - Gate 2: Two-candle breakout pattern
        # - Gate 3: RSI momentum surge
        # - Gate 4: Risk cap (max 20 points)
        ...
```

### Strategy Comparison Table

| React UI Name | Daemon Maps To | Registry Lookup | Core Python File | Status |
|---------------|---|---|---|---|
| 21EMA | ema21 | ema21 | strategies/ema21.py | ✅ Works |
| HD | hd | hd | strategies/hd.py | ✅ Works |
| CD | cd | cd | strategies/cd.py | ✅ Works |
| TC | tc | tc | strategies/tc.py | ✅ Works |
| **2BC** | **2bc** | **2bc** | **strategies/2bc.py** | ✅ **NEW** |
| **BO** | **bo** | **bo** | **strategies/bo.py** | ✅ **NEW** |

---

## Setup & Installation

### Prerequisites
- **Node.js** 18+ (includes npm)
- **Python** 3.9+ (for broker connection & strategy execution)
- **Broker Account**: Connected via OpenAlgo API
- **Git** (to clone repository)

### Installation Steps

#### 1. Clone Repository
```bash
git clone https://github.com/yourusername/trading-dashboard.git
cd trading-dashboard
cd frontend-react
```

#### 2. Install Node.js Dependencies
```bash
npm install
```

**This installs:**
- React 18.2.0 and dependencies
- Vite bundler and plugins
- TypeScript, ESLint
- Tailwind CSS and PostCSS
- Express.js for backend API

#### 3. Set Environment Variables
Create `.env` file in `frontend-react/` directory:
```bash
# Logs directory where dashboard writes config files
LOGS_DIR=/Users/manojkumar/Documents/GitHub/openalgo_buying_setups/logs
```

Or set shell environment:
```bash
export LOGS_DIR=/Users/manojkumar/Documents/GitHub/openalgo_buying_setups/logs
```

#### 4. Python Setup (In project root)
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

#### 5. Verify Setup
```bash
# Check Node.js
node --version   # Should be 18+
npm --version    # Should be 9+

# Check Python
python3 --version  # Should be 3.9+
pip list | grep -E "pandas|numpy"  # Strategy dependencies
```

---

## Running the Dashboard

### Start All Services (Recommended)

From `frontend-react/` directory:

```bash
# Run React dev server + Express backend + Python daemon (with orchestration)
npm run dev
```

This concurrently runs:
1. Express backend on `http://localhost:4000`
2. Vite dev server on `http://localhost:3000`

Then in separate terminal:
```bash
# Start Python strategy daemon
cd ..
source .venv/bin/activate
python3 strategy_daemon.py
```

### Or Run Individually

**Terminal 1 - React Dev Server:**
```bash
cd frontend-react
npm run dev
# Output: VITE v5.0.8 ready in 245 ms
#         ➜  Local:   http://localhost:3000
#         ➜  press h to show help
```

**Terminal 2 - Express Backend:**
```bash
cd frontend-react
npm run server
# Output: Express server listening on port 4000
#         Health endpoint: http://localhost:4000/health
```

**Terminal 3 - Python Daemon:**
```bash
cd project-root
source .venv/bin/activate
python3 strategy_daemon.py
# Output: Strategy Daemon started
#         Monitoring instruments_config.json for changes...
```

### Access Dashboard
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:4000
- **Health Check**: http://localhost:4000/health

---

## Configuration

### Tailwind CSS Customization

Edit `tailwind.config.js` to customize theme:

```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0A1929',      // Dark navy background
        'bg-secondary': '#132F4C',    // Slightly lighter
        'text-primary': '#FFFFFF',    // White text
        'text-secondary': '#B3B3B3',  // Gray text
        'accent-cyan': '#59D0FF',     // Cyan accent
        'accent-green': '#2BD48A',    // Green for profit
        'accent-red': '#FF7180',      // Red for loss
      },
      // ... other customizations
    }
  }
}
```

### Vite Configuration

Edit `vite.config.ts` to modify:

**Dev Server Port:**
```typescript
server: {
  port: 3000,  // Change here
  host: '0.0.0.0',  // Accessible from network
}
```

**API Proxy:**
```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:4000',  // Backend URL
      // ... other options
    }
  }
}
```

**Build Output:**
```typescript
build: {
  outDir: 'dist',  // Output directory
  // ... other build options
}
```

### Zustand Store Customization

Edit `src/stores/app.ts` to:
- Add new state properties
- Add new methods
- Modify persistence behavior

```typescript
const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      // State properties and methods
      myNewProperty: null,
      setMyNewProperty: (value) => set({ myNewProperty: value }),
    }),
    {
      name: 'app-store',  // localStorage key
      // Customize what gets persisted:
      partialize: (state) => ({
        instruments: state.instruments,  // Only persist instruments
        // ... other fields to persist
      }),
    }
  )
)
```

---

## Integration with Python Backend

### How Python and React Communicate

The React dashboard is **stateless** relative to Python execution. It coordinates via **JSON file-based IPC**:

#### Communication Channels

**Channel 1: React → Python (Instrument Configuration)**
```
React Instruments.tsx
  ↓ (useEffect on change)
  ↓ exportInstruments() 
  ↓ POST /api/instruments/export
  ↓
Express backend
  ↓ fs.writeFileSync()
  ↓
logs/instruments_config.json
  ↓ (read by daemon every 5 seconds)
  ↓
Python strategy_daemon.py
  ↓ _load_config()
  ↓ Spawns strategy subprocesses
```

**Channel 2: Python → React (Strategy Status)**
```
Python strategy_daemon.py
  ↓ _save_status()
  ↓ fs.writeFileSync()
  ↓
logs/strategies_status.json
  ↓ (polled by React every 3 seconds)
  ↓
React Instruments.tsx
  ↓ useEffect hook
  ↓ getStrategyStatus()
  ↓ GET /api/instruments/status
  ↓
Express backend
  ↓ fs.readFileSync()
  ↓
React component
  ↓ setStrategyStatus(status)
  ↓ Re-render with latest status
```

### File Formats

**instruments_config.json** (Written by React, Read by Python):
```json
{
  "exported_at": "2026-10-09T12:30:45.123Z",
  "instruments": [
    {
      "id": "inst-1",
      "name": "NIFTY",
      "brokerSymbol": "NIFTY50",
      "strategy": "2BC",
      "status": true,
      "atmPrice": 27500,
      "minPremium": 10,
      "maxPremium": 500,
      "breakeven_rr": 1.0,
      "trail_step_rr": 0.5,
      "max_initial_risk_points": 20.0,
      "lotSizeAdjustment": 1,
      "monitoringStartTime": "09:15",
      "monitoringEndTime": "15:30"
    }
  ]
}
```

**strategies_status.json** (Written by Python, Read by React):
```json
{
  "updated_at": "2026-10-09T12:35:12.456Z",
  "running_strategies": {
    "inst-1": {
      "pid": 12345,
      "status": "running",
      "started_at": "2026-10-09T12:30:00.000Z",
      "instrument_name": "NIFTY",
      "strategy": "2BC",
      "error": null
    }
  }
}
```

### Python Broker Connection

Strategy core logic connects to broker via **OpenAlgo API**:

```python
# In strategies/2bc.py
from core.broker import BrokerConnection

broker = BrokerConnection()
broker.subscribe('NIFTY', '3-min')  # Subscribe to 3-minute candles

for candle in broker.listen():
    signal = strategy.process_candle(candle)
    if signal == Signal.BUY_CE:
        broker.place_order(...)
```

### Risk Config Flow

Risk parameters configured in React are passed through:

```
React UI Input:
  breakeven_rr = 1.0
  trail_step_rr = 0.5
  max_initial_risk_points = 20.0
  ↓
instruments_config.json
  ↓
Python daemon passes to strategy subprocess
  ↓
Strategy core logic applies during trade execution:
  - At 1.0 × risk: Move SL to breakeven
  - Every 0.5 × risk thereafter: Trail SL up
  - Never take trade with initial risk > 20 points
```

---

## Testing & Debugging

### Run Type Checking
```bash
npm run type-check
# TypeScript compiler checks all files for type errors
```

### Run Linter
```bash
npm run lint
# ESLint checks code quality and style
```

### Build for Production
```bash
npm run build
# Outputs to dist/ directory
# Ready to deploy
```

### Debug Mode
Open browser DevTools (F12):
- **Console**: React/JavaScript errors and logs
- **Network**: API requests to backend
- **React DevTools** (browser extension): Inspect component tree and props
- **Storage → Application → Local Storage**: View persisted Zustand state

### Common Issues & Solutions

**Issue: "Cannot find module 'strategies.2bc'"**
- Solution: Ensure `strategies/2bc.py` file exists
- Run: `ls strategies/2bc.py`

**Issue: "Strategy registration not working"**
- Solution: Check `run_strategy.py` registry contains all 6 strategies
- Run validation: `python3 -c "import run_strategy; print(list(run_strategy.STRATEGY_REGISTRY.keys()))"`

**Issue: Instruments not exporting to backend**
- Solution: Check Express backend is running on port 4000
- Verify: `curl http://localhost:4000/health`
- Check logs: Browser console (F12) for 404 errors

**Issue: React showing "Crashed" status for all strategies**
- Solution: Python daemon may not be running
- Start: `python3 strategy_daemon.py`
- Check: `logs/strategies_status.json` should be updated every 5 seconds

---

## Summary

The **React Trading Dashboard** is a comprehensive, modern web application for managing automated trading strategies. It provides:

✅ **Strategic Trading Control**: Add/edit/monitor instruments with configurable strategies
✅ **Real-Time Status**: See which strategies are running and their PIDs
✅ **Risk Management**: Configure breakeven, trailing stoploss, and risk caps
✅ **Performance Analytics**: Charts, statistics, and historical trade analysis
✅ **Professional UI**: Dark theme, responsive design, real-time updates
✅ **Python Integration**: Seamless bridge to strategy core logic via JSON IPC
✅ **6 Trading Strategies**: 21EMA, HD, CD, TC, 2BC (new), BO (new)

**Technology Stack**: React 18 + TypeScript 5 + Vite 5 + Tailwind CSS + Zustand + Express.js 4 + Node.js

**Ports**: Frontend 3000, Backend 4000, Python Daemon (varies)

**For Questions**: Refer to individual file documentation or review TypeScript type definitions in `src/types/`
