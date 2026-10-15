import React, { useState } from 'react'
import { Fields, ResourceState, array, textValue } from './Primitives.jsx'

export function traceLayout(nodes) {
  const perDepth = new Map()
  return array(nodes).map((node) => {
    const depth = Math.max(0, Number(node.depth) || 0)
    const index = perDepth.get(depth) || 0
    perDepth.set(depth, index + 1)
    return { ...node, x: 110 + depth * 245, y: 70 + index * 100 }
  })
}

export function TraceGraph({ data, t }) {
  const nodes = traceLayout(data.nodes)
  const byId = new Map(nodes.map((node) => [node.node_id, node]))
  const edges = array(data.edges)
  const width = Math.max(720, ...nodes.map((node) => node.x + 130))
  const height = Math.max(220, ...nodes.map((node) => node.y + 85))
  return <div className="pk-graph-scroll"><svg className="pk-trace-graph" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={t('trace.graphLabel')}>
    <title>{t('trace.graphLabel')}</title>
    <defs><marker id="pk-trace-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" /></marker></defs>
    {edges.map((edge, i) => {
      const from = byId.get(edge.from); const to = byId.get(edge.to)
      if (!from || !to) return null
      return <g key={`${edge.from}:${edge.to}:${i}`} className="pk-trace-edge"><path d={`M${from.x + 95},${from.y} C${from.x + 160},${from.y} ${to.x - 160},${to.y} ${to.x - 95},${to.y}`} markerEnd="url(#pk-trace-arrow)" /><text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 8}>{edge.relation}</text><title>{textValue(edge.path, t)}</title></g>
    })}
    {nodes.map((node) => <g key={node.node_id} className="pk-trace-node" data-type={node.object_type} data-missing={node.exists === false ? 'true' : 'false'} transform={`translate(${node.x},${node.y})`}><rect x="-95" y="-27" width="190" height="58" rx="10" /><text className="pk-node-title" textAnchor="middle" y="-5">{node.object_id || node.node_id}</text><text className="pk-node-kind" textAnchor="middle" y="15">{node.object_type}</text><title>{`${node.node_id} · ${node.revision_id || t('common.unknown')}`}</title></g>)}
  </svg></div>
}

export function TracePanel({ resource, t, allowQuery = true }) {
  const [root, setRoot] = useState({ project_id: '', object_type: '', object_id: '', revision_id: '' })
  const [direction, setDirection] = useState('both')
  const [depth, setDepth] = useState(3)
  const [invalid, setInvalid] = useState(false)
  const data = resource?.data || {}
  const submit = (event) => {
    event.preventDefault()
    const filled = Object.values(root).filter((value) => value.trim()).length
    if (filled !== 0 && filled !== 4) { setInvalid(true); return }
    setInvalid(false)
    resource?.refresh?.({ root_ref: filled ? Object.fromEntries(Object.entries(root).map(([key, value]) => [key, value.trim()])) : undefined, direction, max_depth: Math.max(1, Math.min(20, Number(depth))) })
  }
  return <>
    {allowQuery && <details className="pk-trace-query"><summary>{t('trace.queryTitle')}</summary><p className="pk-note">{t('trace.queryHint')}</p><form className="pk-query-form pk-trace-form" onSubmit={submit}>
      {Object.keys(root).map((key) => <label key={key}>{t(`trace.${key}`)}<input value={root[key]} maxLength={128} onChange={(event) => setRoot({ ...root, [key]: event.target.value })} /></label>)}
      <label>{t('trace.direction')}<select value={direction} onChange={(event) => setDirection(event.target.value)}>{['both', 'incoming', 'outgoing'].map((value) => <option key={value} value={value}>{t(`trace.${value}`)}</option>)}</select></label>
      <label>{t('trace.depth')}<input type="number" value={depth} min="1" max="20" required onChange={(event) => setDepth(event.target.value)} /></label><button className="pk-button" type="submit">{t('common.query')}</button>
      {invalid && <p className="pk-note pk-note-warn" role="alert">{t('trace.fullRootRequired')}</p>}
    </form></details>}
    <ResourceState resource={resource} t={t} empty={!array(data.nodes).length}>
      {data.truncated && <p className="pk-note pk-note-warn">{t('trace.truncated')}</p>}
      <Fields t={t} values={[[t('trace.root'), data.root], [t('trace.nodeCount'), data.node_count], [t('trace.edgeCount'), data.edge_count]]} /><TraceGraph data={data} t={t} />
      <details className="pk-trace-records"><summary>{t('trace.records')}</summary><div className="pk-table-wrap"><table><thead><tr><th>{t('trace.object_id')}</th><th>{t('trace.object_type')}</th><th>{t('trace.relation')}</th><th>{t('trace.revision_id')}</th><th>{t('trace.exists')}</th></tr></thead><tbody>{array(data.nodes).map((node) => <tr key={node.node_id}><td><code>{node.object_id}</code></td><td>{node.object_type}</td><td>{node.relation}</td><td><code>{node.revision_id}</code></td><td>{node.exists === false ? t('common.no') : node.exists === true ? t('common.yes') : t('common.unknown')}</td></tr>)}</tbody></table></div></details>
    </ResourceState>
  </>
}
