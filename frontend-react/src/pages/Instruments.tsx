import { useState } from 'react'
import { Plus, Trash2, Edit2, Power, AlertCircle, CheckCircle2 } from 'lucide-react'
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
}

const Instruments: React.FC = () => {
  const { instruments, addInstrument, updateInstrument, deleteInstrument, toggleInstrument } = useAppStore()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [strategyFilter, setStrategyFilter] = useState<string>('ALL')
  const [filterStatus, setFilterStatus] = useState<string>('ALL')
  const [formData, setFormData] = useState<FormData>({
    name: '',
    brokerSymbol: '',
    monitoringStartTime: '09:15',
    monitoringEndTime: '15:30',
    lotSizeAdjustment: 1,
    strategy: '21EMA',
  })

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

    if (editingId) {
      updateInstrument(editingId, {
        ...formData,
        lotSize,
        strikeStep,
        strategy: formData.strategy as '21EMA' | 'HD' | 'CD' | 'TC' | '2BC' | 'BO',
        productType: 'INTRADAY',
      })
      setEditingId(null)
    } else {
      addInstrument({
        id: `inst-${Date.now()}`,
        ...formData,
        lotSize,
        strikeStep,
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
                placeholder="e.g., NIFTY, BANKNIFTY"
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
                step="0.1"
                value={formData.lotSizeAdjustment}
                onChange={(e) => setFormData({ ...formData, lotSizeAdjustment: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Calculated Lot Size</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                {calculateLotSize(formData.name)} (Read-only)
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
              <label className="block text-sm font-medium text-text-secondary mb-2">Strike Step</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                {getStrikeStep(formData.strategy)} (Read-only)
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Product Type</label>
              <div className="w-full px-3 py-2 bg-bg-primary border border-bg-tertiary rounded-lg text-text-primary font-semibold">
                INTRADAY (Fixed)
              </div>
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
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Strike Step</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Monitoring</th>
                  <th className="px-6 py-4 text-left text-sm font-semibold text-text-secondary">Status</th>
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
                    <td className="px-6 py-4 text-text-secondary font-mono">{inst.lotSize || calculateLotSize(inst.name)}</td>
                    <td className="px-6 py-4 text-text-secondary font-mono">{inst.strikeStep}</td>
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
