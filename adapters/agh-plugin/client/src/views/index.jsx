import Overview from './Overview.jsx'
import Structure from './Structure.jsx'
import Requirements from './Requirements.jsx'
import Permissions from './Permissions.jsx'
import Execution from './Execution.jsx'
import Knowledge from './Knowledge.jsx'
import Errors from './Errors.jsx'
import Skills from './Skills.jsx'
import Environment from './Environment.jsx'
import Versions from './Versions.jsx'
import WorkspaceProject from './WorkspaceProject.jsx'
import Documents from './Documents.jsx'
import Events from './Events.jsx'
import Design from './Design.jsx'

// Two-level navigation: what the project is, how work runs, how it is governed, what is recorded.
export const VIEW_GROUPS = [
  { id: 'project', views: ['overview', 'design', 'workspace', 'structure', 'requirements'] },
  { id: 'run', views: ['execution', 'permissions', 'environment'] },
  { id: 'govern', views: ['versions', 'events', 'errors'] },
  { id: 'records', views: ['documents', 'skills', 'knowledge'] },
]
export const VIEW_IDS = VIEW_GROUPS.flatMap((group) => group.views)
export const VIEWS = { overview: Overview, design: Design, structure: Structure, requirements: Requirements, permissions: Permissions, execution: Execution, knowledge: Knowledge, errors: Errors, skills: Skills, environment: Environment, versions: Versions, workspace: WorkspaceProject, documents: Documents, events: Events }
export { PermissionNotice } from './Permissions.jsx'
export { SourceTag, ResourceState } from '../parts/Primitives.jsx'
export { phaseOf } from './helpers.js'
