import { Shell } from './app/Shell.jsx'
import { messages } from './i18n/messages.js'

export function apply(ctx, config = {}) {
  const offLocale = ctx.locale?.register?.('project-kernel', messages)
  const offPanel = ctx.slots.register('workbench.panel', () => <Shell ctx={ctx} config={config} />, { priority: 0 })
  let disposed = false
  const dispose = () => {
    if (disposed) return
    disposed = true
    offPanel?.()
    offLocale?.()
  }
  ctx.effect?.(() => dispose)
  return dispose
}

