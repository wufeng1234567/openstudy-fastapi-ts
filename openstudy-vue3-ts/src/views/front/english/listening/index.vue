<template>
    <div class="listening-page">
        <!--
          2026-10-26：整行「< 返回」导航栏已删除。
          顶栏已经显示 `英语学习 · 单词听写`，页面层级清晰，
          再来一行返回栏只是重复占位（用户反馈「第二行多余了」）。
          练习中的「结束练习」按钮仍可退出，返回逻辑保留在 `goBack()` 里备用。
        -->
        <!--
          练习结果面板（2026-10-26 闭环）
          --------------------------------
          改前：练完弹一个 ElMessageBox（只有 4 个数字），点「返回」就丢光了。
          改后：结果留在页面里，能看到**具体写错了哪些词**，并给出三个出口。
        -->
        <div class="result-panel" v-if="hasResult && !isPracticing">
            <div class="result-panel__head">
                <div class="result-panel__score">
                    <span class="result-panel__pct">{{ resultSummary.accuracy }}<i>%</i></span>
                    <span class="result-panel__label">本次正确率</span>
                </div>
                <div class="result-panel__nums">
                    <span>共 {{ resultSummary.total }} 题</span>
                    <span class="is-ok">对 {{ resultSummary.correct }}</span>
                    <span class="is-bad">错 {{ resultSummary.total - resultSummary.correct }}</span>
                </div>
            </div>

            <div class="result-panel__wrong" v-if="resultWrongWords.length">
                <div class="result-panel__wrong-title">
                    写错的 {{ resultWrongWords.length }} 个词
                </div>
                <div class="wrong-list">
                    <div v-for="(w, i) in resultWrongWords" :key="i" class="wrong-item">
                        <span class="wrong-item__word">{{ w.word }}</span>
                        <span class="wrong-item__trans">{{ w.translation }}</span>
                        <span class="wrong-item__mine">你写的是：{{ w.userAnswer || '（空）' }}</span>
                    </div>
                </div>
            </div>
            <div class="result-panel__allok" v-else>
                <el-icon :size="20"><CircleCheck /></el-icon>
                <span>全部写对了，这本词库掌握得不错</span>
            </div>

            <div class="result-panel__actions">
                <el-button
                    v-if="resultWrongWords.length"
                    type="primary"
                    size="large"
                    @click="retryWrongWords"
                >
                    再练一遍错词（{{ resultWrongWords.length }}）
                </el-button>
                <el-button size="large" @click="backToBookSelect">换一本词库</el-button>
                <el-button size="large" text @click="router.push('/front/english/vocabulary')">
                    去我的词库
                </el-button>
            </div>

            <!--
              把这次练习交给智能体分析：跳过去时把问题带在 route state 里，
              智能体的 `english_practice` 工具能读到刚提交的这条记录，
              于是"页面练完 → 聊天里复盘"也接上了。
            -->
            <p class="result-panel__ai">
                想让 AI 帮你看看这次练习？
                <a class="result-panel__link" @click="askAiForAnalysis">交给智能体分析</a>
            </p>
        </div>

        <!-- 词库选择（未开始时显示） -->
        <div class="book-select-section" v-if="!isPracticing && !hasResult">
            <div class="select-label">选择词库</div>
            <el-select v-model="selectedBookId" placeholder="请选择词库" size="large" style="width: 100%"
                @change="onBookChange">
                <el-option v-for="book in bookOptions" :key="book.bookId" :label="book.bookName" :value="book.bookId" />
            </el-select>

            <!--
              2026-10-26 新增：未选词库时的空状态。
              改前这里什么都没有 —— 整页只有一个下拉框，下方全空，
              用户不知道下一步该干什么。现在给出明确指引。
            -->
            <div class="start-empty" v-if="!selectedBookId">
                <div class="start-empty__icon">
                    <el-icon :size="26">
                        <Headset />
                    </el-icon>
                </div>
                <p class="start-empty__title">先选一本词库</p>
                <span class="start-empty__desc">
                    选好后点「开始听写」，系统会念中文释义，你拼出对应的英文单词
                </span>
            </div>

            <div class="start-empty" v-else-if="wordList.length === 0 && !loadingWords">
                <div class="start-empty__icon">
                    <el-icon :size="26">
                        <Collection />
                    </el-icon>
                </div>
                <p class="start-empty__title">这本词库还是空的</p>
                <span class="start-empty__desc">先去「我的词库」往里加几个单词，再回来听写</span>
                <el-button class="start-empty__btn" size="small" @click="router.push('/front/english/vocabulary')">
                    去添加单词
                </el-button>
            </div>

            <!-- 词库统计 -->
            <!--
              只说「总单词」。
              原来还有「已掌握 / 未掌握」两项，但 `words` 表根本没有掌握状态列
              （word_id / book_id / word / phonetic / translation / example /
                audio_url / sort_order / create_time），那两个数字永远是
              0 和全部 —— 等于给用户看两个假指标。2026-10-23 去掉。
            -->
            <div class="book-stats" v-if="selectedBookId && wordList.length > 0">
                <div class="stat-item">
                    <span class="stat-value">{{ wordList.length }}</span>
                    <span class="stat-label">总单词</span>
                </div>
            </div>

            <!--
              练习设置（2026-10-26 重构：三模式 + 可调参数）
              -----------------------------------------------------------------
              用户要求：
                · 模式可选 —— ①纯播放听力（自己手写）②打字输入 ③自动听写
                · 打字输入**不设时间限制**
                · 播放速度 / 间隔等参数可调

              结构：
                第一行 模式（三选一，带一句话说明）
                其余   与模式相关的参数，逐个一行，两列网格对齐
            -->
            <div class="practice-settings" v-if="selectedBookId && wordList.length > 0">
                <!-- 模式选择：用卡片而不是单选框，因为三个选项差别大、需要解释 -->
                <div class="mode-picker">
                    <div class="mode-card" :class="{ 'is-active': practiceMode === 'listen' }"
                        @click="practiceMode = 'listen'">
                        <div class="mode-card__icon">
                            <el-icon :size="18"><Headset /></el-icon>
                        </div>
                        <div class="mode-card__body">
                            <div class="mode-card__title">纯听力</div>
                            <div class="mode-card__desc">只播放，自己在纸上写，不限时</div>
                        </div>
                    </div>

                    <div class="mode-card" :class="{ 'is-active': practiceMode === 'input' }"
                        @click="practiceMode = 'input'">
                        <div class="mode-card__icon">
                            <el-icon :size="18"><EditPen /></el-icon>
                        </div>
                        <div class="mode-card__body">
                            <div class="mode-card__title">打字输入</div>
                            <div class="mode-card__desc">看中文敲英文，提交判对错，不限时</div>
                        </div>
                    </div>

                    <div class="mode-card" :class="{ 'is-active': practiceMode === 'dictation' }"
                        @click="practiceMode = 'dictation'">
                        <div class="mode-card__icon">
                            <el-icon :size="18"><Timer /></el-icon>
                        </div>
                        <div class="mode-card__body">
                            <div class="mode-card__title">自动听写</div>
                            <div class="mode-card__desc">播完自动跳下一题，适合快速过一遍</div>
                        </div>
                    </div>
                </div>

                <!-- 播放顺序：三种模式都用得上 -->
                <div class="setting-item">
                    <span class="setting-label">播放顺序</span>
                    <el-radio-group v-model="playOrder">
                        <el-radio value="sequential">按词库顺序</el-radio>
                        <el-radio value="random">随机</el-radio>
                    </el-radio-group>
                </div>

                <!-- 播放速度：三种模式都有意义 -->
                <div class="setting-item setting-item--slider">
                    <span class="setting-label">播放速度</span>
                    <div class="setting-control">
                        <el-slider v-model="speechRate" :min="0.5" :max="1.5" :step="0.1" show-stops
                            :format-tooltip="(v) => v.toFixed(1) + '×'" />
                        <span class="setting-hint">
                            当前 {{ speechRate.toFixed(1) }}×
                            <template v-if="speechRate < 0.9">（较慢，适合跟读）</template>
                            <template v-else-if="speechRate > 1.1">（较快，接近母语语速）</template>
                            <template v-else>（正常语速）</template>
                        </span>
                    </div>
                </div>

                <!-- 播放次数：纯听力 / 自动听写有意义；打字输入只播一遍 -->
                <div class="setting-item" v-if="practiceMode !== 'input'">
                    <span class="setting-label">播放遍数</span>
                    <el-radio-group v-model="repeatCount">
                        <el-radio :value="1">1 遍</el-radio>
                        <el-radio :value="2">2 遍</el-radio>
                        <el-radio :value="3">3 遍</el-radio>
                    </el-radio-group>
                </div>

                <!-- 每遍之间的间隔 -->
                <div class="setting-item setting-item--slider" v-if="practiceMode !== 'input' && repeatCount > 1">
                    <span class="setting-label">遍间隔</span>
                    <div class="setting-control">
                        <el-slider v-model="playInterval" :min="0.5" :max="5" :step="0.5" show-stops
                            :format-tooltip="(v) => v + ' 秒'" />
                        <span class="setting-hint">每遍播放之间停 {{ playInterval }} 秒，留给书写时间</span>
                    </div>
                </div>

                <!-- 自动下一题：只有「自动听写」模式才需要 -->
                <div class="setting-item setting-item--slider" v-if="practiceMode === 'dictation'">
                    <span class="setting-label">自动下一题</span>
                    <div class="setting-control">
                        <el-slider v-model="autoNextInterval" :min="1" :max="10" :step="0.5" show-stops
                            :format-tooltip="(v) => v + ' 秒'" />
                        <span class="setting-hint">播放完成后等待此时间自动进入下一题</span>
                    </div>
                </div>

                <!-- 打字输入 / 纯听力的说明（明确「不限时」） -->
                <div class="mode-note" v-if="practiceMode !== 'dictation'">
                    <el-icon :size="14"><InfoFilled /></el-icon>
                    <span>
                        {{ practiceMode === 'listen'
                            ? '纯听力模式不计分、不限时，跟着播放自己写，写完点「下一题」。'
                            : '打字输入不限时，想多久都可以；打完按 Enter 或点「提交」判定。' }}
                    </span>
                </div>
            </div>

            <!-- 开始按钮 -->
            <div class="start-section" v-if="selectedBookId && wordList.length > 0">
                <el-button type="primary" size="large" @click="startPractice" :loading="loadingWords">
                    <el-icon>
                        <VideoPlay />
                    </el-icon>
                    开始听写
                </el-button>
            </div>

            <!-- 空状态 -->
            <el-empty v-else-if="selectedBookId && wordList.length === 0 && !loadingWords"
                description="该词库还没有单词，请先添加单词" />
        </div>

        <!--
          练习界面
          ⚠️ 2026-10-26：加上 `!hasResult`。
          原来这里是裸 `v-else`，接在 `book-select-section`（`!isPracticing && !hasResult`）
          后面，所以当 `isPracticing=false` 且 `hasResult=true` 时，
          它仍然成立 —— 结果面板和题目卡会同时渲染（截图实测叠在一起）。
        -->
        <div class="practice-section" v-else-if="!hasResult">
            <!-- 进度条 -->
            <div class="progress-bar">
                <div class="progress-text">{{ currentIndex + 1 }} / {{ practiceWords.length }}</div>
                <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
            </div>

            <!--
              练习中的实时设置（2026-10-26 新增）
              -----------------------------------------------------------------
              用户要求：「设置也要可以在听力播放的练习页面实时调整」。

              改前：设置只在开始前能改，练到一半觉得"太快了/太慢了/想多听一遍"
                    只能退出重来 —— 而退出会丢掉本轮进度。

              改后：练习页顶部一个可折叠的「实时设置」条，展开即可调：
                播放速度 / 播放遍数 / 遍间隔（/ 自动下一题，仅自动听写模式）。
              所有参数都是 `ref`，改完**立即对下一次播放生效**，不必重启练习。
              默认折叠，不打扰正在答题的人。
            -->
            <div class="live-settings">
                <button type="button" class="live-settings__toggle" @click="showLiveSettings = !showLiveSettings">
                    <el-icon class="live-settings__icon" :class="{ 'is-open': showLiveSettings }">
                        <ArrowRight />
                    </el-icon>
                    <span>实时设置</span>
                    <span class="live-settings__summary">
                        {{ speechRate.toFixed(1) }}× 速度
                        · {{ practiceMode === 'input' ? 1 : repeatCount }} 遍
                        <template v-if="practiceMode !== 'input' && repeatCount > 1"> · 间隔 {{ playInterval }}s</template>
                        <template v-if="practiceMode === 'dictation'"> · 自动跳 {{ autoNextInterval }}s</template>
                    </span>
                </button>

                <div class="live-settings__body" v-show="showLiveSettings">
                    <div class="live-row">
                        <span class="live-row__label">播放速度</span>
                        <el-slider v-model="speechRate" :min="0.5" :max="1.5" :step="0.1" show-stops
                            :format-tooltip="(v) => v.toFixed(1) + '×'" />
                        <span class="live-row__value">{{ speechRate.toFixed(1) }}×</span>
                    </div>

                    <div class="live-row" v-if="practiceMode !== 'input'">
                        <span class="live-row__label">播放遍数</span>
                        <el-radio-group v-model="repeatCount" size="small">
                            <el-radio-button :value="1">1</el-radio-button>
                            <el-radio-button :value="2">2</el-radio-button>
                            <el-radio-button :value="3">3</el-radio-button>
                        </el-radio-group>
                        <span class="live-row__value">{{ repeatCount }} 遍</span>
                    </div>

                    <div class="live-row" v-if="practiceMode !== 'input' && repeatCount > 1">
                        <span class="live-row__label">遍间隔</span>
                        <el-slider v-model="playInterval" :min="0.5" :max="5" :step="0.5" show-stops
                            :format-tooltip="(v) => v + ' 秒'" />
                        <span class="live-row__value">{{ playInterval }}s</span>
                    </div>

                    <div class="live-row" v-if="practiceMode === 'dictation'">
                        <span class="live-row__label">自动下一题</span>
                        <el-slider v-model="autoNextInterval" :min="1" :max="10" :step="0.5" show-stops
                            :format-tooltip="(v) => v + ' 秒'" />
                        <span class="live-row__value">{{ autoNextInterval }}s</span>
                    </div>

                    <!--
                      切换模式也是「实时」的一部分：
                      练着练着发现「纯听力跟不上」，可以直接切到打字输入，
                      本轮进度不丢（`practiceWords` / `currentIndex` 都不重置）。
                    -->
                    <div class="live-row live-row--mode">
                        <span class="live-row__label">练习模式</span>
                        <el-radio-group v-model="practiceMode" size="small">
                            <el-radio-button value="listen">纯听力</el-radio-button>
                            <el-radio-button value="input">打字输入</el-radio-button>
                            <el-radio-button value="dictation">自动听写</el-radio-button>
                        </el-radio-group>
                        <span class="live-row__value"></span>
                    </div>

                    <p class="live-settings__hint">
                        改完立即对下一次播放生效，不用退出练习；切模式也不会丢本轮进度。
                    </p>
                </div>
            </div>

            <!-- 当前单词卡片 -->
            <div class="word-card">
                <!--
                  ⚠️ 字段是 `translation` / `word`，不是 `chinese` / `english`（2026-10-23 修）

                  2026-10-26：**纯听力模式不能显示中文释义和音标**。
                  截图实测：纯听力模式下页面把「adj. 根本的 / ˈfʌndəmentl」全摆出来了 ——
                  用户照着抄就行，"听力"练了个寂寞。
                  现在纯听力只显示"第几题"和播放入口，释义与音标一律隐藏；
                  打字输入 / 自动听写才显示中文（它们是"中译英"，需要题面）。
                -->
                <template v-if="practiceMode !== 'listen'">
                    <div class="word-chinese">{{ currentWord?.translation || '' }}</div>
                    <div class="word-phonetic" v-if="currentWord?.phonetic">{{ currentWord.phonetic }}</div>
                </template>
                <template v-else>
                    <div class="listen-question-mark">?</div>
                    <div class="listen-question-hint">听发音，写出这个单词</div>
                </template>

                <!-- 播放按钮 -->
                <!--
                  ⚠️ 2026-10-23 修：原来是 `:loading="isPlaying"`。
                      Element Plus 的 button 在 loading 时会**同时置 disabled**，
                      并且 `handleClick` 里 `if (props.loading) { evt.stopPropagation(); return }`
                      —— 也就是说只要 `isPlaying` 卡在 true，这个按钮就永久点不动，
                      表现正是「点击没反应」。
                      现在去掉 loading，只用图标在 播放/暂停 之间切换：
                      按钮始终可点，用户可以随时重播或打断。

                  2026-10-26：三种模式共用同一个按钮，
                  只有 dictation 才走「播 N 遍后自动跳」，其余都是纯播放。
                -->
                <div class="play-section">
                    <el-button type="primary" circle size="large"
                        @click="practiceMode === 'dictation' ? startDictationRound() : playCurrentWord()"
                        class="play-btn" :disabled="isWaitingAutoNext">
                        <el-icon :size="28">
                            <VideoPlay v-if="!isPlaying" />
                            <VideoPause v-else />
                        </el-icon>
                    </el-button>

                    <span class="play-hint">
                        <span v-if="isPlaying">
                            正在播放第 {{ currentPlayCount }}/{{ practiceMode === 'input' ? 1 : repeatCount }} 遍...
                        </span>
                        <span v-else-if="isWaitingAutoNext">
                            ⏳ {{ autoNextCountdown }}秒后自动下一题
                        </span>
                        <span v-else-if="practiceMode === 'listen'">
                            点击播放，可反复听，写完点「下一题」
                        </span>
                        <span v-else>点击重新播放</span>
                    </span>
                </div>

                <!--
                  输入区域：只有「打字输入」模式才有
                  ------------------------------------------------------
                  纯听力（listen）是纸笔写，页面上不该出现输入框；
                  自动听写（dictation）是播完就跳，也没有输入。
                  输入框**不设任何计时**：不打字不催、不自动跳。
                -->
                <div class="input-section" v-if="practiceMode === 'input'">
                    <el-input ref="inputRef" v-model="userAnswer" placeholder="请输入英文单词...（不限时）" size="large"
                        clearable @keyup.enter="submitAnswer" :disabled="isCorrect || isWrong">
                        <template #suffix>
                            <el-button type="primary" @click="submitAnswer"
                                :disabled="!userAnswer.trim() || isCorrect || isWrong">
                                提交
                            </el-button>
                        </template>
                    </el-input>
                </div>

                <!-- 纯听力模式：给一句明确的操作指引，代替输入框 -->
                <div class="listen-tip" v-else-if="practiceMode === 'listen'">
                    <el-icon :size="15"><Headset /></el-icon>
                    <span>听发音，在纸上写下单词；想听几遍都行，写完点下方「下一题」</span>
                </div>

                <!-- 结果反馈：只有打字输入才有对错 -->
                <div class="feedback-section" v-if="showFeedback && practiceMode === 'input'">
                    <div :class="['feedback-card', isCorrect ? 'correct' : 'wrong']">
                        <div class="feedback-icon">
                            <el-icon :size="32">
                                <CircleCheck v-if="isCorrect" />
                                <CircleClose v-else />
                            </el-icon>
                        </div>
                        <div class="feedback-content">
                            <div class="correct-answer">
                                <span class="label">正确答案：</span>
                                <span class="value">{{ currentWord.word }}</span>
                            </div>
                            <div class="your-answer" v-if="!isCorrect">
                                <span class="label">你的答案：</span>
                                <span class="value">{{ userAnswer }}</span>
                            </div>
                            <div class="word-meaning">
                                <span class="label">释义：</span>
                                <span class="value">{{ currentWord.translation }}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!--
              操作按钮（2026-10-26 适配三模式）
              -----------------------------------------------------------------
                listen    —— 只有「下一题」＋「重听」＋「结束」。
                             下一题**永远手动**，绝不自动跳（用户可能还在写）。
                input     —— 提交前有「跳过」；提交后出现「下一题」。
                dictation —— 播完自动跳，未跳前可手动「下一题」。
            -->
            <div class="action-buttons">
                <!-- 纯听力：重听 + 下一题 -->
                <template v-if="practiceMode === 'listen'">
                    <el-button size="large" @click="playCurrentWord" :disabled="isPlaying">
                        重听一遍
                    </el-button>
                    <el-button type="primary" size="large" @click="autoNextWord">
                        下一题
                        <el-icon><ArrowRight /></el-icon>
                    </el-button>
                </template>

                <el-button v-if="practiceMode === 'input' && showFeedback" type="primary" size="large"
                    @click="nextWord">
                    下一题
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </el-button>
                <el-button v-if="practiceMode === 'dictation' && !isWaitingAutoNext" type="primary" size="large"
                    @click="autoNextWord">
                    下一题
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </el-button>
                <el-button v-if="practiceMode === 'input' && !showFeedback" type="info" size="large" @click="skipWord">
                    跳过
                </el-button>
                <el-button type="danger" plain size="large" @click="stopPractice">
                    结束练习
                </el-button>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishListening' })
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
    ArrowLeft, VideoPlay, VideoPause, ArrowRight,
    CircleCheck, CircleClose, Headset, Collection,
    // 三种练习模式的卡片图标（2026-10-26）
    EditPen, Timer, InfoFilled
} from '@element-plus/icons-vue'
import { listFrontWordBooks } from '@/api/wordBooks/wordBooks'
import { listAllWords, submitPractice } from '@/api/words/words'
import { ElMessage, ElMessageBox } from 'element-plus'
import { speak, stopSpeak, speakReasonText, warmUpVoices, unlockAudio } from '@/utils/speech'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

