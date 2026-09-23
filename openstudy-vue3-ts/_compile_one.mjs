import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import fs from 'fs'
const file = process.argv[2]
const src = fs.readFileSync(file, 'utf8')
const { descriptor, errors } = parse(src, { filename: file })
if (errors.length) { console.log('PARSE_ERRORS', errors.map(e => String(e))); process.exit(1) }
try {
  compileScript(descriptor, { id: 'x' })
  console.log('SCRIPT_OK')
} catch (e) { console.log('SCRIPT_FAIL', e.message); process.exit(1) }
const t = compileTemplate({ source: descriptor.template.content, filename: file, id: 'x' })
if (t.errors.length) { console.log('TEMPLATE_FAIL', t.errors.map(String)); process.exit(1) }
console.log('TEMPLATE_OK')
