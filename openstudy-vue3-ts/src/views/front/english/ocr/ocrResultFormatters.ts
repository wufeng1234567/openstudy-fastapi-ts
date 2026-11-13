/** OCR 结果与裁剪器的纯格式化辅助（从 index.vue 抽出，无 Vue/API/交互依赖）。 */

// 格式化后的 JSON
/** 清理 markdown 代码块后 pretty-print；解析失败返回原内容。 */
export function formatStreamJson(content: string): string {
        if (!content) return ''
        try {
            // 提取 JSON 部分（可能包含 markdown 代码块）
            let jsonStr = content
                .replace(/```json\s*/g, '')
                .replace(/```\s*/g, '')
                .trim()
            const parsed = JSON.parse(jsonStr)
            return JSON.stringify(parsed, null, 2)
        } catch (e) {
            // 如果不是完整 JSON，返回原始内容
            return content
        }
}

// 自定义尺寸限制算法（允许图片完全自由）
const sizeRestrictionsAlgorithm = (minWidth: any, minHeight: any, maxWidth: any, maxHeight: any) => {
    return {
        minWidth: 10,      // 最小宽度 10px
        minHeight: 10,     // 最小高度 10px
        maxWidth: 5000,    // 最大宽度 5000px
        maxHeight: 5000    // 最大高度 5000px
    }
}

export { sizeRestrictionsAlgorithm }
