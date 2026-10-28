/**
 * 模拟考试判分（**纯函数**，可被单测直接 import）
 * ============================================================================
 * 为什么从 `PracticeComponent.vue` 里搬出来（2026-10-28）：
 *   这两个函数原本是 `<script setup>` 里的局部函数，**没有任何办法被测试引用**
 *   —— 要么在浏览器里点一遍 UI 才能验（慢、脆），要么在测试里抄一份公式
 *   （那验的是副本，改了实现测试照样绿，属于假测试）。
 *   判分是"分数算错了用户会当场发现"的逻辑，必须有参数化的纯函数级测试。
 *
 * 搬移是**逐字**的，唯一的行为改动是 F7 的漏选公式（见 `judgeMockItem` 注释）。
 *
 * ⚠️ 注意：这里只服务**模拟考试**。练习模式的即时判分在
 *   `composables/useQuestionPractice.ts` 的 `handleAnswerSubmission` 里，
 *   两套规则目前并不完全一致（见审核发现 F2），不要随手把它俩合并。
 */
import type { MockExamConfig } from '@/types'

/** 取某题的标准答案（与原判分逻辑同口径，但只读不依赖 answers 数组位置） */
export function correctAnswerOf(q: any): any {
	return q.correctAnswer ?? q.answer
}

/**
 * 判定一道题对错，并返回实得分
 *
 * 与原 `correctCount` 计算的差别只在多选题：
 *   · 原逻辑：必须完全一致才算对（0/1）；
 *   · 这里额外支持 `partial`（漏选按比例得分），且**错选一律 0 分** ——
 *     这是绝大多数真实考试的规则，也是配置页那个选项的语义。
 *
 * 多选题 `partial` 的公式（2026-10-28 修正，审核发现 F7）
 * ---------------------------------------------------------------------------
 * 旧公式：`ratio = partialRatio * user.length`（再 `Math.min(1, …)` 封顶）
 *
 *   它只数"选了几项"，不看"应该选几项"，于是：
 *     系数 0.5、应选 3 项、只选对 2 项 → ratio = 0.5 × 2 = **1.0** → 拿满分。
 *   漏选反而拿满分，与配置页「漏选按比例得分」的语义直接冲突；
 *   而 `Math.min(1, …)` 的封顶恰好把这个矛盾藏了起来（表面看不出问题）。
 *
 * 新公式：`ratio = partialRatio * (user.length / std.length)`
 *
 *   漏选得分 = 该题满分 × 系数 ×（已选 ÷ 应选），与配置页文案一致。
 *   全选对时走上面的 `exact` 分支直接拿满分，不受本公式影响。
 */
export function judgeMockItem(
	q: any,
	userAnswer: any,
	cfg: MockExamConfig
): { isCorrect: boolean; gotScore: number } {
	const full = Number(q._mockScore) || 0
	const type = String(q._mockType || q.type || 'unknown')
	const correct = correctAnswerOf(q)

	const empty =
		userAnswer === null ||
		userAnswer === undefined ||
		(Array.isArray(userAnswer) && userAnswer.length === 0) ||
		(typeof userAnswer === 'string' && userAnswer.trim() === '')
	if (empty) return { isCorrect: false, gotScore: 0 }

	if (type === 'multiple') {
		const user = (Array.isArray(userAnswer) ? userAnswer : [userAnswer]).map(String).sort()
		const std = (Array.isArray(correct) ? correct : String(correct).split(/[,，]/)).map(String).sort()
		const exact = user.length === std.length && user.every((v, i) => v === std[i])
		if (exact) return { isCorrect: true, gotScore: full }

		const noWrongPick = user.every((v) => std.includes(v))
		if (cfg.multipleMode === 'partial' && noWrongPick && user.length > 0) {
			/*
			 * 漏选：按「已选 ÷ 应选」的比例给分，再乘配置系数，封顶不超过满分。
			 * `std.length || 1` 只是防御 —— 走到这里 `noWrongPick` 成立且
			 * `user.length > 0`，std 至少含 user 的每一项，不可能为 0。
			 */
			const hitRatio = user.length / (std.length || 1)
			const ratio = Math.min(1, Math.max(0, Number(cfg.partialRatio) || 0)) * hitRatio
			const got = Math.min(full, Math.round(full * ratio * 10) / 10)
			return { isCorrect: false, gotScore: got }
		}
		return { isCorrect: false, gotScore: 0 }
	}

	if (type === 'fillblank' || type === 'essay') {
		const ok = String(userAnswer).trim().toLowerCase() === String(correct ?? '').trim().toLowerCase()
		return { isCorrect: ok, gotScore: ok ? full : 0 }
	}

	// 单选 / 判断：严格相等
	const ok = String(userAnswer) === String(correct)
	return { isCorrect: ok, gotScore: ok ? full : 0 }
}