// 状态
const isPracticing = ref(false)
const loadingWords = ref(false)

/*
 * 练习模式（2026-10-26 重构）
 * ============================================================================
 * 用户要求：「要可以选择模式 —— 一种是单纯播放听力、用户自己手动听写（纸笔写），
 * 另一种才是用户输入单词；手动打字输入的不需要时间限制；
 * 并且要可以调节播放速度 / 间隔等等相关设置。」
 *
 * 于是三种模式：
 *
 *   listen   —— **纯听力**：只播放，不输入、不判分、不限时。
 *               页面上显示「播放第 N/M 遍」，用户自己在纸上写。
 *               下一题完全手动（点「下一题」），绝不自动跳 ——
 *               自动跳会让还在写的人丢题。
 *
 *   input    —— **打字输入**：显示中文释义，用户敲英文，提交判对错。
 *               **不设任何计时**：不打字也不催、不自动跳，
 *               想多久想多久（这是用户明确要求的）。
 *
 *   dictation—— **听写模式**（原有）：播放 N 遍后自动进入下一题。
 *               保留它是因为"跟读式快练"确实有人用，但默认不再是它。
 */
type PracticeMode = 'listen' | 'input' | 'dictation'
const practiceMode = ref<PracticeMode>('input')

/** 播放速度（0.5~1.5，1 = 正常）。传给 TTS 的 rate */
const speechRate = ref(1)

