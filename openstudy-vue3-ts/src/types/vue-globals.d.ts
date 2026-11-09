/**
 * Global Vue component properties injected by `main.ts`.
 *
 * These are RuoYi-compatible helpers used by legacy admin pages. Declaring
 * them here removes `Property '$modal' does not exist` class errors without
 * weakening `strict` for the rest of the project.
 */
import 'vue'

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $modal: {
      confirm: (content: string, title?: string, options?: Record<string, any>) => Promise<any>
      msgSuccess: (content: string) => void
      msgError: (content: string) => void
      loading: (options?: Record<string, any>) => { close: () => void }
      msgWarning: (content: string) => void
    }
    download: (url: string, params?: any, filename?: string, config?: any) => void
    parseTime: (time: any, pattern?: string) => string
    resetForm: (formRef?: any) => void
  }
}
