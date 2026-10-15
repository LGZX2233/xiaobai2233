import React from 'react'
import { Section, ResourceState, Stat, DataList, ViewTitle, array } from '../parts/Primitives.jsx'
import { statusDistribution, tally, timelineFailureSeries } from './helpers.js'

export function BarChart({ counts, t, label }) {
  const entries = Object.entries(counts)
  const largest = Math.max(1, ...entries.map(([, value]) => value))
  const height = entries.length * 46 + 36
  return entries.length ? <div className="pk-chart-scroll"><svg className="pk-bar-chart" viewBox={`0 0 660 ${height}`} width="660" height={height} role="img" aria-label={label}><title>{label}</title>{entries.map(([name, value], i) => <g key={name} transform={`translate(0,${i * 46 + 25})`} data-status={name}><text x="0" y="0">{name.length > 27 ? `${name.slice(0, 26)}…` : name}</text><rect x="240" y="-15" width={Math.max(1, value / largest * 340)} height="23" rx="2" /><text x={252 + value / largest * 340} y="1">{value}</text><title>{`${name}: ${value}`}</title></g>)}</svg></div> : <p className="pk-note">{t('errors.noObservations')}</p>
}

export function FailureSeries({ events, t }) {
  const series = timelineFailureSeries(events)
  if (!series.length) return <p className="pk-note">{t('errors.noExplicitEvents')}</p>
  const width = 680; const height = 210
  const maximum = Math.max(1, ...series.map((item) => Math.max(item.failed, item.unknown)))
  const x = (i) => series.length === 1 ? 335 : 45 + i / (series.length - 1) * 590
  const y = (value) => 160 - value / maximum * 125
  return <div className="pk-chart-scroll"><svg className="pk-series-chart" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={t('errors.series')}><title>{t('errors.series')}</title><path className="pk-chart-axis" d="M45,25 V160 H635" />{['failed', 'unknown'].map((kind) => <g key={kind} data-kind={kind}><polyline points={series.map((item, i) => `${x(i)},${y(item[kind])}`).join(' ')} />{series.map((item, i) => <circle key={item.seq} cx={x(i)} cy={y(item[kind])} r="4"><title>{`${item.seq} · ${t(`status.${kind}`)}: ${item[kind]}`}</title></circle>)}</g>)}<text x="45" y="185">{series[0].seq}</text><text x="610" y="185">{series.at(-1).seq}</text><text x="5" y="35">{maximum}</text><text x="335" y="207" textAnchor="middle">{t('errors.sequence')}</text></svg><div className="pk-chart-legend"><span className="pk-legend-failed">{t('status.failed')}</span><span className="pk-legend-unknown">{t('status.unknown')}</span></div></div>
}

export default function Errors({ resources, t }) {
  const compare = resources.compare
  const overview = resources.overview
  const timeline = resources.timeline
  const events = array(timeline?.data?.events)
  const tip = t('errors.derivedNote')
  return <div className="pk-view"><ViewTitle id="errors" t={t} subtitle={t('errors.subtitle')} />
    <div className="pk-view-grid">
      <Section title={t('errors.attemptStates')} source="derived" t={t} hint={tip}><ResourceState resource={compare} t={t}><BarChart counts={statusDistribution(compare?.data)} t={t} label={t('errors.attemptStates')} /></ResourceState></Section>
      <Section title={t('errors.eventTypes')} source="derived" t={t} hint={tip}><ResourceState resource={timeline} t={t}><BarChart counts={tally(events, (event) => event.event_type || event.kind)} t={t} label={t('errors.eventTypes')} /></ResourceState></Section>
      <Section title={t('errors.retained')} source="derived" t={t} hint={tip}><ResourceState resource={compare} t={t}><Stat label={t('errors.retainedCount')} value={array(compare?.data?.failures_retained).length} /><DataList items={compare?.data?.failures_retained} t={t} /></ResourceState></Section>
      <Section title={t('errors.blockers')} source="derived" t={t} hint={tip}><ResourceState resource={overview} t={t}><Stat label={t('errors.blockerCount')} value={array(overview?.data?.blockers).length} /><DataList items={overview?.data?.blockers} t={t} /></ResourceState></Section>
    </div>
    <Section title={t('errors.series')} source="derived" t={t} hint={`${tip} ${t('errors.seriesTip')}`}><ResourceState resource={timeline} t={t}><FailureSeries events={events} t={t} /></ResourceState></Section>
  </div>
}
