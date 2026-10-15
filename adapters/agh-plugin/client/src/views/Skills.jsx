import React, { useState } from 'react'
import { Section, ResourceState, Fields, Badge, ViewTitle, DataList, array, stagger } from '../parts/Primitives.jsx'

export const SCORE_DIMENSIONS = ['correctness', 'applicability', 'reuse_benefit', 'maintainability']
export function AssessmentPreview({ t }) {
  const [scores, setScores] = useState(() => Object.fromEntries(SCORE_DIMENSIONS.map((dimension) => [dimension, 'null'])))
  return <div className="pk-assessment-preview"><p className="pk-note">{t('skills.scoreHint')}</p><form className="pk-preview-form" onSubmit={(event) => event.preventDefault()}>
    <label>{t('skills.newSkill')}<input placeholder={t('skills.namePlaceholder')} maxLength={128} /></label><label>{t('skills.version')}<input placeholder="0.1.0" maxLength={64} /></label><label className="pk-form-wide">{t('skills.scope')}<textarea placeholder={t('skills.scopePlaceholder')} rows="2" maxLength={2000} /></label>
    {SCORE_DIMENSIONS.map((dimension) => <label key={dimension}>{t(`score.${dimension}`)}<select value={scores[dimension]} onChange={(event) => setScores({ ...scores, [dimension]: event.target.value })}>{['null', '0', '1', '2'].map((score) => <option key={score} value={score}>{score === 'null' ? t('skills.unassessed') : t(`score.value${score}`)}</option>)}</select></label>)}
  </form><p className="pk-note">{t('skills.localOnly')}</p></div>
}

export default function Skills({ resources, t }) {
  const resource = resources.skills
  const skills = array(resource?.data?.skills)
  return <div className="pk-view"><ViewTitle id="skills" t={t} subtitle={t('skills.subtitle')} />
    <Section title={t('skills.registry')} source="document" t={t} hint={t('skills.registryHint')}><ResourceState resource={resource} t={t} source="document" empty={!skills.length}>
      <div className="pk-skill-list">{skills.map((skill, i) => <article className={`pk-skill-card ${stagger(i)}`} key={skill.skill_id}><header><h4><code>{skill.skill_id}</code></h4><span>{t('skills.currentVersion')}: <code>{skill.current_version}</code></span></header><p><code>{skill.path}</code></p>
        {array(skill.versions).map((version) => <details className="pk-skill-version" key={version.version} open={version.version === skill.current_version}><summary><code>{version.version}</code><Badge value={version.status} t={t} /><Badge value={version.validation_status} t={t} /></summary><Fields t={t} values={[[t('skills.sourceRevision'), version.source_revision]]} />{['applies_to', 'prerequisites', 'exclusions'].map((key) => <div className="pk-scope-group" key={key}><h5>{t(`skills.${key}`)}</h5><DataList items={version.scope?.[key]} t={t} /></div>)}<h5>{t('skills.reviewRefs')}</h5><DataList items={version.review_refs} t={t} /><h5>{t('skills.evidenceRefs')}</h5><DataList items={version.evidence_refs} t={t} /></details>)}
        <h5>{t('skills.recordedScores')}</h5><Fields t={t} values={SCORE_DIMENSIONS.map((dimension) => [t(`score.${dimension}`), t('skills.unassessed')])} /><p className="pk-note">{t('skills.noRecordedScores')}</p>
      </article>)}</div>
    </ResourceState></Section>
    <Section title={t('skills.formPreview')} source="preview" t={t}><AssessmentPreview t={t} /></Section>
  </div>
}
