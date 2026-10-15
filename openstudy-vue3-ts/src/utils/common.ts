/**
 * 删除 URL 查询参数
 * @param param 要删除的参数名
 */
export function deleteQueryParam(param: string) {
  const url = new URL(window.location.href)
  url.searchParams.delete(param)
  window.history.replaceState({}, '', url.toString())
}