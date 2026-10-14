import type { PluginOption } from 'vite'
import vue from '@vitejs/plugin-vue'

import createAutoImport from './auto-import'
import createSvgIcon from './svg-icon'
import createCompression from './compression'

export default function createVitePlugins(viteEnv: Record<string, string>, isBuild = false): PluginOption[] {
    const vitePlugins: PluginOption[] = [vue()]
    vitePlugins.push(createAutoImport())
    vitePlugins.push(createSvgIcon(isBuild))
    isBuild && vitePlugins.push(...createCompression(viteEnv))
    return vitePlugins
}
