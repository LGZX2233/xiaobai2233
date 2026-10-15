import React, { useEffect, useState } from 'react'
import { Section, ResourceState, Badge, Info, Verdict, ViewTitle, array, shortId, stagger, useArrivals, verdictOf } from '../parts/Primitives.jsx'
import { fitOf } from './helpers.js'

/** The candidate a person is about to approve: selected strategy, its verdict and fit. */
export function candidateOf(compare) {
  const data = compare?.data || {}
  const attempts = array(data.attempts)
  const id = data.selected?.attempt_id
  const attempt = attempts.find((a) => a.attempt_id === id)
  if (!attempt) return null
  return { strategy: attempt.strategy_id || shortId(id), verdict: verdictOf(attempt), fit: fitOf(attempt) }
}

function CandidateLine({ candidate, t }) {
  if (!candidate) return null
  return <p className="pk-candidate"><span>{t('permissions.candidate')}</span><strong>{candidate.strategy}</strong><Verdict value={candidate.verdict} t={t} size="md" />{candidate.fit != null && <code>{candidate.fit}</code>}</p>
}

export function expirationLabel(expiresAt, now, t) {
  const at = Date.parse(expiresAt)
  if (!Number.isFinite(at)) return t('common.unknown')
  const remaining = Math.max(0, Math.ceil((at - now) / 1000))
  return remaining === 0 ? t('permissions.expiredTime') : t('permissions.remaining', { minutes: Math.floor(remaining / 60), seconds: String(remaining % 60).padStart(2, '0') })
}

/** One request: the digest prefix is the thing a person types, so it is the largest element. */
export function ApprovalDetails({ approval, t, now, historical = false, index = 0, fresh = false, candidate = null }) {
  const digest = approval.snapshot_digest ? String(approval.snapshot_digest) : null
  const pending = approval.status === 'pending'
  return <article className={`pk-approval-card ${stagger(index)} ${fresh ? 'pk-arrived' : ''}`} data-status={approval.status}>
    <header><code className="pk-approval-id">{approval.approval_id}</code><Badge value={approval.status} t={t} /></header>
    {pending && <CandidateLine candidate={candidate} t={t} />}
    {digest && <div className="pk-digest" data-tip={t('permissions.bindTip')} tabIndex={0}>
      <span className="pk-digest-label">{t('permissions.digest')}</span>
      <code className="pk-digest-prefix">{digest.slice(0, 8)}</code>
      <code className="pk-digest-rest">{digest.slice(8, 24)}</code>
    </div>}
    <dl className="pk-approval-facts">
      <div><dt>{t('permissions.snapshot')}</dt><dd><code>{approval.snapshot_id ?? '—'}</code></dd></div>
      <div><dt>{t('permissions.headVersion')}</dt><dd>{approval.head_version ?? '—'}</dd></div>
      <div><dt>{t('permissions.commit')}</dt><dd>#{approval.commit_seq ?? '—'}</dd></div>
    </dl>
    {!historical && pending && Number.isFinite(Date.parse(approval.expires_at)) && <p className="pk-countdown"><span>{t('permissions.countdown')}</span><strong>{expirationLabel(approval.expires_at, now, t)}</strong></p>}
    {pending && <p className="pk-terminal-line">{t('permissions.terminal')}</p>}
  </article>
}

function useClock(active, key) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return undefined
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [active, key])
  return now
}

export function PermissionNotice({ resource, compare, t, asOfSeq }) {
  const candidate = candidateOf(compare)
  const queue = array(resource?.data?.queue)
  const pending = queue.filter((item) => item.status === 'pending')
  const pendingCount = resource?.data?.pending_count ?? pending.length
  const [dismissed, setDismissed] = useState('')
  const pendingKey = `${pendingCount}:${pending.map((item) => item.approval_id).join('|')}`
  const now = useClock(pendingCount > 0 && asOfSeq == null, pendingKey)
  const visible = pendingCount > 0 && dismissed !== pendingKey
  return visible ? <aside className="pk-approval-drawer" role="region" aria-label={t('permissions.pendingDrawer', { count: pendingCount })}>
    <header><Verdict value="human" t={t} size="md" /><h3>{t('permissions.pendingDrawer', { count: pendingCount })}</h3><Info text={t('permissions.humanTip')} /><button className="pk-icon-button" type="button" onClick={() => setDismissed(pendingKey)} aria-label={t('common.close')}>×</button></header>
    <div className="pk-approval-row">{pending.slice(0, 3).map((approval, i) => <ApprovalDetails key={approval.approval_id} approval={approval} t={t} now={now} historical={asOfSeq != null} index={i} candidate={candidate} />)}</div>
    {pending.length > 3 && <p className="pk-quiet">{t('permissions.morePending', { count: pending.length - 3 })}</p>}
  </aside> : null
}

export default function Permissions({ resources, t, asOfSeq }) {
  const resource = resources.approvals
  const candidate = candidateOf(resources.compare)
  const queue = array(resource?.data?.queue)
  const now = useClock(asOfSeq == null && queue.some((item) => item.status === 'pending'), resource?.data)
  const arrived = useArrivals(queue.map((item) => item.approval_id))
  return <div className="pk-view"><ViewTitle id="permissions" t={t} subtitle={t('permissions.subtitle')} />
    <Section title={t('permissions.queue')} t={t} hint={t('permissions.humanTip')}><ResourceState resource={resource} t={t} empty={!queue.length} emptyText={t('permissions.noPending')}>
      <div className="pk-card-grid">{queue.map((approval, i) => <ApprovalDetails key={approval.approval_id} approval={approval} t={t} now={now} historical={asOfSeq != null} index={i} fresh={arrived.has(approval.approval_id)} candidate={candidate} />)}</div>
      {asOfSeq != null && <p className="pk-quiet">{t('permissions.historical')}</p>}
    </ResourceState></Section>
  </div>
}
