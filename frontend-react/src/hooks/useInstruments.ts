import { useState, useEffect } from 'react'
import { Instrument } from '@/types'

interface InstrumentPayload {
  name: string
  brokerSymbol: string
  monitoringStartTime: string
  monitoringEndTime: string
  entryCutoffTime: string
  lotSizeAdjustment: number
  calculatedLotSize: number
  strategy: string
  productType: string
  premiumMinPrice?: number
  premiumMaxPrice?: number
  maxInitialRiskPoints?: number
  status?: string
}

export const useInstruments = (includeArchived = false) => {
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch instruments from backend
  const fetchInstruments = async () => {
    setIsLoading(true)
    try {
      const response = await fetch('/api/instruments')
      const data = await response.json()
      const allResponse = includeArchived
        ? await fetch('/api/instruments/debug/all')
        : null
      const allData = allResponse?.ok ? await allResponse.json() : { instruments: [] }
      
      const transformInstrument = (inst: any) => ({
        id: inst.id.toString(),
        name: inst.name,
        brokerSymbol: inst.brokerSymbol || inst.broker_symbol || inst.name.toUpperCase(),
        monitoringStartTime: inst.monitoringStartTime || inst.monitoring_start_time || '',
        monitoringEndTime: inst.monitoringEndTime || inst.monitoring_end_time || '',
        entryCutoffTime: inst.entryCutoffTime || inst.entry_cutoff_time || '14:40',
        lotSizeAdjustment: inst.lotSizeAdjustment ?? inst.lot_size_adjustment ?? 1,
        lotSize: inst.calculatedLotSize || inst.calculated_lot_size,
        strategy: inst.strategy as any,
        productType: inst.productType || inst.product_type || 'INTRADAY',
        status: inst.status === 'ACTIVE' || inst.status === true,
        premiumMinPrice: inst.premiumMinPrice || inst.premium_min_price,
        premiumMaxPrice: inst.premiumMaxPrice || inst.premium_max_price,
        maxInitialRiskPoints: inst.maxInitialRiskPoints ?? inst.max_initial_risk_points ?? 20,
        premiumOptionStrike: inst.premiumOptionStrike || inst.premium_option_strike,
        createdAt: inst.createdAt || inst.created_at,
        updatedAt: inst.updatedAt || inst.updated_at,
      })

      const activeInstruments = (data.instruments || []).map(transformInstrument)
      const activeIds = new Set(activeInstruments.map((instrument: Instrument) => instrument.id))
      const inactiveInstruments = (allData.instruments || [])
        .filter((inst: any) => inst.status === 'INACTIVE' && !activeIds.has(inst.id.toString()))
        .map(transformInstrument)
      
      setInstruments([...activeInstruments, ...inactiveInstruments])
      setError(null)
    } catch (err) {
      console.error('Error fetching instruments:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch instruments')
    } finally {
      setIsLoading(false)
    }
  }

  // Create instrument
  const addInstrument = async (formData: InstrumentPayload) => {
    try {
      let response = await fetch('/api/instruments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          brokerSymbol: formData.brokerSymbol,
          monitoringStartTime: formData.monitoringStartTime,
          monitoringEndTime: formData.monitoringEndTime,
          entryCutoffTime: formData.entryCutoffTime,
          lotSizeAdjustment: formData.lotSizeAdjustment,
          calculatedLotSize: formData.calculatedLotSize,
          strategy: formData.strategy,
          productType: formData.productType,
          premiumMinPrice: formData.premiumMinPrice,
          premiumMaxPrice: formData.premiumMaxPrice,
          maxInitialRiskPoints: formData.maxInitialRiskPoints,
        }),
      })
      
      let result = await response.json().catch(() => ({}))
      if (!response.ok && /duplicate key|uq_instrument_name/i.test(String(result.error || ''))) {
        const archivedResponse = await fetch('/api/instruments/debug/all')
        const archivedData = await archivedResponse.json()
        const archivedInstruments = archivedData.instruments || []
        const isArchived = (instrument: { id: number; name: string; status: string }) => instrument.status !== 'ACTIVE'
        const archived = archivedInstruments.find((instrument: { id: number; name: string; status: string }) =>
          instrument.name.trim() === formData.name.trim() && isArchived(instrument)
        ) || archivedInstruments.find((instrument: { id: number; name: string; status: string }) =>
          instrument.name.trim().toLowerCase() === formData.name.trim().toLowerCase()
          && isArchived(instrument)
        )

        if (archived) {
          response = await fetch(`/api/instruments/${archived.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: formData.name,
              brokerSymbol: formData.brokerSymbol,
              monitoringStartTime: formData.monitoringStartTime,
              monitoringEndTime: formData.monitoringEndTime,
              entryCutoffTime: formData.entryCutoffTime,
              lotSizeAdjustment: formData.lotSizeAdjustment,
              calculatedLotSize: formData.calculatedLotSize,
              strategy: formData.strategy,
              productType: formData.productType,
              premiumMinPrice: formData.premiumMinPrice,
              premiumMaxPrice: formData.premiumMaxPrice,
              maxInitialRiskPoints: formData.maxInitialRiskPoints,
              status: 'ACTIVE',
            }),
          })
          result = await response.json().catch(() => ({}))
        }
      }

      if (!response.ok) throw new Error(result.error || `Failed to create instrument (${response.status})`)
      
      // Refresh instruments after creation
      await fetchInstruments()
      return { success: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create instrument'
      setError(message)
      return { success: false, error: message }
    }
  }

  // Update instrument
  const updateInstrument = async (id: string, formData: InstrumentPayload) => {
    try {
      const response = await fetch(`/api/instruments/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          brokerSymbol: formData.brokerSymbol,
          monitoringStartTime: formData.monitoringStartTime,
          monitoringEndTime: formData.monitoringEndTime,
          entryCutoffTime: formData.entryCutoffTime,
          lotSizeAdjustment: formData.lotSizeAdjustment,
          calculatedLotSize: formData.calculatedLotSize,
          strategy: formData.strategy,
          productType: formData.productType,
          premiumMinPrice: formData.premiumMinPrice,
          premiumMaxPrice: formData.premiumMaxPrice,
          maxInitialRiskPoints: formData.maxInitialRiskPoints,
        }),
      })
      
      if (!response.ok) throw new Error('Failed to update instrument')
      
      // Refresh instruments after update
      await fetchInstruments()
      return { success: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update instrument'
      setError(message)
      return { success: false, error: message }
    }
  }

  // Delete instrument
  const deleteInstrument = async (id: string) => {
    try {
      const response = await fetch(`/api/instruments/${id}`, {
        method: 'DELETE',
      })
      
      if (!response.ok) throw new Error('Failed to delete instrument')
      
      // Refresh instruments after deletion
      await fetchInstruments()
      return { success: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete instrument'
      setError(message)
      return { success: false, error: message }
    }
  }

  // Toggle instrument status
  const toggleInstrument = async (id: string) => {
    try {
      const instrument = instruments.find(i => i.id === id)
      if (!instrument) throw new Error('Instrument not found')
      
      const newStatus = instrument.status ? 'INACTIVE' : 'ACTIVE'
      
      const response = await fetch(`/api/instruments/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: newStatus,
        }),
      })
      
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.error || 'Failed to toggle instrument status')
      
      // Refresh instruments after update
      await fetchInstruments()
      return { success: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to toggle instrument status'
      setError(message)
      return { success: false, error: message }
    }
  }

  // Initial fetch on mount
  useEffect(() => {
    fetchInstruments()
  }, [includeArchived])

  return {
    instruments,
    isLoading,
    error,
    fetchInstruments,
    addInstrument,
    updateInstrument,
    deleteInstrument,
    toggleInstrument,
  }
}
