# UI 修复：智能对话用户提问气泡自适应

- 日期：2026-11-03
- 文件：`openstudy-vue3-ts/src/components/AiChatStream/index.vue`
- 现象：用户只发一句「你好」/短文本时，蓝色用户气泡仍横向撑满约 78% 的对话列宽，留下大片空白。
- 根因：`.message.user .message-content` 是块级 `div`，`width: auto` 会吃满父级可用宽度，只靠 `max-width: 78%` 限制上限；短文本也会被撑到上限附近。
- 修复：给用户气泡增加 `width: fit-content`，保留 `min-width: 96px`（容纳右下角复制按钮）与 `max-width: 78%`（长文本换行上限）。AI 正文、工具卡片不受影响。
- 验证：
  - 浏览器实测短消息「你好」气泡缩到约 96px 宽，不再横向撑满；
  - 长消息仍按 78% 上限正常换行；
  - 智能对话页与右侧 AiAssistant 共用 `AiChatStream`，两处同步生效；
  - `npm run build:prod` 通过。
- 截图：`evidence/智能对话/用户气泡_修复后.png`（短消息「你好」）。
