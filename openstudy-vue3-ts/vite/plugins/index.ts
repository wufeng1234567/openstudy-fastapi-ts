import type { PluginOption } from 'vite'
import vue from '@vitejs/plugin-vue'

import createAutoImport from './auto-import'
import createSvgIcon from './svg-icon'
import createCompression from './compression'
import createDsBridge from './ds-bridge'

export default function createVitePlugins(viteEnv: Record<string, string>, isBuild = false): PluginOption[] {
    const vitePlugins: PluginOption[] = [vue()]
    vitePlugins.push(createAutoImport())
    vitePlugins.push(createSvgIcon(isBuild))
    // DS 网页桥（无头 Edge，无需浏览器插件）：dev server 启动时自动 fork，关闭时一并收掉。
    // 只随 dev 起；build 时 apply:'serve' 自动跳过。
    vitePlugins.push(createDsBridge())
    isBuild && vitePlugins.push(...createCompression(viteEnv))
    return vitePlugins
}