/** 播放次数（1~3 遍） */
const repeatCount = ref(2)

/** 每遍之间的间隔（秒） */
const playInterval = ref(2)

/** 自动下一题间隔（秒）—— 只有 dictation 模式用 */
const autoNextInterval = ref(3)

/**
 * 练习中的「实时设置」面板是否展开（2026-10-26）
 *
 * 默认收起：正在答题的人不需要每次都看到一堆滑块。
 * 但它必须存在 —— 否则练到一半觉得"太快了"只能退出重来，
 * 而退出会丢掉本轮进度。
 */
const showLiveSettings = ref(false)

// 自动下一题定时器
let autoNextTimer = null
// 是否正在等待自动下一题
const isWaitingAutoNext = ref(false)
// 当前播放进度（第几次播放）
const currentPlayCount = ref(0)

// 词库相关
const bookOptions = ref([])
const selectedBookId = ref(null)
const wordList = ref([])

// 练习设置
/*
 * ⚠️ `practiceRange` 已删除（2026-10-26）：
 *    它只有「全部单词」一个选项 —— 不是设置项，是个装饰。
 *    原设计想按「已掌握/未掌握」筛选，但 `words` 表没有掌握状态列，
 *    那个筛选永远返回空，所以选项被砍到只剩一个。
 *    留一个只有一种选择的下拉，用户会以为坏了。
 */
