import React from 'react'

// Minimal Markdown renderer that builds React elements only (no innerHTML, no inline style),
// enough for the project's documents: headings, lists, tables, quotes, fenced code, inline code/links.
function inline(text, openDocument, keyBase) {
  const parts = []
  const pattern = /(`[^`]+`)|\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*/g
  let last = 0
  let match
  let i = 0
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const key = `${keyBase}-${i++}`
    if (match[1]) parts.push(<code key={key}>{match[1].slice(1, -1)}</code>)
    else if (match[2]) {
      const target = match[3]
      parts.push(openDocument && /\.md(#.*)?$/.test(target) && !/^[a-z]+:/i.test(target)
        ? <button key={key} type="button" className="pk-md-link" onClick={() => openDocument(target.replace(/#.*$/, ''))}>{match[2]}</button>
        : <span key={key} className="pk-md-ext" title={target}>{match[2]}</span>)
    } else parts.push(<strong key={key}>{match[4]}</strong>)
    last = pattern.lastIndex
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim())

export function Markdown({ text, openDocument }) {
  const lines = String(text || '').split(/\r?\n/)
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const key = `b${i}`
    if (/^```/.test(line)) {
      const body = []
      i += 1
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++])
      i += 1
      blocks.push(<pre key={key} className="pk-md-code">{body.join('\n')}</pre>)
    } else if (/^#{1,6}\s/.test(line)) {
      const level = Math.min(6, line.match(/^#+/)[0].length + 1)
      const Tag = `h${level}`
      blocks.push(<Tag key={key} className="pk-md-heading">{inline(line.replace(/^#+\s*/, ''), openDocument, key)}</Tag>)
      i += 1
    } else if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
      const head = cells(line)
      const rows = []
      i += 2
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]))
      blocks.push(<div key={key} className="pk-table-wrap"><table className="pk-md-table"><thead><tr>{head.map((cell, c) => <th key={c}>{inline(cell, openDocument, `${key}h${c}`)}</th>)}</tr></thead>
        <tbody>{rows.map((row, r) => <tr key={r}>{row.map((cell, c) => <td key={c}>{inline(cell, openDocument, `${key}r${r}c${c}`)}</td>)}</tr>)}</tbody></table></div>)
    } else if (/^\s*([-*]|\d+\.)\s/.test(line)) {
      const ordered = /^\s*\d+\./.test(line)
      const items = []
      while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) {
        const item = lines[i].replace(/^\s*([-*]|\d+\.)\s+/, '')
        const task = /^\[( |x)\]\s/i.exec(item)
        items.push({ text: task ? item.slice(4) : item, task: task ? task[1].toLowerCase() === 'x' : null, depth: /^\s{2,}/.test(lines[i]) })
        i += 1
      }
      const List = ordered ? 'ol' : 'ul'
      blocks.push(<List key={key} className="pk-md-list">{items.map((item, n) => <li key={n} data-depth={item.depth ? 'nested' : 'top'} data-task={item.task == null ? undefined : item.task ? 'done' : 'open'}>
        {item.task != null && <span className="pk-md-check" aria-hidden="true">{item.task ? '✓' : '○'}</span>}{inline(item.text, openDocument, `${key}-${n}`)}</li>)}</List>)
    } else if (/^>\s?/.test(line)) {
      const body = []
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ''))
      blocks.push(<blockquote key={key} className="pk-md-quote">{inline(body.join(' '), openDocument, key)}</blockquote>)
    } else if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push(<hr key={key} className="pk-md-rule" />)
      i += 1
    } else if (!line.trim()) {
      i += 1
    } else {
      const body = []
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*([-*]|\d+\.)\s|>|\s*\|)/.test(lines[i])) body.push(lines[i++])
      if (!body.length) body.push(lines[i++])
      blocks.push(<p key={key} className="pk-md-p">{inline(body.join(' '), openDocument, key)}</p>)
    }
  }
  return <div className="pk-markdown">{blocks}</div>
}
