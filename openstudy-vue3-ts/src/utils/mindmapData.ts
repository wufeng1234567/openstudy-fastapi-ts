/**
 * ============================================================================
 * 思维导图 · 纯函数工具（2026-10-28 从 MindMap/index.vue 拆出）
 * ============================================================================
 *
 * 目标：把「Markdown → 树」与「树 → mind-elixir 数据」的解析逻辑独立成纯函数，
 * 便于单元测试，也让组件本身只负责渲染与交互。
 *
 * 内容：
 *   · stripInline / clipName / parseMarkdownToTree —— 原样从 MindMap/index.vue 搬出，行为不变
 *   · toMindElixirData —— 递归转 mind-elixir 的 { nodeData: { id, topic, children } } 结构
 *   · countMindNodes —— 统计树的总节点数
 * ============================================================================
 */

/** 树的节点结构（与 echarts 时代的结构一致，后端 outline_tree_service 也兼容） */
export interface TreeNode {
    name: string
    children?: TreeNode[]
    value?: number
    depthLevel?: number
}

/** mind-elixir 的节点对象 */
export interface MindElixirNode {
    id: string
    topic: string
    children?: MindElixirNode[]
    expanded?: boolean
}

/** mind-elixir 的实例数据 */
export interface MindElixirData {
    nodeData: MindElixirNode
}

/** 去掉行内 Markdown 标记（加粗/斜体/代码/链接/公式），只留可读文字 */
export function stripInline(s: string): string {
    return (s || '')
        .replace(/\$[^$]*\$/g, '')           // 行内公式整个去掉（导图里显示 LaTeX 没意义）
        .replace(/!\[[^\]]*\]\([^)]*\)/g, '') // 图片
        .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1') // 链接保留文字
        .replace(/`([^`]*)`/g, '$1')          // 行内代码
        .replace(/\*\*([^*]*)\*\*/g, '$1')    // 粗体
        .replace(/\*([^*]*)\*/g, '$1')        // 斜体
        .replace(/【图\d+】/g, '')             // 解析器插入的图片占位
        .replace(/\s+/g, ' ')
        .trim()
}

/** 截断过长的节点名（图里放不下，反而看不清） */
export function clipName(s: string, max = 26): string {
    if (!s) return ''
    return s.length > max ? s.slice(0, max - 1) + '…' : s
}

/**
 * 解析 Markdown 为树
 *
 * 层级判定：
 *   · 标题 `#{1,6}` → level = # 的个数
 *   · 列表 `-`/`*`/`1.` → level = 5 + (缩进空格数 / 2)
 *
 * 为什么列表层级加 5：让列表永远排在标题**下面**，
 * 不会出现「## 小节」和「- 要点」平级的错乱。
 *
 * 边界：如果整段压根没有标题和列表，就返回 null（由调用方显示空态），
 *       而不是硬造一个只有根节点的图 —— 那对用户没有价值。
 */
export function parseMarkdownToTree(md: string, rootName: string): TreeNode | null {
    if (!md || !md.trim()) return null

    const lines = md.split(/\r?\n/)
    const root: TreeNode = { name: clipName(rootName || '导图', 30), children: [] }

    /** 每个层级最近一次出现的节点，用于挂载下一层 */
    const stack: Array<{ level: number; node: TreeNode }> = [{ level: 0, node: root }]
    let nodeCount = 0

    /**
     * 去掉与根节点同名的首个标题
     *
     * 传入 title="Vue3 深度实战笔记" 而 Markdown 第一行恰好是
     * `# Vue3 深度实战笔记` 时，图上会出现「标题 → 标题」的重复节点，
     * 中间那个毫无意义还占一层布局，所以首层同名词直接去掉。
     */
    const rootText = (rootName || '').trim()
    if (rootText) {
        for (let i = 0; i < lines.length; i++) {
            const h = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(lines[i])
            if (!h) continue
            if (h[1].length === 1 && stripInline(h[2]).trim() === rootText) {
                lines.splice(i, 1)
            }
            break // 只看第一个标题
        }
    }

    const push = (level: number, text: string) => {
        if (!text) return
        // 弹出比当前层级更深的栈
        while (stack.length > 1 && stack[stack.length - 1].level >= level) stack.pop()
        const parent = stack[stack.length - 1].node
        const node: TreeNode = { name: clipName(text), children: [], depthLevel: level }
        if (!parent.children) parent.children = []
        parent.children.push(node)
        stack.push({ level, node })
        nodeCount++
    }

    for (const raw of lines) {
        const line = raw.replace(/\t/g, '  ')

        // ① 标题
        const h = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line)
        if (h) {
            push(h[1].length, stripInline(h[2]))
            continue
        }

        // ② 列表（先算缩进）
        const indentMatch = /^(\s*)/.exec(line)
        const indent = indentMatch ? indentMatch[1].length : 0
        const list = /^\s*(?:[-*+]|\d+[.)])\s+(.+)$/.exec(line)
        if (list) {
            // 每 2 个空格算一层；1 个空格也至少进一层（容忍不规整缩进）
            const depth = Math.floor(indent / 2)
            push(5 + depth, stripInline(list[1]))
            continue
        }

        // ③ 表格/代码块/引用/分隔线：跳过（导图里放这些没意义）
        if (/^\s*[|>`]/.test(line) || /^\s*---+\s*$/.test(line)) continue
    }

    // 没有任何子节点 → 不算有效导图
    if (nodeCount === 0 || !root.children || root.children.length === 0) return null
    return root
}

/**
 * 稳定的短哈希（djb2 变体）：同名/同路径下 id 可复现，且碰撞概率足够低
 */
function hashText(s: string): string {
    let h = 5381
    for (let i = 0; i < s.length; i++) {
        h = ((h << 5) + h + s.charCodeAt(i)) | 0
    }
    // 转成无符号 36 进制，短且可读
    return (h >>> 0).toString(36)
}

/**
 * 递归把树转成 mind-elixir 需要的 { nodeData: { id, topic, children } }
 *
 * id 规则：`me-${depth}-${index}-${hash(topic+path)}` ——
 *   · depth/index 保证同一层不重复；
 *   · hash 让 id 对内容稳定（同一棵树两次转换 id 一致，利于测试与 diff）。
 *
 * `expanded` 不设置：mind-elixir 默认全部展开，与旧行为一致。
 */
export function toMindElixirData(tree: TreeNode | null): MindElixirData | null {
    if (!tree || !tree.name && !tree.children?.length) return null

    const convert = (node: TreeNode, depth: number, index: number, path: string): MindElixirNode => {
        const pathKey = `${path}/${node.name}`
        const children = (node.children || []).map((c, i) => convert(c, depth + 1, i, pathKey))
        return {
            id: `me-${depth}-${index}-${hashText(pathKey)}`,
            topic: node.name,
            children,
        }
    }

    return { nodeData: convert(tree, 0, 0, '') }
}

/** 统计树的总节点数（含根） */
export function countMindNodes(tree: TreeNode | null | undefined): number {
    if (!tree) return 0
    return 1 + (tree.children || []).reduce((s, c) => s + countMindNodes(c), 0)
}
