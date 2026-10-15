import { serviceError, unpackResponse } from './services.js'

const empty = () => ({ phase: 'loading', data: undefined, meta: undefined, error: undefined })

/** A paused request cannot be aborted by the host API, so its result is discarded. */
export function createPollController({ request, onState, interval = 2500,
  schedule = (callback, delay) => setTimeout(callback, delay), unschedule = (id) => clearTimeout(id) }) {
  let active = false
  let disposed = false
  let generation = 0
  let timer
  let failures = 0
  let input = {}
  let state = empty()
  const emit = (next) => { state = next; onState(next) }
  const clearTimer = () => { if (timer !== undefined) unschedule(timer); timer = undefined }
  const tick = async () => {
    if (!active || disposed) return undefined
    clearTimer()
    const token = ++generation
    try {
      const response = await request({ ...input })
      if (token !== generation || !active || disposed) return undefined
      const { data, meta } = unpackResponse(response)
      failures = 0
      emit({ phase: data === null || data === undefined || data?.data_state === 'no_data' ? 'empty' : 'ready',
        data, meta, error: undefined, at: Date.now() })
    } catch (error) {
      if (token !== generation || !active || disposed) return undefined
      failures += 1
      emit({ ...state, phase: 'unavailable', error: serviceError(error) })
    }
    if (token === generation && active && !disposed) {
      timer = schedule(tick, failures ? Math.min(10000, interval * 2 ** (failures - 1)) : interval)
    }
    return state
  }
  return {
    start(nextInput = {}) {
      if (disposed) return
      generation += 1
      clearTimer()
      input = nextInput
      failures = 0
      active = true
      emit(empty())
      return tick()
    },
    refresh() {
      return tick()
    },
    pause() { active = false; generation += 1; clearTimer() },
    dispose() { disposed = true; active = false; generation += 1; clearTimer() },
  }
}
