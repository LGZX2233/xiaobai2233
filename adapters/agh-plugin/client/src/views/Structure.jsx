import React, { useMemo, useState } from 'react'
import { Section, ResourceState, SourceTag, ViewTitle, Info, array } from '../parts/Primitives.jsx'
import { TracePanel } from '../parts/TraceGraph.jsx'
import { moduleDegrees, moduleNeighbours } from './helpers.js'


function computeAllDegrees(nodes) {
  const incoming = new Map()
  const outgoing = new Map()
  nodes.forEach((n) => { incoming.set(n.node_id, 0); outgoing.set(n.node_id, array(n.depends_on).length) })
  nodes.forEach((n) => { array(n.depends_on).forEach((id) => { if (incoming.has(id)) incoming.set(id, incoming.get(id) + 1) }) })
  return { incoming, outgoing }
}
function NodeCard({ node, t, openDocument, inDeg = 0, outDeg = 0 }) {
  const facts = node.facts || {}
  const requirementIds = array(facts.requirement_ids)
  const recordCounts = facts.linked_records || {}
  const totalLinks = Object.values(recordCounts).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0)
  const conversations = array(node.conversation_refs)
  return <article className="pk-node-card">
    <header>
      <div><code className="pk-node-id">{node.node_id}</code><span className="pk-node-kind-label">{node.node_kind}</span></div>
      {facts.document_version && <span className="pk-version-badge">v{facts.document_version}</span>}
    </header>
    {facts.title && <h4>{facts.title}</h4>}
    {node.document && <p className="pk-node-doc-link"><button type="button" className="pk-text-button" onClick={() => openDocument(`docs/modules/${node.document}`)}>{node.document}</button></p>}
    <dl className="pk-node-facts">
      {facts.implementation_status && <div><dt>{t('structure.status')}</dt><dd>{facts.implementation_status}</dd></div>}
      {facts.updated_at && <div><dt>{t('structure.updated')}</dt><dd>{facts.updated_at}</dd></div>}
      {facts.source_revision && <div><dt>{t('structure.revision')}</dt><dd><code>{facts.source_revision}</code></dd></div>}
      <div><dt>{t('structure.couplingDegree')}</dt><dd className="pk-degree-chips">
          <span className="pk-degree-chip pk-degree-in" data-tip={t('structure.degreeIncoming')} tabIndex={0}>{t('structure.inLabel', { n: inDeg })}</span>
          <span className="pk-degree-chip pk-degree-out" data-tip={t('structure.degreeOutgoing')} tabIndex={0}>{t('structure.outLabel', { n: outDeg })}</span>
          <Info text={t('structure.degreeHint')} />
        </dd></div>
        {requirementIds.length > 0 && <div><dt>{t('structure.requirements')}</dt><dd className="pk-req-list">
          {requirementIds.map((reqId) => <button key={reqId} type="button" className="pk-req-chip"
            onClick={() => openDocument('docs/requirements/' + reqId + '.md')} title={t('structure.openReq', { id: reqId })}>{reqId}</button>)}
        </dd></div>}
      {totalLinks > 0 && <div><dt>{t('structure.linkedRecords')}</dt><dd><span className="pk-count-badge">{totalLinks}</span></dd></div>}
    </dl>
    {conversations.length > 0
        ? <div className="pk-conversation-refs"><h5>{t('structure.conversations')}</h5>
            <ul className="pk-conv-list">{conversations.map((ref) => <li key={ref}>{ref.endsWith('.md')
              ? <button type="button" className="pk-text-button" onClick={() => openDocument(ref)} title={ref}>{ref.split('/').pop()}</button>
              : <code>{ref}</code>}</li>)}</ul></div>
        : <p className="pk-note">{t('structure.noConversation')}<Info text={t('structure.noConversationTip')} /></p>}
    {totalLinks > 0 && <div className="pk-linked-records">
      <h5>{t('structure.linkedList')}</h5>
      {Object.entries(recordCounts).map(([kind, arr]) => Array.isArray(arr) && arr.length > 0 && <div key={kind}>
        <strong>{kind}:</strong>
        <ul>
          {arr.map((path) => <li key={path}>{path.endsWith('.md')
            ? <button type="button" className="pk-text-button" onClick={() => openDocument(path)} title={path}>{path.split('/').pop()}</button>
            : <code title={path}>{path.split('/').pop()}</code>}</li>)}
        </ul>
      </div>)}
    </div>}
  </article>
}

