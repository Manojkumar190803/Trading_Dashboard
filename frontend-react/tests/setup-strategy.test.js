import assert from 'node:assert/strict'
import { test } from 'node:test'

import { getSetupIdentity } from '../src/utils/setup-strategy.js'

test('preserves EMA21 and HD identities for a shared contract', () => {
  assert.deepEqual(getSetupIdentity('PE EMA21 setup', true), {
    side: 'PE', strategy: 'EMA21', setupName: 'PE EMA21 setup',
  })
  assert.deepEqual(getSetupIdentity('PE HD setup', true), {
    side: 'PE', strategy: 'HD', setupName: 'PE HD setup',
  })
})

test('infers HD only for unlabeled legacy rows', () => {
  assert.deepEqual(getSetupIdentity('PE setup', true), {
    side: 'PE', strategy: 'HD', setupName: 'PE HD setup',
  })
  assert.deepEqual(getSetupIdentity('PE setup', false), {
    side: 'PE', strategy: 'EMA21', setupName: 'PE setup',
  })
})