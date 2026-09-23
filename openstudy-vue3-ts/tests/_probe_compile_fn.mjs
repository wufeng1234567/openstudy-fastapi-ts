/** 临时探针（用完即删）：看 compileTemplate 在 function 模式下生成的代码形状 */
import { parse, compileTemplate } from '@vue/compiler-sfc'

const SRC = `<template>
  <div class="wrap">
    <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role]">
      <div v-if="msg.type === 'turn_end'" class="turn-end-slot">T</div>
      <div class="message-content" v-else-if="msg.role === 'assistant'">B</div>
    </div>
  </div>
</template>`

const { descriptor } = parse(SRC, { filename: 'probe.vue' })
const r = compileTemplate({
  source: descriptor.template.content,
  filename: 'probe.vue',
  id: 'probe',
  compilerOptions: { mode: 'function' }
})
console.log(r.errors)
console.log(r.code.slice(0, 600))
