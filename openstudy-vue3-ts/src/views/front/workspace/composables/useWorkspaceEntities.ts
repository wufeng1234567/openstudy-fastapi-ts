import { computed } from 'vue'
import type { ComputedRef } from 'vue'
import { documentStatusKey, documentTypeKey } from '../utils/helpers'

export type WorkspaceEntityType = 'document' | 'web' | 'image' | 'bank' | 'note'

export interface WorkspaceEntity {
  key: string
  type: WorkspaceEntityType
  typeLabel: string
  icon: string
  tagType: 'primary' | 'success' | 'info' | 'warning' | 'danger'
  title: string
  subtitle: string
  metaText: string
  createTime: string
  statusKey: string
  doc?: any
  bank?: any
  note?: any
  image?: any
}

const TYPE_META: Record<WorkspaceEntityType, Pick<WorkspaceEntity, 'typeLabel' | 'icon' | 'tagType'>> = {
  document: { typeLabel: '文档', icon: 'file-text', tagType: 'primary' },
  web: { typeLabel: '网页', icon: 'globe', tagType: 'info' },
  image: { typeLabel: '图片', icon: 'layout-grid', tagType: 'warning' },
  bank: { typeLabel: '题库', icon: 'database', tagType: 'success' },
  note: { typeLabel: '笔记', icon: 'book', tagType: 'info' }
}

function entityBase(type: WorkspaceEntityType, key: string): Omit<WorkspaceEntity, 'title' | 'subtitle' | 'metaText' | 'createTime' | 'statusKey'> {
  return { key, type, ...TYPE_META[type] }
}

function documentEntity(doc: any): WorkspaceEntity {
  const rawType = documentTypeKey(doc)
  const type: WorkspaceEntityType = doc?.sourceUrl
    ? 'web'
    : rawType === 'image'
      ? 'image'
      : 'document'
  const meta: string[] = []
  if (doc?.sizeText) meta.push(doc.sizeText)
  if (doc?.chunkCount) meta.push(`${doc.chunkCount} 个片段`)
  if (doc?.imageCount) meta.push(`${doc.imageCount} 张图`)
  return {
    ...entityBase(type, `doc-${doc.docId}`),
    title: String(doc?.fileName || '未命名资料'),
    subtitle: String(doc?.note || doc?.subject || doc?.materialType || ''),
    metaText: meta.join(' · '),
    createTime: String(doc?.createTime || ''),
    statusKey: documentStatusKey(doc),
    doc
  }
}

function bankEntity(bank: any): WorkspaceEntity {
  return {
    ...entityBase('bank', `bank-${bank.bankId || bank.id}`),
    title: String(bank?.bankName || bank?.name || '未命名题库'),
    subtitle: [bank?.subject, `${Number(bank?.questionCount || bank?.totalQuestions || 0)} 道题`].filter(Boolean).join(' · '),
    metaText: String(bank?.description || ''),
    createTime: '',
    statusKey: '',
    bank
  }
}

function noteEntity(note: any): WorkspaceEntity {
  return {
    ...entityBase('note', `note-${note.noteId || note.id}`),
    title: String(note?.title || '未命名笔记'),
    subtitle: String(note?.summary || ''),
    metaText: '',
    createTime: '',
    statusKey: '',
    note
  }
}

function galleryEntity(image: any): WorkspaceEntity {
  const source = String(image?.sourceName || image?.sourceType || '')
  return {
    ...entityBase('image', `image-${image.assetKey || image.imageId || image.url}`),
    title: String(image?.displayName || image?.fileName || image?.imageName || '未命名图片'),
    subtitle: source,
    metaText: [image?.kind, image?.descriptionStatus ? `描述 ${image.descriptionStatus}` : ''].filter(Boolean).join(' · '),
    createTime: String(image?.createTime || ''),
    statusKey: '',
    image
  }
}

/**
 * 把资料夹里的不同实体统一成同一张卡片模型。
 *
 * 文档（含网页/图片文件）、题库、笔记、画廊独立图片只在这一层归一化；
 * 展示组件不感知后端各接口的字段差异。
 */
export function useWorkspaceEntities(options: {
  activeKb: ComputedRef<any>
  linkedBanks: { value: any[] }
  linkedNotes: { value: any[] }
  galleryAssets: { value: any[] }
  standaloneImages: { value: any[] }
}) {
  const entities = computed<WorkspaceEntity[]>(() => {
    const docs = (options.activeKb.value?.files || []).map(documentEntity)
    const banks = (options.linkedBanks.value || []).map(bankEntity)
    const notes = (options.linkedNotes.value || []).map(noteEntity)

    const images = new Map<string, WorkspaceEntity>()
    for (const image of options.galleryAssets.value || []) {
      // 文档内嵌图片已由文档卡片体现，独立图片才作为实体展示。
      if (String(image?.sourceType || '') === 'document') continue
      const entity = galleryEntity(image)
      images.set(entity.key, entity)
    }
    for (const image of options.standaloneImages.value || []) {
      const entity = galleryEntity(image)
      if (!images.has(entity.key)) images.set(entity.key, entity)
    }
    return [...docs, ...banks, ...notes, ...images.values()]
  })
  return { entities }
}
