import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { createTranslator } from '../i18n/messages.js'
import { Info } from '../parts/Primitives.jsx'
import { VIEW_IDS, VIEWS, VIEW_GROUPS, PermissionNotice } from '../views/index.jsx'
import { usePanelVisibility, usePoll } from '../data/usePoll.js'

const noopSubscribe = () => () => {}
const VIEW_SERVICES = {
  overview: ['compare'], design: [], structure: ['tree', 'trace'], requirements: ['coverage', 'trace'],
  permissions: [], execution: ['compare', 'operation'], knowledge: [],
  errors: ['compare', 'timeline'], skills: ['skills'], environment: ['environment'], versions: ['timeline'],
  workspace: ['tree'], documents: ['documents', 'document'], events: ['events'],
}
// Documents describe the repository as it is now; history watermarks never apply to them.
const DOCUMENT_SERVICES = ['tree', 'skills', 'documents', 'document']

function useHostSnapshot(service, fallback) {
  const subscribe = useCallback((listener) => service?.subscribe?.(listener) ?? noopSubscribe(), [service])
  const read = useCallback(() => service?.getSnapshot?.() ?? fallback, [service, fallback])
  return useSyncExternalStore(subscribe, read, read)
}

export function metadataIsStale(meta) {
  if (!meta) return false
  const freshness = meta.freshness ?? {}
  return freshness.projection_stale === true || Number(freshness.projection_lag_seq ?? 0) > 0 ||
    ['stale', 'source_failed', 'incomplete'].includes(freshness.state) ||
    ['incomplete', 'unknown'].includes(meta.completeness) ||
    Boolean(meta.gaps?.length || meta.required_missing?.length)
}

/**
 * The shell owns navigation and query scope; views only display service resources.
 * It renders as a fixed drawer over the AGH workbench so it never takes height from the
 * conversation column (the host mounts workbench.panel inside the flex <main>).
 */