const playOrder = ref('random')
// ⚠️ `repeatCount` / `playInterval` 已上移到模式定义处（2026-10-26），
//    那里和 speechRate 放在一起更易读，不再重复声明。

// 练习状态
const practiceWords = ref([])
const currentIndex = ref(0)
const userAnswer = ref('')
const showFeedback = ref(false)
const isCorrect = ref(false)
const isWrong = ref(false)
const isPlaying = ref(false)




// 输入框引用
const inputRef = ref(null)

// ==================== 语音合成（Web Speech API） ====================
// 2026-10-23 改：原来这一页自己手写 `speechSynthesis.speak()`，踩了三个坑，
// 表现就是「点了没声音 / 点了没反应」。现在统一走 @/utils/speech：
//
//   ① `cancel()` 后立刻 `speak()` 会被 Chrome 静默丢弃（不报错、不触发 onend）
//      —— 原代码每次播放前都 cancel()，于是「第一次能响，之后点就哑了」。
//   ② `onerror` 一律 `() => resolve()`，缺语音包 / 被策略拦下全被吞掉，
//      用户永远不知道为什么没声音。
//   ③ 没有任何超时。引擎卡住时 `isPlaying` 永远是 true，而播放按钮是
//      `:loading="isPlaying"`，Element Plus 的 loading 会同时变成 disabled
//      并在 handleClick 里直接 return —— 按钮就**永久点不动**了。
//
// 具体细节见 `src/utils/speech.ts` 顶部注释。

// 统计
const practiceResults = ref([])

/* ============================================================================
 * 练习结果面板状态（2026-10-26 闭环）
 *
 * 改前练完只弹一个 ElMessageBox，关掉就什么都不剩。
 * 现在结果留在页面里，用户可以：
 *   · 看到本次写错的具体单词（不是只给个数字）
 *   · 点「再练一遍错词」只练这几个
 *   · 去词库 / 让 AI 分析这次练习
 * ========================================================================== */
const hasResult = ref(false)
const resultSummary = ref({ total: 0, correct: 0, accuracy: 0 })
const resultWrongWords = ref<Array<{ word: string; translation: string; userAnswer: string }>>([])

/** 本次练习用时（秒）—— 从点「开始听写」起算 */
const practiceStartedAt = ref(0)
const practiceElapsedSeconds = computed(() =>
    practiceStartedAt.value ? Math.max(0, Math.round((Date.now() - practiceStartedAt.value) / 1000)) : 0
)

/** 当前词书名（提交记录时带上，列表里能看出练的哪本） */
const currentBookName = ref('')

// 计算属性
// ⚠️ `masteredCount` / `unmasteredCount` 已删除（2026-10-23）：
//    `words` 表没有掌握状态列，这两个数只能是 0 和"全部"，属于假指标。

const currentWord = computed(() => {
    return practiceWords.value[currentIndex.value] || null
})

const progressPercent = computed(() => {
    if (practiceWords.value.length === 0) return 0
    return Math.round(((currentIndex.value) / practiceWords.value.length) * 100)
})

// 加载词库选项
const loadBookOptions = async () => {
    try {
        // ⚠️ 2026-10-23 修「加词库 422」：
        //    原来传 `pageSize: 100` 给 `/wordBooks/wordBooks/list` —— 那个接口上限就是 100，
        //    刚好卡在边界上没问题；但换个写法（>100）立刻 422。
        //    这里统一用 `listFrontWordBooks`（内部按 100 翻页取全量），不再依赖调用方算上限。
        //    另外 `userId` 后端不收（归属由登录态决定），传了也会被忽略，已去掉。
        const response = await listFrontWordBooks()
        if (response.code === 200) {
            bookOptions.value = response.rows || []
        } else {
            ElMessage.error(response.msg || '加载词库失败')
        }
    } catch (error) {
        console.error('加载词库失败:', error)
        ElMessage.error('加载词库失败')
    }
}

// 词库切换
const onBookChange = async (bookId) => {
    if (!bookId) return
    loadingWords.value = true
    // 记住书名：提交练习记录时要带上，列表里才看得出练的哪本
    currentBookName.value =
        String(bookOptions.value.find((b) => b.bookId === bookId)?.bookName || '')
    try {
        // ⚠️ 后端参数名是 `bookId`
        //
        // ⚠️ 2026-10-23 修「加载单词 422」：
        //    原来 `pageSize: 1000`，后端 `le=200` 是硬上限 → FastAPI 直接 HTTP 422，
        //    单词永远加载不出来（页面只会显示"该词库还没有单词"）。
        //    听写要练的就是**整本书**，所以用 listAllWords（内部翻页取完）。
        const response = await listAllWords({ bookId: bookId })
        if (response.code === 200) {
            wordList.value = response.rows || []
        } else {
            ElMessage.error(response.msg || '加载单词失败')
        }
    } catch (error) {
        console.error('加载单词失败:', error)
        ElMessage.error('加载单词失败')
    } finally {
        loadingWords.value = false
    }
}

// 开始练习
const startPractice = () => {
    // ⚠️ `words` 表没有 isMastered 列，原先按「未掌握」筛选永远为空。
    //    现在不做这个筛选：练的就是这本词库里的全部单词。
    let words = [...wordList.value]

    if (words.length === 0) {
        ElMessage.warning('没有可练习的单词')
        return
    }

    // 随机打乱
    if (playOrder.value === 'random') {
        words = shuffleArray(words)
    }

    practiceWords.value = words
    currentIndex.value = 0
    isPracticing.value = true
    practiceResults.value = []
    userAnswer.value = ''
    showFeedback.value = false
    isCorrect.value = false
    isWrong.value = false
    isWaitingAutoNext.value = false
    currentPlayCount.value = 0

    // 2026-10-26：清掉上一轮的结果面板，开始计时（提交记录时要报用时）
    hasResult.value = false
    resultWrongWords.value = []
    resultSummary.value = { total: 0, correct: 0, accuracy: 0 }
    practiceSubmitted.value = false
    practiceStartedAt.value = Date.now()

    // 清除之前的定时器
    clearAutoNextTimer()

    // 自动播放第一个单词
    nextTick(() => {
        if (practiceMode.value === 'dictation') {
            // 听写模式：自动开始播放
            startDictationRound()
        } else {
            // 输入模式：手动点击播放
            playCurrentWord()
        }
    })
}

// ==================== 播放（三种模式共用） ====================
/**
 * 播放当前单词的中文发音 N 遍
 *
 * 2026-10-26 抽出来给三种模式共用：
 *   · listen    —— 播完就停，**不自动跳题**（用户可能正在纸上写）
 *   · input     —— 手动点播放，播一遍就行（用户要看中文释义打字）
 *   · dictation —— 播 N 遍后启动自动下一题倒计时
 *
 * `autoNext` 参数决定播完是否启动倒计时 —— 这是三个模式唯一的行为差异，
 * 所以不再写三份播放循环。
 */
