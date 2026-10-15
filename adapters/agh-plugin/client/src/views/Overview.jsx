import React from 'react'
import { Section, ResourceState, Stat, Verdict, ViewTitle, Info, Ticker, array, shortId, stagger, verdictOf, useArrivals } from '../parts/Primitives.jsx'
import { phaseOf, fitOf } from './helpers.js'

const STEPS = ['dispatch', 'attempt', 'verify', 'select', 'approval', 'delivery']

/** Six stages on a rail. The fill animates to the current stage whenever the polled phase changes. */
export function Stepper({ active, t }) {
  return <div className="pk-stepper" data-at={active}>
    <div className="pk-stepper-rail" aria-hidden="true"><span className="pk-stepper-fill" /></div>
    <ol className="pk-steps" aria-label={t('overview.workflow')}>{STEPS.map((step, i) => <li key={step} data-tip={t(`step.${step}Hint`)} data-state={i === active ? 'active' : i < active ? 'observed' : 'future'} aria-current={i === active ? 'step' : undefined}>
      <span className="pk-step-dot" aria-hidden="true">{i < active ? '✓' : i + 1}</span><strong>{t(`step.${step}`)}</strong>
    </li>)}</ol>
  </div>
}

const HEADLINE_COUNTS = ['attempt', 'verification', 'approval', 'requirement']

export default function Overview({ resources, t, navigate }) {
  const overview = resources.overview
  const compare = resources.compare
  const approvals = resources.approvals
  const data = overview?.data || {}
  const attempts = array(compare?.data?.attempts)
  const selectedId = compare?.data?.selected?.attempt_id
  const queue = array(approvals?.data?.queue)
  const pending = queue.filter((item) => item.status === 'pending')
  const pendingCount = Number(approvals?.data?.pending_count ?? pending.length)
  const active = phaseOf(attempts, compare?.data?.selected, queue, resources.operation?.data)
  const counts = data.object_counts || {}
  const issues = [...array(data.blockers), ...array(data.source_gaps)]
  const arrived = useArrivals(attempts.map((attempt) => attempt.attempt_id))
  return <div className="pk-view pk-overview"><ViewTitle id="overview" t={t} subtitle={t('overview.subtitle')} />
    <Section title={t('overview.workflow')} t={t} source="derived" hint={t('overview.inferred')} className="pk-story">
      <ResourceState resource={compare} t={t}><Stepper active={active} t={t} /></ResourceState>
      {queue.some((item) => item.status === 'approved') && resources.operation?.data == null && <p className="pk-quiet">{t('overview.deliveryUnknown')}</p>}
    </Section>
    {pendingCount > 0 && <aside className="pk-callout" data-verdict="human" role="status">
      <Verdict value="human" t={t} size="lg" />
      <div className="pk-callout-body"><strong>{t('overview.pending', { count: pendingCount })}</strong>
        {pending[0]?.snapshot_digest && <p><code className="pk-digest-inline">{String(pending[0].snapshot_digest).slice(0, 8)}</code>{t('overview.pendingLine')}</p>}</div>
      {navigate && <button type="button" className="pk-button pk-button-strong" onClick={() => navigate('permissions')}>{t('overview.openApprovals')}</button>}
    </aside>}
    <Section title={t('overview.currentAttempts')} t={t}><ResourceState resource={compare} t={t} empty={!attempts.length} emptyText={t('execution.noAttempts')}>
      <ol className="pk-attempt-strip">{attempts.map((attempt, i) => {
        const verdict = verdictOf(attempt)
        const fit = fitOf(attempt)
        return <li key={attempt.attempt_id} className={`${stagger(i)} ${arrived.has(attempt.attempt_id) ? 'pk-arrived' : ''}`} data-verdict={verdict} data-selected={attempt.attempt_id === selectedId ? 'true' : 'false'}>
          <span className="pk-strip-strategy">{attempt.strategy_id || '—'}</span>
          <Verdict value={verdict} t={t} stamp />
          {fit && <span className="pk-strip-fit"><i>{t('execution.fit')}</i> {fit}</span>}
          <code className="pk-strip-id" title={attempt.attempt_id}>{shortId(attempt.attempt_id)}</code>
          {attempt.attempt_id === selectedId && <span className="pk-chip pk-chip-selected">{t('status.selected')}</span>}
        </li>
      })}</ol>
    </ResourceState></Section>
    <Section title={t('overview.objects')} t={t}><ResourceState resource={overview} t={t} empty={!Object.keys(counts).length}>
      <div className="pk-stats">{HEADLINE_COUNTS.filter((type) => counts[type] != null).map((type, i) => <Stat key={type} label={t(`overview.count.${type}`)} value={counts[type]} index={i} />)}
        <Stat label={t('overview.lastCommit')} value={`#${data.last_commit_seq ?? '—'}`} index={4} /></div>
      <details className="pk-more"><summary>{t('overview.allObjects', { count: Object.keys(counts).length })}</summary>
        <ul className="pk-chip-list">{Object.entries(counts).map(([type, count]) => <li key={type} className="pk-chip"><code>{type}</code><Ticker value={count} /></li>)}</ul></details>
      <p className="pk-issues" data-empty={issues.length ? 'false' : 'true'}>{issues.length
        ? <><span aria-hidden="true">△</span>{t('overview.issues', { count: issues.length })}<Info text={issues.map((item) => typeof item === 'string' ? item : JSON.stringify(item)).join('\n')} /></>
        : <><span aria-hidden="true">✓</span>{t('overview.noIssues')}</>}</p>
    </ResourceState></Section>
  </div>
}
