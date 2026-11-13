// utils/latexBraceScan.ts
//
// LaTeX **花括号组**的扫描（从 `latex.ts` 抽出）。
//
//   · `scanBraceGroups` —— 从某个位置开始，连续吃掉若干个 `{...}` 组（支持嵌套），
//     返回「吃到的组」与「吃掉后的位置」
//
// ⚠ 依赖方向单向：`latex.ts` → 本模块；本模块**零 import**，不反向依赖它，
//    因此不会形成循环依赖。
//
// ⚠ **Markdown / LaTeX 行为一个字节都没变** —— 这里只把「怎么数花括号」挪到了
//    可独立读、可独立测的地方；调用方拿到的组内容与结束位置与原来逐字一致。
//
// ⚠ `allowScript` 这个开关对应**真实的行为差异**，不是可选的装饰：
//    · `false`：命令后面紧跟 `{` 才算一组（`\frac{A}{B}`）。
//    · `true` ：允许命令与花括号之间夹一个 `_` / `^` 标记，并且**把它一起吃掉**
//      （`\sum_{i=1}^{n}` —— 大运算符的上下限写法；2026-10-27 修的正是这个）。
export interface BraceGroupScan {
  /** 吃到的 `{...}` 组（`true` 时可能带上前置的 `_` / `^`） */
  groups: string[]
  /** 吃完之后的下一个位置（组与组之间的空格会被跳过） */
  end: number
}

/**
 * 从 `pos` 开始，连续吃掉若干个 `{...}` 组（支持嵌套）。
 *
 * @param allowScript 是否允许 `_` / `^` 标记（并把它并入组内容）
 */
export function scanBraceGroups(
  text: string,
  pos: number,
  allowScript = false
): BraceGroupScan {
  const groups: string[] = []
  let scanPos = pos
  while (scanPos < text.length) {
    let cursor = scanPos
    if (allowScript && (text[cursor] === '_' || text[cursor] === '^')) {
      cursor++
      while (cursor < text.length && text[cursor] === ' ') cursor++
    }
    if (text[cursor] !== '{') break

    // 括号配平：找到与这个 `{` 配对的 `}`
    let depth = 0
    let end = -1
    for (let i = cursor; i < text.length; i++) {
      if (text[i] === '{') depth++
      else if (text[i] === '}') {
        depth--
        if (depth === 0) {
          end = i + 1
          break
        }
      }
    }
    if (end > 0) {
      groups.push(text.substring(scanPos, end))
      scanPos = end
      while (scanPos < text.length && text[scanPos] === ' ') scanPos++
    } else {
      break
    }
  }
  return { groups, end: scanPos }
}