const playRound = async ({ autoNext = false } = {}) => {
    if (!currentWord.value) return

    clearAutoNextTimer()
    isWaitingAutoNext.value = false

    const chinese = currentWord.value.translation
    if (!chinese) {
        ElMessage.warning('该单词没有中文释义')
        if (autoNext) autoNextWord()
        return
    }

    // input 模式只播一遍（用户是看着中文打字，重复播放没意义）
    const times = practiceMode.value === 'input' ? 1 : repeatCount.value
    /*
     * ⚠️ 本轮遍数在**循环开始前**就固定（`times`），而不是每轮重新读 `repeatCount`。
     *    否则用户在播放中途把「2 遍」改成「3 遍」，这一轮会突然多播一遍 ——
     *    听感上是"话没说完又重复了一次"。
     *    改动从**下一次播放**起生效，实时设置面板底部的提示也这么写。
     */

    isPlaying.value = true
    currentPlayCount.value = 0

    try {
        for (let i = 0; i < times; i++) {
            currentPlayCount.value = i + 1
            const res = await speakChinesePromise(chinese)
            if (res && res.ok === false) {
                if (res.reason !== 'interrupted' && res.reason !== 'canceled') {
                    ElMessage.warning(speakReasonText(res.reason, 'zh-CN'))
                }
                // 播放失败不自动跳题：否则用户会看着题目一题题跳过却不知道为什么
                return
            }
            if (i < times - 1) {
                await sleep(playInterval.value * 1000)
            }
        }

        // 只有 dictation 模式才自动进入下一题
        if (autoNext) startAutoNextCountdown()
    } finally {
        isPlaying.value = false
        currentPlayCount.value = 0
    }
}

/** dictation 模式：播 N 遍 → 自动下一题 */
const startDictationRound = () => playRound({ autoNext: true })

/** listen / input 模式：只播，不自动跳题 */
const playCurrentWord = () => playRound({ autoNext: false })


// 倒计时显示
const autoNextCountdown = ref(0)
let countdownInterval = null

// 开始自动下一题倒计时
// 开始自动下一题倒计时（带显示）
const startAutoNextCountdown = () => {
    isWaitingAutoNext.value = true
    autoNextCountdown.value = Math.ceil(autoNextInterval.value)  // ✅ 向上取整

    // 每秒更新倒计时显示
    countdownInterval = setInterval(() => {
        if (autoNextCountdown.value > 0) {
            autoNextCountdown.value--
        }
        if (autoNextCountdown.value <= 0) {
            clearInterval(countdownInterval)
            countdownInterval = null
        }
    }, 1000)  // ✅ 改为每秒更新

    autoNextTimer = setTimeout(() => {
        clearInterval(countdownInterval)
        countdownInterval = null
        isWaitingAutoNext.value = false
        autoNextWord()
    }, autoNextInterval.value * 1000)
}




// 进入下一题（手动或自动）
const autoNextWord = () => {
    clearAutoNextTimer()

    /*
     * 记录"跳过"只在**需要作答的模式**下才有意义：
     *   · dictation —— 播完自动跳，用户没机会写，记 skipped
     *   · input     —— 用户自己点「跳过」，记 skipped
     *   · listen    —— **纯听力不计分**，用户就是来听的，
     *                  把每一题都记成"错"会让正确率永远是 0，
     *                  那个数字毫无意义。所以 listen 模式不写结果。
     */
    const countsAsAnswer = practiceMode.value === 'dictation' || practiceMode.value === 'input'
    if (countsAsAnswer && currentWord.value) {
        practiceResults.value.push({
            wordId: currentWord.value.wordId,
            word: currentWord.value,
            userAnswer: '',
            isCorrect: false,
            skipped: true,
            mode: practiceMode.value
        })
    }

    if (currentIndex.value < practiceWords.value.length - 1) {
        currentIndex.value++
        userAnswer.value = ''
        showFeedback.value = false
        isCorrect.value = false
        isWrong.value = false
        isWaitingAutoNext.value = false

        nextTick(() => {
            // dictation 自动播，其余模式交给用户点
            if (practiceMode.value === 'dictation') {
                startDictationRound()
            } else if (practiceMode.value === 'listen') {
                playCurrentWord()
            }
        })
    } else {
        // 练习完成
        isPracticing.value = false
        showPracticeResult()
    }
}




// 清除定时器
const clearAutoNextTimer = () => {
    if (autoNextTimer) {
        clearTimeout(autoNextTimer)
        autoNextTimer = null
    }
    if (countdownInterval) {
        clearInterval(countdownInterval)
        countdownInterval = null
    }
    isWaitingAutoNext.value = false
    autoNextCountdown.value = 0  // ✅ 重置为 0
}
/**
 * 中文语音播放（Promise 版本）
 *
 * 走统一的 `speak()`：内部已处理 cancel→speak 的间隔、语音包选择、
 * 错误码透出和看门狗超时。返回 `{ok, reason}`，不再无声吞掉失败。
 *
 * ⚠️ 2026-10-26：`rate` 原来是硬编码的 `0.9`，现在读用户设置的
 * `speechRate`（0.5~1.5）。语速是听力练习最常被需要的参数 ——
 * 太快听不懂、太慢没挑战，写死一个值等于替用户做了决定。
 */
const speakChinesePromise = (text) => {
    return speak(text, { lang: 'zh-CN', rate: speechRate.value })
}

// 数组随机打乱
const shuffleArray = (array) => {
    const newArray = [...array]
    for (let i = newArray.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
            ;[newArray[i], newArray[j]] = [newArray[j], newArray[i]]
    }
    return newArray
}

/**
 * 停止当前语音播放
 *
 * 2026-10-23 改：原实现只在 `speechSynthesis.speaking` 为 true 时才 cancel()。
 * 但 Chrome 里队列可能处于「pending 却没进入 speaking」的卡住状态，
 * 此时不 cancel 就永远解锁不了。现在无条件 cancel()，并把排队回调作废。
 */
const stopSpeaking = () => {
    stopSpeak()
}

// 延时函数
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// 提交答案
const submitAnswer = () => {
    if (!userAnswer.value.trim()) {
        ElMessage.warning('请输入答案')
        return
    }

    if (!currentWord.value) return

    const correctEnglish = String(currentWord.value.word || '').toLowerCase().trim()
    const userEnglish = userAnswer.value.toLowerCase().trim()

    // 判断是否正确（忽略大小写和前后空格）
    isCorrect.value = correctEnglish === userEnglish
    isWrong.value = !isCorrect.value
    showFeedback.value = true

    // 记录结果
    practiceResults.value.push({
        wordId: currentWord.value.wordId,
        word: currentWord.value,
        userAnswer: userAnswer.value,
        isCorrect: isCorrect.value
    })

    // 聚焦到下一题按钮
    nextTick(() => {
        inputRef.value?.blur()
    })
}

/*
 * 原 `markAsMastered()` 已删除（2026-10-23）
 * ----------------------------------------
 * 它写的是 `updateWords({ id, isMastered: 1 })`，但：
 *   · `words` 表**没有 isMastered 列**，后端不认这个字段；
 *   · 参数名也错（要 `wordId`，不是 `id`）。
 * 也就是说这个函数从来没成功过，只是把错误吞进了 catch。
 * 与其留一个假装存在的"掌握"概念，不如去掉 —— 见 `practiceRange` 的说明。
 */

// 下一题
const nextWord = () => {
    if (currentIndex.value < practiceWords.value.length - 1) {
        currentIndex.value++
        userAnswer.value = ''
        showFeedback.value = false
        isCorrect.value = false
        isWrong.value = false

        nextTick(() => {
            inputRef.value?.focus()
            playCurrentWord()
        })
    } else {
        // 练习完成
        showPracticeResult()
    }
}

