import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { requireWorkspace, workspaceDependency } from '../scripts/dependencies.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
const temp = mkdtempSync(join(tmpdir(), 'pk-panel-render-'))
after(() => rmSync(temp, { recursive: true, force: true }))
const outfile = join(temp, 'panel.cjs')
await requireWorkspace('esbuild').build({
  stdin: { contents: [
    "export { apply } from './client/src/main.jsx'",
    "export { Shell, metadataIsStale } from './client/src/app/Shell.jsx'",
    "export { VIEWS, VIEW_IDS, PermissionNotice } from './client/src/views/index.jsx'",
    "export { phaseOf } from './client/src/views/helpers.js'",
    "export { createTranslator, messages } from './client/src/i18n/messages.js'",
    "export { ResourceState } from './client/src/parts/Primitives.jsx'",
    "export { createElement } from 'react'",
    "export { renderToStaticMarkup } from 'react-dom/server'",
  ].join('\n'), resolveDir: root, loader: 'jsx' },
  bundle: true, platform: 'node', format: 'cjs', outfile, jsx: 'automatic',
  alias: { react: workspaceDependency('react'), 'react-dom': workspaceDependency('react-dom') },
})
const panel = createRequire(import.meta.url)(outfile)
const render = (component, props) => panel.renderToStaticMarkup(panel.createElement(component, props))
const sourceByView = { overview: 'live', design: 'document', structure: 'document', requirements: 'live', permissions: 'live',
  execution: 'live', knowledge: 'preview', errors: 'derived', skills: 'document', environment: 'live', versions: 'live', workspace: 'preview',
  documents: 'document', events: 'live' }
function resources() {
  const data = {
    overview: { object_counts: { task: 1 }, phases: { dispatch_ready: 1 }, blockers: [], source_gaps: [] },
    compare: { attempts: [{ attempt_id: 'attempt-1', strategy_id: 's1', status: 'unknown', verification_result: 'pending' }], failures_retained: [], cost: { unknown: 1 }, comparability: { comparable: false, reason: 'different evidence' } },
    approvals: { queue: [{ approval_id: 'approval-1', status: 'pending', snapshot_id: 'snapshot-1', snapshot_digest: 'a'.repeat(64), head_version: 1, expires_at: '2099-01-01T00:00:00Z' }], pending_count: 1 },
    timeline: { events: [{ kind: 'event', event_type: 'attempt.unknown', commit_seq: '4', object_type: 'attempt', object_id: 'attempt-1' }] },
    tree: { nodes: [{ node_id: 'K-ROOT', document: 'root.md', node_kind: 'root', navigation_parent: null, depends_on: [], related_to: [] }] },
    skills: { skills: [{ skill_id: 'skill-demo', path: 'skill.md', current_version: '0.1.0', versions: [{
      version: '0.1.0', status: 'trial', validation_status: 'limited_evidence', source_revision: 'revision-1',
      scope: { applies_to: ['test evidence'], prerequisites: [], exclusions: ['release'] }, review_refs: [], evidence_refs: [],
    }] }] }, trace: { nodes: [{ node_id: 'task:task-1', object_type: 'task', object_id: 'task-1', exists: true, depth: 0 }], edges: [], truncated: true },
    coverage: { requirements: [], covered: 0, denominator: 0 }, environment: { data_state: 'no_data', facts: [] }, operation: {},
    documents: { documents: [{ path: 'DELIVERY_PLAN.md', title: 'Plan', category: 'plans' }, { path: 'docs/handoffs/a.md', title: 'Handoff', category: 'handoffs' }], count: 2 },
    document: { path: 'DELIVERY_PLAN.md', title: 'Plan', text: '# Plan\n\n| a | b |\n| --- | --- |\n| `x` | [h](docs/handoffs/a.md) |\n\n- [ ] open item\n- [x] done item\n\n```\ncode\n```',
      references: [{ path: 'docs/handoffs/a.md', exists: true }, { path: 'docs/gone.md', exists: false }] },
    events: [{ commit_seq: '3', event_index: 0, event_type: 'attempt.started', event_schema: 'v1', command_id: 'c-1', object_refs: [{ object_type: 'attempt', object_id: 'attempt-1' }] }],
  }
  return Object.fromEntries(Object.entries(data).map(([name, value]) => [name, { phase: 'ready', data: value,
    meta: { as_of_seq: '4', completeness: 'complete', freshness: { state: 'observed', store_head_seq: '4', projection_lag_seq: '0', projection_stale: false }, gaps: [] }, refresh() {} }]))
}
function assertReadOnly(html) {
  assert.ok(!html.includes('style='), 'CSP forbids inline style attributes')
  assert.ok(!html.includes('已通过验收'), 'must not claim acceptance')
  assert.ok(!html.includes('已发布'), 'must not claim release')
  const controls = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/gi) ?? []
  for (const control of controls) assert.doesNotMatch(control, /批准|拒绝|撤销|\bapprove\b|\breject\b|\brevoke\b/i)
}