function ModuleBranch({ node, childrenByParent, expanded, setExpanded, selected, setSelected, t, openDocument, ancestry = [] }) {
  if (ancestry.includes(node.node_id)) return <li className="pk-note pk-note-warn">{t('structure.cycle')}: <code>{node.node_id}</code></li>
  const children = childrenByParent.get(node.node_id) || []
  const open = expanded.has(node.node_id)
  const facts = node.facts || {}
  return <li className="pk-tree-node" data-selected={selected === node.node_id ? 'true' : 'false'}><div className="pk-tree-row">
    {children.length ? <button className="pk-tree-toggle" aria-label={t(open ? 'structure.collapse' : 'structure.expand', { id: node.node_id })} aria-expanded={open} onClick={() => { const next = new Set(expanded); open ? next.delete(node.node_id) : next.add(node.node_id); setExpanded(next) }}>{open ? '−' : '+'}</button> : <span className="pk-tree-leaf" aria-hidden="true">·</span>}
    <button className="pk-tree-select" aria-pressed={selected === node.node_id} onClick={() => setSelected(node.node_id)}>
      <span className="pk-tree-label"><code>{node.node_id}</code><small>{node.node_kind}</small></span>
      {facts.document_version && <span className="pk-tree-version">v{facts.document_version}</span>}
    </button>
  </div>{children.length > 0 && open && <ul>{children.map((child) => <ModuleBranch key={child.node_id} node={child} childrenByParent={childrenByParent} expanded={expanded} setExpanded={setExpanded} selected={selected} setSelected={setSelected} t={t} openDocument={openDocument} ancestry={[...ancestry, node.node_id]} />)}</ul>}</li>
}

// Classifies the status sentence the node document states; it is a reading aid, not an acceptance claim.
export function statusTone(status) {
  if (typeof status !== 'string' || !status.trim()) return 'unknown'
  if (/test|未装配|待接受|未行为验证|可选|未接线|无 runtime|无真实|未批准/i.test(status)) return 'limited'
  if (/已实现|implemented|可用/i.test(status)) return 'implemented'
  return 'unknown'
}

const COLUMN = 250
const ROW = 46
const BOX = { width: 196, height: 34 }

// Tidy left-to-right tree: depth from navigation_parent, leaves in order, parents centred on their children.
export function layoutTree(nodes) {
  const ids = new Set(nodes.map((node) => node.node_id))
  const children = new Map()
  nodes.forEach((node) => {
    const parent = node.navigation_parent && ids.has(node.navigation_parent) ? node.navigation_parent : ''
    children.set(parent, [...(children.get(parent) || []), node])
  })
  const positions = new Map()
  let row = 0
  let depthMax = 0
  const place = (node, depth, seen) => {
    if (seen.has(node.node_id) || positions.has(node.node_id)) return null
    const next = new Set(seen).add(node.node_id)
    depthMax = Math.max(depthMax, depth)
    const ys = (children.get(node.node_id) || []).map((child) => place(child, depth + 1, next)).filter((y) => y !== null)
    const y = ys.length ? (ys[0] + ys.at(-1)) / 2 : 30 + (row++) * ROW
    positions.set(node.node_id, { x: 20 + depth * COLUMN, y, depth })
    return y
  }
  ;(children.get('') || []).forEach((node) => place(node, 0, new Set()))
  nodes.forEach((node) => { if (!positions.has(node.node_id)) place(node, 0, new Set()) })
  return { positions, width: 40 + depthMax * COLUMN + BOX.width, height: Math.max(120, row * ROW + 20) }
}

export function ModuleGraph({ nodes, selected, setSelected, t }) {
  const { positions, width, height } = useMemo(() => layoutTree(nodes), [nodes])
  const active = nodes.find((node) => node.node_id === selected)
  const near = useMemo(() => moduleNeighbours(nodes, selected), [nodes, selected])
  const associated = new Set([selected, ...near.out, ...near.incoming, ...near.related])
  const relationOf = (id) => id === selected ? 'self' : near.out.has(id) ? 'out' : near.incoming.has(id) ? 'in' : near.related.has(id) ? 'related' : 'none'
  // First-order edges only: what the selection depends on, what depends on it, and declared relations.
  const edges = [
    ...[...near.out].map((id) => ({ from: selected, to: id, relation: 'depends_on', dir: 'out' })),
    ...[...near.incoming].map((id) => ({ from: id, to: selected, relation: 'depends_on', dir: 'in' })),
    ...[...near.related].map((id) => ({ from: selected, to: id, relation: 'related_to', dir: 'related' })),
  ]
  const anchor = (id, side) => { const p = positions.get(id); return p && { x: p.x + (side === 'right' ? BOX.width : 0), y: p.y } }
  return <div className="pk-graph-scroll"><svg className="pk-module-graph" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="group" aria-label={t('structure.graph')}>
    <title>{t('structure.graph')}</title>
    {nodes.map((node) => {
      const from = anchor(node.navigation_parent, 'right'); const to = anchor(node.node_id, 'left')
      if (!from || !to) return null
      const mid = (from.x + to.x) / 2
      return <path key={`tree:${node.node_id}`} className="pk-tree-edge" data-active={node.navigation_parent === selected || node.node_id === selected ? 'true' : 'false'} d={`M${from.x},${from.y} C${mid},${from.y} ${mid},${to.y} ${to.x},${to.y}`} />
    })}
    {active && edges.map((edge) => {
      const from = positions.get(edge.from); const to = positions.get(edge.to)
      if (!from || !to || edge.from === edge.to) return null
      const a = { x: from.x + BOX.width / 2, y: from.y }; const b = { x: to.x + BOX.width / 2, y: to.y }
      const bend = Math.max(40, Math.abs(a.y - b.y) / 3)
      const side = a.x === b.x ? 1 : Math.sign(b.x - a.x)
      return <g key={`${edge.relation}:${edge.from}:${edge.to}`} className={`pk-module-edge pk-edge-${edge.relation}`} data-dir={edge.dir}><path d={`M${a.x},${a.y} Q${(a.x + b.x) / 2 + bend * side},${(a.y + b.y) / 2} ${b.x},${b.y}`} /><title>{edge.from} {t(edge.relation === 'depends_on' ? 'structure.dependency' : 'structure.related')} {edge.to}</title></g>
    })}
    {nodes.map((node) => {
      const pos = positions.get(node.node_id)
      if (!pos) return null
      const facts = node.facts || {}
      return <g key={node.node_id} className="pk-module-node" transform={`translate(${pos.x},${pos.y - BOX.height / 2})`} role="button" tabIndex={0} aria-label={node.node_id} aria-pressed={selected === node.node_id}
        data-selected={selected === node.node_id ? 'true' : 'false'} data-associated={associated.has(node.node_id) ? 'true' : 'false'} data-rel={relationOf(node.node_id)} data-tone={statusTone(facts.implementation_status)} data-kind={node.node_kind}
        onClick={() => setSelected(node.node_id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected(node.node_id) } }}>
        <rect width={BOX.width} height={BOX.height} rx="8" /><rect className="pk-node-tone" width="4" height={BOX.height} rx="2" />
        <text x="12" y="15">{node.node_id}</text>
        <text className="pk-node-kind" x="12" y="28">{facts.title || node.node_kind}</text>
        {facts.document_version && <text className="pk-node-version" x={BOX.width - 8} y="15" textAnchor="end">v{facts.document_version}</text>}
        <title>{[node.node_id, facts.title, facts.implementation_status, node.document].filter(Boolean).join(' · ')}</title></g>
    })}
  </svg></div>
}

