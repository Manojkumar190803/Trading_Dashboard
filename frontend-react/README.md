# Trading Dashboard - Frontend React App

A professional, modern trading dashboard built with **React 18**, **TypeScript**, **Tailwind CSS**, and **Vite**. This application provides real-time monitoring of trading strategies, positions, orders, and analytics with a beautiful dark-themed UI.

## 🎯 Features

### Core Pages
- **Dashboard** - Real-time control room with key metrics, pre-market readiness checks, and recent alerts
- **Positions** - Monitor open positions, entry prices, P&L, and pending entries
- **Orderbook** - Track all orders placed (open, filled, cancelled)
- **Analytics** - Performance charts, equity curve, trade distribution, and statistics
- **Logs** - Detailed system logs with filtering by level and strategy

### Key Capabilities
- ✅ Real-time data polling from CSV/JSON files
- ✅ Professional dark theme with custom color palette
- ✅ Responsive design (desktop-first, mobile support planned)
- ✅ Interactive charts using Recharts
- ✅ Global state management with Zustand
- ✅ TypeScript strict mode for type safety
- ✅ Component-based architecture with reusable UI components
- ✅ Custom hooks for data fetching
- ✅ Path aliases for clean imports
- ✅ Fast HMR with Vite dev server

## 🚀 Getting Started

### Prerequisites
- Node.js 18+ (with npm or yarn)
- Git

### Installation

```bash
# Clone the repository (if separate)
cd frontend-react

# Install dependencies
npm install

# Create environment file
cp .env.example .env
```

### Development

```bash
# Start development server
npm run dev

# The app will open at http://localhost:3000 with hot module replacement
```

### Build

```bash
# Type check
npm run type-check

# Build for production
npm run build

# Preview production build
npm run preview
```

### Linting

```bash
# Run ESLint
npm run lint
```

## 📁 Project Structure

```
frontend-react/
├── src/
│   ├── components/
│   │   ├── Layout.tsx          # Main layout with sidebar
│   │   └── UI.tsx              # Reusable UI components
│   ├── pages/
│   │   ├── Dashboard.tsx       # Dashboard page
│   │   ├── Positions.tsx       # Positions page
│   │   ├── Orderbook.tsx       # Orders page
│   │   ├── Analytics.tsx       # Analytics page
│   │   └── Logs.tsx            # Logs page
│   ├── hooks/
│   │   └── useData.ts          # Custom data fetching hooks
│   ├── stores/
│   │   └── app.ts             # Zustand global store
│   ├── styles/
│   │   └── globals.css        # Global styles and animations
│   ├── types/
│   │   └── index.ts           # TypeScript interfaces
│   ├── utils/
│   │   ├── format.ts          # Formatting utilities
│   │   ├── files.ts           # File I/O utilities
│   │   └── index.ts           # Barrel exports
│   ├── App.tsx                # Main app component
│   └── main.tsx               # React entry point
├── index.html                 # HTML entry point
├── package.json              # Dependencies and scripts
├── tsconfig.json             # TypeScript configuration
├── vite.config.ts            # Vite configuration
├── tailwind.config.ts        # Tailwind CSS configuration
└── .env.example              # Environment variables template
```

## 🔌 Data Sources

The dashboard reads data from CSV and JSON files in the `/logs/` directory:

### Alerts
- **File**: `trade_alerts_YYYYMMDD.csv`
- **Columns**: timestamp, category, message, strategy, symbol
- **Categories**: ENTRY, EXIT, TARGET, SL, SIGNAL, PENDING_ENTRY, PROTECTIVE_SL, TSL, ERROR

### Analytics Trades
- **File**: `analytics_trades.csv`
- **Columns**: timestamp, strategy, pnl, source, message

### Monitoring Logs
- **File**: `monitoring_YYYYMMDD.csv`
- **Columns**: timestamp, level, message, category, strategy

### Dashboard Preferences
- **File**: `dashboard_preferences.json`
- **Structure**: User preferences and UI state

## 🎨 Design System

### Color Palette
- **Primary Background**: `#0a0e27`
- **Accent Cyan**: `#59d0ff` (primary accent)
- **Accent Green**: `#27d48a` (profit, success)
- **Accent Red**: `#ff5f6d` (loss, danger)
- **Accent Yellow**: `#ffbe32` (warning)
- **Accent Blue**: `#4a9eff` (info)

### Tailwind Configuration
All colors and animations are defined in `tailwind.config.ts` with custom extensions:
- Custom shadows with glow effects
- Smooth animations (fadeIn, slideIn, pulse-soft)
- Extended opacity and spacing scales

## 🔧 Available Scripts

```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run preview      # Preview production build
npm run type-check   # Run TypeScript type checker
npm run lint         # Run ESLint
```

## 📊 Component Documentation

### UI Components (from `components/UI.tsx`)

#### Card
```tsx
<Card hoverable>
  <p>Content</p>
</Card>
```

#### MetricCard
```tsx
<MetricCard
  label="Net P&L"
  value="₹1,234.50"
  color="green"
  trend="up"
/>
```

#### Badge
```tsx
<Badge variant="success">Active</Badge>
```

#### Table
```tsx
<Table headers={['Name', 'Value']}>
  <TableRow>
    <TableCell>Item 1</TableCell>
    <TableCell>Value 1</TableCell>
  </TableRow>
</Table>
```

## 🪝 Custom Hooks

### useStrategyAlerts
```tsx
const { alerts, isLoading, error, refetch } = useStrategyAlerts(shouldWatch)
```
Fetches and watches strategy alerts from CSV files.

### useAnalyticsTrades
```tsx
const { trades, isLoading, error, refetch } = useAnalyticsTrades()
```
Fetches analytics trades data.

### useEquityCurve
```tsx
const curve = useEquityCurve(trades)
```
Generates equity curve data from trades.

### useLiveMetrics
```tsx
const { lastUpdate } = useLiveMetrics()
```
Triggers periodic updates for live metrics.

## 🌐 Global State Management

State is managed with **Zustand** in `stores/app.ts`:

```tsx
import { useAppStore } from '@/stores'

const { metrics, setMetrics, positions, setPositions } = useAppStore()
```

Available store slices:
- Dashboard metrics
- Positions
- Trades
- Equity curve
- Alerts
- Orders
- Logs
- UI state (sidebar, current page, auto-refresh)
- Loading and error states

## 🚀 Performance Optimizations

- **Code splitting**: Separate chunks for React, charts, and utilities
- **Lazy loading**: Pages loaded on demand via React Router
- **Memoization**: Components wrapped with React.memo where appropriate
- **Polling optimization**: Configurable intervals (2-5 seconds)
- **History capping**: Alerts (500), Logs (200) to prevent memory bloat

## 🔮 Future Enhancements

- [ ] WebSocket integration for real-time updates (replacing polling)
- [ ] Dark/Light theme toggle
- [ ] Export functionality (charts, tables as PDF/CSV)
- [ ] Toast notifications system
- [ ] Error boundaries and fallback UI
- [ ] Mobile responsive improvements
- [ ] Advanced filtering and search
- [ ] Custom dashboard layouts
- [ ] Performance metrics and profiling

## 🤝 Contributing

This is a personal project for resume purposes. Enhancements and improvements will be added based on requirements.

## 📝 License

Private project - Not for public distribution.

## 💡 Notes

- All data is read from CSV/JSON files (no backend database)
- Uses Streamlit dashboard as design reference
- Built with production-grade tooling and best practices
- TypeScript strict mode enforced for code quality
