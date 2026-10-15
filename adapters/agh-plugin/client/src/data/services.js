const SERVICES = {
  overview: 'pk.overview',
  compare: 'pk.compare',
  approvals: 'pk.approvals',
  timeline: 'pk.timeline',
  trace: 'pk.trace',
  coverage: 'pk.coverage',
  environment: 'pk.environment',
  operation: 'pk.operation',
  tree: 'pk.tree',
  skills: 'pk.skills',
  events: 'pk.events',
}

export const SERVICE_NAMES = Object.freeze(SERVICES)

export function serviceError(error) {
  return String(error?.message ?? error ?? 'Unknown service error')
}

export async function callService(ctx, shortName, input = {}) {
  const name = SERVICES[shortName] ?? (Object.values(SERVICES).includes(shortName) ? shortName : null)
  if (!name) throw new TypeError(`Unknown read-only service: ${shortName}`)
  if (!ctx?.agnes?.services?.call) throw new Error('client service requires an active session and services capability')
  return ctx.agnes.services.call(name, Object.fromEntries(Object.entries(input).filter(([, value]) => value !== undefined)))
}

export function unpackResponse(response) {
  if (response && typeof response === 'object' && !Array.isArray(response) &&
      Object.prototype.hasOwnProperty.call(response, 'data')) {
    const { data, ...envelope } = response
    const meta = response.meta ?? envelope
    return { data, meta: meta && typeof meta === 'object' ? meta : {} }
  }
  return { data: response, meta: {} }
}