test('native entry registers a single panel and disposes the locale catalog and slot', () => {
  const slots = []
  let localeOff = 0
  let panelOff = 0
  const ctx = {
    slots: { register: (name, render, options) => { slots.push({ name, render, options }); return () => { panelOff += 1 } } },
    locale: { register: (namespace, messages) => {
      assert.equal(namespace, 'project-kernel'); assert.ok(messages.en); assert.ok(messages['zh-CN']); return () => { localeOff += 1 }
    } },
  }
  const dispose = panel.apply(ctx)
  assert.equal(slots.length, 1)
  assert.equal(slots[0].name, 'workbench.panel')
  const html = panel.renderToStaticMarkup(slots[0].render())
  assertReadOnly(html)
  for (const id of panel.VIEW_IDS) assert.ok(html.includes(panel.createTranslator('zh-CN')(`navigation.${id}`)))
  dispose(); dispose()
  assert.equal(localeOff, 1)
  assert.equal(panelOff, 1)
})

for (const locale of ['en', 'zh-CN']) {
  for (const id of panel.VIEW_IDS) {
    test(`${id} displays its title and source with ${locale}, preserving read-only and CSP rules`, () => {
      const translate = panel.createTranslator(locale)
      const t = (key, vars) => {
        assert.equal(typeof panel.messages[locale]?.[key], 'string', `missing ${locale} translation ${key}`)
        return translate(key, vars)
      }
      const html = render(panel.VIEWS[id], { resources: resources(), t, asOfSeq: null, maxSeq: '4', setAsOfSeq() {},
        documentPath: 'DELIVERY_PLAN.md', openDocument() {} })
      assert.ok(html.includes(t(`navigation.${id}`)))
      assert.ok(html.includes(`data-source="${sourceByView[id]}"`), `missing ${sourceByView[id]} source`)
      assertReadOnly(html)
      if (id === 'knowledge' || id === 'skills') assert.ok(html.includes(t('source.preview')))
    })
  }
}

test('document reader renders markdown as elements, marks missing references and flags the draft plan', () => {
  const t = panel.createTranslator('zh-CN')
  const html = render(panel.VIEWS.documents, { resources: resources(), t, documentPath: 'DELIVERY_PLAN.md', openDocument() {} })
  assert.ok(html.includes('<table'), 'tables render as tables')
  assert.ok(html.includes('data-task="open"') && html.includes('data-task="done"'), 'checklists keep their state')
  assert.ok(html.includes('docs/gone.md') && html.includes(t('documents.missing')), 'missing references stay visible')
  assert.ok(html.includes(t('documents.planNotice')), 'the draft plan carries its void-items notice')
  assert.ok(!html.includes('<script'), 'document text is never injected as HTML')
  assertReadOnly(html)
})

test('approval popup uses queue and remains display-only, with no current countdown in history', () => {
  const t = panel.createTranslator('zh-CN')
  const props = { resource: resources().approvals, t, asOfSeq: null }
  const live = render(panel.PermissionNotice, props)
  assert.ok(live.includes('approval-1'))
  assert.ok(live.includes('snapshot-1'))
  assertReadOnly(live)
  const history = render(panel.PermissionNotice, { ...props, asOfSeq: '4' })
  assert.ok(!history.includes('pk-countdown'))
})

