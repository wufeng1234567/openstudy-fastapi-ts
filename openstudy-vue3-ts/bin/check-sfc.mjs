/**
 * 轻量前端自检（不启动 dev server、不跑完整 vite build）
 *
 * 用途：改完 .vue / .ts 后快速确认「语法与模板编译都没问题」。
 * 为什么需要它：本项目的 `vue-tsc` 跑不起来（与 TS 版本不兼容，报
 * `Search string not found: "/supportedTSExtensions = .*(?=;)/"`），
 * 而 `vite build` 要约 1 分钟、且与 dev server 抢 I/O 时偶发卡死。
 * 这个脚本只做 parse + compileScript + compileTemplate + esbuild 转译，几秒出结果。
 *
 * 用法（在 frontend 根目录，或任意位置用绝对路径调用）：
 *   node bin/check-sfc.mjs                      # 检查默认清单
 *   node bin/check-sfc.mjs src/foo/Bar.vue ...   # 检查指定文件
 *
 * ⚠️ 它只能查「编译期」问题：类型错误、以及**顺序类运行期 bug**
 * （例如 `watch(x)` 写在 `const x = computed()` 之前导致的 TDZ ReferenceError）
 * 都查不出来，那类问题必须人工核对声明顺序。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse as parseSfc, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

const DEFAULT_TARGETS = [
  'src/components/AiAssistant/index.vue',
  'src/components/AiModelSelector/index.vue',
  'src/components/AiThinkingToggle/index.vue',
  'src/components/ChatFileUploader/index.vue',
  'src/components/ChatAttachmentList/index.vue',
  'src/components/AiChatStream/index.vue',
  'src/api/ai/ai.ts',
  'src/utils/ai-model-capability.ts',
  'src/utils/ds-proxy.ts',
  'src/utils/image-compress.ts',
  'src/utils/doc-parse.ts',
  // Agent（工具调用）链路：事件流客户端 + 状态机 + 卡片 + 大屏智能体页
  'src/api/ai/agent.ts',
  'src/api/ai/agentDsFree.ts',
  'src/composables/useAgentChat.ts',
  'src/components/AgentToolResult/index.vue',
  'src/components/AgentConfirmCard/index.vue',
  'src/components/ChatInputArea/index.vue',
  'src/views/front/agent/index.vue',
  'src/views/front/agent/chat.vue',
  'src/layout/front.vue',
  'src/router/index.ts',
  'src/views/front/studio/create/index.vue'
]

const targets = process.argv.slice(2).length ? process.argv.slice(2) : DEFAULT_TARGETS
let failed = 0

for (const rel of targets) {
  const abs = resolve(ROOT, rel)
  const label = relative(ROOT, abs)
  try {
    const src = readFileSync(abs, 'utf8')
    if (rel.endsWith('.vue')) {
      const { descriptor, errors } = parseSfc(src, { filename: abs })
      if (errors.length) throw new Error(errors.map((e) => e.message).join(' | '))
      const id = label.replace(/[^a-z0-9]/gi, '')
      const script = compileScript(descriptor, { id })
      if (descriptor.template) {
        const tpl = compileTemplate({
          source: descriptor.template.content,
          filename: abs,
          id,
          compilerOptions: { bindingMetadata: script.bindings }
        })
        if (tpl.errors.length) throw new Error(tpl.errors.map((e) => String(e)).join(' | '))
      }
      transformSync(script.content, { loader: 'ts', format: 'esm' })
    } else {
      transformSync(src, { loader: 'ts', format: 'esm' })
    }
    console.log('OK   ' + label)
  } catch (e) {
    failed++
    console.log('FAIL ' + label + '\n     ' + (e && e.message ? e.message : e))
  }
}

console.log(failed ? `\n${failed} file(s) failed` : '\nall good')
process.exit(failed ? 1 : 0)
