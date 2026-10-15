import React, { useState } from 'react'
import { Section, ResourceState, Fields, Badge, Verdict, ViewTitle, Info, array, shortId, stagger, textValue, verdictOf, useArrivals } from '../parts/Primitives.jsx'
import { fitOf, reasonOf } from './helpers.js'

const costText = (cost, t) => cost == null || cost.state === 'unknown' ? t('execution.costUnknown') : textValue(cost.total ?? cost.value ?? cost, t)

/** One attempt as a ledger card: the verdict leads, then the fit, the check reason and the record. */
export function AttemptCard({ attempt, selected, t, index = 0, fresh = false }) {
  const verdict = verdictOf(attempt)
  const fit = fitOf(attempt)
  const reason = reasonOf(attempt)
  const unreported = attempt.cost == null || attempt.cost.state === 'unknown'
  return <article className={`pk-attempt-card ${stagger(index)} ${fresh ? 'pk-arrived' : ''}`} data-verdict={verdict} data-status={attempt.status || 'unknown'} data-selected={selected ? 'true' : 'false'}>
    <header>
      <span className="pk-attempt-strategy">{attempt.strategy_id || t('common.unknown')}</span>
      {selected && <span className="pk-chip pk-chip-selected">{t('status.selected')}</span>}
    </header>
    <Verdict value={verdict} t={t} size="xl" stamp />
    {fit != null && <p className="pk-attempt-fit"><i>{t('execution.fit')}</i><strong>{fit}</strong></p>}
    {reason && <p className="pk-attempt-reason">{reason}</p>}
    <dl className="pk-attempt-facts">
      <div><dt>{t('common.status')}</dt><dd><Badge value={attempt.status} t={t} /></dd></div>
      <div><dt>{t('execution.exit')}</dt><dd><code>{attempt.exit_code ?? '—'}</code></dd></div>
      <div><dt>{t('execution.cost')}</dt><dd>{costText(attempt.cost, t)}{unreported && <Info text={t('execution.costTip')} />}</dd></div>
    </dl>
    <footer><code title={attempt.attempt_id}>{shortId(attempt.attempt_id, 10)}</code><span>{attempt.mode}</span><span>{t('execution.revisionsShort', { count: attempt.revision_count ?? '—' })}</span></footer>
  </article>
}

const OPERATION_STATES = ['prepared', 'claimed', 'applying', 'applied', 'failed', 'unknown']
export function OperationStatus({ resource, t }) {
  const data = resource?.data || {}
  const state = data.status || data.state || data.receipt?.status || 'unknown'
  return <ResourceState resource={resource} t={t} disabledText={t('execution.operationPrompt')}><Fields t={t} values={[[t('execution.operationId'), data.operation_id], [t('execution.operationKind'), data.operation_kind]]} />
    <ol className="pk-operation-states" aria-label={t('execution.operationState')}>{OPERATION_STATES.map((name) => <li key={name} data-active={state === name ? 'true' : 'false'} aria-current={state === name ? 'step' : undefined}><Badge value={name} t={t} /></li>)}</ol>
    <details className="pk-json-details"><summary>{t('common.details')}</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
  </ResourceState>
}

export default function Execution({ resources, t }) {
  const compare = resources.compare
  const data = compare?.data || {}
  const attempts = array(data.attempts)
  const selectedId = data.selected?.attempt_id
  const selectedAttempt = attempts.find((attempt) => attempt.attempt_id === selectedId)
  const retained = array(data.failures_retained)
  const [operationId, setOperationId] = useState('')
  const arrived = useArrivals(attempts.map((attempt) => attempt.attempt_id))
  return <div className="pk-view"><ViewTitle id="execution" t={t} subtitle={t('execution.subtitle')} />
    <Section title={t('execution.attempts')} t={t} hint={t('execution.runHint')}><ResourceState resource={compare} t={t} empty={!attempts.length} emptyText={t('execution.noAttempts')}>
      {data.comparability?.comparable === false && <p className="pk-flag" data-verdict="unknown"><span aria-hidden="true">△</span>{t('execution.incomparable')}: {textValue(data.comparability.reason, t)}</p>}
      <div className="pk-compare-grid" data-count={Math.min(attempts.length, 4)}>{attempts.map((attempt, i) => <AttemptCard key={attempt.attempt_id} attempt={attempt} selected={attempt.attempt_id === selectedId} t={t} index={i} fresh={arrived.has(attempt.attempt_id)} />)}</div>
      {data.selected && <div className="pk-selected" data-verdict={selectedAttempt ? verdictOf(selectedAttempt) : 'open'}>
        <span className="pk-selected-mark" aria-hidden="true">★</span>
        <div><h4>{t('execution.selection', { strategy: selectedAttempt?.strategy_id ?? shortId(selectedId) })}</h4>
          <p className="pk-selected-reason">{textValue(data.selected.reason, t)}</p>
          <p className="pk-quiet">{t('execution.basis')} <code>{data.selected.basis}</code> · <code title={selectedId}>{shortId(selectedId, 10)}</code></p></div>
      </div>}
      {retained.length > 0 && <p className="pk-flag" data-verdict="unknown"><span aria-hidden="true">?</span>{t('execution.retained', { count: retained.length })}<Info text={t('execution.unknownNote')} /></p>}
    </ResourceState></Section>
    <details className="pk-section pk-fold"><summary><span>{t('execution.operation')}</span><span className="pk-quiet">{t('execution.operationFold')}</span></summary>
      <form className="pk-query-form" onSubmit={(event) => { event.preventDefault(); if (operationId.trim()) resources.operation?.refresh?.({ operation_id: operationId.trim() }) }}>
        <label>{t('execution.operationId')}<input type="text" value={operationId} maxLength={256} onChange={(event) => setOperationId(event.target.value)} placeholder={t('execution.operationPlaceholder')} required /></label><button className="pk-button" type="submit">{t('common.query')}</button>
      </form><OperationStatus resource={resources.operation} t={t} />
    </details>
  </div>
}
