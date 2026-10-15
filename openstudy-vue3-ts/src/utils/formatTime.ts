// src/utils/formatTime.ts

/** 支持的时间入参类型 */
export type TimeInput = string | number | Date

export const formatTime = (time: TimeInput, format: string = '{y}-{m}-{d}'): string => {
  if (!time) return ''

  const date = new Date(time)
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()

  return format
    .replace('{y}', String(year))
    .replace('{m}', month.toString().padStart(2, '0'))
    .replace('{d}', day.toString().padStart(2, '0'))
}
