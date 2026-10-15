import React, { useRef } from 'react'

export const array = (value) => Array.isArray(value) ? value : []
export const textValue = (value, t) => value == null || value === '' ? t('common.unknown') : typeof value === 'object' ? JSON.stringify(value) : String(value)
export const stagger = (index) => `pk-enter pk-i-${Math.min(index, 15)}`

/**
 * Keys that showed up after the first non-empty render. Rows with such a key get the
 * `pk-arrived` class and slide in once; the first load never animates as "new".
 */
export function useArrivals(keys) {
  const seen = useRef(null)
  const arrived = useRef(new Set())
  if (seen.current === null) {
    if (keys.length) seen.current = new Set(keys)
  } else {
    for (const key of keys) if (!seen.current.has(key)) { seen.current.add(key); arrived.current.add(key) }
  }
  return arrived.current
}

/** Small info marker: caveats live here instead of in paragraphs. Tooltip text shows on hover and focus. */
export function Info({ text, label }) {
  if (!text) return null
  return <span className="pk-info" tabIndex={0} role="note" aria-label={label ? `${label}: ${text}` : text} data-tip={text}>i</span>
}

const SOURCE_GLYPH = { live: '●', document: '▤', derived: '≈', preview: '◇' }
export function SourceTag({ kind = 'live', source, t }) {
  kind = source || kind
  return <span className={`pk-source pk-source-${kind}`} data-source={kind} data-tip={t(`source.${kind}Tip`)} data-edge="end" tabIndex={0}>
    <span aria-hidden="true">{SOURCE_GLYPH[kind] ?? '·'}</span>{t(`source.${kind}`)}
  </span>
}

export function Section({ title, source = 'live', t, children, className = '', hint, aside }) {
  return <section className={`pk-section ${source === 'preview' ? 'pk-preview' : ''} ${className}`} data-source={source}>
    <header className="pk-section-head"><h3>{title}</h3><Info text={hint} />{aside}<SourceTag kind={source} t={t} /></header>
    {children}
  </section>
}

