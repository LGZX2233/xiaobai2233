import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { callService } from './services.js'
import { createPollController } from './poll-controller.js'

export function usePoll(ctx, shortName, {
  visible = true, active = true, asOfSeq = null, sessionId, interval = 2500, manual = false,
} = {}) {
  const [state, setState] = useState({ phase: manual ? 'disabled' : 'loading' })
  const [payload, setPayload] = useState({ sessionId, asOfSeq, input: {} })
  const [revision, setRevision] = useState(0)
  const [manualSession, enable] = useState(manual ? undefined : sessionId)
  const manuallyEnabled = !manual || manualSession === sessionId
  const input = useMemo(() => {
    const next = payload.sessionId === sessionId ? { ...payload.input } : {}
    if (payload.asOfSeq !== asOfSeq) delete next.page_token
    if (asOfSeq !== null) next.as_of_seq = String(asOfSeq)
    return next
  }, [payload, asOfSeq, sessionId])
  const scopeKey = `${sessionId ?? ''}:${JSON.stringify(input)}`
  const controller = useMemo(() => createPollController({
    request: (nextInput) => callService(ctx, shortName, nextInput),
    onState: (next) => setState({ ...next, scopeKey }), interval,
  }), [ctx, shortName, interval, scopeKey])
  useEffect(() => () => controller.pause(), [controller])
  useEffect(() => {
    if (visible && active && manuallyEnabled) controller.start(input)
    else controller.pause()
    return () => controller.pause()
  }, [controller, visible, active, manuallyEnabled, input, revision])
  const refresh = useCallback((nextPayload) => {
    if (nextPayload) setPayload((current) => ({ sessionId, asOfSeq,
      input: { ...(current.sessionId === sessionId ? current.input : {}), ...nextPayload },
    }))
    enable(sessionId)
    setRevision((value) => value + 1)
  }, [sessionId, asOfSeq])
  return { ...(state.scopeKey === scopeKey ? state : { phase: manual && !manuallyEnabled ? 'disabled' : 'loading' }), refresh }
}

/** Resume only when both the document and the panel itself are visible. */
export function usePanelVisibility() {
  const [visible, setVisible] = useState(false)
  const target = useRef(null)
  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    let intersecting = typeof IntersectionObserver !== 'function'
    const update = () => setVisible(intersecting && document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', update)
    let observer
    if (typeof IntersectionObserver === 'function' && target.current) {
      observer = new IntersectionObserver((entries) => {
        intersecting = entries.some((entry) => entry.isIntersecting)
        update()
      }, { threshold: 0.01 })
      observer.observe(target.current)
    }
    update()
    return () => { document.removeEventListener('visibilitychange', update); observer?.disconnect() }
  }, [])
  return { visible, target }
}
