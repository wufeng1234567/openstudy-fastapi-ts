/**
 * Pinia persist plugin type augmentation.
 * The project uses a persist option on stores but pinia-plugin-persistedstate
 * is not installed as a dependency. This declaration restores action inference
 * by telling TypeScript the `persist` option is valid on defineStore options.
 */
import 'pinia'

declare module 'pinia' {
  export interface DefineStoreOptionsBase<S, Store> {
    persist?: {
      enabled?: boolean
      strategies?: Array<{
        key?: string
        storage?: Storage
        paths?: string[]
      }>
    }
  }
}