// 跳过当前单词
const skipWord = () => {
    if (currentIndex.value < practiceWords.value.length - 1) {
        practiceResults.value.push({
            wordId: currentWord.value.wordId,
            word: currentWord.value,
            userAnswer: '',
            isCorrect: false,
            skipped: true
        })

        currentIndex.value++
        userAnswer.value = ''
        showFeedback.value = false
        isCorrect.value = false
        isWrong.value = false

        nextTick(() => {
            playCurrentWord()
        })
    } else {
        showPracticeResult()
    }
}

// 显示练习结果
/*
 * 2026-10-26 闭环改造
 * ---------------------------------------------------------------------------
 * 改前：练完只弹一个 ElMessageBox（总题数/正确/错误/正确率），点「返回」
 *       就把 `practiceResults` 丢掉 —— 关掉页面什么都不剩。
 *       下次进来重头开始，也不知道上次哪些词写错了。
 *
 * 改后：
 *   ① 把结果 POST 到 `/words/practice/submit` 落库；
 *   ② 结果面板里列出**本次写错的词**（不是只给个数字）；
 *   ③ 点「再练一遍错词」直接只练这几个词；
 *   ④ 「去词库」/「让 AI 帮我分析」两个出口。
 *      后者跳到智能体并带上问题，智能体的 `english_practice` 工具
 *      能读到刚才这次练习 —— 页面与对话就此闭环。
 */
/**
 * 本次练习是否已经提交过记录
 *
 * ⚠️ 2026-10-26 修「一次练习存了 3 条记录」：
 *    `showPracticeResult()` 有**三个**触发点 ——
 *      · 答完最后一题的 `nextWord()`
 *      · `skipWord()` 跳过最后一题
 *      · 「结束练习」按钮
 *    用户点「结束练习」时如果刚好已经答完，这三条路径会各调一次，
 *    于是同一次练习在库里躺了 3 条（实测：id 2/3/4 完全相同的数据）。
 *
 *    用这个标记做幂等：提交过一次就不再提交，
 *    新一轮练习开始时（`startPractice` / `retryWrongWords`）重置为 false。
 */
const practiceSubmitted = ref(false)

const submitPracticeRecord = async () => {
    if (!practiceResults.value.length) return
    // 幂等：同一次练习只落库一条
    if (practiceSubmitted.value) return
    practiceSubmitted.value = true

    const total = practiceResults.value.length
    const correct = practiceResults.value.filter(r => r.isCorrect).length
    try {
        await submitPractice({
            mode: 'dictation',
            bookId: selectedBookId.value || undefined,
            title: currentBookName.value || undefined,
            total,
            correct,
            duration: practiceElapsedSeconds.value,
            detail: practiceResults.value.map(r => ({
                word: String(r.word?.word || ''),
                input: String(r.userAnswer || ''),
                ok: !!r.isCorrect
            }))
        })
    } catch (e) {
        // 记录失败不该打断用户看结果，静默即可。
        // 但要把幂等标记放开，让用户还能重试。
        practiceSubmitted.value = false
        console.warn('[listening] 练习记录保存失败', e)
    }
}

// 显示练习结果
const showPracticeResult = async () => {
    stopSpeaking()

    const total = practiceResults.value.length
    const correct = practiceResults.value.filter(r => r.isCorrect).length
    const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0
    const wrongList = practiceResults.value.filter(r => !r.isCorrect)

    // 先落库，再展示（顺序反了会在用户点得太快时丢记录）
    await submitPracticeRecord()

    /*
     * ⚠️ 必须把 `isPracticing` 置 false：结果面板的显示条件是
     *    `hasResult && !isPracticing`，而练习区（题目卡片）的条件是
     *    `isPracticing`。不清掉的话两块钱同时渲染 ——
     *    截图实测：结果面板和题目卡叠在一起，页面很长很乱。
     */
    isPracticing.value = false
    clearAutoNextTimer()

    hasResult.value = true
    resultSummary.value = { total, correct, accuracy }
    resultWrongWords.value = wrongList.map(r => ({
        word: String(r.word?.word || ''),
        translation: String(r.word?.translation || ''),
        userAnswer: String(r.userAnswer || '')
    }))
}


// 结束练习
const stopPractice = () => {
    ElMessageBox.confirm('确定要结束本次练习吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
    }).then(async () => {
        stopSpeaking()
        clearAutoNextTimer()

        // 已经做了一些题 → 落到结果面板（会先提交记录）
        if (practiceResults.value.length > 0) {
            isPracticing.value = false
            await showPracticeResult()
            return
        }

        isPracticing.value = false
        if (selectedBookId.value) {
            onBookChange(selectedBookId.value)
        }
    }).catch(() => { })
}

/* ============================================================================
 * 结果面板的三个出口（2026-10-26 闭环）
 * ========================================================================== */

/** 只练刚才写错的那几个词 */
function retryWrongWords() {
    const wanted = new Set(resultWrongWords.value.map((w) => w.word))
    const subset = wordList.value.filter((w: any) => wanted.has(String(w.word || '')))
    if (!subset.length) {
        ElMessage.warning('错词已经不在当前词库里了')
        return
    }
    hasResult.value = false
    practiceWords.value = subset
    currentIndex.value = 0
    isPracticing.value = true
    practiceResults.value = []
    userAnswer.value = ''
    showFeedback.value = false
    isCorrect.value = false
    isWrong.value = false
    isWaitingAutoNext.value = false
    currentPlayCount.value = 0
    practiceSubmitted.value = false
    practiceStartedAt.value = Date.now()
    nextTick(() => {
        if (practiceMode.value === 'dictation') {
            playCurrentWord()
        }
    })
}

/** 回到词库选择态 */
function backToBookSelect() {
    hasResult.value = false
    resultWrongWords.value = []
    if (selectedBookId.value) {
        onBookChange(selectedBookId.value)
    }
}

/**
 * 交给智能体分析
 *
 * 跳过去时把问题带在 route state 里 —— 智能体那边的 `english_practice`
 * 工具刚读到这次提交的记录，于是「页面练完 → 聊天里复盘」这条线也接通了。
 */
function askAiForAnalysis() {
    router.push({
        path: '/front/agent/chat',
        state: {
            seedQuestion: '我刚练完一次英语听写，帮我分析一下这次练习，我该重点复习哪些词？'
        } as any
    })
}

// 监听页面离开
watch(() => isPracticing.value, (val) => {
    if (!val) {
        stopSpeaking()
        clearAutoNextTimer()  // ✅ 清除定时器
    }
})
/*
 * 原 `goBack()` 已删除（2026-10-26）
 * ---------------------------------
 * 返回栏从模板移除后它没有调用方了。练习中退出用「结束练习」按钮，
 * 它内部会弹确认框并回到词库选择态，覆盖了唯一的退出需求。
 */

// 组件挂载：预热语音 + 加载词库
onMounted(() => {
    // 预热语音列表，让用户点播放时不必 await（保住用户手势上下文，
    // 否则 Chrome 会以 not-allowed 拒绝发声）。
    warmUpVoices()
    loadBookOptions()

    /*
     * 第一次交互时解锁 Web Audio 通道。
     * 服务端合成的声音走 Web Audio 播放（`<audio>` 在本环境会卡在
     * readyState 0，见 utils/speech.ts 顶部注释），而 AudioContext
     * 必须在用户手势里 resume 才不会一直被挂起。
     */
    const unlock = () => {
        unlockAudio()
        window.removeEventListener('pointerdown', unlock)
        window.removeEventListener('keydown', unlock)
    }
    window.addEventListener('pointerdown', unlock)
    window.addEventListener('keydown', unlock)
})

// 监听页面离开
watch(() => isPracticing.value, (val) => {
    if (!val) {
        stopSpeaking()
    }
})
</script>

