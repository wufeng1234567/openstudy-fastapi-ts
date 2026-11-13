// composables/agentChatReferences.ts
//
// Agent 回答里的**引用来源**收集器（从 `useAgentChat.ts` 抽出的纯逻辑模块）。
//
// 这些函数把各种工具的原始返回（知识库检索 / 文档读取 / 图库 / 网页搜索）翻译成
// 统一的「引用片段」形状，好让界面渲染文档 chip、网页 chip、图片 chip。
//
// 这里**全部是无副作用的纯函数**：输入工具返回，输出引用数组；
// 合并去重也由调用方显式传入「已有引用」（`mergeKnowledgeReferences(base, list)`），
// 模块内部不持有任何状态。
//
// 本模块**不依赖**其它模块，因此不会与 `useAgentChat.ts` 形成循环依赖。

/**
 * 知识库检索命中的引用片段。
 *
 * `knowledge_search` 的结果里本来就有 docName / chunkId / chunkIndex / content，
 * 但工具结果只用于回灌模型，最终回答气泡并不知道这些来源。这里在 tool_result
 * 时先收起来，随后创建 assistant 正文气泡时挂到 `references` 上，前端即可渲染
 * 「文档 chip + hover 切片」。
 */
export function collectKnowledgeReferences(data: any): any[] {
  const hits = Array.isArray(data?.hits)
    ? data.hits
    : Array.isArray(data?.data?.hits)
      ? data.data.hits
      : []
  return hits
    .map((hit: any) => ({
      chunkId: hit?.chunkId ?? null,
      docId: hit?.docId ?? null,
      docName: String(hit?.docName || hit?.wikiPageTitle || hit?.source || '').trim(),
      chunkIndex: Number.isFinite(Number(hit?.chunkIndex)) ? Number(hit.chunkIndex) : null,
      source: String(hit?.source || '').trim(),
      sourceType: String(hit?.sourceType || 'document'),
      wikiPageId: hit?.wikiPageId ?? null,
      wikiPageTitle: String(hit?.wikiPageTitle || '').trim(),
      content: String(hit?.content || hit?.preview || '').trim(),
      images: Array.isArray(hit?.images) ? hit.images.slice(0, 4) : []
    }))
    .filter((ref: any) => ref.docName || ref.wikiPageTitle || ref.source)
}

/**
 * 网页搜索/抓取的引用：保留真实 url、站点与日期。
 * `ChatSourceList` 会把它渲染成 chip；点击直接打开外部网页。
 */
