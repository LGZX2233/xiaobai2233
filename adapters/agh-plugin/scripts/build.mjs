import { readFile, writeFile, stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { requireWorkspace } from './dependencies.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
const esbuild = requireWorkspace('esbuild')
const external = ['react', 'react/jsx-runtime', 'react-dom', 'react-dom/client', '@agnes/cordis', '@agnes/web-client']
await esbuild.build({
  entryPoints: [resolve(root, 'client/src/main.jsx')], outfile: resolve(root, 'client/index.js'),
  bundle: true, format: 'esm', jsx: 'automatic', platform: 'browser', target: 'es2022', external,
  legalComments: 'inline', minify: false,
})
const cssFiles = ['shell.css', 'views.css']
const styles = await Promise.all(cssFiles.map((name) => readFile(resolve(root, 'client/src/styles', name), 'utf8')))
await writeFile(resolve(root, 'client/index.css'), styles.join('\n'), 'utf8')
const [js, css] = await Promise.all(['index.js', 'index.css'].map((name) => stat(resolve(root, 'client', name))))
if (js.size >= 4 * 1024 * 1024 || js.size + css.size >= 16 * 1024 * 1024) throw new Error('Client package asset limit exceeded')
console.log(`Built client/index.js (${js.size} bytes) and client/index.css (${css.size} bytes)`)

