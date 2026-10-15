import React, { useState } from 'react'
import { Section, ViewTitle } from '../parts/Primitives.jsx'

const STATUS_GLYPH = { tested: '✓', unwired: '△', preview: '◇' }

// Each item names the code or test that backs it. Status comes from the project documents and tests.
// `doc` marks an item whose evidence is a document declaration rather than a test run.
export const DESIGN_PILLARS = [
  { id: 'memory', items: [
    { id: 'ledger', paths: ['src/project_kernel/data/store/uow.py', 'tests/p15 step A'], status: 'tested' },
    { id: 'unknown', paths: ['tests/p14_science_demo/science_executor.py', 'tests/p15 step B'], status: 'tested' },
    { id: 'idempotent', paths: ['src/project_kernel/data/store/uow.py', 'tests/p15 step D'], status: 'tested' },
    { id: 'knowledge', paths: ['src/project_kernel/knowledge', 'tests/p08_knowledge'], status: 'unwired' },
  ] },
  { id: 'trust', items: [
    { id: 'forged', paths: ['tests/p14_science_demo/science_checker.py', 'tests/p14', 'tests/p15'], status: 'tested' },
    { id: 'human', paths: ['src/project_kernel/interfaces/rpc/policy.py', 'tests/p14', 'tests/p15'], status: 'tested' },
    { id: 'rules', paths: ['src/project_kernel/domain/design/rules.py', 'tests/p15'], status: 'tested' },
    { id: 'voided', paths: ['src/project_kernel/application/delivery', 'tests/p15 step E'], status: 'tested' },
    { id: 'reconcile', paths: ['src/project_kernel/application/delivery', 'tests/p15 step F'], status: 'tested' },
  ] },
  { id: 'view', items: [
    { id: 'readmodel', paths: ['src/project_kernel/data/queries/service.py', 'tests/p15 step G'], status: 'tested' },
    { id: 'tree', paths: ['docs/modules/registry.json'], status: 'tested', doc: true },
    { id: 'panel', paths: ['adapters/agh-plugin/client'], status: 'tested' },
  ] },
  { id: 'integration', items: [
    { id: 'plugin', paths: ['adapters/agh-plugin', 'bridge/protocol'], status: 'tested' },
    { id: 'skill', paths: ['docs/records/skills/registry.json'], status: 'preview' },
    { id: 'exchange', paths: ['docs/architecture/agent-exchange-and-live-forms.md'], status: 'preview' },
    { id: 'workspace', paths: ['docs/frontend/workspace-project-design.md'], status: 'preview' },
  ] },
]

const ALL_ITEMS = DESIGN_PILLARS.flatMap((pillar) => pillar.items)

export function StatusMark({ status, t }) {
  return <span className="pk-design-status" data-status={status}><span aria-hidden="true">{STATUS_GLYPH[status]}</span>{t(`design.status.${status}`)}</span>
}

/** Pain point, mechanism, code or test path, status. A map to scan, not prose to read. */
export default function Design({ t }) {
  const [filter, setFilter] = useState('all')
  const counts = { all: ALL_ITEMS.length }
  for (const item of ALL_ITEMS) counts[item.status] = (counts[item.status] || 0) + 1
  return <div className="pk-view pk-design"><ViewTitle id="design" t={t} subtitle={t('design.subtitle')} />
    <Section title={t('design.map')} source="document" t={t} hint={t('design.mapTip')} aside={
      <div className="pk-filter" role="group" aria-label={t('design.col.status')}>
        {['all', 'tested', 'unwired', 'preview'].map((key) => <button key={key} type="button" className="pk-filter-chip" data-status={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>
          {key === 'all' ? t('design.all') : t(`design.status.${key}`)}<b>{counts[key] || 0}</b></button>)}
      </div>}>
      <div className="pk-design-head" aria-hidden="true"><span>{t('design.col.item')}</span><span>{t('design.col.how')}</span><span>{t('design.col.path')}</span><span>{t('design.col.status')}</span></div>
      {DESIGN_PILLARS.map((pillar) => {
        const items = pillar.items.filter((item) => filter === 'all' || item.status === filter)
        if (!items.length) return null
        return <section key={pillar.id} className="pk-pillar" data-pillar={pillar.id} aria-label={t(`design.pillar.${pillar.id}`)}>
          <h4>{t(`design.pillar.${pillar.id}`)}<small>{items.length}</small></h4>
          <ul>{items.map((item, i) => <li key={item.id} className={`pk-design-row pk-enter pk-i-${Math.min(i, 15)}`} data-status={item.status}>
            <div className="pk-design-pain"><strong>{t(`design.${item.id}.name`)}</strong><span>{t(`design.${item.id}.pain`)}</span></div>
            <p className="pk-design-how">{t(`design.${item.id}.how`)}</p>
            <ul className="pk-design-paths">{item.paths.map((path) => <li key={path}><code>{path}</code></li>)}</ul>
            <div className="pk-design-state"><StatusMark status={item.status} t={t} />{item.doc && <small>{t('design.note.document')}</small>}</div>
          </li>)}</ul>
        </section>
      })}
    </Section>
  </div>
}