export default function Structure({ resources, t, openDocument }) {
  const tree = resources.tree
  const nodes = array(tree?.data?.nodes)
  const [selected, setSelected] = useState('K-ROOT')
  const [expanded, setExpanded] = useState(() => new Set(['K-ROOT', 'K-CORE', 'K-DATA', 'K-EXTENSIONS']))
  const childrenByParent = useMemo(() => {
    const map = new Map(); nodes.forEach((node) => { const key = node.navigation_parent || ''; map.set(key, [...(map.get(key) || []), node]) }); return map
  }, [tree?.data])
  const ids = new Set(nodes.map((node) => node.node_id))
  const roots = nodes.filter((node) => !node.navigation_parent || !ids.has(node.navigation_parent))
  const selectedNode = nodes.find((node) => node.node_id === selected)
  const degrees = moduleDegrees(nodes, selected)
  return <div className="pk-view"><ViewTitle id="structure" t={t} subtitle={t('structure.subtitle')} />
    <Section title={t('structure.modules')} source="document" t={t} hint={t('structure.docHint')}><ResourceState resource={tree} t={t} source="document" empty={!nodes.length}>
      <div className="pk-structure-layout"><div className="pk-tree-container"><ul className="pk-module-tree" aria-label={t('structure.navigation')}>{(roots.length ? roots : nodes.slice(0, 1)).map((node) => <ModuleBranch key={node.node_id} node={node} childrenByParent={childrenByParent} expanded={expanded} setExpanded={setExpanded} selected={selected} setSelected={setSelected} t={t} openDocument={openDocument} />)}</ul></div><div className="pk-structure-detail">
        {selectedNode && (() => {
          const allDeg = computeAllDegrees(nodes)
          return <NodeCard node={selectedNode} t={t} openDocument={openDocument}
            inDeg={allDeg.incoming.get(selectedNode.node_id) ?? 0}
            outDeg={allDeg.outgoing.get(selectedNode.node_id) ?? 0} />
        })()}
        <div className="pk-structure-relations"><h4>{t('structure.relations')}</h4><ModuleGraph nodes={nodes} selected={selected} setSelected={setSelected} t={t} />
        <p className="pk-edge-legend"><span className="pk-edge-swatch pk-dependency-swatch" />{t('structure.dependency')}<span className="pk-edge-swatch pk-related-swatch" />{t('structure.related')}</p>
        <p className="pk-tone-legend">{['implemented', 'limited', 'unknown'].map((tone) => <span key={tone}><span className="pk-tone-swatch" data-tone={tone} />{t(`structure.tone.${tone}`)}</span>)}</p>
        <div className="pk-degree-row"><SourceTag kind="derived" t={t} /><span className="pk-degree-chip pk-degree-in" data-tip={t('structure.degreeIncoming')}>{t('structure.inLabel', { n: degrees.incoming })}</span><span className="pk-degree-chip pk-degree-out" data-tip={t('structure.degreeOutgoing')}>{t('structure.outLabel', { n: degrees.outgoing })}</span><Info text={t('structure.degreeHint')} /></div></div>
      </div></div>
    </ResourceState></Section>
    <Section title={t('structure.businessGraph')} t={t} hint={t('structure.runtimeHint')}><TracePanel resource={resources.trace} t={t} /></Section>
  </div>
}
