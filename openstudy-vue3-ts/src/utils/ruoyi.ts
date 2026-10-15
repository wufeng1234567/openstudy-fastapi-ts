/**
 * 通用方法封装处理
 * Copyright (c) 2019 openstudy
 */

/** 时间入参类型 */
export type TimeInput = string | number | Date | null | undefined

// 日期格式化
export function parseTime(time: TimeInput, pattern?: string): string | null {
  if (arguments.length === 0 || !time) {
    return null
  }
  const format = pattern || '{y}-{m}-{d} {h}:{i}:{s}'
  let date: Date
  let t: any = time
  if (typeof time === 'object') {
    date = time as Date
  } else {
    if ((typeof time === 'string') && (/^[0-9]+$/.test(time))) {
      t = parseInt(time)
    } else if (typeof time === 'string') {
      t = (time as string).replace(new RegExp(/-/gm), '/').replace('T', ' ').replace(new RegExp(/\.[\d]{3}/gm), '')
    }
    if ((typeof t === 'number') && (t.toString().length === 10)) {
      t = t * 1000
    }
    date = new Date(t)
  }
  const formatObj: Record<string, number> = {
    y: date.getFullYear(),
    m: date.getMonth() + 1,
    d: date.getDate(),
    h: date.getHours(),
    i: date.getMinutes(),
    s: date.getSeconds(),
    a: date.getDay()
  }
  const time_str = format.replace(/{(y|m|d|h|i|s|a)+}/g, (result: string, key: string) => {
    let value = formatObj[key]
    // Note: getDay() returns 0 on Sunday
    if (key === 'a') { return ['日', '一', '二', '三', '四', '五', '六'][value] }
    if (result.length > 0 && value < 10) {
      value = Number('0' + value)
    }
    return String(value || 0)
  })
  return time_str
}

// 表单重置（挂载在全局属性上，使用 this 上下文）
export function resetForm(this: any, refName: string): void {
  if (this.$refs[refName]) {
    this.$refs[refName].resetFields()
  }
}

// 添加日期范围
export function addDateRange<T extends Record<string, any>>(params: T, dateRange: any[], propName?: string): T {
  let search = params
  search.params = typeof (search.params) === 'object' && search.params !== null && !Array.isArray(search.params) ? search.params : {}
  dateRange = Array.isArray(dateRange) ? dateRange : []
  if (typeof (propName) === 'undefined') {
    search.params['beginTime'] = dateRange[0]
    search.params['endTime'] = dateRange[1]
  } else {
    search.params['begin' + propName] = dateRange[0]
    search.params['end' + propName] = dateRange[1]
  }
  return search
}

// 回显数据字典
export function selectDictLabel(datas: Record<string, any>, value: any): string {
  if (value === undefined) {
    return ''
  }
  const actions: string[] = []
  Object.keys(datas).some((key) => {
    if (datas[key].value == ('' + value)) {
      actions.push(datas[key].label)
      return true
    }
  })
  if (actions.length === 0) {
    actions.push(value)
  }
  return actions.join('')
}

// 回显数据字典（字符串数组）
export function selectDictLabels(datas: Record<string, any>, value: any, separator?: string): string {
  if (value === undefined || value.length === 0) {
    return ''
  }
  let val: any = value
  if (Array.isArray(val)) {
    val = val.join(',')
  }
  const actions: string[] = []
  const currentSeparator = undefined === separator ? ',' : separator
  const temp = String(val).split(currentSeparator)
  Object.keys(String(val).split(currentSeparator)).some((v) => {
    let match = false
    Object.keys(datas).some((key) => {
      if (datas[key].value == ('' + temp[Number(v)])) {
        actions.push(datas[key].label + currentSeparator)
        match = true
      }
    })
    if (!match) {
      actions.push(temp[Number(v)] + currentSeparator)
    }
  })
  return actions.join('').substring(0, actions.join('').length - 1)
}

// 字符串格式化(%s )
export function sprintf(str: string, ...args: any[]): string {
  let i = 1
  let flag = true
  const result = str.replace(/%s/g, function () {
    const arg = args[i - 1]
    i++
    if (typeof arg === 'undefined') {
      flag = false
      return ''
    }
    return arg
  })
  return flag ? result : ''
}

// 转换字符串，undefined,null等转化为""
export function parseStrEmpty(str: any): string {
  if (!str || str == 'undefined' || str == 'null') {
    return ''
  }
  return str
}

// 数据合并
export function mergeRecursive(source: any, target: any): any {
  for (const p in target) {
    try {
      if (target[p].constructor == Object) {
        source[p] = mergeRecursive(source[p], target[p])
      } else {
        source[p] = target[p]
      }
    } catch (e) {
      source[p] = target[p]
    }
  }
  return source
}

/**
 * 构造树型结构数据
 * @param data 数据源
 * @param id id字段 默认 'id'
 * @param parentId 父节点字段 默认 'parentId'
 * @param children 孩子节点字段 默认 'children'
 */
export function handleTree(data: any[], id?: string, parentId?: string, children?: string): any[] {
  const config = {
    id: id || 'id',
    parentId: parentId || 'parentId',
    childrenList: children || 'children'
  }

  const childrenListMap: Record<string, any[]> = {}
  const nodeIds: Record<string, any> = {}
  const tree: any[] = []

  for (const d of data) {
    const pid = d[config.parentId]
    if (childrenListMap[pid] == null) {
      childrenListMap[pid] = []
    }
    nodeIds[d[config.id]] = d
    childrenListMap[pid].push(d)
  }

  for (const d of data) {
    const pid = d[config.parentId]
    if (nodeIds[pid] == null) {
      tree.push(d)
    }
  }

  for (const t of tree) {
    adaptToChildrenList(t)
  }

  function adaptToChildrenList(o: any): void {
    if (childrenListMap[o[config.id]] !== null) {
      o[config.childrenList] = childrenListMap[o[config.id]]
    }
    if (o[config.childrenList]) {
      for (const c of o[config.childrenList]) {
        adaptToChildrenList(c)
      }
    }
  }
  return tree
}

/**
 * 参数处理
 * @param params 参数
 */
export function tansParams(params: Record<string, any>): string {
  let result = ''
  for (const propName of Object.keys(params)) {
    const value = params[propName]
    const part = encodeURIComponent(propName) + '='
    if (value !== null && value !== '' && typeof (value) !== 'undefined') {
      if (typeof value === 'object') {
        for (const key of Object.keys(value)) {
          if (value[key] !== null && value[key] !== '' && typeof (value[key]) !== 'undefined') {
            const paramsName = propName + '[' + key + ']'
            const subPart = encodeURIComponent(paramsName) + '='
            result += subPart + encodeURIComponent(value[key]) + '&'
          }
        }
      } else {
        result += part + encodeURIComponent(value) + '&'
      }
    }
  }
  return result
}

// 返回项目路径
export function getNormalPath(p: string): string {
  if (p.length === 0 || !p || p == 'undefined') {
    return p
  }
  let res = p.replace('//', '/')
  if (res[res.length - 1] === '/') {
    return res.slice(0, res.length - 1)
  }
  return res
}

// 验证是否为blob格式
export function blobValidate(data: Blob): boolean {
  return data.type !== 'application/json'
}
