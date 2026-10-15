import React, { useState } from 'react'
import { Section, ResourceState, Fields, ViewTitle, array, stagger } from '../parts/Primitives.jsx'

export function sortTimeline(events) {
  return [...array(events)].sort((a, b) => {
    try { const left = BigInt(a.commit_seq); const right = BigInt(b.commit_seq); return left === right ? 0 : left > right ? -1 : 1 } catch { return 0 }
  })
}

export default function Versions({ resources, t, asOfSeq, setAsOfSeq, maxSeq }) {
  const resource = resources.timeline
  const events = sortTimeline(resource?.data?.events)
  const [filter, setFilter] = useState('')
  const maxNumber = Number(maxSeq)
  const validMax = Number.isSafeInteger(maxNumber) && maxNumber >= 0
  const [draftSeq, setDraftSeq] = useState(null)
  const selectedSeq = draftSeq ?? (asOfSeq == null ? maxSeq || '0' : asOfSeq)
  const types = [...new Set(events.map((event) => event.object_type).filter(Boolean))].sort()
  const pageToken = resource?.meta?.next_page_token ?? resource?.data?.next_page_token
  const rows = events.filter((event) => !filter || event.object_type === filter)
  const applyHistory = () => { if (validMax) { setAsOfSeq?.(String(selectedSeq)); setDraftSeq(null) } }
  return <div className="pk-view"><ViewTitle id="versions" t={t} subtitle={t('versions.subtitle')} />
    <Section title={t('versions.watermark')} t={t} hint={t('versions.watermarkHint')}><div className="pk-history-controls"><label htmlFor="pk-history-slider">{t('shell.asOf')}: <output htmlFor="pk-history-slider">{selectedSeq}</output></label><input id="pk-history-slider" type="range" min="0" max={validMax ? maxNumber : 0} value={validMax ? Math.min(maxNumber, Math.max(0, Number(selectedSeq))) : 0} disabled={!validMax} onChange={(event) => setDraftSeq(event.target.value)} /><div className="pk-control-actions"><button className="pk-button" type="button" disabled={!validMax} onClick={applyHistory}>{t('versions.viewHistory')}</button><button className="pk-button pk-button-secondary" type="button" onClick={() => { setDraftSeq(null); setAsOfSeq?.(null) }}>{t('versions.returnCurrent')}</button></div></div>
      {asOfSeq != null && <p className="pk-note pk-note-warn">{t('shell.history', { seq: asOfSeq })}</p>}{!validMax && <p className="pk-note">{t('versions.noHead')}</p>}
    </Section>
    <Section title={t('versions.timeline')} t={t}><div className="pk-timeline-tools"><label>{t('versions.objectFilter')}<select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">{t('common.all')}</option>{types.map((type) => <option value={type} key={type}>{type}</option>)}</select></label><button className="pk-button pk-button-secondary" type="button" onClick={() => resource?.refresh?.({ page_token: undefined })}>{t('versions.firstPage')}</button></div>
      <ResourceState resource={resource} t={t} empty={!rows.length} emptyText={filter ? t('versions.noMatchingEvents') : t('versions.noEvents')}><ol className="pk-timeline">{rows.map((event, i) => <li key={JSON.stringify([event.commit_seq, event.kind, event.object_type, event.object_id, event.revision_id, event.pointer_name, event.head_version, event.event_type, event.event_index, i])} className={stagger(i)} data-kind={event.kind}><span className="pk-timeline-symbol" aria-hidden="true">{event.kind === 'revision' ? '◇' : event.kind === 'head' ? '◆' : '•'}</span><article><header><strong>#{event.commit_seq}</strong><span className="pk-badge">{['revision', 'head', 'event'].includes(event.kind) ? t(`versions.kind.${event.kind}`) : event.kind}</span></header><Fields t={t} values={[[t('trace.object_type'), event.object_type], [t('trace.object_id'), event.object_id], [t('trace.revision_id'), event.revision_id], [t('versions.eventType'), event.event_type]]} /><details className="pk-json-details"><summary>{t('common.details')}</summary><pre>{JSON.stringify(event, null, 2)}</pre></details></article></li>)}</ol></ResourceState>
      <footer className="pk-page-tools"><p className="pk-note">{t('versions.pageCount', { count: rows.length })}</p><button className="pk-button" type="button" disabled={!pageToken || resource?.phase === 'loading'} onClick={() => resource?.refresh?.({ page_token: pageToken })}>{t('versions.nextPage')}</button></footer><p className="pk-note">{t('versions.filterScope')}</p>
    </Section>
    <p className="pk-note">{t('versions.rulesHint')}</p>
  </div>
}