for (const locale of ['en', 'zh-CN']) {
  test(`design map lists sixteen items, each with a code path and one of three statuses (${locale})`, () => {
    const t = panel.createTranslator(locale)
    const html = render(panel.VIEWS.design, { resources: resources(), t })
    const rows = html.match(/pk-design-row/g) ?? []
    assert.equal(rows.length, 16)
    for (const status of ['tested', 'unwired', 'preview']) assert.ok(html.includes(t(`design.status.${status}`)), `missing status ${status}`)
    for (const path of ['src/project_kernel/data/store/uow.py', 'tests/p14_science_demo/science_executor.py', 'src/project_kernel/interfaces/rpc/policy.py',
      'docs/modules/registry.json', 'src/project_kernel/knowledge', 'docs/records/skills/registry.json', 'docs/frontend/workspace-project-design.md']) {
      assert.ok(html.includes(path), `missing path ${path}`)
    }
    assert.equal((html.match(/data-status="preview"/g) ?? []).length >= 3, true, 'design previews stay marked')
    assertReadOnly(html)
  })
}

test('the verdict language is used by overview and execution with glyph, colour hook and label', () => {
  const t = panel.createTranslator('zh-CN')
  const fixture = resources()
  fixture.compare.data = { attempts: [
    { attempt_id: 'a-3', strategy_id: 's3', status: 'unknown', verification_result: null },
    { attempt_id: 'a-1', strategy_id: 's1', status: 'completed', verification_result: 'failed', alpha_fit: 0.35, reason: 'outside tolerance' },
    { attempt_id: 'a-2', strategy_id: 's2', status: 'completed', verification_result: 'passed', alpha_fit: 0.37286 },
  ], failures_retained: ['a-3'], comparability: { comparable: true }, selected: { attempt_id: 'a-2', basis: 'explicit_selection', reason: 'passes the independent check' } }
  for (const view of ['overview', 'execution']) {
    const html = render(panel.VIEWS[view], { resources: fixture, t, navigate() {} })
    for (const key of ['passed', 'failed', 'unknown']) assert.ok(html.includes(`data-verdict="${key}"`), `${view} lacks ${key}`)
    for (const label of ['通过', '失败·保留', '未知·不重跑']) assert.ok(html.includes(label), `${view} lacks ${label}`)
    assertReadOnly(html)
  }
  const execution = render(panel.VIEWS.execution, { resources: fixture, t })
  assert.ok(execution.includes('0.35000') && execution.includes('0.37286'), 'fit values show when the service carries them')
  assert.ok(execution.includes('outside tolerance') && execution.includes('passes the independent check'), 'check reason and selection reason show')
})

test('approvals show a large digest prefix, the terminal line as plain text, and no decision control', () => {
  const t = panel.createTranslator('zh-CN')
  const html = render(panel.VIEWS.permissions, { resources: resources(), t, asOfSeq: null })
  assert.ok(html.includes('aaaaaaaa'), 'first eight digest characters')
  assert.ok(html.includes('pk-digest-prefix'))
  assert.ok(html.includes('在终端运行 tools\\pk-human-approve.ps1，输入摘要前 8 位确认'))
  assert.ok(!/<button[^>]*>[^<]*pk-human-approve/.test(html), 'the terminal line is text, not a button')
  assertReadOnly(html)
})

test('events can be searched and grouped by commit_seq', () => {
  const t = panel.createTranslator('en')
  const html = render(panel.VIEWS.events, { resources: resources(), t })
  assert.ok(html.includes('type="search"'))
  assert.ok(html.includes('pk-commit-seq') && html.includes('#3'))
  assert.ok(html.includes('1 of 1') || html.includes('1 / 1') || /of\s*1/.test(html), 'match count')
  assertReadOnly(html)
})