export function collectWebReferences(data: any): any[] {
  const business = data?.data && typeof data.data === 'object' ? data.data : data
  const action = String(business?.action || data?.action || '')
  if (action === 'fetch' && typeof business?.url === 'string') {
    return [{
      sourceType: 'web',
      docName: String(business.title || business.siteName || business.url).trim(),
      webTitle: String(business.title || '').trim(),
      url: String(business.url).trim(),
      source: String(business.siteName || '').trim(),
      siteIcon: String(business.siteIcon || business.site_icon || '').trim(),
      content: String(business.content || '').slice(0, 1200),
      date: ''
    }].filter((ref) => ref.url && /^https?:\/\//i.test(ref.url))
  }
  const list = Array.isArray(business?.results)
    ? business.results
    : Array.isArray(business?.hits)
      ? business.hits
      : []
  return list
    .map((item: any, index: number) => ({
      sourceType: 'web',
      index: Number(item?.index || index + 1),
      docName: String(item?.title || item?.siteName || item?.url || '').trim(),
      webTitle: String(item?.title || '').trim(),
      url: String(item?.url || '').trim(),
      source: String(item?.siteName || item?.site_name || '').trim(),
      siteIcon: String(item?.siteIcon || item?.site_icon || '').trim(),
      content: String(item?.snippet || item?.summary || '').trim(),
      date: String(item?.date || '').trim()
    }))
    .filter((ref: any) => ref.url && /^https?:\/\//i.test(ref.url))
}

/**
 * 把**已有引用**与**新收集的引用**合并去重（最多保留 24 条）。
 *
 * ⚠️ 已有引用由调用方显式传入（`base`）—— 本模块不持有状态，
 *    这样「合并谁」的判断永远由状态机那一侧说了算。
 */
export function mergeKnowledgeReferences(base: any[], list: any[]): any[] {
  const seen = new Set<string>()
  return [...base, ...list].filter((ref: any) => {
    const key = String(
      ref.chunkId ?? ref.url ?? `${ref.docId || ref.docName}:${ref.chunkIndex ?? ''}:${String(ref.content || '').slice(0, 40)}`
    )
    if (seen.has(key)) return false
    seen.add(key)
    return true
  }).slice(0, 24)
}

/** 整篇文档读取结果没有 chunk 列表，按段落切成可展示的知识切片。 */
export function isDocumentHeading(line: string): boolean {
  const text = line.trim()
  if (!text) return false
  return (
    /^#{1,2}\s+/.test(text) ||
    /^[一二三四五六七八九十百]+[、.]/.test(text) ||
    /^\d+[.、](?!\d)\s*\S/.test(text)
  )
}

export function splitDocumentContent(content: string): string[] {
  const text = String(content || '').replace(/\r\n/g, '\n').trim()
  if (!text) return []
  const sections: string[] = []
  let current: string[] = []
  let inFence = false
  const flush = () => {
    const value = current.join('\n').trim()
    if (value) sections.push(value)
    current = []
  }
  for (const line of text.split('\n')) {
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      current.push(line)
      continue
    }
    // 文档引用按「大点」切，不要把一个 chunk 切成跨章节的 900 字片段；
    // 否则「四、数据清洗」可能命中包含前面「二、流程」的同一块，浮层显示错内容。
    if (!inFence && isDocumentHeading(line) && current.some((item) => item.trim())) {
      flush()
      current = [line]
      continue
    }
    current.push(line)
  }
  flush()
  const chunks: string[] = []
  for (const section of sections) {
    if (section.length <= 1400) {
      chunks.push(section)
      continue
    }
    // 超长章节再按段落/长度切，避免单块过大。
    let rest = section
    while (rest.length > 1400) {
      let cut = rest.lastIndexOf('\n\n', 1400)
      if (cut < 500) cut = 1400
      chunks.push(rest.slice(0, cut).trim())
      rest = rest.slice(cut).trim()
    }
    if (rest) chunks.push(rest)
  }
  return chunks
}

export function collectDocumentReferences(data: any): any[] {
  if (!data?.content || !(data?.fileName || data?.docName)) return []
  const docName = String(data.fileName || data.docName)
  const docId = data.docId ?? null
  return splitDocumentContent(String(data.content)).map((content, index) => ({
    chunkId: null,
    docId,
    docName,
    chunkIndex: index,
    source: `${docName} 第 ${index + 1} 段`,
    sourceType: 'document',
    content
  }))
}

/**
 * gallery_manage 命中的图片资产 → 可点击的文档来源 chip。
 *
 * 图片描述本身不在文档 chunk 里；只有 asset.offset 能精确回到原文的图片位置。
 * 因此这里把 caption/OCR 作为浮层内容，把 offset / imageSeq 带到阅读器，
 * 点击后由 DocumentAnatomyPanel 滚动到对应图片并闪烁高亮。
 */
export function collectGalleryReferences(data: any): any[] {
  const images = Array.isArray(data?.images) ? data.images : []
  return images.map((img: any) => {
    const docId = Number(img?.docId || 0)
    if (!docId) return null
    const assetKey = String(img?.assetKey || '')
    const lastPart = assetKey.startsWith('doc:') ? Number(assetKey.split(':').pop()) : null
    const imageSeq = Number.isFinite(lastPart as number) ? Number(lastPart) : null
    const docName = String(img?.sourceName || img?.source || '资料').trim()
    const section = String(img?.sectionTitle || '').trim()
    const caption = String(img?.caption || '').trim()
    const keywords = Array.isArray(img?.keywords) ? img.keywords.filter(Boolean).join('、') : ''
    const content = [caption, keywords].filter(Boolean).join('；') || section || String(img?.imageName || '')
    return {
      chunkId: null,
      docId,
      docName,
      chunkIndex: null,
      source: `${docName}${section ? ` · ${section}` : ''}${imageSeq != null ? ` · 图片 ${imageSeq + 1}` : ''}`,
      sourceType: 'image',
      content,
      snippet: content,
      highlightText: '',
      imageSeq,
      offset: Number.isFinite(Number(img?.offset)) ? Number(img.offset) : null,
      assetKey,
      images: img?.url ? [String(img.url)] : []
    }
  }).filter(Boolean)
}
