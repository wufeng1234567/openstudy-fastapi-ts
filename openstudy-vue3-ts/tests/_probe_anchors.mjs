/** 临时调试（用完即删）：看变异锚点在真文件里命中几次 */
import fs from 'node:fs'

const REAL = 'D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts'
const STREAM = fs.readFileSync(`${REAL}/src/components/AiChatStream/index.vue`, 'utf8')

const anchors = {
  'M1 removal': `        <div v-else-if="msg.type === 'turn_end'" class="turn-end-slot">\n          <AgentTurnRollback :turn-id="msg.turnId" :active="!!msg.turnId && msg.turnId === lastTurnId"\n            :state="rollbackState" :disabled="isGenerating" @rollback="$emit('rollback-turn', msg.turnId)" />\n        </div>\n`,
  'M1 insert': '        <!-- user 消息 -->',
  'M6b css': '.message.msg-turn_end {\n  margin-bottom: 0;\n}',
  'M6b css2': '.message.msg-turn_end {',
  'M9 key': ' :key="idx" :class='
}
for (const [k, a] of Object.entries(anchors)) {
  console.log(`${k}: ${STREAM.split(a).length - 1} hits`)
}
const i = STREAM.indexOf('msg-turn_end {')
console.log('--- css 现场 ---')
console.log(JSON.stringify(STREAM.slice(i - 40, i + 60)))
