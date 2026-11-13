/**
 * @ 提及的统一解析规则（全仓唯一一份）
 *
 * 线上格式（存库、发给后端的）是 `@{用户id} 昵称`，由 `CommentInput.vue` 在提交时序列化出来，
 * 后端 `notes.py` 用 `re.findall(r"@\{(\d+)\}")` 从正文里取出被 @ 的人发通知 —— 所以这个格式不能改。
 *
 * 本文件负责把它**渲染**成人看得懂的样子，两种出口共用同一套规则：
 * - `renderMentionsHtml()`：评论正文用（出 DOM，带 data-userid，点击能跳对应用户）
 * - `plainMentions()`：私信 / 通知正文用（只要文字）
 *
 * ⚠️ 必须**一条正则、一趟替换**，别拆成两次 replace。
 *    旧实现是连续两次：第一条把 `@{106} 演示用户2` 换成带 data-userid 的 span，
 *    第二条的「裸 @昵称」又会匹配到该 span 内部的 `@演示用户2`，再包一层 ——
 *    于是最内层那个 data-userid="" 成了点击目标，点 @ 只能按昵称去前 100 个用户里猜。
 *    合并成一条后，两个分支互不嵌套。
 */

/** 昵称可用的字符（裸 @昵称 分支） */
const NAME = '[\\u4e00-\\u9fa5a-zA-Z0-9_]'

/**
 * 带 id 的规范格式里昵称额外允许 `.` 和 `-`（真实昵称里有这些字符）。
 * ⚠️ 故意**不**和上面的 `NAME` 共用：正文里手打的 `@张三.` 如果把句号吃进昵称就错了。
 */
const NAME_WITH_ID = '[\\u4e00-\\u9fa5a-zA-Z0-9_.\\-]'

/**
 * 分支一：`@{106} 演示用户2` / `@{106}演示用户2`（昵称可缺 —— 用户把昵称删掉后只剩 `@{106}`）
 * 分支二：`@演示用户2` / `＠演示用户2`（老数据、用户手打，没有 id）
 */
const AT_RE = new RegExp(
  `@\\{(\\d+)\\}(?:\\s*(${NAME_WITH_ID}+))?|([\\u0040\\uFF20])(${NAME}+)`,
  'g'
)

export function escapeHtml(text: string): string {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * 昵称缺失时的兜底显示（`@{106}` 这种）。
 * 目的只有一个：**不许把 `{106}` 这种实现细节漏到界面上**；
 * data-userid 仍然带 106，所以点它照样能跳到那个人。
 */
const fallbackName = (id: string | number) => (id === '' || id === undefined ? '' : `用户${id}`)

/** 渲染成 HTML（调用方给 atSpan，自己决定 span 长什么样和 data-* 怎么带） */
export function renderMentionsHtml(
  text: string,
  atSpan: (userId: string | number, name: string) => string
): string {
  return escapeHtml(text).replace(AT_RE, (_m, id, nameWithId, _at, bareName) => {
    if (id) return atSpan(id, nameWithId || fallbackName(id))
    return atSpan('', bareName)
  })
}

/** 只出文字（给不用 v-html 的地方，例如私信列表） */
export function plainMentions(text: string): string {
  return String(text ?? '').replace(AT_RE, (_m, id, nameWithId, _at, bareName) => {
    if (id) return `@${nameWithId || fallbackName(id)}`
    return `@${bareName}`
  })
}

/** 昵称字符判定：序列化时要确认 `@张三` 后面不再跟昵称字符，否则会吃掉 `@张三丰` 的前缀 */
export const isNameChar = (ch: string) => /[a-zA-Z0-9_\u4e00-\u9fa5]/.test(ch)
