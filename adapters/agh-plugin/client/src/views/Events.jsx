import React, { useMemo, useState } from 'react'
import { ViewTitle, Section, ResourceState, array, stagger, useArrivals } from '../parts/Primitives.jsx'

const refsOf = (event) => array(event.object_refs).map((ref) => `${ref.object_type}:${ref.object_id}`)
const haystack = (event) => [event.event_type, event.command_id, event.event_schema, `#${event.commit_seq}`, ...refsOf(event)].filter(Boolean).join(' ').toLowerCase()

/** Group by commit_seq, newest commit first, events inside a commit in ledger order. */
export function groupByCommit(events) {
  const groups = new Map()
  for (const event of events) {
    const key = String(event.commit_seq)
    groups.set(key, [...(groups.get(key) || []), event])
  }
  const bigint = (value) => { try { return BigInt(value) } catch { return 0n } }
  return [...groups.entries()].sort(([a], [b]) => (bigint(b) > bigint(a) ? 1 : bigint(b) < bigint(a) ? -1 : 0))
    .map(([seq, items]) => [seq, items.slice().sort((a, b) => (Number(a.event_index) || 0) - (Number(b.event_index) || 0))])
}

/** events.read returns an array of committed events; nothing here is aggregated or inferred. */
export default function Events({ resources, t }) {
  const resource = resources.events
  const events = array(resource?.data)
  const [filter, setFilter] = useState('')
  const [query, setQuery] = useState('')
  const types = [...new Set(events.map((event) => event.event_type).filter(Boolean))].sort()
  const needle = query.trim().toLowerCase()
  const rows = useMemo(() => events.filter((event) => (!filter || event.event_type === filter) && (!needle || haystack(event).includes(needle))),
    [events, filter, needle])
  const groups = useMemo(() => groupByCommit(rows), [rows])
  const last = events.at(-1)
  const arrived = useArrivals(events.map((event) => `${event.commit_seq}:${event.event_index}`))
  return <div className="pk-view"><ViewTitle id="events" t={t} subtitle={t('events.subtitle')} />
    <Section title={t('events.stream')} t={t} hint={t('events.hint')} aside={<span className="pk-match-count" aria-live="polite">{t('common.shown', { shown: rows.length, total: events.length })}</span>}>
      <div className="pk-timeline-tools">
        <label className="pk-grow">{t('events.search')}<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <label>{t('events.filterByType')}<select value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="">{t('common.all')}</option>{types.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
        <button className="pk-button pk-button-secondary" type="button" onClick={() => resource?.refresh?.({ commit_seq: undefined, event_index: undefined })}>{t('events.fromStart')}</button>
        <button className="pk-button" type="button" disabled={!last} onClick={() => resource?.refresh?.({ commit_seq: String(last.commit_seq), event_index: Number(last.event_index) || 0 })}>{t('events.more')}</button>
      </div>
      <ResourceState resource={resource} t={t} empty={!events.length} emptyText={t('events.noEvents')}>
        {rows.length === 0 ? <p className="pk-quiet">{t('events.noMatch')}</p>
          : <ol className="pk-commits">{groups.map(([seq, items], g) => <li key={seq} className={`pk-commit ${stagger(g)}`}>
            <h4 className="pk-commit-seq"><span>#{seq}</span><small>{t('events.entries', { count: items.length })}</small></h4>
            <ul className="pk-commit-events">{items.map((event) => {
              const key = `${event.commit_seq}:${event.event_index}`
              return <li key={key} className={arrived.has(key) ? 'pk-arrived' : ''}>
                <code className="pk-event-index">.{event.event_index}</code>
                <strong className="pk-event-type">{event.event_type}</strong>
                <span className="pk-event-meta">{event.command_id && <code title={t('events.command')}>{event.command_id}</code>}
                  {refsOf(event).map((ref) => <code className="pk-ref" key={ref}>{ref}</code>)}</span>
              </li>
            })}</ul>
          </li>)}</ol>}
      </ResourceState>
    </Section>
  </div>
}
