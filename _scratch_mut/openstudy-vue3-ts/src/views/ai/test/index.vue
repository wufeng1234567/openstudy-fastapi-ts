<template>
    <div class="app-container">
        <!-- 模型切换 -->
        <el-card class="box-card" style="margin-bottom: 20px">
            <div class="flex-between">
                <div>
                    <span>当前模型：</span>
                    <el-tag type="success">{{ currentModel }}</el-tag>
                </div>
                <div>
                    <el-radio-group v-model="selectedProvider" @change="handleSwitchModel">
                        <el-radio-button value="zhipuai">智谱AI</el-radio-button>
                        <el-radio-button value="deepseek">DeepSeek</el-radio-button>
                    </el-radio-group>
                </div>
            </div>
        </el-card>

        <!-- 聊天区域 -->
        <el-card class="box-card">
            <div class="chat-container">
                <div class="chat-messages" ref="messagesContainer">
                    <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
                        <div class="message-content">
                            <div class="message-name">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
                            <div class="message-text">{{ msg.content }}</div>
                        </div>
                    </div>
                    <div v-if="loading" class="message assistant">
                        <div class="message-text typing">正在输入...</div>
                    </div>
                </div>

                <div class="chat-input">
                    <el-input v-model="inputMessage" type="textarea" :rows="3" placeholder="输入消息..."
                        @keydown.ctrl.enter="sendMessage" />
                    <div class="input-actions">
                        <el-button type="primary" @click="sendMessage" :loading="loading">发送</el-button>
                        <el-button @click="clearChat">清空</el-button>
                    </div>
                </div>
            </div>
        </el-card>

        <!-- 出题区域 -->
        <el-card class="box-card" style="margin-top: 20px">
            <el-form inline>
                <el-form-item label="知识点">
                    <el-input v-model="questionForm.knowledgePoint" style="width: 300px" />
                </el-form-item>
                <el-form-item label="题型">
                    <el-select v-model="questionForm.questionType" style="width: 120px">
                        <el-option label="单选题" value="single" />
                        <el-option label="多选题" value="multiple" />
                        <el-option label="判断题" value="judge" />
                    </el-select>
                </el-form-item>
                <el-form-item label="数量">
                    <el-input-number v-model="questionForm.count" :min="1" :max="10" />
                </el-form-item>
                <el-form-item>
                    <el-button type="success" @click="handleGenerateQuestions" :loading="genLoading">生成题目</el-button>
                </el-form-item>
            </el-form>
            <pre v-if="generatedQuestions" class="question-result">{{ generatedQuestions }}</pre>
        </el-card>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'AiTest' })
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { chat, switchModel, getModels, generateQuestions } from '@/api/ai/ai'

const selectedProvider = ref('zhipuai')
const currentModel = ref('智谱AI')
const messages = ref([])
const inputMessage = ref('')
const loading = ref(false)
const genLoading = ref(false)
const generatedQuestions = ref('')

const questionForm = ref({
    knowledgePoint: 'Java面向对象三大特性',
    questionType: 'single',
    count: 3
})

// 获取当前模型
const getCurrentModel = async () => {
    try {
        const res = await getModels()
        console.log('getModels 响应:', res)
        if (res.code === 200 && res.data) {
            const model = res.data.currentModel
            const modelValue = (model === 'zhipuai' || model === 'deepseek') ? model : 'zhipuai'

            selectedProvider.value = modelValue
            currentModel.value = modelValue === 'zhipuai' ? '智谱AI' : 'DeepSeek'
            console.log('初始化完成 - currentModel:', currentModel.value, 'selectedProvider:', selectedProvider.value)
        }
    } catch (error) {
        console.error('获取模型失败', error)
    }
}

