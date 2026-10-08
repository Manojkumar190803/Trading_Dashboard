import { useState, useEffect } from 'react'
import { Plus, Trash2, Edit2, Power, AlertCircle, CheckCircle2, Play, Square } from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '@/stores'
import { Instrument } from '@/types'

const STRATEGIES = ['21EMA', 'HD', 'CD', 'TC', '2BC', 'BO']

// Lot size mapping by instrument
const LOT_SIZE_MAP: Record<string, number> = {
  'NIFTY': 65,
  'NIFTY50': 65,
  'BANKNIFTY': 30,
  'SENSEX': 20,
}

// Strike step mapping by strategy
const STRIKE_STEP_MAP: Record<string, number> = {
  '21EMA': 50,  // NIFTY default
  'HD': 50,
  'CD': 50,
  'TC': 50,
  '2BC': 50,
  'BO': 50,
}

interface FormData {
  name: string
  brokerSymbol: string
  monitoringStartTime: string
  monitoringEndTime: string
  lotSizeAdjustment: number
  strategy: string
  atmPrice: number
  minPremium: number
  maxPremium: number
  breakeven_rr: number
  trail_step_rr: number
  max_initial_risk_points: number
}

const Instruments: React.FC = () => {
  const { instruments, addInstrument, updateInstrument, deleteInstrument, toggleInstrument, exportInstruments, getStrategyStatus } = useAppStore()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [strategyFilter, setStrategyFilter] = useState<string>('ALL')
  const [filterStatus, setFilterStatus] = useState<string>('ALL')
  const [strategyStatus, setStrategyStatus] = useState<Record<string, any>>({})
  const [formData, setFormData] = useState<FormData>({
    name: '',
    brokerSymbol: '',
    monitoringStartTime: '09:15',
    monitoringEndTime: '15:30',
    lotSizeAdjustment: 1,
    strategy: '21EMA',
    atmPrice: 0,
    minPremium: 0,
    maxPremium: 0,
    breakeven_rr: 1.0,
    trail_step_rr: 0.5,
    max_initial_risk_points: 20.0,
  })

  // Auto-export instruments when they change
  useEffect(() => {
    const exportInsts = async () => {
      try {
        await exportInstruments()
      } catch (error) {
        console.error('Failed to export instruments:', error)
      }
    }
    exportInsts()
  }, [instruments, exportInstruments])

  // Poll strategy status every 3 seconds
  useEffect(() => {
    const pollStatus = async () => {
      try {
        const status = await getStrategyStatus()
        if (status) {
          setStrategyStatus(status.running_strategies || {})
        }
      } catch (error) {
        console.error('Failed to get strategy status:', error)
      }
    }
    
    pollStatus()
    const interval = setInterval(pollStatus, 3000)
    return () => clearInterval(interval)
  }, [getStrategyStatus])

  const calculateLotSize = (instrumentName: string): number => {
    const normalized = instrumentName.toUpperCase()
    return LOT_SIZE_MAP[normalized] || 1
  }

  const getStrikeStep = (strategyName: string): number => {
    return STRIKE_STEP_MAP[strategyName] || 50
  }

  const filteredInstruments = instruments.filter((inst) => {
    const matchSearch = inst.name.toLowerCase().includes(searchTerm.toLowerCase())
    const matchStrategy = strategyFilter === 'ALL' || inst.strategy === strategyFilter
    const matchStatus = filterStatus === 'ALL' || (filterStatus === 'ACTIVE' ? inst.status : !inst.status)
    return matchSearch && matchStrategy && matchStatus
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!formData.name || !formData.brokerSymbol || !formData.monitoringStartTime || !formData.monitoringEndTime || !formData.strategy) {
      alert('Please fill in all required fields')
      return
    }

    const lotSize = calculateLotSize(formData.name)
    const strikeStep = getStrikeStep(formData.strategy)
    // For 21EMA, ATM price is auto-locked by the system, so clear manual input
    // For other strategies, use premium range for strike monitoring
    const atmPrice = formData.strategy === '21EMA' ? 0 : formData.atmPrice
    const minPremium = formData.strategy === '21EMA' ? 0 : formData.minPremium
    const maxPremium = formData.strategy === '21EMA' ? 0 : formData.maxPremium

    if (editingId) {
      updateInstrument(editingId, {
        ...formData,
        atmPrice,
        minPremium,
        maxPremium,
        breakeven_rr: formData.breakeven_rr,
        trail_step_rr: formData.trail_step_rr,
        max_initial_risk_points: formData.max_initial_risk_points,
        lotSize,
        strikeStep: formData.strategy === '21EMA' ? 0 : strikeStep,
        strategy: formData.strategy as '21EMA' | 'HD' | 'CD' | 'TC' | '2BC' | 'BO',
        productType: 'INTRADAY',
      })
      setEditingId(null)
    } else {
      addInstrument({
        id: `inst-${Date.now()}`,
        ...formData,
        atmPrice,
        minPremium,
        maxPremium,
        breakeven_rr: formData.breakeven_rr,
        trail_step_rr: formData.trail_step_rr,
        max_initial_risk_points: formData.max_initial_risk_points,
        lotSize,
        strikeStep: formData.strategy === '21EMA' ? 0 : strikeStep,
        strategy: formData.strategy as '21EMA' | 'HD' | 'CD' | 'TC' | '2BC' | 'BO',
        productType: 'INTRADAY',
        status: true,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })
    }

    setFormData({
      name: '',
      brokerSymbol: '',
      monitoringStartTime: '09:15',
      monitoringEndTime: '15:30',
      lotSizeAdjustment: 1,
      strategy: '21EMA',
      atmPrice: 0,
      minPremium: 0,
      maxPremium: 0,
      breakeven_rr: 1.0,
      trail_step_rr: 0.5,
      max_initial_risk_points: 20.0,
    })
    setShowForm(false)
  }

  const handleEdit = (inst: Instrument) => {
    setFormData({
      name: inst.name,
      brokerSymbol: inst.brokerSymbol,
      monitoringStartTime: inst.monitoringStartTime,
      monitoringEndTime: inst.monitoringEndTime,
      lotSizeAdjustment: inst.lotSizeAdjustment,
      strategy: inst.strategy,
      atmPrice: inst.atmPrice || 0,
      minPremium: inst.minPremium || 0,
      maxPremium: inst.maxPremium || 0,
      breakeven_rr: inst.breakeven_rr || 1.0,
      trail_step_rr: inst.trail_step_rr || 0.5,
      max_initial_risk_points: inst.max_initial_risk_points || 20.0,
    })
    setEditingId(inst.id)
    setShowForm(true)
  }

  const handleCancel = () => {
    setShowForm(false)
    setEditingId(null)
    setFormData({
      name: '',
      brokerSymbol: '',
      monitoringStartTime: '09:15',
      monitoringEndTime: '15:30',
      lotSizeAdjustment: 1,
      strategy: '21EMA',
      atmPrice: 0,
      minPremium: 0,
      maxPremium: 0,
      breakeven_rr: 1.0,
      trail_step_rr: 0.5,
      max_initial_risk_points: 20.0,
    })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-text-primary">Instruments</h1>
          <p className="text-text-secondary mt-1">Manage trading instruments and monitoring configurations</p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-accent-cyan to-accent-blue text-bg-primary rounded-lg hover:shadow-lg hover:shadow-accent-cyan/50 transition-all duration-200 font-semibold"
        >
          <Plus size={20} />
          Add Instrument
        </button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <input
          type="text"
          placeholder="Search by name..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="px-4 py-2 bg-bg-secondary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
        />
        <select
          value={strategyFilter}
          onChange={(e) => setStrategyFilter(e.target.value)}
          className="px-4 py-2 bg-bg-secondary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
        >
          <option value="ALL">All Strategies</option>
          {STRATEGIES.map((strat) => (
            <option key={strat} value={strat}>{strat}</option>
          ))}
        </select>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="px-4 py-2 bg-bg-secondary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
        >
          <option value="ALL">All Status</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>

      {/* Add/Edit Form */}
      {showForm && (
        <div className="bg-bg-secondary border border-bg-tertiary rounded-lg p-6 space-y-4">
          <h2 className="text-xl font-semibold text-text-primary">
            {editingId ? 'Edit Instrument' : 'Add New Instrument'}
          </h2>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Instrument Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., NIFTY, BANKNIFTY, SENSEX"
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Broker Symbol *
              </label>
              <input
                type="text"
                value={formData.brokerSymbol}
                onChange={(e) => setFormData({ ...formData, brokerSymbol: e.target.value })}
                placeholder="e.g., NIFTY50, BANKNIFTY"
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
              <p className="text-xs text-text-tertiary mt-1">Symbol used by your broker for this instrument</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Monitoring Start Time *
              </label>
              <input
                type="time"
                value={formData.monitoringStartTime}
                onChange={(e) => setFormData({ ...formData, monitoringStartTime: e.target.value })}
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Monitoring End Time *
              </label>
              <input
                type="time"
                value={formData.monitoringEndTime}
                onChange={(e) => setFormData({ ...formData, monitoringEndTime: e.target.value })}
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Lot Size Adjustment</label>
              <input
                type="number"
                step="1"
                min="1"
                value={formData.lotSizeAdjustment}
                onChange={(e) => {
                  const value = e.target.value
                  if (value === '') {
                    setFormData({ ...formData, lotSizeAdjustment: 1 })
                  } else {
                    const intValue = Math.max(1, parseInt(value) || 1)
                    setFormData({ ...formData, lotSizeAdjustment: intValue })
                  }
                }}
                onBlur={(e) => {
                  // Ensure value is at least 1 on blur
                  const value = parseInt(e.target.value) || 1
                  setFormData({ ...formData, lotSizeAdjustment: Math.max(1, value) })
                }}
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Base Lot Size</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                {calculateLotSize(formData.name)} (Read-only)
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Total Quantity</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-accent-cyan/50 rounded-lg text-text-primary font-bold text-lg">
                <span className="text-accent-cyan">{formData.lotSizeAdjustment}</span>
                <span className="text-text-secondary mx-1">×</span>
                <span className="text-accent-green">{calculateLotSize(formData.name)}</span>
                <span className="text-text-secondary mx-1">=</span>
                <span className="text-accent-green">{formData.lotSizeAdjustment * calculateLotSize(formData.name)}</span>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Select Strategy *</label>
              <select
                value={formData.strategy}
                onChange={(e) => setFormData({ ...formData, strategy: e.target.value })}
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              >
                {STRATEGIES.map((strat) => (
                  <option key={strat} value={strat}>{strat}</option>
                ))}
              </select>
            </div>
            {formData.strategy !== '21EMA' && (
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">Strike Step</label>
                <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                  {getStrikeStep(formData.strategy)} (Read-only)
                </div>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Product Type</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                INTRADAY (Fixed)
              </div>
            </div>
            {formData.strategy === '21EMA' ? (
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  ATM Price (Auto-Locked at 9:20 AM)
                </label>
                <div className="w-full px-3 py-2 bg-bg-primary border border-accent-cyan/40 rounded-lg text-text-primary font-semibold text-accent-cyan">
                  {formData.atmPrice > 0 ? formData.atmPrice.toFixed(2) : 'Locked during market hours'}
                </div>
                <p className="text-xs text-text-tertiary mt-1">Automatically captured by the system at 9:20 AM</p>
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Min Premium Range
                </label>
                <input
                  type="number"
                  step="1"
                  min="0"
                  value={formData.minPremium || ''}
                  onChange={(e) => setFormData({ ...formData, minPremium: parseInt(e.target.value) || 0 })}
                  placeholder="e.g., 120"
                  className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                />
                <p className="text-xs text-text-tertiary mt-1">Minimum premium to monitor (integers only)</p>
              </div>
            )}
            {formData.strategy !== '21EMA' && (
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Max Premium Range
                </label>
                <input
                  type="number"
                  step="1"
                  min="0"
                  value={formData.maxPremium || ''}
                  onChange={(e) => setFormData({ ...formData, maxPremium: parseInt(e.target.value) || 0 })}
                  placeholder="e.g., 170"
                  className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                />
                <p className="text-xs text-text-tertiary mt-1">Maximum premium to monitor (integers only)</p>
              </div>
            )}
            {/* Trailing Stoploss Mechanism - Applied to all strategies */}
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Breakeven RR (At 1R Milestone)
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="5"
                value={formData.breakeven_rr || ''}
                onChange={(e) => setFormData({ ...formData, breakeven_rr: parseFloat(e.target.value) || 1.0 })}
                placeholder="e.g., 1.0"
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
              <p className="text-xs text-text-tertiary mt-1">Move stop to entry price at 1R (default: 1.0)</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Trail Step RR (Per 0.5R Milestone)
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="5"
                value={formData.trail_step_rr || ''}
                onChange={(e) => setFormData({ ...formData, trail_step_rr: parseFloat(e.target.value) || 0.5 })}
                placeholder="e.g., 0.5"
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
              <p className="text-xs text-text-tertiary mt-1">Advance stop by this amount at each 0.5R (default: 0.5)</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Max Initial Risk Points
              </label>
              <input
                type="number"
                step="1"
                min="1"
                max="100"
                value={formData.max_initial_risk_points || ''}
                onChange={(e) => setFormData({ ...formData, max_initial_risk_points: parseFloat(e.target.value) || 20.0 })}
                placeholder="e.g., 20"
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
              <p className="text-xs text-text-tertiary mt-1">Discard setup if initial risk exceeds this (default: 20)</p>
            </div>
            <div className="col-span-1 md:col-span-3 flex gap-3">
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-accent-cyan text-bg-primary rounded-lg hover:bg-accent-cyan/90 transition-colors font-semibold"
              >
                {editingId ? 'Update' : 'Add'} Instrument
              </button>
              <button
                type="button"
                onClick={handleCancel}
                className="flex-1 px-4 py-2 bg-bg-tertiary text-text-primary rounded-lg hover:bg-bg-tertiary/80 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Instruments Table */}
      <div className="bg-bg-secondary rounded-lg border border-bg-tertiary overflow-hidden">
        {filteredInstruments.length === 0 ? (
          <div className="text-center py-12">
            <AlertCircle size={48} className="mx-auto text-text-tertiary mb-4" />
            <p className="text-text-secondary">No instruments configured yet. Add one to get started!</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-bg-tertiary bg-bg-primary">
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Name</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Broker Symbol</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Strategy</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Lot Size</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Price Range</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Stoploss Config</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Monitoring</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Status</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Strategy Running</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-text-secondary">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredInstruments.map((inst) => (
                  <tr
                    key={inst.id}
                    className="border-b border-bg-tertiary hover:bg-bg-primary/50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <span className="font-semibold text-text-primary">{inst.name}</span>
                    </td>
                    <td className="px-6 py-4 text-text-secondary font-mono text-sm">{inst.brokerSymbol}</td>
                    <td className="px-6 py-4">
                      <span
                        className={clsx(
                          'px-3 py-1 rounded-full text-xs font-medium',
                          inst.strategy === '21EMA'
                            ? 'bg-accent-cyan/20 text-accent-cyan'
                            : inst.strategy === 'HD'
                              ? 'bg-accent-blue/20 text-accent-blue'
                              : inst.strategy === 'CD'
                                ? 'bg-accent-green/20 text-accent-green'
                                : inst.strategy === 'TC'
                                  ? 'bg-accent-yellow/20 text-accent-yellow'
                                  : inst.strategy === '2BC'
                                    ? 'bg-accent-red/20 text-accent-red'
                                    : 'bg-accent-purple/20 text-accent-purple'
                        )}
                      >
                        {inst.strategy}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-text-secondary font-mono">
                      <div>{inst.lotSizeAdjustment} × {inst.lotSize}</div>
                      <div className="text-xs text-text-tertiary">= {inst.lotSizeAdjustment * (inst.lotSize || 0)} qty</div>
                    </td>
                    <td className="px-6 py-4 text-text-secondary font-mono">
                      {inst.strategy === '21EMA' ? (
                        inst.atmPrice ? (
                          <span className="text-accent-cyan font-semibold">{inst.atmPrice.toFixed(2)}</span>
                        ) : (
                          <span className="text-text-tertiary italic">Auto-locked</span>
                        )
                      ) : (
                        inst.minPremium || inst.maxPremium ? (
                          <span className="text-accent-green font-semibold">
                            {inst.minPremium?.toFixed(0) || '0'} - {inst.maxPremium?.toFixed(0) || '0'}
                          </span>
                        ) : (
                          <span className="text-text-tertiary italic">—</span>
                        )
                      )}
                    </td>
                    <td className="px-6 py-4 text-text-secondary text-sm">
                      {inst.monitoringStartTime} → {inst.monitoringEndTime}
                    </td>
                    <td className="px-6 py-4 text-text-secondary text-sm font-mono">
                      <div className="flex flex-col gap-1">
                        <div><span className="text-text-tertiary text-xs">BE:</span> {inst.breakeven_rr?.toFixed(1) || '1.0'}R</div>
                        <div><span className="text-text-tertiary text-xs">Trail:</span> {inst.trail_step_rr?.toFixed(1) || '0.5'}R</div>
                        <div><span className="text-text-tertiary text-xs">Max Risk:</span> {inst.max_initial_risk_points?.toFixed(0) || '20'} pts</div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {inst.status ? (
                          <CheckCircle2 size={18} className="text-accent-green" />
                        ) : (
                          <AlertCircle size={18} className="text-accent-red" />
                        )}
                        <span className={inst.status ? 'text-accent-green' : 'text-accent-red'}>
                          {inst.status ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {(() => {
                        const status = strategyStatus[inst.id]
                        if (!status) {
                          return <span className="text-text-tertiary text-sm">Not running</span>
                        }
                        return (
                          <div className="flex items-center gap-2">
                            {status.status === 'running' ? (
                              <>
                                <div className="w-2 h-2 bg-accent-green rounded-full animate-pulse"></div>
                                <span className="text-accent-green text-sm font-semibold">Running (PID: {status.pid})</span>
                              </>
                            ) : status.status === 'crashed' ? (
                              <>
                                <AlertCircle size={16} className="text-accent-red" />
                                <span className="text-accent-red text-sm">Crashed</span>
                              </>
                            ) : status.status === 'stopped' ? (
                              <>
                                <Square size={16} className="text-text-tertiary" />
                                <span className="text-text-tertiary text-sm">Stopped</span>
                              </>
                            ) : (
                              <span className="text-accent-yellow text-sm">{status.status}</span>
                            )}
                          </div>
                        )
                      })()}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={() => toggleInstrument(inst.id)}
                          className="p-2 hover:bg-bg-tertiary rounded transition-colors text-text-secondary hover:text-accent-cyan"
                          title={inst.status ? 'Disable' : 'Enable'}
                        >
                          <Power size={18} />
                        </button>
                        <button
                          onClick={() => handleEdit(inst)}
                          className="p-2 hover:bg-bg-tertiary rounded transition-colors text-text-secondary hover:text-accent-cyan"
                          title="Edit"
                        >
                          <Edit2 size={18} />
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm(`Delete ${inst.name}?`)) {
                              deleteInstrument(inst.id)
                            }
                          }}
                          className="p-2 hover:bg-bg-tertiary rounded transition-colors text-text-secondary hover:text-accent-red"
                          title="Delete"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Summary */}
      {filteredInstruments.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-bg-secondary rounded-lg border border-bg-tertiary p-4">
            <p className="text-text-secondary text-sm mb-1">Total Instruments</p>
            <p className="text-2xl font-bold text-accent-cyan">{instruments.length}</p>
          </div>
          <div className="bg-bg-secondary rounded-lg border border-bg-tertiary p-4">
            <p className="text-text-secondary text-sm mb-1">Active</p>
            <p className="text-2xl font-bold text-accent-green">
              {instruments.filter((i) => i.status).length}
            </p>
          </div>
          <div className="bg-bg-secondary rounded-lg border border-bg-tertiary p-4">
            <p className="text-text-secondary text-sm mb-1">Inactive</p>
            <p className="text-2xl font-bold text-accent-red">
              {instruments.filter((i) => !i.status).length}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default Instruments
