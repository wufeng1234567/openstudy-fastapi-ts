import compression from 'vite-plugin-compression'
import type { PluginOption } from 'vite'

export default function createCompression(env: Record<string, string>): PluginOption[] {
    const { VITE_BUILD_COMPRESS } = env
    const plugin: PluginOption[] = []
    if (VITE_BUILD_COMPRESS) {
        const compressList = VITE_BUILD_COMPRESS.split(',')
        if (compressList.includes('gzip')) {
            // gzip 静态资源压缩说明见 Vite 构建文档
            plugin.push(
                compression({
                    ext: '.gz',
                    deleteOriginFile: false
                })
            )
        }
        if (compressList.includes('brotli')) {
            plugin.push(
                compression({
                    ext: '.br',
                    algorithm: 'brotliCompress',
                    deleteOriginFile: false
                })
            )
        }
    }
    return plugin
}