test('structure highlights first-order neighbours and says plainly when no conversation is mapped', () => {
  const t = panel.createTranslator('zh-CN')
  const fixture = resources()
  fixture.tree.data = { nodes: [
    { node_id: 'K-ROOT', node_kind: 'root', navigation_parent: null, depends_on: ['K-A'], related_to: [], document: 'root.md', conversation_refs: [] },
    { node_id: 'K-A', node_kind: 'aggregate', navigation_parent: 'K-ROOT', depends_on: [], related_to: ['K-B'], document: 'a.md', conversation_refs: [] },
    { node_id: 'K-B', node_kind: 'aggregate', navigation_parent: 'K-ROOT', depends_on: [], related_to: [], document: 'b.md', conversation_refs: [] },
  ] }
  const html = render(panel.VIEWS.structure, { resources: fixture, t, openDocument() {} })
  assert.ok(html.includes('data-rel="out"') && html.includes('data-rel="self"') && html.includes('data-rel="none"'))
  assert.ok(html.includes(t('structure.noConversation')))
  assert.ok(html.includes(t('structure.outLabel', { n: 1 })))
})

test('every translation key used by a component exists in both languages', async () => {
  const { readFileSync, readdirSync } = await import('node:fs')
  const dir = join(root, 'client/src')
  const files = []
  const walk = (folder) => { for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name)
    if (entry.isDirectory()) walk(path); else if (/\.(jsx|js)$/.test(entry.name) && !path.includes('i18n')) files.push(path)
  } }
  walk(dir)
  const missing = new Set()
  for (const file of files) {
    for (const match of readFileSync(file, 'utf8').matchAll(/\bt\(\s*['"]([\w.]+)['"]/g)) {
      for (const locale of ['en', 'zh-CN']) if (typeof panel.messages[locale][match[1]] !== 'string') missing.add(`${locale}:${match[1]}`)
    }
  }
  assert.deepEqual([...missing], [])
  assert.deepEqual(Object.keys(panel.messages.en).sort(), Object.keys(panel.messages['zh-CN']).sort())
})

test('progress uses verification_result and does not infer delivery from approval alone', () => {
  assert.equal(panel.phaseOf([{ verification_result: { passed: false } }], null, []), 2)
  assert.equal(panel.phaseOf([{ verification: true }], null, []), 1)
  assert.equal(panel.phaseOf([], { attempt_id: 'a' }, [{ status: 'approved' }]), 4)
})

test('observed reads are distinct from stale or incomplete reads', () => {
  const meta = resources().overview.meta
  assert.equal(panel.metadataIsStale(meta), false)
  assert.equal(panel.metadataIsStale({ ...meta, completeness: 'incomplete' }), true)
  assert.equal(panel.metadataIsStale({ ...meta, freshness: { state: 'observed', projection_stale: true } }), true)
  const t = panel.createTranslator('zh-CN')
  const html = render(panel.ResourceState, { resource: resources().overview, t, children: 'live-read' })
  assert.ok(!html.includes('pk-stale-banner'), 'observed is the real kernel read state and must not be called expired')
  const documentation = render(panel.ResourceState, { resource: { phase: 'ready', data: {}, meta: {
    as_of_seq: null, completeness: 'unknown', freshness: null, origin_kind: 'documentation', gaps: [],
  } }, t, source: 'document', children: 'document-read' })
  assert.ok(!documentation.includes('pk-stale-banner'), 'document declaration has no runtime completeness')
})

test('empty responses retain their source gaps and distinguish no probe from a failed probe', () => {
  const t = panel.createTranslator('zh-CN')
  const empty = render(panel.ResourceState, { resource: { phase: 'empty', data: { data_state: 'no_data' },
    meta: { completeness: 'incomplete', gaps: ['no_environment_snapshot'] } }, t })
  assert.ok(empty.includes('no_environment_snapshot'), 'lack of records must not erase source gaps')
  const fixture = resources()
  const noProbe = render(panel.VIEWS.environment, { resources: fixture, t })
  assert.ok(noProbe.includes(t('environment.noProbe')))
  fixture.environment.data = { data_state: 'source_failed', facts: [] }
  const failedProbe = render(panel.VIEWS.environment, { resources: fixture, t })
  assert.ok(failedProbe.includes(t('environment.sourceFailed')))
  assert.ok(!failedProbe.includes(t('environment.noProbe')))
})