<style scoped lang="scss">
.listening-page {
    /*
     * 2026-10-26：原来 `min-height: 100vh` 会让页面比可视区高一点
     * （顶栏已占掉 52px），出现不必要的滚动条。改成 100%。
     *
     * ⚠️ 这里**不要**写 `align-items: center`：子元素已用
     *    `max-width + margin: 0 auto` 水平居中，再叠一层 center
     *    会因为 `width: 100%` 与 flex 收缩规则打架，实测整体偏右。
     */
    min-height: 100%;
    display: flex;
    flex-direction: column;

    .setting-hint {
        font-size: 12px;
        color: #9ca3af;
        margin-top: 4px;
        display: block;
    }

    .page-header {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        align-items: center;
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e5e7eb;

        .header-left {
            display: flex;
            align-items: center;
            gap: 4px;
            color: #6b7280;
            cursor: pointer;
            font-size: 15px;
            justify-self: start;
            width: fit-content;

            &:hover {
                color: #4b5563;
            }
        }

        .header-title {
            font-size: 20px;
            font-weight: 700;
            color: #1f2937;
            text-align: center;
        }

        .header-right {
            justify-self: end;
            width: 60px;
        }
    }

    /*
     * 练习结果面板（2026-10-26 闭环）
     * ---------------------------------
     * 取代原来那个只有 4 个数字的 ElMessageBox：
     * 给分数、列错词、三个出口，让"练完 → 复盘 → 再练"形成回路。
     */
    .result-panel {
        max-width: 620px;
        margin: 0 auto;
        padding: 28px 26px;
        background: #fff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        display: flex;
        flex-direction: column;
        gap: 18px;
    }

    .result-panel__head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
        padding-bottom: 16px;
        border-bottom: 1px solid #f1f5f9;
    }

    .result-panel__score {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }

    .result-panel__pct {
        font-size: 40px;
        font-weight: 700;
        line-height: 1;
        color: #111827;

        i {
            font-style: normal;
            font-size: 18px;
            font-weight: 600;
            color: #9ca3af;
            margin-left: 2px;
        }
    }

    .result-panel__label {
        font-size: 12.5px;
        color: #9ca3af;
    }

    .result-panel__nums {
        display: flex;
        gap: 14px;
        font-size: 13px;
        color: #6b7280;

        .is-ok {
            color: #10b981;
        }

        .is-bad {
            color: #ef4444;
        }
    }

    .result-panel__wrong-title {
        margin-bottom: 10px;
        font-size: 12.5px;
        font-weight: 600;
        letter-spacing: .02em;
        color: #9ca3af;
    }

    .wrong-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-height: 280px;
        overflow-y: auto;
    }

    .wrong-item {
        display: grid;
        grid-template-columns: minmax(90px, 140px) 1fr;
        gap: 4px 12px;
        padding: 10px 12px;
        background: #fef2f2;
        border: 1px solid #fee2e2;
        border-radius: 10px;
        font-size: 13px;

        .wrong-item__word {
            font-weight: 600;
            color: #b91c1c;
        }

        .wrong-item__trans {
            color: #6b7280;
        }

        .wrong-item__mine {
            grid-column: 1 / -1;
            font-size: 12px;
            color: #9ca3af;
        }
    }

    .result-panel__allok {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 22px;
        background: #ecfdf5;
        border-radius: 12px;
        color: #047857;
        font-size: 14px;
    }

    .result-panel__actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
    }

    .result-panel__ai {
        margin: 0;
        padding-top: 14px;
        border-top: 1px dashed #f1f5f9;
        font-size: 13px;
        color: #9ca3af;
    }

    .result-panel__link {
        color: #3b82f6;
        cursor: pointer;

        &:hover {
            text-decoration: underline;
        }
    }

    .book-select-section {
        flex: 1;
        padding: 0;
        max-width: 560px;
        margin: 0 auto;
        width: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        /* 垂直方向也居中，避免内容全挤在页面顶部、下方一大片空白 */
        min-height: calc(100vh - 220px);
        .select-label {
            font-size: 13px;
            font-weight: 600;
            letter-spacing: .02em;
            color: #6b7280;
            margin-bottom: 10px;
        }

        /*
         * 空状态卡片（2026-10-26 新增）
         * 改前未选词库时页面只有一个孤立下拉框，下方空无一物。
         */
        .start-empty {
            margin-top: 28px;
            padding: 44px 24px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 6px;
            background: #fff;
            border: 1px dashed #e2e8f0;
            border-radius: 16px;

            .start-empty__icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 56px;
                height: 56px;
                margin-bottom: 6px;
                border-radius: 14px;
                background: #f1f5f9;
                color: #94a3b8;
            }

            .start-empty__title {
                margin: 0;
                font-size: 15px;
                font-weight: 600;
                color: #374151;
            }

            .start-empty__desc {
                max-width: 340px;
                font-size: 13px;
                line-height: 1.7;
                color: #9ca3af;
            }

            .start-empty__btn {
                margin-top: 10px;
            }
        }

        .book-stats {
            display: flex;
            gap: 24px;
            margin-top: 16px;
            padding: 14px 20px;
            background: #fff;
            border-radius: 14px;
            border: 1px solid #e5e7eb;

            .stat-item {
                display: flex;
                /* 2026-10-26：原来 `column + center` —— 一个数字孤零零居中，
                   下面还顶着"总单词"，看起来像张空卡片。改成一行横排更紧凑。 */
                align-items: baseline;
                gap: 8px;

                .stat-value {
                    font-size: 20px;
                    font-weight: 700;
                    line-height: 1;
                    color: #3b82f6;
                }

                .stat-label {
                    font-size: 13px;
                    color: #6b7280;
                }
            }
        }

        .practice-settings {
            margin-top: 24px;
            padding: 20px;
            background: #fff;
            border-radius: 16px;
            border: 1px solid #e5e7eb;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);

            /*
             * 模式选择卡片（2026-10-26）
             * -----------------------------------------------------------------
             * 用卡片而不是 radio：三个模式差别大、各需一句说明，
             * radio 那样一行排不下，用户也看不出「纯听力」和「自动听写」的区别。
             */
            .mode-picker {
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-bottom: 22px;
            }

            .mode-card {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 14px;
                border: 1.5px solid #e5e7eb;
                border-radius: 12px;
                cursor: pointer;
                transition: border-color .18s, background .18s, box-shadow .18s;

                &:hover {
                    border-color: #c7d2fe;
                    background: #f8faff;
                }

                &.is-active {
                    border-color: #3b82f6;
                    background: #eff6ff;
                    box-shadow: 0 0 0 3px rgba(59, 130, 246, .08);
                }

                .mode-card__icon {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    width: 34px;
                    height: 34px;
                    flex: none;
                    border-radius: 9px;
                    background: #f1f5f9;
                    color: #64748b;
                }

                &.is-active .mode-card__icon {
                    background: #dbeafe;
                    color: #2563eb;
                }

                .mode-card__title {
                    font-size: 13.5px;
                    font-weight: 600;
                    color: #111827;
                }

                .mode-card__desc {
                    margin-top: 1px;
                    font-size: 12px;
                    line-height: 1.5;
                    color: #9ca3af;
                }
            }

            /* 「不限时」说明条 */
            .mode-note {
                display: flex;
                align-items: flex-start;
                gap: 7px;
                margin-top: 4px;
                padding: 10px 12px;
                border-radius: 10px;
                background: #f8fafc;
                font-size: 12.5px;
                line-height: 1.55;
                color: #64748b;

                .el-icon {
                    margin-top: 2px;
                    flex: none;
                    color: #94a3b8;
                }
            }

            /*
             * 2026-10-26 重排
             * -----------------------------------------------------------------
             * 改前：`.setting-label` 是 `display: block`（标签独占一行），
             *       而「练习模式」又被错嵌进「播放顺序」里 —— 那一行是 flex，
             *       于是标签和单选框直接压在一起（截图里能看到字叠字）。
             *
             * 改后：统一两列网格 —— 左列 96px 放标签、右列放控件。
             *       标签不再独占一行，各行左边缘对齐，视觉上是一条竖线。
             */
            .setting-item {
                display: grid;
                grid-template-columns: 96px minmax(0, 1fr);
                align-items: center;
                gap: 16px;
                margin-bottom: 18px;

                &:last-child {
                    margin-bottom: 0;
                }

                .setting-label {
                    font-size: 13.5px;
                    font-weight: 500;
                    color: #1f2937;
                    /* 不再 block：在网格里它天然占左列 */
                    white-space: nowrap;
                }

                /* 单选框之间留出呼吸感，避免挤在一起 */
                :deep(.el-radio) {
                    margin-right: 20px;

                    &:last-child {
                        margin-right: 0;
                    }
                }
            }

            /*
             * 滑块行：`align-items: center` 会让滑块和标签基线错位，
             * 这里改成顶部对齐，并让滑块占满右列。
             */
            .setting-item--slider {
                align-items: start;

                .setting-label {
                    /* 与滑块轨道视觉对齐（滑块本身有内边距） */
                    padding-top: 2px;
                }

                .setting-control {
                    display: flex;
                    flex-direction: column;
                    gap: 2px;
                    min-width: 0;
                }

                :deep(.el-slider) {
                    /* 去掉默认左右外边距，让它和上方单选框左边缘对齐 */
                    padding: 0 6px;
                }

                .setting-hint {
                    font-size: 12px;
                    line-height: 1.5;
                    color: #9ca3af;
                }
            }
        }

        .start-section {
            margin-top: 28px;
            text-align: center;

            .el-button {
                width: 200px;
                height: 48px;
                font-size: 16px;
                border-radius: 8px;
            }
        }
    }

    .practice-section {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 24px 20px;
        max-width: 600px;
        margin: 0 auto;
        width: 100%;

        .progress-bar {
            margin-bottom: 32px;

            .progress-text {
                text-align: center;
                font-size: 16px;
                font-weight: 500;
                color: #409eff;
                margin-bottom: 12px;
            }
        }


            /*
             * 练习中的实时设置（2026-10-26）
             * -----------------------------------------------------------------
             * 默认折叠成一条细栏，展开后是一组可实时调的参数。
             * 放在进度条下方、题卡上方 —— 调完抬头就能看到题目。
             *
             * ⚠️ 这段样式必须写在 `.practice-section` **下面、`.word-card` 外面**。
             *    第一版误放在 `.word-card` 里面，编译成
             *    `.practice-section .word-card .live-settings { ... }`，
             *    而 DOM 里它是 `.word-card` 的**兄弟**节点，选择器匹配不到 ——
             *    于是 `display: grid` 全都没生效，标签和滑块挤成一团（实测如此）。
             */
            .live-settings {
                margin-bottom: 16px;
                border: 1px solid #eef1f5;
                border-radius: 12px;
                background: #fff;
                overflow: hidden;
            }

            .live-settings__toggle {
                display: flex;
                align-items: center;
                gap: 8px;
                width: 100%;
                padding: 10px 14px;
                border: none;
                background: transparent;
                font-family: inherit;
                font-size: 13px;
                color: #4b5563;
                cursor: pointer;
                text-align: left;

                &:hover {
                    background: #f8fafc;
                }
            }

            .live-settings__icon {
                flex: none;
                color: #9ca3af;
                transition: transform .18s;

                &.is-open {
                    transform: rotate(90deg);
                }
            }

            .live-settings__summary {
                margin-left: auto;
                font-size: 12px;
                color: #9ca3af;
            }

            .live-settings__body {
                padding: 4px 14px 12px;
                border-top: 1px solid #f1f5f9;
            }

            .live-row {
                display: grid;
                grid-template-columns: 76px minmax(0, 1fr) 52px;
                align-items: center;
                gap: 12px;
                padding: 6px 0;

                .live-row__label {
                    font-size: 12.5px;
                    color: #6b7280;
                    white-space: nowrap;
                }

                .live-row__value {
                    font-size: 12.5px;
                    font-variant-numeric: tabular-nums;
                    color: #111827;
                    text-align: right;
                }

                :deep(.el-slider) {
                    padding: 0 6px;
                }
            }

            /*
             * 模式切换行：三个按钮比滑块宽，让它们可以换行、并把右侧的
             * 数值占位去掉（那一列对按钮没意义）。
             */
            .live-row--mode {
                grid-template-columns: 76px minmax(0, 1fr);

                :deep(.el-radio-group) {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 6px;
                }

                :deep(.el-radio-button__inner) {
                    padding: 5px 12px;
                    font-size: 12.5px;
                }
            }

            .live-settings__hint {
                margin: 6px 0 0;
                font-size: 12px;
                color: #9ca3af;
            }

        .word-card {
            flex: 1;
            background: #fff;
            border-radius: 16px;
            padding: 40px 24px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
            border: 1px solid #e5e7eb;
            display: flex;
            flex-direction: column;

            .word-chinese {
                font-size: 36px;
                font-weight: 700;
                color: #1f2937;
                text-align: center;
                margin-bottom: 12px;
            }

            .word-phonetic {
                font-size: 16px;
                color: #9ca3af;
                text-align: center;
                margin-bottom: 32px;
                font-family: monospace;
            }

            .play-section {
                text-align: center;
                margin-bottom: 40px;

                .play-btn {
                    width: 80px;
                    height: 80px;
                    margin-bottom: 12px;

                    .el-icon {
                        font-size: 32px;
                    }
                }

                .play-hint {
                    display: block;
                    font-size: 14px;
                    color: #6b7280;
                }
            }


            /*
             * 纯听力的题面（2026-10-26）
             * 不显示释义/音标，只给一个问号占位 ——
             * 否则用户直接照抄，听力练习失去意义。
             */
            .listen-question-mark {
                font-size: 56px;
                font-weight: 700;
                line-height: 1;
                color: #e2e8f0;
                text-align: center;
            }

            .listen-question-hint {
                margin-top: 6px;
                font-size: 13px;
                color: #9ca3af;
                text-align: center;
            }

            .input-section {
                margin-bottom: 24px;
            }

            /*
             * 纯听力模式的提示条（2026-10-26）
             * 这个模式没有输入框，需要一句话告诉用户"现在该干什么"，
             * 否则页面上只剩一个播放按钮和"下一题"，很容易懵。
             */
            .listen-tip {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                margin-bottom: 24px;
                padding: 14px 16px;
                border-radius: 12px;
                background: #f8fafc;
                border: 1px dashed #e2e8f0;
                font-size: 13px;
                color: #64748b;
                text-align: center;

                .el-icon {
                    flex: none;
                    color: #94a3b8;
                }
            }

            .feedback-section {
                .feedback-card {
                    display: flex;
                    align-items: flex-start;
                    gap: 16px;
                    padding: 20px;
                    border-radius: 16px;
                    border: 1px solid transparent;

                    &.correct {
                        background: #f0f9eb;
                        border-color: #b3e19d;
                    }

                    &.wrong {
                        background: #fef0f0;
                        border-color: #fbc4c4;
                    }

                    .feedback-icon {
                        color: #67c23a;

                        .wrong & {
                            color: #f56c6c;
                        }
                    }

                    .feedback-content {
                        flex: 1;

                        .correct-answer,
                        .your-answer,
                        .word-meaning {
                            margin-bottom: 8px;

                            &:last-child {
                                margin-bottom: 0;
                            }

                            .label {
                                font-weight: 500;
                                color: #6b7280;
                            }

                            .value {
                                color: #1f2937;
                                font-weight: 500;
                            }
                        }
                    }
                }
            }
        }

        .action-buttons {
            display: flex;
            gap: 12px;
            justify-content: center;
            margin-top: 24px;
            padding-top: 16px;

            .el-button {
                min-width: 120px;
                border-radius: 8px;
            }
        }
    }
}

@media (max-width: 768px) {
    .listening-page {
        .practice-section {
            .word-card {
                padding: 24px 16px;

                .word-chinese {
                    font-size: 28px;
                }
            }

            .action-buttons {
                flex-wrap: wrap;

                .el-button {
                    flex: 1;
                    min-width: auto;
                }
            }
        }
    }
}
</style>
