import fs from 'node:fs'
const b = JSON.parse(fs.readFileSync('tests/_probe_browser_rows.json', 'utf8'))
const n = JSON.parse(fs.readFileSync('tests/check_agent_dsfree_result.json', 'utf8'))
const nm = new Map(n.rows.filter((r) => r.suite === 'LOOP').map((r) => [r.id, r]))
let diffs = 0
let total = 0
for (const row of b) {
  const other = nm.get(row.id)
  if (!other) { console.log('缺：' + row.id); diffs++; continue }
  const a = row.asserts
  const c = (other.asserts || []).map((x) => [x.label, !!x.pass, x.actual == null ? '' : String(x.actual)])
  total += a.length
  if (a.length !== c.length) { console.log(row.id + ' 断言条数不同 ' + a.length + ' vs ' + c.length); diffs++; continue }
  for (let i = 0; i < a.length; i++) {
    if (a[i][0] !== c[i][0] || a[i][1] !== c[i][1] || a[i][2] !== c[i][2]) {
      diffs++
      console.log(row.id + ' #' + i + ' 浏览器=' + JSON.stringify(a[i]) + ' node=' + JSON.stringify(c[i]))
    }
  }
}
console.log('比对断言格数=' + total + '  不一致=' + diffs)