export function Shell({ ctx, config = {}, initialView = 'overview', initialOpen = true }) {
  const [view, setView] = useState(VIEW_IDS.includes(initialView) ? initialView : 'overview')
  const [open, setOpen] = useState(initialOpen)
  const [wide, setWide] = useState(false)
  const [asOfSeq, setAsOfSeq] = useState(null)
  const [maxSeq, setMaxSeq] = useState('0')
  const [documentPath, setDocumentPath] = useState(null)
  const theme = useHostSnapshot(ctx?.theme, 'dark')
  const locale = useHostSnapshot(ctx?.locale, 'zh-CN')
  const sessionId = useHostSnapshot(ctx?.session, null)
  const t = useMemo(() => ctx?.locale?.bind?.('project-kernel') ?? createTranslator(locale), [ctx?.locale, locale])
  const { target, visible: inViewport } = usePanelVisibility()
  const visible = open && inViewport
  const active = !ctx?.session || Boolean(sessionId)
  const needs = VIEW_SERVICES[view] ?? []
  // Overview and approvals keep polling while the drawer is closed so a pending request can open it.
  const options = (service, extra = {}) => ({
    visible: service === 'approvals' || service === 'overview' ? inViewport : visible,
    active: active && (service === 'overview' || service === 'approvals' || needs.includes(service)),
    asOfSeq: DOCUMENT_SERVICES.includes(service) ? null : asOfSeq, sessionId, ...extra,
  })
  const approvalsResource = usePoll(ctx, 'approvals', options('approvals'))
  const hasPending = Number(approvalsResource.data?.pending_count ?? 0) > 0
  const loadedResources = {
    overview: usePoll(ctx, 'overview', options('overview')),
    compare: usePoll(ctx, 'compare', { ...options('compare'), active: active && (hasPending || needs.includes('compare')), visible: hasPending ? inViewport : visible }),
    approvals: approvalsResource,
    timeline: usePoll(ctx, 'timeline', options('timeline')),
    trace: usePoll(ctx, 'trace', options('trace')),
    coverage: usePoll(ctx, 'coverage', options('coverage')),
    environment: usePoll(ctx, 'environment', options('environment')),
    operation: usePoll(ctx, 'operation', options('operation', { manual: true })),
    tree: usePoll(ctx, 'tree', options('tree', { interval: 10000 })),
    skills: usePoll(ctx, 'skills', options('skills', { interval: 10000 })),
    documents: usePoll(ctx, 'documents', options('documents', { interval: 15000 })),
    document: usePoll(ctx, 'document', options('document', { manual: true, interval: 15000 })),
    events: usePoll(ctx, 'events', options('events')),
  }
  const resources = active ? loadedResources : Object.fromEntries(Object.entries(loadedResources).map(([name, resource]) => [name, {
    phase: 'unavailable', error: t('shell.sessionRequired'), refresh: resource.refresh,
  }]))
  const meta = resources.overview.meta
  const error = resources.overview.error
  const connected = active && resources.overview.phase === 'ready'
  const gaps = [...(meta?.gaps ?? []), ...(meta?.required_missing ?? [])]
  const pendingCount = Number(resources.approvals?.data?.pending_count ?? 0)
  const refresh = () => ['overview', 'approvals', ...needs].forEach((name) => {
    if (!['operation', 'document'].includes(name) || resources[name].phase !== 'disabled') resources[name]?.refresh()
  })
  useEffect(() => {
    const head = meta?.freshness?.store_head_seq ?? meta?.as_of_seq
    if (head !== null && head !== undefined && /^(0|[1-9][0-9]*)$/.test(String(head))) {
      setMaxSeq((current) => BigInt(head) > BigInt(current) ? String(head) : current)
    }
  }, [meta])
  useEffect(() => { setAsOfSeq(null); setMaxSeq('0') }, [sessionId])
  // A new pending human request opens the drawer once; dismissing it is the user's choice.
  useEffect(() => { if (pendingCount > 0 && asOfSeq == null) setOpen(true) }, [pendingCount, asOfSeq])
  useEffect(() => {
    if (!open || typeof document === 'undefined') return undefined
    const onKey = (event) => { if (event.key === 'Escape' && !event.defaultPrevented) setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])
  const CurrentView = VIEWS[view]
  // Any view may open a project document; the documents view then reads it through pk.document.
  const openDocument = (path) => {
    setDocumentPath(path)
    setView('documents')
    resources.document?.refresh?.({ path })
  }
  const select = (id) => { setView(id); setOpen(true) }
  const navigateWithKeys = (event, id) => {
    const change = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0
    if (!change && event.key !== 'Home' && event.key !== 'End') return
    event.preventDefault()
    const index = VIEW_IDS.indexOf(id)
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? VIEW_IDS.length - 1 : (index + change + VIEW_IDS.length) % VIEW_IDS.length
    setView(VIEW_IDS[next])
    event.currentTarget.closest('[role="tablist"]')?.querySelector(`#pk-tab-${VIEW_IDS[next]}`)?.focus()
  }
  const groupOf = VIEW_GROUPS.find((group) => group.views.includes(view))
  return <section ref={target} className="pk-root" data-theme={theme} data-view={view} data-open={open ? 'true' : 'false'} data-wide={wide ? 'true' : 'false'}>
    <button type="button" className="pk-launcher" aria-expanded={open} aria-controls="pk-drawer" onClick={() => setOpen(!open)}>
      <span className="pk-launcher-mark" aria-hidden="true">PK</span>
      <span className="pk-launcher-label">{t('shell.title')}</span>
      {pendingCount > 0 && <span className="pk-launcher-badge" aria-label={t('permissions.pendingDrawer', { count: pendingCount })}>{pendingCount}</span>}
      <span className="pk-live" data-state={connected ? 'on' : 'off'} aria-hidden="true" />
    </button>
    <div id="pk-drawer" className="pk-drawer" role="dialog" aria-modal="false" aria-label={t('shell.title')} hidden={!open}>
      <header className="pk-shell-header">
        <div className="pk-shell-branding"><span className="pk-brand-mark" aria-hidden="true">PK</span>
          <div><h2>{config.publicConfig?.title ?? t('shell.title')}</h2>
            <nav className="pk-breadcrumb" aria-label={t('shell.breadcrumb')}><span>{groupOf ? t(`group.${groupOf.id}`) : ''}</span><span aria-hidden="true">/</span><strong>{t(`navigation.${view}`)}</strong></nav></div>
        </div>
        <div className="pk-shell-actions">
          <span className="pk-live" data-state={connected ? 'on' : 'off'}>{t(connected ? 'shell.connected' : 'shell.disconnected')}</span>
          <button type="button" className="pk-button" onClick={refresh}>{t('shell.refresh')}</button>
          <button type="button" className="pk-icon-button" aria-pressed={wide} onClick={() => setWide(!wide)} aria-label={t(wide ? 'shell.narrow' : 'shell.widen')} title={t(wide ? 'shell.narrow' : 'shell.widen')}>{wide ? '⇥' : '⇤'}</button>
          <button type="button" className="pk-icon-button" onClick={() => setOpen(false)} aria-label={t('shell.close')} title={t('shell.close')}>×</button>
        </div>
      </header>
      {(!active || error) && <div className="pk-banner pk-warning" role="status"><strong>{t('shell.sessionRequired')}</strong>{error && <p>{t('shell.connectionError', { error })}</p>}</div>}
      <PermissionNotice resource={resources.approvals} compare={resources.compare} t={t} asOfSeq={asOfSeq} />
      <div className="pk-shell-content">
        <aside className="pk-shell-nav">
          <div role="tablist" aria-orientation="vertical" aria-label={t('shell.title')} className="pk-nav">
            {VIEW_GROUPS.map((group) => <div key={group.id} className="pk-nav-group" role="presentation">
              <p className="pk-nav-group-title" role="presentation">{t(`group.${group.id}`)}</p>
              {group.views.map((id) => <button key={id} type="button" id={`pk-tab-${id}`} role="tab" aria-selected={view === id} aria-controls="pk-view-panel" tabIndex={view === id ? 0 : -1}
                className={`pk-nav-item ${view === id ? 'is-active' : ''}`} onKeyDown={(event) => navigateWithKeys(event, id)} onClick={() => select(id)}>
                <span>{t(`navigation.${id}`)}</span>
                {id === 'permissions' && pendingCount > 0 && <span className="pk-count-badge">{pendingCount}</span>}
              </button>)}
            </div>)}
          </div>
        </aside>
        <main className="pk-shell-main">
          <div id="pk-view-panel" className="pk-view-scroll" role="tabpanel" aria-labelledby={`pk-tab-${view}`}>
            <div className="pk-enter" key={view}>
              <CurrentView resources={resources} t={t} asOfSeq={asOfSeq} setAsOfSeq={setAsOfSeq} maxSeq={maxSeq} documentPath={documentPath} openDocument={openDocument} navigate={select} />
            </div>
          </div>
          <footer className="pk-view-metadata">
            <div className={`pk-watermarks ${metadataIsStale(meta) ? 'pk-stale' : ''}`} aria-live="polite">
              {asOfSeq !== null && <span className="pk-history">{t('shell.history', { seq: asOfSeq })}</span>}
              <span>{t('shell.asOf')} <code>#{meta?.as_of_seq ?? '—'}</code></span>
              <span>{t('shell.head')} <code>#{meta?.freshness?.store_head_seq ?? '—'}</code></span>
              <span>{t('shell.completeness')} <strong>{meta?.completeness ?? '—'}</strong></span>
              <span>{t('shell.freshness')} <strong>{meta?.freshness?.state ?? '—'}</strong></span>
              <Info text={t('shell.watermarkTip')} />
              {!meta && <small>{t('shell.noMetadata')}</small>}
              {asOfSeq !== null && <button type="button" className="pk-text-button" onClick={() => setAsOfSeq(null)}>{t('shell.current')}</button>}
              {gaps.length > 0 && <details className="pk-gaps"><summary>{t('shell.gaps', { count: gaps.length })}</summary><ul>{gaps.map((gap, index) => <li key={index}><code>{typeof gap === 'string' ? gap : JSON.stringify(gap)}</code></li>)}</ul></details>}
            </div>
          </footer>
        </main>
      </div>
    </div>
  </section>
}
