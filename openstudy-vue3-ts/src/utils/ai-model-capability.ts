/**
 * 模型能力登记表（前端侧）
 *
 * 与后端 `app/services/ai/model_capabilities.py` 是**镜像关系**：
 * 前端需要「同步」判断（用户点发送的那一刻就要决定是否切换模型并提示），
 * 等接口返回再判断会有一帧延迟、且断网时无兜底，所以这里保留一份本地表。
 * **改一边必须改另一边。**
 *
 * 口径：
 *   deepseek-flash  ✅ 多模态，可识图（系统默认模型）
 *   deepseek-free   ✅ DS 官网 Web 版，网页端本身支持传图
 *   deepseek-v4-pro ❌ 仅文本；带图发送前要自动切到 flash 并提示用户
 *   其它（未知 / 用户自定义）→ 宽松放行，不在本地拦
 */

/** 需要视觉能力时自动切换到的模型 */
export const DEFAULT_VISION_MODEL = 'deepseek-flash'

/** 明确支持图片输入的模型 */
const VISION_MODELS = new Set(['deepseek-flash', 'deepseek-free'])

/** 明确只支持文本的模型 */
const TEXT_ONLY_MODELS = new Set(['deepseek-v4-pro'])

/** 该模型是否能接收图片输入（未知模型宽松放行） */
export function supportsVision(model?: string | null): boolean {
  const key = (model || '').trim().toLowerCase()
  if (VISION_MODELS.has(key)) return true
  if (TEXT_ONLY_MODELS.has(key)) return false
  return true
}

/** 该模型是否「明确只支持文本」——用于给用户提示 + 自动切换 */
export function isTextOnlyModel(model?: string | null): boolean {
  return TEXT_ONLY_MODELS.has((model || '').trim().toLowerCase())
}

/** 模型在「附件能力」上的说明文案（下拉框里做标签用） */
export function capabilityLabel(model?: string | null): string {
  return isTextOnlyModel(model) ? '仅文本' : ''
}
