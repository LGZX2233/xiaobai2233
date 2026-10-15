import React, { useState } from 'react'
import { ViewTitle, Section, Badge, SourceTag } from '../parts/Primitives.jsx'

export default function WorkspaceProject({ resources, t }) {
  const [showImport, setShowImport] = useState(false)
  const [importSource, setImportSource] = useState('')
  const [importName, setImportName] = useState('')

  // 设计预览数据：演示工作区和项目切换界面，实际运行需要内核实现相应 RPC 命令
  const currentWorkspace = { id: 'example-ws-1', name: '[示例] kernel-demo', path: '/path/to/kernel_next' }
  const workspaces = [
    currentWorkspace,
    { id: 'example-ws-2', name: '[示例] other-workspace', path: '/path/to/other' },
  ]
  const currentProject = { id: 'example-proj-1', name: '[示例] project-kernel', workspace: 'example-ws-1', hasStore: true, lastOpened: '2026-10-14T10:30:00Z' }
  const projects = [
    currentProject,
    { id: 'example-proj-2', name: '[示例] agh-integration', workspace: 'example-ws-1', hasStore: true, lastOpened: '2026-10-13T16:00:00Z' },
    { id: 'example-proj-3', name: '[示例] demo-project', workspace: 'example-ws-2', hasStore: false, lastOpened: null },
  ]

  return <div className="pk-view">
    <ViewTitle id="workspace" t={t} subtitle={t('workspace.subtitle')} />

    <Section title={t('workspace.current')} source="preview" t={t}>
      <div className="pk-preview-notice"><SourceTag kind="preview" t={t} /><p>{t('workspace.previewNote')}</p></div>
      <article className="pk-workspace-card pk-current">
        <header><h3>{currentWorkspace.name}</h3><Badge value="selected" t={t} /></header>
        <dl className="pk-fields">
          <div><dt>{t('workspace.path')}</dt><dd><code>{currentWorkspace.path}</code></dd></div>
          <div><dt>{t('workspace.projectCount')}</dt><dd>{projects.filter(p => p.workspace === currentWorkspace.id).length}</dd></div>
        </dl>
      </article>

      <h4>{t('workspace.currentProject')}</h4>
      <article className="pk-project-card pk-current">
        <header><h4><code>{currentProject.name}</code></h4><Badge value={currentProject.hasStore ? 'ok' : 'missing'} t={t} /></header>
        <dl className="pk-node-facts">
          <div><dt>{t('workspace.projectId')}</dt><dd><code>{currentProject.id}</code></dd></div>
          <div><dt>{t('workspace.hasStore')}</dt><dd>{currentProject.hasStore ? t('common.yes') : t('common.no')}</dd></div>
          {currentProject.lastOpened && <div><dt>{t('workspace.lastOpened')}</dt><dd>{currentProject.lastOpened.split('T')[0]}</dd></div>}
        </dl>
      </article>
    </Section>

    <Section title={t('workspace.allWorkspaces')} source="preview" t={t}>
      <div className="pk-workspace-list">
        {workspaces.map((ws) => <article key={ws.id} className={`pk-workspace-card ${ws.id === currentWorkspace.id ? 'pk-current' : ''}`}>
          <header><h3>{ws.name}</h3>{ws.id === currentWorkspace.id && <Badge value="selected" t={t} />}</header>
          <p className="pk-path"><code>{ws.path}</code></p>
          <div className="pk-project-count">{projects.filter(p => p.workspace === ws.id).length} {t('workspace.projects')}</div>
          {ws.id !== currentWorkspace.id && <button className="pk-button" disabled>{t('workspace.switchTo')}</button>}
        </article>)}
      </div>
      <button className="pk-button" disabled>{t('workspace.create')}</button>
    </Section>

    <Section title={t('workspace.allProjects')} source="preview" t={t}>
      <div className="pk-project-grid">
        {projects.map((proj) => <article key={proj.id} className={`pk-project-card ${proj.id === currentProject.id ? 'pk-current' : ''}`}>
          <header><h4><code>{proj.name}</code></h4><Badge value={proj.hasStore ? (proj.id === currentProject.id ? 'selected' : 'ok') : 'missing'} t={t} /></header>
          <dl className="pk-node-facts">
            <div><dt>{t('workspace.workspace')}</dt><dd>{workspaces.find(w => w.id === proj.workspace)?.name}</dd></div>
            {proj.lastOpened && <div><dt>{t('workspace.lastOpened')}</dt><dd>{proj.lastOpened.split('T')[0]}</dd></div>}
          </dl>
          {proj.id !== currentProject.id && <button className="pk-button" disabled>{t('workspace.open')}</button>}
        </article>)}
      </div>
    </Section>

    <Section title={t('workspace.import')} source="preview" t={t}>
      {!showImport ? <button className="pk-button" onClick={() => setShowImport(true)}>{t('workspace.importProject')}</button> : <form className="pk-import-form" onSubmit={(e) => e.preventDefault()}>
        <label>{t('workspace.importSource')}<input value={importSource} placeholder={t('workspace.sourcePlaceholder')} onChange={(e) => setImportSource(e.target.value)} /></label>
        <label>{t('workspace.importName')}<input value={importName} placeholder={t('workspace.namePlaceholder')} onChange={(e) => setImportName(e.target.value)} /></label>
        <div className="pk-control-actions">
          <button className="pk-button" type="submit" disabled>{t('workspace.importAction')}</button>
          <button className="pk-text-button" type="button" onClick={() => setShowImport(false)}>{t('common.close')}</button>
        </div>
      </form>}
    </Section>

    <Section title={t('workspace.implementation')} source="preview" t={t}>
      <ul className="pk-data-list">
        <li><code>workspace.list</code> — {t('workspace.cmdList')}</li>
        <li><code>workspace.create</code> — {t('workspace.cmdCreate')}</li>
        <li><code>project.import</code> — {t('workspace.cmdImport')}</li>
        <li><code>project.select</code> — {t('workspace.cmdSelect')}</li>
      </ul>
      <p className="pk-note">{t('workspace.implementationNote')}</p>
    </Section>
  </div>
}
