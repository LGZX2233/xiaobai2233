import React from 'react'
import { Section, ResourceState, EmptyState, Fields, Badge, ViewTitle, array, textValue } from '../parts/Primitives.jsx'

export const ENVIRONMENT_BUCKETS = ['satisfied', 'missing', 'unknown', 'too_old', 'not_checked']
export function environmentBuckets(data) {
  return Object.fromEntries(ENVIRONMENT_BUCKETS.map((state) => [state, Array.isArray(data?.[state]) ? data[state] : array(data?.facts).filter((fact) => fact.state === state)]))
}

export default function Environment({ resources, t }) {
  const resource = resources.environment
  const data = resource?.data || {}
  const buckets = environmentBuckets(data)
  return <div className="pk-view"><ViewTitle id="environment" t={t} subtitle={t('environment.subtitle')} />
    <Section title={t('environment.report')} t={t}><ResourceState resource={resource} t={t} empty={data.data_state === 'no_data'} emptyText={t('environment.noProbe')}>
      {data.data_state === 'source_failed' && <EmptyState t={t} kind="error" message={t('environment.sourceFailed')} />}
      <Fields t={t} values={[[t('environment.checkedAt'), data.checked_at], [t('environment.freshness'), data.freshness_state], [t('environment.snapshot'), data.snapshot], [t('environment.dataState'), data.data_state]]} />
      <div className="pk-env-buckets">{ENVIRONMENT_BUCKETS.map((state) => <section className="pk-env-bucket" data-state={state} key={state}><header><h4><Badge value={state} t={t} /></h4><span className="pk-env-count">{buckets[state].length}</span></header>{buckets[state].length ? <div className="pk-table-wrap"><table><caption className="pk-sr-only">{t(`status.${state}`)}</caption><thead><tr><th>{t('environment.requirement')}</th><th>{t('environment.requiredVersion')}</th><th>{t('environment.installedVersion')}</th><th>{t('environment.path')}</th></tr></thead><tbody>{buckets[state].map((fact, i) => <tr key={`${textValue(fact.requirement, t)}:${i}`}><td><code>{textValue(fact.requirement, t)}</code><details><summary>{t('common.details')}</summary><pre>{JSON.stringify(fact.detail, null, 2)}</pre></details></td><td>{textValue(fact.required_version, t)}</td><td>{textValue(fact.installed_version, t)}</td><td><code>{textValue(fact.path, t)}</code></td></tr>)}</tbody></table></div> : <p className="pk-note">{t('environment.bucketEmpty')}</p>}</section>)}</div>
    </ResourceState><p className="pk-note">{t('environment.readOnlyHint')}</p></Section>
  </div>
}
