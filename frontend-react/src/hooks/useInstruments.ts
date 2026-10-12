import { useState, useEffect } from 'react'
import { Instrument } from '@/types'

interface InstrumentPayload {
  name: string
  brokerSymbol: string
  monitoringStartTime: string
  monitoringEndTime: string
  lotSizeAdjustment: number
  calculatedLotSize: number
  strategy: string
  productType: string
  premiumMinPrice?: number
  premiumMaxPrice?: number
  status?: string
}

export const useInstruments = () => {
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch instruments from backend
  const fetchInstruments = async () => {
    setIsLoading(true)
    try {
      const response = await fetch('/api/instruments')
      const data = await response.json()
      
      // Transform backend response to frontend format
      const transformedInstruments = (data.instruments || []).map((inst: any) => ({
        id: inst.id.toString(),
        name: inst.name,
        brokerSymbol: inst.brokerSymbol || inst.broker_symbol,
        monitoringStartTime: inst.monitoringStartTime || inst.monitoring_start_time,
        monitoringEndTime: inst.monitoringEndTime || inst.monitoring_end_time,
        lotSizeAdjustment: inst.lotSizeAdjustment || inst.lot_size_adjustment,
        lotSize: inst.calculatedLotSize || inst.calculated_lot_size,
        strategy: inst.strategy as any,
        productType: inst.productType || inst.product_type,
        status: inst.status === 'ACTIVE' || inst.status === true,
        premiumMinPrice: inst.premiumMinPrice || inst.premium_min_price,
        premiumMaxPrice: inst.premiumMaxPrice || inst.premium_max_price,
        premiumOptionStrike: inst.premiumOptionStrike || inst.premium_option_strike,
        createdAt: inst.createdAt || inst.created_at,
        updatedAt: inst.updatedAt || inst.updated_at,
      }))
      
      setInstruments(transformedInstruments)
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
      const response = await fetch('/api/instruments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          brokerSymbol: formData.brokerSymbol,
          monitoringStartTime: formData.monitoringStartTime,
          monitoringEndTime: formData.monitoringEndTime,
          lotSizeAdjustment: formData.lotSizeAdjustment,
          calculatedLotSize: formData.calculatedLotSize,
          strategy: formData.strategy,
          productType: formData.productType,
          premiumMinPrice: formData.premiumMinPrice,
          premiumMaxPrice: formData.premiumMaxPrice,
        }),
      })
      
      if (!response.ok) throw new Error('Failed to create instrument')
      
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
          lotSizeAdjustment: formData.lotSizeAdjustment,
          calculatedLotSize: formData.calculatedLotSize,
          strategy: formData.strategy,
          productType: formData.productType,
          premiumMinPrice: formData.premiumMinPrice,
          premiumMaxPrice: formData.premiumMaxPrice,
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
      
      const newStatus = instrument.status ? 'ARCHIVED' : 'ACTIVE'
      
      const response = await fetch(`/api/instruments/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: newStatus,
        }),
      })
      
      if (!response.ok) throw new Error('Failed to toggle instrument status')
      
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
  }, [])

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
