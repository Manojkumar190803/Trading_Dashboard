import assert from 'node:assert/strict'
import { test } from 'node:test'

import { collectUnseenAlerts } from '../src/utils/alert-notifications.js'

test('notifies once when newest-first polling prepends an alert', () => {
  const seenIds = new Set(['older-alert'])
  const alerts = [
    { id: 'new-alert', message: 'Order triggered' },
    { id: 'older-alert', message: 'Previous alert' },
  ]

  assert.deepEqual(collectUnseenAlerts(alerts, seenIds), [alerts[0]])
  assert.deepEqual(collectUnseenAlerts(alerts, seenIds), [])
})

test('returns every unseen alert without replaying previously seen ids', () => {
  const seenIds = new Set(['seen-alert'])
  const alerts = [
    { id: 'newer-alert', message: 'Order cancelled' },
    { id: 'seen-alert', message: 'Previous order' },
    { id: 'another-new-alert', message: 'Order triggered' },
  ]

  assert.deepEqual(
    collectUnseenAlerts(alerts, seenIds),
    [alerts[0], alerts[2]],
  )
})