export function EmptyState({ t, message, kind = 'empty' }) {
  return <div className={`pk-state pk-state-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
    <span className="pk-state-icon" aria-hidden="true">{kind === 'loading' ? '◌' : kind === 'error' ? '!' : '○'}</span>
    <p>{message || t(kind === 'loading' ? 'status.loading' : kind === 'error' ? 'status.unavailable' : 'status.noData')}</p>
  </div>
}

export function ResourceState({ resource, t, empty = false, emptyText, children, disabledText, source = 'live' }) {
  const phase = resource?.phase || 'loading'
  if (phase === 'disabled') return <EmptyState t={t} message={disabledText || t('common.queryPrompt')} />
  if (phase === 'loading' && resource?.data == null) return <EmptyState t={t} kind="loading" />
  if ((phase === 'error' || phase === 'unavailable') && resource?.data == null) return <div>
    <EmptyState t={t} kind="error" message={/(active session|services? capability|client service is unavailable)/i.test(String(resource?.error || '')) ? t('shell.sessionRequired') : undefined} />
    {resource?.error && <p className="pk-error-detail"><code>{textValue(resource.error, t)}</code></p>}
  </div>
  const meta = resource.meta
  const gaps = [...array(meta?.gaps), ...array(meta?.required_missing)]
  const documentation = source === 'document' || meta?.origin_kind === 'documentation'
  const fresh = meta?.freshness || {}
  const stale = phase === 'error' || phase === 'unavailable' || gaps.length > 0 || (!documentation && (fresh.projection_stale === true || Number(fresh.projection_lag_seq || 0) > 0 || ['stale', 'source_failed', 'incomplete'].includes(fresh.state) || ['incomplete', 'unknown'].includes(meta?.completeness)))
  const noData = phase === 'empty' || resource?.data == null || empty
  return <>
    {stale && <div className="pk-stale-banner" role="status"><span aria-hidden="true">△</span><strong>{t(documentation ? 'status.documentGaps' : 'status.stale')}</strong>
      {resource.error && <span>{textValue(resource.error, t)}</span>}
      {gaps.length > 0 && <details><summary>{t('shell.gaps', { count: gaps.length })}</summary><ul>{gaps.map((gap, i) => <li key={i}><code>{textValue(gap, t)}</code></li>)}</ul></details>}
    </div>}{noData ? <EmptyState t={t} message={emptyText} /> : children}
  </>
}

const KNOWN_STATUS = new Set(['completed', 'failed', 'unknown', 'running', 'starting', 'cancelled', 'interrupted', 'pending', 'approved', 'rejected', 'expired', 'prepared', 'claimed', 'applying', 'applied', 'selected', 'not_checked', 'satisfied', 'missing', 'too_old', 'ok', 'passed', 'not_validated', 'limited_evidence', 'review_required', 'trial'])
export function Badge({ value = 'unknown', t }) {
  const status = typeof value === 'string' ? value : 'unknown'
  return <span className="pk-badge" data-status={status}>{KNOWN_STATUS.has(status) ? t(`status.${status}`) : status}</span>
}

/**
 * The verdict language used in every view: glyph + colour + label.
 * passed: independent check passed (self-test). failed: failure kept on record.
 * unknown: provider outcome unconfirmed, never retried automatically. human: waits for a person. open: not checked yet.
 */
export const VERDICT_GLYPH = { passed: '✓', failed: '✕', unknown: '?', human: '◐', open: '○' }
export function verdictOf(attempt) {
  const result = attempt?.verification_result
  const checked = typeof result === 'string' ? result
    : result && typeof result === 'object' ? (result.passed === true ? 'passed' : result.passed === false ? 'failed' : result.status ?? result.result ?? null) : null
  if (attempt?.status === 'failed' || checked === 'failed') return 'failed'
  if (attempt?.status === 'unknown' || !attempt?.status) return 'unknown'
  if (checked === 'passed') return 'passed'
  return 'open'
}
export function Verdict({ value = 'open', t, size = 'md', stamp = false }) {
  const verdict = VERDICT_GLYPH[value] ? value : 'open'
  // The keyed child remounts when the verdict changes, so the stamp animation replays on a new result.
  return <>{<span key={verdict} className={`pk-verdict pk-verdict-${size}`} data-verdict={verdict} data-stamp={stamp ? 'true' : 'false'} data-tip={t(`verdict.${verdict}.tip`)} tabIndex={0}>
    <span className="pk-verdict-glyph" aria-hidden="true">{VERDICT_GLYPH[verdict]}</span><span className="pk-verdict-label">{t(`verdict.${verdict}`)}</span>
  </span>}</>
}

/** A number that ticks (re-animates) whenever its value changes. */
export function Ticker({ value }) {
  return <>{<span key={String(value)} className="pk-tick">{value}</span>}</>
}

export function Stat({ label, value, index = 0, tone }) {
  return <div className={`pk-stat ${stagger(index)}`} data-tone={tone}><strong className="pk-number"><Ticker value={value} /></strong><span>{label}</span></div>
}

export function Fields({ values, t }) {
  return <dl className="pk-fields">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{textValue(value, t)}</dd></div>)}</dl>
}

export function DataList({ items, t }) {
  return array(items).length ? <ul className="pk-data-list">{array(items).map((item, i) => <li className={stagger(i)} key={i}><code>{textValue(item, t)}</code></li>)}</ul> : <p className="pk-quiet">{t('common.none')}</p>
}

export function ViewTitle({ id, t, subtitle, children }) {
  return <header className="pk-view-heading"><div><h2>{t(`navigation.${id}`)}</h2>{subtitle && <p>{subtitle}</p>}</div>{children}</header>
}

/** A short caption-and-value pair used in ledger rows. */
export function Figure({ label, value, tone, index = 0 }) {
  return <div className={`pk-figure ${stagger(index)}`} data-tone={tone}><strong className="pk-number"><Ticker value={value} /></strong><span>{label}</span></div>
}

export const shortId = (value, size = 8) => {
  const text = String(value ?? '')
  const tail = text.split('-').pop()
  return tail.length > size ? tail.slice(-size) : tail || text
}
