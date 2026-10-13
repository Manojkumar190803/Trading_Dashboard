import { useState, useEffect, useRef } from 'react'
import { Plus, Trash2, Edit2, Power, AlertCircle, CheckCircle2, Search, ChevronDown } from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '@/stores'
import { Instrument } from '@/types'
import { useInstruments } from '@/hooks/useInstruments'

const STRATEGIES = ['21EMA', 'HD', 'CD', 'TC', '2BC', 'BO']

// Lot size mapping by instrument
const LOT_SIZE_MAP: Record<string, number> = {
  'NIFTY': 65,
  'NIFTY50': 65,
  'BANKNIFTY': 30,
  'SENSEX': 20,
}

interface FormData {
  name: string
  brokerSymbol: string
  monitoringStartTime: string
  monitoringEndTime: string
  lotSizeAdjustment: number
  strategy: string
  premiumMinPrice?: number
  premiumMaxPrice?: number
}

const Instruments: React.FC = () => {
  const { trailingStopsConfig, setTrailingStopsConfig, resetTrailingStopsConfig } = useAppStore()
  const { instruments, isLoading, error, addInstrument: apiAddInstrument, updateInstrument: apiUpdateInstrument, deleteInstrument: apiDeleteInstrument, toggleInstrument: apiToggleInstrument } = useInstruments(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [strategyFilter, setStrategyFilter] = useState<string>('ALL')
  const [symbolSuggestions, setSymbolSuggestions] = useState<string[]>([])
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false)
  const symbolDropdownRef = useRef<HTMLDivElement>(null)
  const [showTrailingConfig, setShowTrailingConfig] = useState(false)
  const [localTrailingConfig, setLocalTrailingConfig] = useState(trailingStopsConfig)
  const [symbolValidation, setSymbolValidation] = useState<{ symbol: string; valid: boolean; message: string } | null>(null)
  const [isValidatingSymbol, setIsValidatingSymbol] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formData, setFormData] = useState<FormData>({
    name: '',
    brokerSymbol: '',
    monitoringStartTime: '09:15',
    monitoringEndTime: '15:30',
    lotSizeAdjustment: 1,
    strategy: '21EMA',
    premiumMinPrice: undefined,
    premiumMaxPrice: undefined,
  })

  // Fetch symbol suggestions from API
  const fetchSymbolSuggestions = async (query: string, strategy: string) => {
    if (query.length < 1) {
      setSymbolSuggestions([])
      return
    }
    try {
      const response = await fetch(`/api/symbols/search?q=${encodeURIComponent(query)}&strategy=${encodeURIComponent(strategy)}`)
      const data = await response.json()
      setSymbolSuggestions(data.symbols || [])
      setShowSymbolDropdown(true)
    } catch (error) {
      console.error('Error fetching symbols:', error)
      setSymbolSuggestions([])
    }
  }

  // Validate symbol with OpenAlgo
  const validateSymbol = async (symbol: string) => {
    if (!symbol) return
    
    setIsValidatingSymbol(true)
    try {
      const response = await fetch('/api/symbols/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: symbol.toUpperCase() })
      })
      const data = await response.json()
      setSymbolValidation({
        symbol: symbol.toUpperCase(),
        valid: data.valid,
        message: data.message || 'Validation complete'
      })
    } catch (error) {
      console.error('Error validating symbol:', error)
      setSymbolValidation({
        symbol: symbol.toUpperCase(),
        valid: false,
        message: '❌ Error validating symbol'
      })
    } finally {
      setIsValidatingSymbol(false)
    }
  }

  useEffect(() => {
    // Debounce symbol search
    const timer = setTimeout(() => {
      if (formData.brokerSymbol.length >= 1) {
        fetchSymbolSuggestions(formData.brokerSymbol, formData.strategy)
      } else {
        setSymbolSuggestions([])
        setShowSymbolDropdown(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [formData.brokerSymbol, formData.strategy])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (symbolDropdownRef.current && !symbolDropdownRef.current.contains(e.target as Node)) {
        setShowSymbolDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Sync local trailing config with global config when it changes
  useEffect(() => {
    setLocalTrailingConfig(trailingStopsConfig)
  }, [trailingStopsConfig])

  const calculateLotSize = (instrumentName: string): number => {
    const normalized = instrumentName.toUpperCase()
    return LOT_SIZE_MAP[normalized] || 1
  }

  const filteredInstruments = instruments.filter((inst) => {
    const matchSearch = inst.name.toLowerCase().includes(searchTerm.toLowerCase())
    const matchStrategy = strategyFilter === 'ALL' || inst.strategy === strategyFilter
    return matchSearch && matchStrategy
  })
  const activeInstruments = filteredInstruments.filter((instrument) => instrument.status)
  const inactiveInstruments = filteredInstruments.filter((instrument) => !instrument.status)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!formData.name || !formData.brokerSymbol || !formData.monitoringStartTime || !formData.monitoringEndTime || !formData.strategy) {
      alert('Please fill in all required fields')
      return
    }

    // Validate premium prices for non-21EMA strategies
    if (formData.strategy !== '21EMA') {
      if (formData.premiumMinPrice === undefined || formData.premiumMaxPrice === undefined) {
        alert('Premium Min and Max prices are required for this strategy')
        return
      }
      if (formData.premiumMinPrice >= formData.premiumMaxPrice) {
        alert('Premium Min price must be less than Max price')
        return
      }
    }

    const baseLotSize = calculateLotSize(formData.name)
    const lotSize = baseLotSize * formData.lotSizeAdjustment  // Apply adjustment multiplier

    setIsSubmitting(true)
    
    const submitData = {
      name: formData.name,
      brokerSymbol: formData.brokerSymbol,
      monitoringStartTime: formData.monitoringStartTime,
      monitoringEndTime: formData.monitoringEndTime,
      lotSizeAdjustment: formData.lotSizeAdjustment,
      calculatedLotSize: lotSize,
      strategy: formData.strategy,
      productType: 'INTRADAY',
      premiumMinPrice: formData.premiumMinPrice,
      premiumMaxPrice: formData.premiumMaxPrice,
    }

    if (editingId) {
      apiUpdateInstrument(editingId, submitData).then((result) => {
        if (result.success) {
          setEditingId(null)
          handleCancel()
        } else {
          alert(`Error updating instrument: ${result.error}`)
        }
        setIsSubmitting(false)
      })
    } else {
      apiAddInstrument(submitData).then((result) => {
        if (result.success) {
          handleCancel()
        } else {
          alert(`Error creating instrument: ${result.error}`)
        }
        setIsSubmitting(false)
      })
    }
  }

  const handleEdit = (inst: Instrument) => {
    setFormData({
      name: inst.name,
      brokerSymbol: inst.brokerSymbol,
      monitoringStartTime: inst.monitoringStartTime,
      monitoringEndTime: inst.monitoringEndTime,
      lotSizeAdjustment: inst.lotSizeAdjustment,
      strategy: inst.strategy,
      premiumMinPrice: (inst as any).premiumMinPrice,
      premiumMaxPrice: (inst as any).premiumMaxPrice,
    })
    setEditingId(inst.id)
    setShowForm(true)
  }

  const handleToggle = async (inst: Instrument) => {
    const result = await apiToggleInstrument(inst.id)
    if (!result.success) {
      const action = inst.status ? 'deactivate' : 'activate'
      alert(`Unable to ${action} ${inst.name}: ${result.error}`)
    }
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
      premiumMinPrice: undefined,
      premiumMaxPrice: undefined,
    })
    setSymbolValidation(null)
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                placeholder="e.g., NIFTY, BANKNIFTY"
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
            </div>
            <div ref={symbolDropdownRef} className="relative">
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Broker Symbol * (Searchable)
              </label>
              <div className="relative">
                <div className="absolute left-3 top-3 text-text-tertiary">
                  <Search size={16} />
                </div>
                <input
                  type="text"
                  value={formData.brokerSymbol}
                  onChange={(e) => {
                    setFormData({ ...formData, brokerSymbol: e.target.value })
                    setShowSymbolDropdown(true)
                    setSymbolValidation(null)
                  }}
                  onFocus={() => setShowSymbolDropdown(true)}
                  onBlur={() => {
                    if (formData.brokerSymbol && !symbolValidation) {
                      setTimeout(() => validateSymbol(formData.brokerSymbol), 200)
                    }
                  }}
                  placeholder="e.g., NIFTY (spot) or NIFTY25DEC26000CE (option)"
                  className="w-full pl-9 pr-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                  autoComplete="off"
                />
              </div>
              
              {symbolValidation && (
                <div className={clsx(
                  "mt-2 p-2 rounded text-sm flex items-center gap-2",
                  symbolValidation.valid 
                    ? "bg-green-900/30 text-green-300" 
                    : "bg-red-900/30 text-red-300"
                )}>
                  {symbolValidation.valid ? (
                    <CheckCircle2 size={16} />
                  ) : (
                    <AlertCircle size={16} />
                  )}
                  <span>{symbolValidation.message}</span>
                </div>
              )}
              
              {showSymbolDropdown && symbolSuggestions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-bg-secondary border border-bg-tertiary rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto">
                  {symbolSuggestions.map((symbol) => (
                    <div
                      key={symbol}
                      onClick={() => {
                        setFormData({ ...formData, brokerSymbol: symbol })
                        setShowSymbolDropdown(false)
                        setTimeout(() => validateSymbol(symbol), 100)
                      }}
                      className="px-3 py-2 hover:bg-bg-tertiary cursor-pointer text-text-primary text-sm border-b border-bg-tertiary last:border-b-0"
                    >
                      ✓ {symbol}
                    </div>
                  ))}
                </div>
              )}
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
                value={formData.lotSizeAdjustment}
                onChange={(e) => setFormData({ ...formData, lotSizeAdjustment: parseInt(e.target.value) || 1 })}
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Calculated Lot Size</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                {calculateLotSize(formData.name) * formData.lotSizeAdjustment} (Read-only) = {calculateLotSize(formData.name)} × {formData.lotSizeAdjustment}
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
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Product Type</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                INTRADAY (Fixed)
              </div>
            </div>

            {/* Trailing Mechanism - Risk Ratio Step */}
            {/* Premium Price Min for Non-21EMA Strategies */}
            {formData.strategy !== '21EMA' && (
              <>
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">Premium Min Price</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    value={formData.premiumMinPrice || ''}
                    onChange={(e) => setFormData({ ...formData, premiumMinPrice: parseFloat(e.target.value) || undefined })}
                    className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                    placeholder="e.g., 25.50"
                  />
                  <p className="text-xs text-text-tertiary mt-1">Minimum option premium price</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">Premium Max Price</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    value={formData.premiumMaxPrice || ''}
                    onChange={(e) => setFormData({ ...formData, premiumMaxPrice: parseFloat(e.target.value) || undefined })}
                    className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                    placeholder="e.g., 150.75"
                  />
                  <p className="text-xs text-text-tertiary mt-1">Maximum option premium price</p>
                </div>
              </>
            )}

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
        {activeInstruments.length === 0 ? (
          <div className="text-center py-12">
            <AlertCircle size={48} className="mx-auto text-text-tertiary mb-4" />
            <p className="text-text-secondary">No active instruments match these filters.</p>
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
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Monitoring</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Status</th>
                  <th className="px-6 py-4 text-center text-sm font-semibold text-text-secondary">Actions</th>
                </tr>
              </thead>
              <tbody>
                {activeInstruments.map((inst) => (
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
                    <td className="px-6 py-4 text-text-secondary font-mono">{inst.lotSize || calculateLotSize(inst.name)}</td>
                    <td className="px-6 py-4 text-text-secondary text-sm">
                      {inst.strategy === '21EMA' ? (
                        <span className="text-text-tertiary">—</span>
                      ) : (
                        <span>
                          {(inst as any).premiumMinPrice?.toFixed(2) || '—'} - {(inst as any).premiumMaxPrice?.toFixed(2) || '—'}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-text-secondary text-sm">
                      {inst.monitoringStartTime} → {inst.monitoringEndTime}
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
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={() => void handleToggle(inst)}
                          aria-label={inst.status ? `Deactivate ${inst.name}` : `Activate ${inst.name}`}
                          className={`p-2 rounded transition-colors ${
                            inst.status 
                              ? 'text-accent-green hover:text-accent-cyan hover:bg-accent-green/10' 
                              : 'text-accent-red hover:text-accent-cyan hover:bg-accent-red/10'
                          }`}
                          title={inst.status ? 'Deactivate instrument' : 'Activate instrument'}
                        >
                          <Power size={18} />
                        </button>
                        <button
                          onClick={() => handleEdit(inst)}
                          className="p-2 hover:bg-bg-tertiary rounded transition-colors text-text-secondary hover:text-accent-cyan"
                          title="Edit instrument settings"
                        >
                          <Edit2 size={18} />
                        </button>
                        <button
                          onClick={() => {
                            const confirmMessage = `⚠️ PERMANENT DELETE\n\n"${inst.name}" will be permanently removed from the database.\n\nThis action CANNOT be undone.\n\nAre you sure?`
                            if (window.confirm(confirmMessage)) {
                              apiDeleteInstrument(inst.id)
                            }
                          }}
                          className="p-2 hover:bg-bg-tertiary rounded transition-colors text-text-secondary hover:text-accent-red hover:bg-accent-red/10"
                          title="Permanently delete (cannot undo)"
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

      {/* Divider */}
      <div className="pt-2 mt-8 border-t-2 border-accent-cyan/20"></div>

      {/* Global Trailing Stops Configuration */}
      <div className="bg-gradient-to-r from-accent-cyan/5 to-accent-blue/5 rounded-lg border-2 border-accent-cyan/40 overflow-hidden shadow-lg shadow-accent-cyan/10">
        <button
          onClick={() => setShowTrailingConfig(!showTrailingConfig)}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-accent-cyan/10 transition-colors group"
        >
          <div className="flex items-center gap-3">
            <div className="px-3 py-1 bg-accent-cyan text-bg-primary rounded-full text-xs font-bold">
              GLOBAL CONFIG
            </div>
            <h2 className="text-lg font-semibold text-text-primary group-hover:text-accent-cyan transition-colors">
              Configure Global Trailing Stops
            </h2>
          </div>
          <ChevronDown
            size={24}
            className={clsx(
              'text-accent-cyan transition-transform duration-200',
              showTrailingConfig && 'rotate-180'
            )}
          />
        </button>

        {showTrailingConfig && (
          <div className="border-t border-bg-tertiary px-6 py-6 space-y-6">
            {/* Info Box */}
            <div className="bg-bg-primary border border-accent-cyan/30 rounded-lg p-4">
              <p className="text-sm text-text-secondary">
                These settings apply globally to all strategies and instruments. Breakeven at <span className="font-semibold text-accent-cyan">{localTrailingConfig.breakEvenRR.toFixed(2)}</span> RR, 
                trailing in <span className="font-semibold text-accent-cyan">{localTrailingConfig.trailStepRR.toFixed(2)}</span> RR steps.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Breakeven RR Milestone */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">Breakeven Milestone (RR)</label>
                <input
                  type="number"
                  step="0.05"
                  min="0.5"
                  max="3.0"
                  value={localTrailingConfig.breakEvenRR}
                  onChange={(e) =>
                    setLocalTrailingConfig({
                      ...localTrailingConfig,
                      breakEvenRR: parseFloat(e.target.value) || 1.25,
                    })
                  }
                  className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                  placeholder="1.25"
                />
                <p className="text-xs text-text-tertiary mt-2">
                  At which Risk Ratio should the stop move to breakeven? (1.0 = entry+1R, 1.25 = entry+1.25R)
                </p>
              </div>

              {/* Trailing Step Size */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">Trailing Step Size (RR)</label>
                <input
                  type="number"
                  step="0.05"
                  min="0.05"
                  max="2.0"
                  value={localTrailingConfig.trailStepRR}
                  onChange={(e) =>
                    setLocalTrailingConfig({
                      ...localTrailingConfig,
                      trailStepRR: parseFloat(e.target.value) || 0.5,
                    })
                  }
                  className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                  placeholder="0.5"
                />
                <p className="text-xs text-text-tertiary mt-2">
                  How much profit to trail on each step? (0.25 = fine, 0.5 = default, 1.0 = aggressive)
                </p>
              </div>

              {/* Max Initial Risk Points */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">Max Initial Risk Points</label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="50"
                  value={localTrailingConfig.maxInitialRiskPoints}
                  onChange={(e) =>
                    setLocalTrailingConfig({
                      ...localTrailingConfig,
                      maxInitialRiskPoints: parseFloat(e.target.value) || 20,
                    })
                  }
                  className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
                  placeholder="20"
                />
                <p className="text-xs text-text-tertiary mt-2">
                  Global default for maximum initial risk. Can be overridden per instrument.
                </p>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3 pt-4 border-t border-bg-tertiary">
              <button
                onClick={() => {
                  setTrailingStopsConfig(localTrailingConfig)
                  setShowTrailingConfig(false)
                }}
                className="flex-1 px-4 py-2 bg-accent-cyan text-bg-primary rounded-lg hover:bg-accent-cyan/90 transition-colors font-semibold"
              >
                Save Configuration
              </button>
              <button
                onClick={() => {
                  setLocalTrailingConfig(trailingStopsConfig)
                  setShowTrailingConfig(false)
                }}
                className="flex-1 px-4 py-2 bg-bg-tertiary text-text-primary rounded-lg hover:bg-bg-tertiary/80 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  resetTrailingStopsConfig()
                  setLocalTrailingConfig({
                    breakEvenRR: 1.25,
                    trailStepRR: 0.5,
                    maxInitialRiskPoints: 20,
                    createdAt: new Date().toISOString(),
                    updatedAt: new Date().toISOString(),
                  })
                }}
                className="px-4 py-2 bg-accent-red/20 text-accent-red rounded-lg hover:bg-accent-red/30 transition-colors font-semibold"
              >
                Reset to Default
              </button>
            </div>
          </div>
        )}
      </div>

      {inactiveInstruments.length > 0 && (
        <section className="space-y-4" aria-labelledby="inactive-instruments-heading">
          <div className="flex items-center justify-between border-b border-accent-yellow/30 pb-3">
            <div>
              <h2 id="inactive-instruments-heading" className="text-lg font-bold text-accent-yellow">
                Inactive Instruments
              </h2>
              <p className="mt-1 text-xs text-text-secondary">
                Saved configurations, excluded from monitoring until activated.
              </p>
            </div>
            <span className="rounded-full border border-accent-yellow/30 bg-accent-yellow/10 px-3 py-1 text-xs font-bold text-accent-yellow">
              {inactiveInstruments.length} inactive
            </span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {inactiveInstruments.map((instrument) => (
              <div
                key={instrument.id}
                className="flex items-center justify-between gap-4 rounded-lg border border-l-4 border-accent-yellow/40 border-l-accent-yellow bg-gradient-to-r from-accent-yellow/10 to-bg-secondary/60 p-4"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <AlertCircle size={16} className="shrink-0 text-accent-yellow" />
                    <h3 className="truncate font-bold text-text-primary">{instrument.name}</h3>
                    <span className="shrink-0 rounded bg-accent-yellow/15 px-2 py-0.5 text-[10px] font-bold uppercase text-accent-yellow">
                      Inactive
                    </span>
                  </div>
                  <p className="mt-1 truncate pl-6 font-mono text-xs text-text-secondary">
                    {instrument.brokerSymbol} <span className="px-1 text-text-tertiary">·</span> {instrument.strategy}
                  </p>
                </div>
                <button
                  onClick={() => void handleToggle(instrument)}
                  aria-label={`Activate ${instrument.name}`}
                  title={`Activate ${instrument.name}`}
                  className="flex shrink-0 items-center gap-2 rounded border border-accent-green/40 bg-accent-green/10 px-3 py-2 text-xs font-bold text-accent-green transition-colors hover:bg-accent-green/20"
                >
                  <Power size={15} />
                  Activate
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Summary */}
      {instruments.length > 0 && (
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
