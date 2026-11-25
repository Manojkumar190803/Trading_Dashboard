export function collectUnseenAlerts(alerts, seenIds) {
  const unseenAlerts = []

  for (const alert of alerts) {
    if (seenIds.has(alert.id)) continue
    seenIds.add(alert.id)
    unseenAlerts.push(alert)
  }

  return unseenAlerts
}

export function getOrderEvent(alert) {
  const type = (alert.alert_type || '').toUpperCase()
  const message = alert.message || ''
  const strategy = (alert.strategy || '').toUpperCase()

  if (type === 'PENDING_ENTRY' && (strategy === 'EMA21' || strategy === 'HD')) return 'placed'
  if (type === 'PROTECTIVE_SL' && /\bprotective SL placed\b/i.test(message)) return 'placed'
  if (type === 'PROTECTIVE_SL' && /\bprotective SL modified\b/i.test(message)) return 'modified'
  if (type === 'ORDER' && /\bexit order accepted\b/i.test(message)) return 'placed'
  if (type === 'ENTRY' && /\b(?:entered|entry fill confirmed)\b/i.test(message)) return 'executed'
  if (type === 'EXIT' && /\bexited\b/i.test(message)) return 'executed'
  if (type === 'RISK' && /\bprotective SL\s+\S+\s+filled;\s*broker quantity=0\b/i.test(message)) return 'executed'
  return null
}
