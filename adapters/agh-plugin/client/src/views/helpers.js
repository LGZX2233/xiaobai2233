import { array } from '../parts/Primitives.jsx'

// Progress is inferred from committed facts. It is never an acceptance verdict.
export function phaseOf(attempts, selected, approvals, operation) {
  const queue = array(approvals)
  const matchingApproval = queue.some((item) => item.approval_id === operation?.approval_id && item.snapshot_id === operation?.snapshot_id)
  if (selected && matchingApproval && operation?.operation_kind === 'delivery' && operation.status === 'applied') return 5
  if (queue.some((item) => item.status === 'pending' || item.status === 'approved')) return 4
  if (selected) return 3
  if (array(attempts).some((attempt) => attempt.verification_result !== undefined && attempt.verification_result !== null)) return 2
  if (array(attempts).length) return 1
  return 0
}

export function finiteCount(value) {
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : null
}

export function tally(items, getKey) {
  return array(items).reduce((counts, item) => {
    const key = String(getKey(item) ?? 'unknown')
    counts[key] = (counts[key] || 0) + 1
    return counts
  }, {})
}

export function moduleDegrees(nodes, nodeId) {
  const list = array(nodes)
  return { outgoing: array(list.find((node) => node.node_id === nodeId)?.depends_on).length,
    incoming: list.filter((node) => array(node.depends_on).includes(nodeId)).length }
}

/** First-order neighbours of a module: what it depends on, what depends on it, and declared relations. */
export function moduleNeighbours(nodes, nodeId) {
  const list = array(nodes)
  const node = list.find((item) => item.node_id === nodeId)
  const out = new Set(array(node?.depends_on))
  const incoming = new Set(list.filter((item) => array(item.depends_on).includes(nodeId)).map((item) => item.node_id))
  const related = new Set(array(node?.related_to))
  list.forEach((item) => { if (array(item.related_to).includes(nodeId)) related.add(item.node_id) })
  out.delete(nodeId); incoming.delete(nodeId); related.delete(nodeId)
  return { out, incoming, related }
}

export function statusDistribution(compare) {
  return tally(compare?.attempts, (attempt) => attempt.status)
}

/** Optional check details; the service may not carry them, then the panel simply shows nothing. */
export function fitOf(attempt) {
  const value = attempt?.alpha_fit ?? attempt?.verification_result?.alpha_fit
  if (value == null || value === '') return null
  return Number.isFinite(Number(value)) ? Number(value).toFixed(5) : String(value)
}
export function reasonOf(attempt) {
  const value = attempt?.reason ?? attempt?.check_reason ?? attempt?.verification_result?.reason
  return value == null || value === '' ? null : String(value)
}

export function timelineFailureSeries(events) {
  const buckets = new Map()
  for (const event of array(events)) {
    const type = String(event.event_type || '')
    // Count only explicit event names. Unknown names do not imply failure.
    if (!/(?:^|[._-])(?:failed|failure|unknown)(?:$|[._-])/.test(type)) continue
    const seq = Number(event.commit_seq)
    if (!Number.isFinite(seq)) continue
    const bucket = buckets.get(seq) || { seq, failed: 0, unknown: 0 }
    if (/(?:^|[._-])unknown(?:$|[._-])/.test(type)) bucket.unknown += 1
    else bucket.failed += 1
    buckets.set(seq, bucket)
  }
  return [...buckets.values()].sort((a, b) => a.seq - b.seq)
}
