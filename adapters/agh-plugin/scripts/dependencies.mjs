import { createRequire } from 'node:module'
import { existsSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

export function workspaceDependency(name) {
  const aghRoot = resolve(process.env.AGH_ROOT ?? 'D:/bisai/agnes-harness-main')
  const direct = join(aghRoot, 'node_modules', name)
  if (existsSync(join(direct, 'package.json'))) return direct
  const pnpm = join(aghRoot, 'node_modules', '.pnpm')
  if (!existsSync(pnpm)) throw new Error(`AGH_ROOT has no installed dependencies: ${aghRoot}`)
  const prefix = name.replace('/', '+') + '@'
  for (const entry of readdirSync(pnpm).sort()) {
    if (!entry.startsWith(prefix)) continue
    const candidate = join(pnpm, entry, 'node_modules', name)
    if (existsSync(join(candidate, 'package.json'))) return candidate
  }
  throw new Error(`Missing local dependency ${name}; set AGH_ROOT to an existing AGH checkout`)
}

export function requireWorkspace(name) {
  return createRequire(pathToFileURL(join(workspaceDependency(name), 'package.json')))(name)
}

