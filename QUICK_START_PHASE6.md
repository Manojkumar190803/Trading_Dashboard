# Phase 6: Quick Start Guide

## ✅ What's Been Implemented

### 1. Flask API Server (api_server.py)
- Symbol search endpoint: `/api/symbols/search?q=NIFTY`
- Connects to OpenAlgo for live symbol lookup
- Runs on port 4000 with CORS enabled
- Includes health check endpoint

### 2. React Form Enhancements
- **Searchable autocomplete** for broker symbols
  - Type 2+ characters to see suggestions
  - Debounced search (300ms) to avoid API spam
  - Click to select broker symbols
  
- **Manual Stop-Loss Override Fields** (Optional)
  - `initialSLOverride`: Override initial stop in points (e.g., 45)
  - `breakevenRROverride`: Override breakeven milestone in RR (e.g., 1.2 instead of 1.0)
  - `trailingStepRROverride`: Override trailing step in RR (e.g., 0.75 instead of 0.5)
  
- **Improved Lot Display**
  - Changed from "1 units" → "1 × 65" format
  - Shows calculation: "1 × 65 = 65 contracts"

### 3. Type Definitions
- Updated `Instrument` interface with new optional fields
- All fields persist in Zustand store

### 4. Docker Status
- ✅ Rebuilt with --no-cache (EXIT_CODE=0)
- ✅ React dashboard running on port 3000
- ✅ Strategy worker running
- ✅ Ready for testing

## 🚀 Quick Start: 3 Steps

### Step 1: Start Flask API Server

```bash
cd /Users/manojkumar/Documents/GitHub/openalgo_buying_setups

# Option A: Use the startup script
./start_api_server.sh

# Option B: Run directly
python api_server.py
```

You should see:
```
WARNING: This is a development server.
Running on http://0.0.0.0:4000
```

### Step 2: Verify Docker is Running

```bash
# Check containers
docker-compose ps

# Should show:
# react_dashboard   running
# strategy_worker   running
```

If not running:
```bash
docker-compose up -d react_dashboard strategy_worker
```

### Step 3: Test in Browser

1. Open: `http://localhost:3000`
2. Go to "Instruments" page
3. Click "Add New Instrument"
4. Fill in the form:
   - **Name**: NIFTY
   - **Broker Symbol**: Type "NIF" → Select "NIFTY25DEC26000CE"
   - **Monitoring Times**: 09:15 to 15:30
   - **Lot Size Adjustment**: 1
   - **Strategy**: 21EMA
   - **Trailing Step RR**: 0.5
   - **Scroll down → Manual Overrides**:
     - Initial SL Override: 45 (optional)
     - Breakeven RR Override: 1.0 (optional)
     - Trailing Step RR Override: 0.5 (optional)
5. Submit form
6. Verify instrument appears in table with "1 × 65" lot display

## 📋 Verification Checklist

- [ ] Flask API running on port 4000
- [ ] React dashboard opens at http://localhost:3000
- [ ] Can type in "Broker Symbol" field
- [ ] Suggestions dropdown appears (search works)
- [ ] Can select a symbol from dropdown
- [ ] Form shows "Manual Stop-Loss Overrides" section
- [ ] Can fill in override fields (all optional)
- [ ] Form submits successfully
- [ ] Lot display shows "1 × 65" format
- [ ] Edit button loads override values
- [ ] Cancel button resets form to defaults

## 🔧 Troubleshooting

### Flask API won't start

```bash
# Check if port 4000 is in use
lsof -i :4000

# Check if requirements are installed
pip install -r requirements.txt

# Try running directly
python api_server.py
```

### Browser can't reach Flask

```bash
# Verify Flask is running
curl http://localhost:4000/api/health

# Should return:
# {"status":"healthy","openalgo":"connected"}
```

### Symbol search returns empty

1. Check OpenAlgo connection: `echo $OPENALGO_API_KEY $OPENALGO_HOST`
2. Flask console should show search requests
3. Try: `curl "http://localhost:4000/api/symbols/search?q=NIFTY"`

## 📁 Files Changed

**New**:
- `api_server.py` - Flask API server
- `start_api_server.sh` - Startup script
- `PHASE_6_IMPLEMENTATION.md` - Full implementation guide

**Modified**:
- `requirements.txt` - Added flask, flask-cors
- `frontend-react/src/pages/Instruments.tsx` - Form enhancements
- `frontend-react/src/types/index.ts` - Type definitions

## 🎯 What's Next?

### For Frontend Testing:
1. Run Flask API
2. Test form with all new fields
3. Verify searchable autocomplete works
4. Verify manual overrides save correctly

### For Backend Integration:
Once form is verified working, integrate with `core/engine.py`:
```python
# Use manual values if provided, else auto-calculate
initial_sl = instrument.initialSLOverride or calculate_auto()
breakeven_rr = instrument.breakevenRROverride or 1.0
trailing_step = instrument.trailingStepRROverride or instrument.trailingStepRR
```

### For Docker Production:
Add Flask service to docker-compose.yml to run everything together.

## 📞 Support

For issues, check:
1. Flask console logs (running in terminal)
2. React browser console (F12 → Console)
3. Docker logs: `docker-compose logs react_dashboard`
4. PHASE_6_IMPLEMENTATION.md (full reference guide)

---

**Current Status**: Form complete, Docker rebuilt, ready for testing ✅
