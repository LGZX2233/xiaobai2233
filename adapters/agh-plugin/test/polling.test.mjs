import test from 'node:test'
import assert from 'node:assert/strict'
import { createPollController } from '../client/src/data/poll-controller.js'
import { callService, unpackResponse } from '../client/src/data/services.js'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function fakeClock() {
  let next = 0
  const pending = new Map()
  return {
    pending,
    schedule: (callback, delay) => { const id = ++next; pending.set(id, { callback, delay }); return id },
    unschedule: (id) => pending.delete(id),
    advance: async () => { const [id, item] = pending.entries().next().value; pending.delete(id); await item.callback() },
  }
}

test('pausing cancels timers and ignores an in-flight request; resuming reloads the new scope', async () => {
  const clock = fakeClock()
  const pending = []
  const states = []
  const controller = createPollController({ ...clock, onState: (state) => states.push(state), request: (input) => {
    const item = deferred(); pending.push({ ...item, input }); return item.promise
  } })
  const stale = controller.start({ as_of_seq: '10000000000000001' })
  controller.pause()
  assert.equal(clock.pending.size, 0)
  const current = controller.start({ as_of_seq: '2' })
  pending[1].resolve({ data: { value: 'historical' }, meta: { as_of_seq: '2' } })
  await current
  pending[0].resolve({ data: { value: 'stale' }, meta: { as_of_seq: '10000000000000001' } })
  await stale
  assert.equal(states.at(-1).data.value, 'historical')
  assert.equal(states.at(-1).meta.as_of_seq, '2')
  assert.equal(pending[0].input.as_of_seq, '10000000000000001', 'sequence must stay a decimal string')
  assert.equal(clock.pending.size, 1)
  controller.pause()
  assert.equal(clock.pending.size, 0)
  assert.equal(await controller.refresh(), undefined, 'manual refresh must not restart a paused panel')
  controller.dispose()
})

test('service failures back off to ten seconds and retain prior data with an unavailable state', async () => {
  const clock = fakeClock()
  const states = []
  let succeeds = true
  const controller = createPollController({ ...clock, onState: (state) => states.push(state), request: async () => {
    if (succeeds) return { data: { count: 3 }, meta: { completeness: 'complete' } }
    throw new Error('services capability disabled')
  } })
  await controller.start()
  assert.equal(clock.pending.values().next().value.delay, 2500)
  succeeds = false
  for (const delay of [2500, 5000, 10000, 10000]) {
    await clock.advance()
    assert.equal(clock.pending.values().next().value.delay, delay)
  }
  assert.equal(states.at(-1).phase, 'unavailable')
  assert.equal(states.at(-1).data.count, 3)
  assert.match(states.at(-1).error, /services/)
  succeeds = true
  await clock.advance()
  assert.equal(states.at(-1).phase, 'ready')
  assert.equal(clock.pending.values().next().value.delay, 2500)
  controller.dispose()
  assert.equal(clock.pending.size, 0)
})

test('no_data remains distinct from service failure and document metadata is preserved', async () => {
  const clock = fakeClock()
  let state
  const controller = createPollController({ ...clock, onState: (next) => { state = next }, request: async () => ({
    data: { data_state: 'no_data' }, meta: { completeness: 'unknown', gaps: ['not_checked'] },
  }) })
  await controller.start()
  assert.equal(state.phase, 'empty')
  assert.deepEqual(state.meta.gaps, ['not_checked'])
  controller.dispose()
  assert.deepEqual(unpackResponse([{ event_type: 'demo' }]), { data: [{ event_type: 'demo' }], meta: {} })
})

test('browser service facade forwards only reads and keeps the requested historical watermark', async () => {
  const calls = []
  const ctx = { agnes: { services: { call: async (name, input) => { calls.push({ name, input }); return { meta: {}, data: {} } } } } }
  await callService(ctx, 'timeline', { as_of_seq: '12345678901234567890', page_token: 'page' })
  assert.deepEqual(calls, [{ name: 'pk.timeline', input: { as_of_seq: '12345678901234567890', page_token: 'page' } }])
  await assert.rejects(callService(ctx, 'approval.decide', {}), /Unknown read-only service/)
  assert.equal(calls.length, 1, 'unsupported write service must not reach the host')
})
