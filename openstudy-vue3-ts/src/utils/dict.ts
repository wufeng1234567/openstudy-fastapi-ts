import { ref, toRefs } from 'vue'
import useDictStore from '@/store/modules/dict'
import { getDicts } from '@/api/system/dict/data'

/** 字典项 */
export interface DictData {
  label: string
  value: string
  elTagType: string
  elTagClass: string
}

/**
 * 获取字典数据
 */
export function useDict(...args: string[]): Record<string, any> {
  const res = ref<Record<string, DictData[]>>({})
  return (() => {
    args.forEach((dictType) => {
      res.value[dictType] = []
      const dicts = useDictStore().getDict(dictType)
      if (dicts) {
        res.value[dictType] = dicts
      } else {
        getDicts(dictType).then((resp: any) => {
          res.value[dictType] = resp.data.map((p: any) => ({
            label: p.dictLabel,
            value: p.dictValue,
            elTagType: p.listClass,
            elTagClass: p.cssClass
          }))
          useDictStore().setDict(dictType, res.value[dictType])
        })
      }
    })
    return toRefs(res.value)
  })()
}
