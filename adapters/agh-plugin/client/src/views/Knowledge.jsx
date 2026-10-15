import React, { useState } from 'react'
import { Section, SourceTag, ViewTitle, Info } from '../parts/Primitives.jsx'

export default function Knowledge({ t }) {
  const [includeOptional, setIncludeOptional] = useState(true)
  return <div className="pk-view pk-knowledge-preview"><ViewTitle id="knowledge" t={t} subtitle={t('knowledge.subtitle')} />
    <div className="pk-preview-notice"><SourceTag kind="preview" t={t} /><p>{t('knowledge.notConnected')}</p></div>
    <div className="pk-view-grid">
      <Section title={t('knowledge.tree')} source="preview" t={t}><ul className="pk-knowledge-tree"><li><details open><summary>{t('knowledge.project')}</summary><ul><li>{t('knowledge.contracts')}</li><li>{t('knowledge.decisions')}</li><li>{t('knowledge.evidence')}</li></ul></details></li><li><details open><summary>{t('knowledge.profile')}</summary><ul><li>{t('knowledge.preferences')}</li><li>{t('knowledge.feedback')}</li></ul></details></li></ul></Section>
      <Section title={t('knowledge.budget')} source="preview" t={t} hint={t('knowledge.budgetHint')}><div className="pk-budget-card" data-priority="mandatory"><strong>{t('knowledge.mandatory')}</strong><p>{t('knowledge.mandatoryDetail')}</p><span className="pk-badge">{t('knowledge.retained')}</span></div><div className="pk-budget-card" data-priority="optional"><label className="pk-check-label"><input type="checkbox" checked={includeOptional} onChange={(event) => setIncludeOptional(event.target.checked)} />{t('knowledge.optional')}</label><p>{t('knowledge.optionalDetail')}</p><p className="pk-note">{t(includeOptional ? 'knowledge.optionalIncluded' : 'knowledge.optionalExcluded')}</p></div></Section>
    </div>
    <Section title={t('knowledge.provenance')} source="preview" t={t}><div className="pk-knowledge-source"><code>docs/records/user-learning-profile.md</code><p>{t('knowledge.sourceLimit')}</p><blockquote>{t('knowledge.sampleSummary')}</blockquote><p className="pk-note">{t('knowledge.descriptive')}</p></div></Section>
  </div>
}
