import React from 'react'
import { Section, ResourceState, Stat, ViewTitle, array, textValue } from '../parts/Primitives.jsx'
import { TracePanel } from '../parts/TraceGraph.jsx'
import { finiteCount } from './helpers.js'

export function coveragePercent(data) {
  const denominator = finiteCount(data?.denominator)
  const covered = finiteCount(data?.covered)
  return denominator && covered != null ? Math.min(100, Math.max(0, covered / denominator * 100)) : null
}

export default function Requirements({ resources, t }) {
  const resource = resources.coverage
  const data = resource?.data || {}
  const requirements = array(data.requirements)
  const percent = coveragePercent(data)
  return <div className="pk-view"><ViewTitle id="requirements" t={t} subtitle={t('requirements.subtitle')} />
    <Section title={t('requirements.coverage')} t={t} hint={`${t('requirements.scope')} ${t('requirements.denominatorHint')}`}><ResourceState resource={resource} t={t}>
      <div className="pk-stats"><Stat label={t('requirements.denominator')} value={data.denominator ?? t('common.unknown')} /><Stat index={1} label={t('requirements.covered')} value={data.covered ?? t('common.unknown')} /><Stat index={2} label={t('requirements.notApplicable')} value={data.not_applicable ?? t('common.unknown')} /></div>
      <div className="pk-coverage-meter"><label htmlFor="pk-coverage-progress">{t('requirements.ratio', { covered: data.covered ?? '—', total: data.denominator ?? '—' })}</label>{percent != null ? <progress id="pk-coverage-progress" value={percent} max="100" aria-label={t('requirements.coverage')} /> : <p className="pk-note">{t('requirements.noDenominator')}</p>}</div>
      {requirements.length ? <div className="pk-table-wrap"><table><caption className="pk-sr-only">{t('requirements.coverage')}</caption><thead><tr><th>{t('requirements.requirement')}</th><th>{t('requirements.links')}</th><th>{t('requirements.packets')}</th><th>{t('requirements.coverageStatus')}</th><th>{t('requirements.reason')}</th></tr></thead><tbody>{requirements.map((item) => <tr key={item.object_id}><td><code>{item.object_id}</code></td><td>{item.link_count}</td><td><code>{textValue(item.linked_packets, t)}</code></td><td>{item.not_applicable ? t('requirements.notApplicable') : textValue(item.coverage, t)}</td><td>{textValue(item.reason, t)}</td></tr>)}</tbody></table></div> : <p className="pk-note">{t('requirements.noRequirements')}</p>}
    </ResourceState></Section>
    <Section title={t('requirements.handoffTrace')} t={t} hint={t('requirements.chain')}><TracePanel resource={resources.trace} t={t} /></Section>
  </div>
}
