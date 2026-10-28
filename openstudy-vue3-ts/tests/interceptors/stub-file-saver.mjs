/** `file-saver` 的替身：`download()` 用不到，避免引入浏览器特有 API。 */
export function saveAs() {}
export default { saveAs }
