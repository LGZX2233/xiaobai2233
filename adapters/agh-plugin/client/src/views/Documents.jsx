import React, { useMemo, useState } from 'react'
import { ViewTitle, Section, ResourceState, Badge, array } from '../parts/Primitives.jsx'
import { Markdown } from '../parts/Markdown.jsx'

const CATEGORY_ORDER = ['plans', 'handoffs', 'requirements', 'architecture', 'modules', 'frontend', 'records', 'acceptance', 'reviews']

/** Resolve a link inside a document relative to that document's folder. */
export function resolveDocumentLink(from, target) {
  const out = []
  for (const part of [...from.split('/').slice(0, -1), ...target.split('/')]) {
    if (part === '..') out.pop()
    else if (part && part !== '.') out.push(part)
  }
  return out.join('/')
}

export default function Documents({ resources, t, documentPath, openDocument }) {
  const index = resources.documents
  const reader = resources.document
  const documents = array(index?.data?.documents)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(() => new Set(['plans', 'handoffs']))
  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const map = new Map()
    for (const doc of documents) {
      if (needle && !`${doc.path} ${doc.title ?? ''}`.toLowerCase().includes(needle)) continue
      map.set(doc.category, [...(map.get(doc.category) || []), doc])
    }
    return [...map.entries()].sort(([a], [b]) => (CATEGORY_ORDER.indexOf(a) + 99) % 99 - (CATEGORY_ORDER.indexOf(b) + 99) % 99)
  }, [documents, query])
  const current = reader?.data
  const shown = current && current.path === documentPath ? current : null
  const references = array(shown?.references)
  const missing = references.filter((ref) => !ref.exists)
  const follow = (target) => openDocument?.(resolveDocumentLink(shown?.path || '', target))
  return <div className="pk-view pk-documents"><ViewTitle id="documents" t={t} subtitle={t('documents.subtitle')} />
    <div className="pk-documents-layout">
      <Section title={t('documents.index', { count: documents.length })} source="document" t={t} className="pk-doc-nav">
        <ResourceState resource={index} t={t} source="document" empty={!documents.length}>
          <label className="pk-doc-search">{t('documents.search')}<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          {groups.map(([category, docs]) => <details key={category} className="pk-doc-category" open={Boolean(query) || open.has(category)} onToggle={(event) => {
            const next = new Set(open); event.currentTarget.open ? next.add(category) : next.delete(category); setOpen(next)
          }}>
            <summary><span>{t(`documents.category.${category}`) === `documents.category.${category}` ? category : t(`documents.category.${category}`)}</span><span className="pk-count-badge">{docs.length}</span></summary>
            <ul className="pk-doc-list">{docs.map((doc) => <li key={doc.path}><button type="button" className="pk-doc-item" aria-current={doc.path === documentPath ? 'true' : undefined} onClick={() => openDocument?.(doc.path)}>
              <span>{doc.title || doc.path.split('/').pop()}</span><small>{doc.path}</small></button></li>)}</ul>
          </details>)}
        </ResourceState>
      </Section>
      <Section title={shown?.title || documentPath || t('documents.reader')} source="document" t={t} className="pk-doc-reader">
        {!documentPath ? <p className="pk-note">{t('documents.selectPrompt')}</p> : <ResourceState resource={shown ? reader : { ...reader, data: null }} t={t} source="document">
          {shown && <>
            <div className="pk-doc-meta"><code>{shown.path}</code><span>{t('documents.bytes', { bytes: reader.meta?.bytes ?? '—' })}</span>
              {reader.meta?.truncated && <Badge value="limited_evidence" t={t} />}</div>
            {shown.path === 'DELIVERY_PLAN.md' && <p className="pk-banner pk-warning">{t('documents.planNotice')}</p>}
            {references.length > 0 && <details className="pk-doc-refs" open={missing.length > 0}>
              <summary>{t('documents.references', { total: references.length, missing: missing.length })}</summary>
              <ul>{references.map((ref) => <li key={ref.path} data-exists={ref.exists ? 'true' : 'false'}>
                <span className="pk-ref-state">{ref.exists ? t('documents.exists') : t('documents.missing')}</span>
                {ref.exists && /\.md$/.test(ref.path) ? <button type="button" className="pk-md-link" onClick={() => openDocument?.(ref.path)}>{ref.path}</button> : <code>{ref.path}</code>}
              </li>)}</ul>
            </details>}
            <article className="pk-doc-article"><Markdown text={shown.text} openDocument={follow} /></article>
          </>}
        </ResourceState>}
      </Section>
    </div>
  </div>
}
