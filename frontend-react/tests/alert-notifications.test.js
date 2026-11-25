import assert from 'node:assert/strict'
import { test } from 'node:test'

import { collectUnseenAlerts, getOrderEvent } from '../src/utils/alert-notifications.js'

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

test('identifies only actual order placement, modification and execution', () => {
  assert.equal(getOrderEvent({ alert_type: 'PROTECTIVE_SL', message: 'PE protective SL placed for NIFTY01DEC2625700PE qty=65 trigger=201.15 order_id=123' }), 'placed')
  assert.equal(getOrderEvent({ alert_type: 'PROTECTIVE_SL', message: 'PE protective SL modified for NIFTY01DEC2625700PE qty=65 trigger=209.15 order_id=123' }), 'modified')
  assert.equal(getOrderEvent({ alert_type: 'ENTRY', message: 'PE entry fill confirmed; tick monitoring activated for NIFTY01DEC2625700PE' }), 'executed')
  assert.equal(getOrderEvent({ alert_type: 'RISK', message: 'PE protective SL 123 filled; broker quantity=0, skipped duplicate MARKET SELL' }), 'executed')
  assert.equal(getOrderEvent({ alert_type: 'RISK', message: 'PE protective SL 123 filled but broker still reports quantity=65; skipped MARKET SELL pending reconciliation' }), null)
  assert.equal(getOrderEvent({ alert_type: 'PENDING_ENTRY', strategy: 'EMA21', message: 'Pending PE NIFTY01DEC2625700PE qty=65 trigger=213.00 SL=201.15' }), 'placed')
  assert.equal(getOrderEvent({ alert_type: 'ORDER', message: 'PE exit order accepted for NIFTY01DEC2625700PE qty=65 order_id=123' }), 'placed')
  assert.equal(getOrderEvent({ alert_type: 'ORDER', message: 'PE exit order placed for NIFTY01DEC2625700PE qty=65 reason=SL' }), null)
  assert.equal(getOrderEvent({ alert_type: 'EXIT', message: 'SL: exited PE NIFTY01DEC2625700PE qty=65 at 196.55' }), 'executed')
  assert.equal(getOrderEvent({ alert_type: 'SIGNAL', message: 'CE BUY_CE signal at close=291.10' }), null)
  assert.equal(getOrderEvent({ alert_type: 'PENDING_ENTRY', message: 'Pending PE NIFTY01DEC2625700PE qty=65 trigger=213.00 SL=201.15' }), null)
  assert.equal(getOrderEvent({ alert_type: 'TSL', message: 'PE 6.5 RR (tick) — TSL=196.55' }), null)
  assert.equal(getOrderEvent({ alert_type: 'RISK', message: 'PE broker position is flat but protective SL 123 is not confirmed closed' }), null)
  assert.equal(getOrderEvent({ alert_type: 'RISK', message: 'CE trade cancelled before order: entry-SL gap 50.50 > 20.00 points' }), null)
})
