export function shuffleArray<T>(array: T[]): T[] {
  const next = [...array]
  for (let i = next.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[next[i], next[j]] = [next[j], next[i]]
  }
  return next
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 由当前 URL 种子参数算内容签名，避免同一批词被重复消费。 */
export function buildUrlSeedSignature(q: Record<string, any>): string {
  return [String(q.words || ''), String(q.scope || ''), String(q.bookId || ''), String(q.mode || '')].join('|')
}
