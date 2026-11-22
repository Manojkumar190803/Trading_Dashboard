export function collectUnseenAlerts(alerts, seenIds) {
  const unseenAlerts = []

  for (const alert of alerts) {
    if (seenIds.has(alert.id)) continue
    seenIds.add(alert.id)
    unseenAlerts.push(alert)
  }

  return unseenAlerts
}
