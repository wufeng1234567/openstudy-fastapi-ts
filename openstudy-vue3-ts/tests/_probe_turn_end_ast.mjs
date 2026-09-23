/**
 * 临时探针（用完即删）：把断言要读的 AST 形状打出来
 *   1. `:turn-id` / `@rollback-turn` 这种带连字符的绑定在 AST 里长什么样
 *   2. `v-for` 编译成 FOR 节点后 `source` 在哪
 *   3. `v-if` / `v-else-if` 链在 IF 节点里怎么排
 */
import { parse, compileTemplate } from '@vue/compiler-sfc'

const SRC = `<template>
  <div class="wrap">
    <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role]">
      <div v-if="msg.type === 'a'" class="message-content">A</div>
      <div v-else-if="msg.type === 'turn_end'">T</div>
      <div class="message-content" v-else-if="msg.role === 'assistant'">B</div>
      <div v-else>C</div>
    </div>
    <AgentTurnRollback :turn-id="msg.turnId" :active="!!msg.turnId && msg.turnId === lastTurnId"
      :state="rollbackState" :disabled="isGenerating" @rollback="$emit('rollback-turn', msg.turnId)" />
  </div>
</template>`

const { descriptor } = parse(SRC, { filename: 'probe.vue' })
const ast = compileTemplate({
  source: descriptor.template.content,
  filename: 'probe.vue',
  id: 'probe'
}).ast

const dump = (n, d = 0) => {
  const pad = '  '.repeat(d)
  const bits = [`type=${n.type}`]
  if (n.tag) bits.push(`tag=${n.tag}`)
  if (n.type === 11) bits.push(`FOR source=${JSON.stringify(n.source?.content ?? n.source?.loc?.source)}`)
  if (n.type === 9) {
    bits.push(
      'IF branches=' +
        JSON.stringify(
          (n.branches || []).map((b) => ({
            cond: b.condition ? String(b.condition.loc?.source ?? b.condition.content) : null,
            kids: (b.children || []).map((c) => c.type + ':' + (c.tag || ''))
          }))
        )
    )
  }
  for (const p of n.props || []) {
    bits.push(
      `prop{type=${p.type},name=${p.name},arg=${JSON.stringify(p.arg?.content)},exp=${JSON.stringify(
        p.exp?.loc?.source ?? p.exp?.content
      )},static=${JSON.stringify(p.value?.content)}}`
    )
  }
  console.log(pad + bits.join(' '))
  for (const b of n.branches || []) dump(b, d + 1)
  for (const c of n.children || []) dump(c, d + 1)
}

dump(ast)