// 切换模型
const handleSwitchModel = async (value) => {
    console.log('========================================')
    console.log('=== 模型切换事件触发 ===')
    console.log('1. 接收到的 value 参数:', value)
    console.log('2. value 类型:', typeof value)
    console.log('3. 当前 selectedProvider.value:', selectedProvider.value)
    console.log('4. 当前 currentModel.value:', currentModel.value)

    // 如果值为空，不处理
    if (!value) {
        console.log('❌ value 为空，停止处理')
        console.log('========================================')
        return
    }

    // 检查是否真的需要切换
    const currentValue = currentModel.value === '智谱AI' ? 'zhipuai' : 'deepseek'
    console.log('5. 从 currentModel 推断的值:', currentValue)

    if (value === currentValue) {
        console.log('❌ 要切换的值和当前模型相同，停止处理')
        console.log('========================================')
        return
    }

    console.log('6. 准备调用后端 API，参数:', value)

    try {
        const res = await switchModel(value)
        console.log('7. 后端 API 响应:', res)

        if (res.code === 200) {
            // ✅ 成功：更新 currentModel
            const newModelName = value === 'zhipuai' ? '智谱AI' : 'DeepSeek'
            console.log('8. ✅ 切换成功，准备更新 currentModel 为:', newModelName)

            currentModel.value = newModelName
            console.log('9. 更新后的 currentModel:', currentModel.value)
            console.log('10. 更新后的 selectedProvider:', selectedProvider.value)

            ElMessage.success(`已切换至 ${currentModel.value}`)
        } else {
            // ❌ 失败：回滚 selectedProvider
            console.log('8. ❌ 后端返回失败，准备回滚')
            selectedProvider.value = currentValue
            console.log('9. 回滚后 selectedProvider:', selectedProvider.value)
            ElMessage.error(res.msg || '切换失败')
        }
    } catch (error) {
        console.error('❌ 请求异常:', error)
        // 失败：回滚 selectedProvider
        selectedProvider.value = currentValue
        console.log('回滚后 selectedProvider:', selectedProvider.value)
        ElMessage.error('切换模型失败')
    }
    console.log('========================================')
}

// 发送消息
const sendMessage = async () => {
    if (!inputMessage.value.trim()) return
    if (loading.value) return

    const userMessage = inputMessage.value
    messages.value.push({ role: 'user', content: userMessage })
    inputMessage.value = ''
    loading.value = true

    await nextTick()
    scrollToBottom()

    try {
        const res = await chat({
            message: userMessage,
            provider: selectedProvider.value
        })

        console.log('AI响应完整数据:', res)

        let replyContent = ''
        if (res.code === 200) {
            replyContent = res.data || res.msg || 'AI返回内容为空'
        } else if (res.code === 0) {
            replyContent = res.msg || res.data || 'AI返回内容为空'
        } else {
            replyContent = res.msg || 'AI响应失败'
        }

        messages.value.push({ role: 'assistant', content: replyContent })
    } catch (error) {
        console.error('发送失败', error)
        messages.value.push({ role: 'assistant', content: '网络错误，请稍后重试' })
    } finally {
        loading.value = false
        await nextTick()
        scrollToBottom()
    }
}

// 清空聊天
const clearChat = () => {
    messages.value = []
    ElMessage.success('已清空')
}

// 生成题目
const handleGenerateQuestions = async () => {
    if (!questionForm.value.knowledgePoint) {
        ElMessage.warning('请输入知识点')
        return
    }

    genLoading.value = true
    try {
        const res = await generateQuestions({
            knowledgePoint: questionForm.value.knowledgePoint,
            questionType: questionForm.value.questionType,
            count: questionForm.value.count,
            provider: selectedProvider.value
        })

        console.log('生成题目响应:', res)

        if (res.code === 200) {
            generatedQuestions.value = res.data || res.msg || '生成成功但内容为空'
        } else if (res.code === 0) {
            generatedQuestions.value = res.msg || res.data || '生成成功但内容为空'
        } else {
            ElMessage.error(res.msg || '生成失败')
        }
    } catch (error) {
        console.error('生成失败', error)
        ElMessage.error('生成失败')
    } finally {
        genLoading.value = false
    }
}

// 滚动到底部
const scrollToBottom = () => {
    const container = document.querySelector('.chat-messages')
    if (container) {
        container.scrollTop = container.scrollHeight
    }
}

onMounted(() => {
    getCurrentModel()
})
</script>

<style scoped lang="scss">
.flex-between {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.chat-container {
    .chat-messages {
        height: 400px;
        overflow-y: auto;
        padding: 15px;
        background: #f5f5f5;
        border-radius: 8px;
        margin-bottom: 15px;

        .message {
            margin-bottom: 15px;

            &.user {
                text-align: right;

                .message-content {
                    background: #409eff;
                    color: white;
                    display: inline-block;
                    padding: 10px 15px;
                    border-radius: 8px;
                    max-width: 70%;
                    text-align: left;
                }

                .message-name {
                    font-size: 12px;
                    color: #999;
                    margin-bottom: 5px;
                }
            }

            &.assistant {
                .message-content {
                    background: white;
                    padding: 10px 15px;
                    border-radius: 8px;
                    max-width: 70%;
                    border: 1px solid #e4e7ed;
                }

                .message-name {
                    font-size: 12px;
                    color: #999;
                    margin-bottom: 5px;
                }
            }

            .typing {
                color: #999;
            }
        }
    }

    .chat-input {
        .input-actions {
            margin-top: 10px;
            text-align: right;
        }
    }
}

.question-result {
    background: #f5f5f5;
    padding: 15px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 12px;
    max-height: 300px;
}
</style>