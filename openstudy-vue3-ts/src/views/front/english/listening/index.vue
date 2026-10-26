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

        <!--
          词库选择（2026-10-26 融合改造，始终可见）
          =================================================================
          用户反馈：「进入听力词库选择然后才可以进行听力播放，但是进行听力播放
          就无法进行词库选择 / 实时更换。需要将这两个页面进行融合。」

          改前：`v-if="!isPracticing && !hasResult"` —— 一旦开始练习，整个
                词库选择区就从 DOM 里消失，想换一本书只能先「结束练习」，
                而结束会丢掉本轮进度。两个状态互斥，页面被切成两半。

          改后：**词库选择常驻页面顶部**，练习中也一直可见、可切换。
                切换时由 `onBookChange` 负责：
                  · 正在播放 → 立刻停声
                  · 有作答进度 → 提示会丢失，确认后才切
                  · 已经在练这本 → 不重复重载

          练习中的显示分两段：
            顶部 = 词库选择 + 实时设置（收起态，省空间）
            下方 = 结果面板 / 练习区 / 空状态
        -->
        <div class="book-select-section">
            <div class="select-label">
                选择词库
                <span v-if="isPracticing" class="select-label__badge">练习中可随时切换</span>
            </div>
            <div class="book-select-row">
                <el-select v-model="selectedBookId" placeholder="请选择词库" size="large" class="book-select-el"
                    @change="onBookChange">
                    <el-option v-for="book in bookOptions" :key="book.bookId" :label="book.bookName"
                        :value="book.bookId">
                        <span class="book-option">
                            <span class="book-option__name">{{ book.bookName }}</span>
                            <span class="book-option__count">{{ book.wordCount || 0 }} 词</span>
                        </span>
                    </el-option>
                </el-select>
                <el-button size="large" class="book-refresh-btn" @click="refreshBooks" :loading="loadingBooks"
                    title="重新加载词库列表">
                    <el-icon><RefreshRight /></el-icon>
                </el-button>
            </div>

            <!-- 词库统计：练习中也显示，让用户知道这本有多少词 -->
            <div class="book-stats" v-if="selectedBookId && wordList.length > 0">
                <div class="stat-item">
                    <span class="stat-value">{{ wordList.length }}</span>
                    <span class="stat-label">总单词</span>
                </div>
                <div class="stat-item" v-if="isPracticing">
                    <span class="stat-value">{{ practiceWords.length }}</span>
                    <span class="stat-label">本轮题数</span>
                </div>
            </div>
        </div>

        <!-- 未开始练习时的空状态 -->
        <div class="start-empty" v-if="!isPracticing && !hasResult && !selectedBookId">
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

        <div class="start-empty" v-else-if="!isPracticing && !hasResult && wordList.length === 0 && !loadingWords">
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
            <div class="practice-settings" v-if="!isPracticing && !hasResult && selectedBookId && wordList.length > 0">
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

                <!--
                  题目范围（2026-10-26 新增）
                  用户反馈：「只能按词库顺序或随机，不能只练最近加的 20 个」。
                  放在「播放顺序」上面 —— 它决定"练哪些"，比"按什么顺序练"更前置。
                -->
                <div class="setting-item">
                    <span class="setting-label">题目范围</span>
                    <div class="setting-control setting-control--stack">
                        <div class="scope-row">
                            <el-radio-group v-model="practiceScope">
                                <el-radio value="all">全部</el-radio>
                                <el-radio value="recent">最近加入</el-radio>
                                <el-radio value="count">前几个</el-radio>
                            </el-radio-group>
                            <!-- 只有选了「最近/前几个」才出现数量下拉，避免占位 -->
                            <el-select
                                v-if="practiceScope !== 'all'"
                                v-model="scopeLimit"
                                size="small"
                                class="scope-limit"
                            >
                                <el-option
                                    v-for="n in scopeLimitOptions"
                                    :key="n"
                                    :label="`${n} 个`"
                                    :value="n"
                                />
                            </el-select>
                        </div>
                        <span class="setting-hint">
                            {{ practiceScope === 'all'
                                ? `整本词库共 ${wordList.length} 个单词`
                                : practiceScope === 'recent'
                                    ? `按加入时间倒序，练最近加的 ${Math.min(scopeLimit, wordList.length)} 个`
                                    : `按词库顺序，练前 ${Math.min(scopeLimit, wordList.length)} 个` }}
                        </span>
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

                <!-- 播放内容：中文 / 英文 / 中文+英文 -->
                <div class="setting-item">
                    <span class="setting-label">播放内容</span>
                    <div class="setting-control setting-control--stack">
                        <el-radio-group v-model="audioContent">
                            <el-radio value="zh">中文</el-radio>
                            <el-radio value="en">英文</el-radio>
                            <el-radio value="both">中文+英文</el-radio>
                        </el-radio-group>
                        <span class="setting-hint">
                            {{ audioContent === 'zh' ? '播中文释义，你写英文单词（中译英，考回忆）'
                                : audioContent === 'en' ? '播英文发音，你拼出单词（真听力，考辨音 + 拼写）'
                                : '每遍先中文后英文，先自己回想再听答案核对' }}
                        </span>
                    </div>
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
            <div class="start-section" v-if="!isPracticing && !hasResult && selectedBookId && wordList.length > 0">
                <el-button type="primary" size="large" @click="startPractice" :loading="loadingWords">
                    <el-icon>
                        <VideoPlay />
                    </el-icon>
                    开始听写
                </el-button>
            </div>
            <!--
              ⚠️ 原来的 `<el-empty v-else-if="selectedBookId && wordList.length === 0">`
                 已删除：它和上面那个 `.start-empty`（「这本词库还是空的」）
                 说的是同一件事，两个空状态叠在一起出现过。
            -->

        <!--
          练习界面
          ⚠️ 2026-10-26：词库选择已移到页面顶部常驻，
             这里的条件从 `v-else` 改成显式的 `isPracticing` ——
             否则结果面板显隐时会把练习区一起拽出来（之前踩过）。
        -->
        <div class="practice-section" v-if="isPracticing && !hasResult">
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
                        {{ audioContent === 'zh' ? '中文' : audioContent === 'en' ? '英文' : '中英' }}
                        · {{ speechRate.toFixed(1) }}× 速度
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

                    <!-- 播放内容：实时可调，且会同步改变卡片显示 -->
                    <div class="live-row live-row--mode">
                        <span class="live-row__label">播放内容</span>
                        <el-radio-group v-model="audioContent" size="small">
                            <el-radio-button value="zh">中文</el-radio-button>
                            <el-radio-button value="en">英文</el-radio-button>
                            <el-radio-button value="both">中文+英文</el-radio-button>
                        </el-radio-group>
                    </div>

                    <p class="live-settings__hint">
                        {{ audioContent === 'zh' ? '播中文释义，你写英文单词'
                            : audioContent === 'en' ? '播英文发音，你拼出单词（卡片不显示任何提示）'
                            : '每遍先中文后英文，先自己回想再听答案' }}
                        <br />
                        改完立即对下一次播放生效，不用退出练习；切模式也不会丢本轮进度。
                    </p>
                </div>
            </div>

            <!-- 当前单词卡片 -->
            <div class="word-card">
                <!--
                  ⚠️ 字段是 `translation` / `word`，不是 `chinese` / `english`（2026-10-23 修）

                  2026-10-26：显示什么由「播放内容」决定，不是由模式决定。
                  见 `showChineseOnCard` / `showPhoneticOnCard` 的注释：
                  播英文时绝不能显示中文和音标（两者都能反推出答案）。
                -->
                <template v-if="showChineseOnCard">
                    <div class="word-chinese">{{ currentWord?.translation || '' }}</div>
                    <div class="word-phonetic" v-if="showPhoneticOnCard && currentWord?.phonetic">
                        {{ currentWord.phonetic }}
                    </div>
                </template>
                <template v-else>
                    <div class="listen-question-mark">?</div>
                    <div class="listen-question-hint">{{ cardPlaceholderHint }}</div>
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
import { ref, computed, onMounted, onActivated, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
    ArrowLeft, VideoPlay, VideoPause, ArrowRight,
    CircleCheck, CircleClose, Headset, Collection,
    // 三种练习模式的卡片图标（2026-10-26）
    EditPen, Timer, InfoFilled
} from '@element-plus/icons-vue'
import { listFrontWordBooks } from '@/api/wordBooks/wordBooks'
import { listAllWords, listWords, submitPractice, getDueWords, getNewWords } from '@/api/words/words'
import { ElMessage, ElMessageBox } from 'element-plus'
import { speak, stopSpeak, speakReasonText, warmUpVoices, unlockAudio } from '@/utils/speech'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const route = useRoute()
const cacheStore = useFrontPageCacheStore()

// 状态
const isPracticing = ref(false)
const loadingWords = ref(false)
/** 词库列表刷新中（2026-10-26） */
const loadingBooks = ref(false)

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

/**
 * 播放内容（2026-10-26 新增）
 *
 *   zh   —— 只播中文释义：听「益处」写 benefit（中译英，考回忆）
 *   en   —— 只播英文发音：听 /bɪˈnefɪt/ 拼出来（真听力，考辨音 + 拼写）
 *   both —— 先中文后英文：先自己想一遍，再听英文对答案（自测）
 *
 * ⚠️ 这个设置**同时决定屏幕上显示什么**，不只是播放内容：
 *    播 `en` 时若还显示中文释义，等于把答案摆在眼前（用户听到 /bɪˈnefɪt/
 *    再照着「益处」抄，练了个寂寞）。
 *    显示规则由 `showChineseOnCard` / `showEnglishOnCard` 两个 computed 统一决定。
 */
type AudioContent = 'zh' | 'en' | 'both'
const audioContent = ref<AudioContent>('zh')

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
/**
 * 当前**正在练**的词库 id（2026-10-26）
 *
 * ⚠️ 与 `selectedBookId` 的区别：那是下拉框里的值（用户正在挑的），
 *    这是实际加载了单词、可能正在练的那本。两者在「用户点了下拉但取消了确认」
 *    这类场景下会不一致 —— 用这个值来判定「是不是真的切了库」。
 */
const currentBookId = ref(null)

// 练习设置
/*
 * ⚠️ `practiceRange` 已删除（2026-10-26）：
 *    它只有「全部单词」一个选项 —— 不是设置项，是个装饰。
 *    原设计想按「已掌握/未掌握」筛选，但 `words` 表没有掌握状态列，
 *    那个筛选永远返回空，所以选项被砍到只剩一个。
 *    留一个只有一种选择的下拉，用户会以为坏了。
 */
const playOrder = ref('random')

/**
 * 题目范围（2026-10-26 新增）
 *
 * 用户反馈：「不能只练最近加的 20 个」。
 *
 *   all    —— 整本词库
 *   recent —— 最近加入的 N 个（按 `wordId` 倒序）
 *   count  —— 只练前 N 个
 *
 * ⚠️ 「最近」用 `wordId` 倒序而不是 `createTime`：
 *    `words` 表虽然有 `create_time`，但它是数据库 `server_default=now()`
 *    写入的，批量导入时同一批词的毫秒时间戳可能完全相同 → 排序不稳定。
 *    `wordId` 是自增主键，天然就是加入顺序，且唯一、稳定。
 *
 * ⚠️ 这段正好补上之前删掉的 `practiceRange` 的位置 ——
 *    那次删它是因为只有"全部单词"一个选项等于装饰；
 *    这次是**真有多个选项可切**，才重新立起来。
 */
type PracticeScope = 'all' | 'recent' | 'count'
const practiceScope = ref<PracticeScope>('all')

/** 「只练 N 个」里的 N */
const scopeLimit = ref(20)

/** 可选题量 */
const scopeLimitOptions = [10, 20, 30, 50]

/**
 * 错词种子（2026-10-26）
 *
 * 学习统计页里点「用这些错词练一轮」时，会把错词通过 `sessionStorage`
 * 传过来（key 见统计页的 `practiceWrongWords`）。
 *
 * 这里读到后直接进入练习，**不写进词库** —— 用户只是"现在练这几个"，
 * 不是"把这几词加进词库"，两者是不同意图，混在一起会污染词库。
 */
const seedWords = ref<string[]>([])

/** URL 指定的词书 ID（等词库列表加载完再切） */
const pendingBookId = ref<number | null>(null)

/** URL 里带了 `auto=1` —— 词库和词就绪后自动开练 */
const urlAutoStart = ref(false)

/**
 * 这批种子是否来自 URL（智能体生成的链接）
 *
 * 区别对待的原因：URL 种子是**从指定词书里选出来的**，
 * 匹配不上就是真的没了，不该跨库去捞；而统计页的错词没有指定词书，
 * 天然可能散在多本里，必须跨库捞。见 startPractice 里的注释。
 */
const seedFromUrl = ref(false)

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

/* ============================================================================
 * 屏幕显示规则（2026-10-26，跟随「播放内容」）
 *
 * 核心原则：**页面上不能出现用户要靠听才能得到的信息**，否则等于给答案。
 *
 *   播放内容   卡片显示                      为什么
 *   ─────────────────────────────────────────────────────────────────────
 *   zh（中文）  中文释义 + 音标               听中文写英文，题面就是那条中文
 *   en（英文）  **什么都不显示**（只一个 ?）   听英文拼写，中文和拼写都不能给
 *   both       中文释义                      先中文自测，英文靠听
 *
 * 另外：`listen`（纯听力）模式一律不显示 —— 用户是纸笔听写，
 * 任何提示都会削弱练习。
 * ========================================================================== */

/** 卡片上是否显示中文释义 */
const showChineseOnCard = computed(() => {
    if (practiceMode.value === 'listen') return false
    return audioContent.value !== 'en'
})

/**
 * 卡片上是否显示英文拼写
 *
 * ⚠️ 永远不显示。这是听写练习 —— 英文拼写就是要写出来的答案。
 *    这里显式写成一个恒 false 的变量而不是直接不写，
 *    是为了让"为什么没有英文"这个决定在代码里是可见的，
 *    以后想改成「答完再显示」时知道该动这里。
 */
const showEnglishOnCard = computed(() => false)

/** 卡片上是否显示音标 —— 只在播中文时给（音标能反推出拼写，播英文时不能给） */
const showPhoneticOnCard = computed(() => {
    if (practiceMode.value === 'listen') return false
    return audioContent.value === 'zh'
})

/** 纯听力模式 / 播英文时的占位文案 */
const cardPlaceholderHint = computed(() => {
    if (audioContent.value === 'en') return '听发音，写出这个单词'
    return '听发音，写出这个单词'
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
            /*
             * 首次加载：自动选中一本并加载它的单词（2026-10-26）。
             *
             * ⚠️ 优先选**第一本有单词的**，而不是无条件选 `[0]`。
             *    实测踩过：列表里有一本 0 词的空词库排在前面，
             *    自动选中它之后页面显示「这本词库还是空的」——
             *    用户会以为功能坏了，其实是他自己建过一个空库。
             *    有词的优先，实在都空才退回第一本。
             */
            if (bookOptions.value.length > 0 && !selectedBookId.value) {
                /*
                 * URL 指定了词书就优先用它（2026-10-26）
                 *
                 * 智能体生成的链接带 `bookId=128` —— 用户点的就是这本，
                 * 不该再被"自动选第一本有词的"覆盖掉。
                 * 但要校验这本还在（可能已被删），不存在才回退。
                 */
                const wanted = pendingBookId.value
                    ? bookOptions.value.find(
                          (b: any) => Number(b.bookId) === Number(pendingBookId.value)
                      )
                    : null

                const firstWithWords =
                    wanted ||
                    bookOptions.value.find((b: any) => Number(b.wordCount || 0) > 0) ||
                    bookOptions.value[0]
                const first = firstWithWords.bookId
                selectedBookId.value = first
                currentBookId.value = first
                await onBookChange(first)
            }

            /*
             * 词和词书都就绪了 → 处理「URL 带 auto=1 自动开练」
             *
             * ⚠️ 必须放在 `onBookChange` 之后：那时 `wordList` 才是新词库的词，
             *    提前调 startPractice 会拿旧词库的列表去匹配种子，一个都匹配不上。
             */
            if (urlAutoStart.value && wordList.value.length > 0) {
                urlAutoStart.value = false
                // 等一帧让按钮/设置区渲染完，避免同时出现"设置区 + 练习区"
                nextTick(() => {
                    startPractice()
                })
            }
        } else {
            ElMessage.error(response.msg || '加载词库失败')
        }
    } catch (error) {
        console.error('加载词库失败:', error)
        ElMessage.error('加载词库失败')
    }
}

/**
 * 词库切换（2026-10-26 重写：融合 + 自动停止）
 * ============================================================================
 * 用户反馈：「进入听力词库选择然后才可以进行听力播放，但是进行听力播放
 * 就无法进行词库选择 / 实时更换。需要将这两个页面进行融合…
 * 并且听力播放时检测到词库被切换，做好相对应的自动停止功能。」
 *
 * 现在词库选择常驻页面顶部，练习中随时可切。切换时必须处理四件事：
 *
 *   ① **停止播放** —— 这是用户明确要求的。不然会出现
 *      「题库 A 的单词还在念，界面已经变成题库 B」的错位，
 *      用户听到的和看到的对不上，完全没法用。
 *   ② **停掉自动下一题的倒计时** —— `autoNextTimer` 是个 setTimeout，
 *      不停会在切库后突然跳题，跳的还是新词库的第 1 题。
 *   ③ **处理已有作答进度** —— 练到第 8 题切库，那 8 题的结果还有意义吗？
 *      没有（它们属于旧词库）。所以要有确认提示，且切完清空。
 *   ④ **不重复重载** —— 如果选的就是当前这本（比如手动重选一次），
 *      不该无谓地清空进度。
 */
const onBookChange = async (bookId) => {
    if (!bookId) return

    // ④ 选的是同一本：什么都不做（避免误清进度）
    if (isPracticing.value && bookId === currentBookId.value) {
        return
    }

    /*
     * ③ 练习中切库：先确认
     *
     * 判据是「有没有已经作答的题」而不是「是否在练习」——
     * 刚点开始、还没答一题就切库，不该弹确认框烦人。
     */
    if (isPracticing.value && practiceResults.value.length > 0) {
        try {
            await ElMessageBox.confirm(
                `本轮已经做了 ${practiceResults.value.length} 题，切换词库会结束当前练习并清空进度。确定切换吗？`,
                '切换词库',
                { confirmButtonText: '切换', cancelButtonText: '继续练这本', type: 'warning' }
            )
        } catch {
            // 用户取消：把下拉框还原成当前正在练的那本
            selectedBookId.value = currentBookId.value
            return
        }
    }

    /*
     * ①② 停止一切正在进行的播放/计时。
     *
     * ⚠️ 顺序很重要：先 `stopSpeaking()`（它会把语音队列 cancel 掉），
     *    再清定时器。反过来会出现「定时器已清，但语音还在念」的残留。
     */
    if (isPracticing.value) {
        stopSpeaking()
        clearAutoNextTimer()
        // 退出练习态（练习区会随之隐藏）
        isPracticing.value = false
        // 清空本轮，避免旧词库的题目残留到新词库
        practiceWords.value = []
        practiceResults.value = []
        currentIndex.value = 0
        userAnswer.value = ''
        showFeedback.value = false
        isCorrect.value = false
        isWrong.value = false
        hasResult.value = false
        resultWrongWords.value = []
        resultSummary.value = { total: 0, correct: 0, accuracy: 0 }
        practiceSubmitted.value = false
    }

    // 记住书名：提交练习记录时要带上，列表里才看得出练的哪本
    currentBookName.value =
        String(bookOptions.value.find((b) => b.bookId === bookId)?.bookName || '')
    currentBookId.value = bookId

    loadingWords.value = true
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
            /*
             * 用实际加载到的单词数**修正**下拉里的计数（2026-10-26）。
             *
             * `word_books.word_count` 是冗余字段，靠 `_recount_book()` 维护；
             * 只要有别的路径忘了重算（或历史数据对不上），
             * 下拉里就会显示「0 词」而实际有 17 个 —— 用户看到自相矛盾的数字，
             * 会怀疑到底哪个是真的。
             *
             * 这里是唯一同时拿到「词书名 + 真实单词」的地方，
             * 顺手把列表里那一本的计数改对，比再发一次请求划算。
             */
            const idx = bookOptions.value.findIndex((b: any) => b.bookId === bookId)
            if (idx >= 0) {
                bookOptions.value[idx] = {
                    ...bookOptions.value[idx],
                    wordCount: wordList.value.length
                }
            }
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

/**
 * 刷新词库列表（2026-10-26）
 *
 * 场景：用户在另一个标签页/别的页面新建了词库，回到这里下拉里看不到 ——
 * 只能刷新整个页面。这个按钮解决的就是这个。
 *
 * ⚠️ 刷新后要保持当前选中的词库（如果它还在），而不是重置成第一本 ——
 *    否则练习中点一下刷新，词库就被悄悄换掉了。
 */
const refreshBooks = async () => {
    loadingBooks.value = true
    try {
        const res = await listFrontWordBooks()
        if (res.code !== 200) {
            ElMessage.error(res.msg || '刷新词库失败')
            return
        }
        const rows = res.rows || []
        const keepId = selectedBookId.value
        bookOptions.value = rows

        const stillThere = rows.some((b) => b.bookId === keepId)
        if (!stillThere && rows.length > 0) {
            // 原来选的那本没了（被删了）：退到第一本，并同步加载它的单词
            selectedBookId.value = rows[0].bookId
            await onBookChange(rows[0].bookId)
            ElMessage.info('原来的词库已不存在，已切到第一本')
        } else {
            ElMessage.success(`已刷新，共 ${rows.length} 本词库`)
        }
    } catch (e: any) {
        console.error('刷新词库失败:', e)
        ElMessage.error('刷新词库失败')
    } finally {
        loadingBooks.value = false
    }
}

/**
 * 跨词库按单词捞词（2026-10-26）
 *
 * 统计页的错词来自用户练过的**所有**词库，不一定是当前选中的这本。
 * 后端 `/words/words/list` 支持 `word` 精确匹配、且不传 `bookId` 时
 * 会搜「我的书 + 系统预置书」范围 —— 正好是用户能访问的全部词库。
 *
 * 每个词单独发一次请求（错词最多 10 个，并发 10 个请求在本机后端
 * 也就几十毫秒）。用 `Promise.allSettled` 而不是 `Promise.all`：
 * 某一个词查失败不该让整轮练习失败。
 */
async function fetchWordsAcrossBooks(words: string[]): Promise<any[]> {
    const results = await Promise.allSettled(
        words.map((w) =>
            listWords({ word: w, pageNum: 1, pageSize: 5 }).then((res: any) => {
                const rows = res?.rows || res?.data?.rows || []
                // 后端 `word` 是模糊匹配（LIKE），这里再按词形精确过滤一次
                const target = String(w).toLowerCase()
                return rows.find(
                    (r: any) => String(r.word || '').toLowerCase() === target
                )
            })
        )
    )

    const out: any[] = []
    for (const r of results) {
        if (r.status === 'fulfilled' && r.value) out.push(r.value)
    }
    return out
}

// 开始练习
const startPractice = async () => {
    // ⚠️ `words` 表没有 isMastered 列，原先按「未掌握」筛选永远为空。
    //    现在不做这个筛选：练的就是这本词库里的全部单词。
    let words = [...wordList.value]

    // ------------------------------------------------------------------
    // 错词种子优先（2026-10-26）
    // ------------------------------------------------------------------
    // 从统计页「用这些错词练一轮」过来时，只练这几个词。
    //
    // ⚠️ 错词天然会**跨词库** —— 统计页统计的是这个人所有练习，
    //    错词可能来自"四级核心词""考研高频词"好几本。
    //    如果只在「当前选中的词库」里匹配，很容易出现
    //    "3 个错词只练到 1 个"（实测就是这个问题）。
    //
    // 所以分两步：
    //   ① 先在当前词库里按词形找（命中最多，且不用发请求）；
    //   ② 剩下的按单词去后端跨词库查回来。
    // 两步都找不到的才放弃，并明确告诉用户少了哪几个。
    const seed = seedWords.value
    // 这批种子是智能体通过 URL 传来的吗（决定要不要跨词库补齐）
    const fromUrl = seedFromUrl.value
    seedFromUrl.value = false

    if (seed.length) {
        // 一次性消费掉
        seedWords.value = []

        const byWord = new Map<string, any>()
        for (const w of wordList.value) {
            const key = String((w as any).word || '').toLowerCase()
            if (key && !byWord.has(key)) byWord.set(key, w)
        }

        const matched: any[] = []
        const missing: string[] = []
        const seen = new Set<string>()

        for (const s of seed) {
            const key = String(s).toLowerCase()
            if (seen.has(key)) continue
            seen.add(key)
            const hit = byWord.get(key)
            if (hit) matched.push(hit)
            else missing.push(s)
        }

        // ② 跨词库补齐
        //
        // ⚠️ 只在**不是** URL 种子时做（2026-10-26）。
        //    智能体生成的链接带 bookId，那些词就是从这本词书里选出来的；
        //    跨库补会把别的词书的同名词拉进来，导致"练的不是我选的那本"。
        //    统计页的错词没有指定词书，才需要跨库捞。
        if (missing.length && !fromUrl) {
            const fetched = await fetchWordsAcrossBooks(missing)
            for (const w of fetched) {
                const key = String((w as any).word || '').toLowerCase()
                if (key && !seen.has('f:' + key)) {
                    seen.add('f:' + key)
                    matched.push(w)
                }
            }
        }

        if (matched.length) {
            words = [...matched]
            if (playOrder.value === 'random') words = shuffleArray(words)
            /*
             * ⚠️ 这里**不要**再弹「本轮只练 N 个错词」（2026-10-26 删除）
             *
             * 用户反馈：这条提示会连着弹好几次，而且每弹一次都盖住上面的词库选择区。
             * 根因不在这一行，在「种子被重复消费」——见 URL 分支里 `urlSeedSignature`
             * 的说明。但即使根因修好，这条提示也是纯冗余：
             * 页面上「总单词 20 / 1 / 20」已经把轮次信息写在明面上了。
             *
             * 只保留「有词被跳过」这一种**异常**提示：那意味着用户选的东西少了，
             * 属于必须告知的信息，不能静默。
             */
            if (matched.length < seed.length) {
                ElMessage.warning(
                    `本轮练 ${matched.length} 个错词；另外 ${seed.length - matched.length} 个已从词库里删掉了，跳过`
                )
            }
            // 种子已接管本轮题目，直接进入练习，不再走下面的范围筛选
            return beginPractice(words)
        }

        ElMessage.warning('这些错词在当前词库里都找不到了，已改为练整本')
    }

    if (words.length === 0) {
        ElMessage.warning('没有可练习的单词')
        return
    }

    // ------------------------------------------------------------------
    // 题目范围（2026-10-26）
    // ------------------------------------------------------------------
    // 顺序说明：**先按范围取子集，再打乱**。
    // 反了的话「最近 20 个」会变成"随机抽 20 个"，和新加的词一点关系都没有。
    if (practiceScope.value === 'recent') {
        const n = Math.min(scopeLimit.value, words.length)
        // 按 wordId 倒序取最近的 n 个
        words = [...words]
            .sort((a: any, b: any) => (b.wordId ?? 0) - (a.wordId ?? 0))
            .slice(0, n)
    } else if (practiceScope.value === 'count') {
        words = words.slice(0, Math.min(scopeLimit.value, words.length))
    }

    // 随机打乱（在范围筛选**之后**）
    if (playOrder.value === 'random') {
        words = shuffleArray(words)
    }

    // 范围比实际词数大时提示一下，避免用户以为没生效
    if (practiceScope.value !== 'all' && scopeLimit.value > wordList.value.length) {
        ElMessage.info(`这本词库只有 ${wordList.value.length} 个单词，本轮全练`)
    }

    beginPractice(words)
}

/**
 * 真正进入练习态（2026-10-26 抽出）
 *
 * 原来这段代码直接写在 `startPractice` 末尾，两处入口（正常开始 / 错词种子）
 * 都要用，抽出来避免复制一份 —— 复制出来的第二份最容易和第一份走偏。
 */
function beginPractice(words: any[]) {
    practiceWords.value = words
    currentIndex.value = 0
    isPracticing.value = true
    // 允许下一批种子进来（详见 resetSeedFlag 的注释）
    resetSeedFlag()
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
 * 播放当前单词 N 遍
 *
 * 2026-10-26 抽出来给三种模式共用：
 *   · listen    —— 播完就停，**不自动跳题**（用户可能正在纸上写）
 *   · input     —— 手动点播放，播一遍就行
 *   · dictation —— 播 N 遍后启动自动下一题倒计时
 *
 * `autoNext` 参数决定播完是否启动倒计时 —— 这是三个模式唯一的行为差异，
 * 所以不再写三份播放循环。
 *
 * 播放内容由 `audioContent`（zh / en / both）决定，见下方 segments 的说明。
 */
const playRound = async ({ autoNext = false } = {}) => {
    if (!currentWord.value) return

    clearAutoNextTimer()
    isWaitingAutoNext.value = false

    // input 模式只播一遍（用户是看着题面打字，重复播放没意义）
    const times = practiceMode.value === 'input' ? 1 : repeatCount.value
    /*
     * ⚠️ 本轮遍数在**循环开始前**就固定（`times`），而不是每轮重新读 `repeatCount`。
     *    否则用户在播放中途把「2 遍」改成「3 遍」，这一轮会突然多播一遍 ——
     *    听感上是"话没说完又重复了一次"。
     *    改动从**下一次播放**起生效，实时设置面板底部的提示也这么写。
     */

    isPlaying.value = true
    currentPlayCount.value = 0

    /*
     * 播放内容（2026-10-26 新增三选一）
     * ----------------------------------------------------------------
     *   zh   —— 只播中文释义：听「益处」写 benefit（中译英，考回忆）
     *   en   —— 只播英文单词：听 /bɪˈnefɪt/ 拼出来（真听力，考辨音+拼写）
     *   both —— 先中文后英文：先自己想，再听英文对答案（自测）
     *
     * ⚠️ 一段"每一遍要念什么"的序列，而不是在循环里写 if/else ——
     *    `both` 需要一遍里念两段，用序列表达最直接；
     *    遍与遍之间、段与段之间都用同一个 `playInterval` 间隔，
     *    用户调一个值就能控制所有停顿，不用记两套参数。
     */
    const segments: Array<{ text: string; lang: string }> = []
    const content = audioContent.value
    if (content === 'zh' || content === 'both') {
        const zh = String(currentWord.value.translation || '').trim()
        if (zh) segments.push({ text: zh, lang: 'zh-CN' })
    }
    if (content === 'en' || content === 'both') {
        const en = String(currentWord.value.word || '').trim()
        if (en) segments.push({ text: en, lang: 'en-US' })
    }

    if (!segments.length) {
        ElMessage.warning(
            content === 'zh' ? '该单词没有中文释义，换个播放内容试试' : '该单词没有英文拼写'
        )
        return
    }

    try {
        for (let i = 0; i < times; i++) {
            currentPlayCount.value = i + 1

            for (let s = 0; s < segments.length; s++) {
                const seg = segments[s]
                const res = await speakWithLang(seg.text, seg.lang)
                if (res && res.ok === false) {
                    if (res.reason !== 'interrupted' && res.reason !== 'canceled') {
                        ElMessage.warning(speakReasonText(res.reason, seg.lang))
                    }
                    // 播放失败不自动跳题：否则用户会看着题目一题题跳过却不知道为什么
                    return
                }

                // 段与段、遍与遍之间都停 playInterval
                const isLastSegmentOfLastRound = i === times - 1 && s === segments.length - 1
                if (!isLastSegmentOfLastRound) {
                    await sleep(playInterval.value * 1000)
                }
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
 * 语音播放（Promise 版本，支持任意语言）
 *
 * 走统一的 `speak()`：内部已处理 cancel→speak 的间隔、语音包选择、
 * 错误码透出和看门狗超时。返回 `{ok, reason}`，不再无声吞掉失败。
 *
 * ⚠️ 2026-10-26：`rate` 原来是硬编码的 `0.9`，现在读用户设置的
 * `speechRate`（0.5~1.5）。语速是听力练习最常被需要的参数 ——
 * 太快听不懂、太慢没挑战，写死一个值等于替用户做了决定。
 *
 * ⚠️ 同日扩展：原来只播中文（`speakChinesePromise`），现在支持 `en-US`。
 *    英文单词由 `speak()` 自动挑英文语音（`pickVoice` 按 lang 匹配），
 *    与中文走同一条链路，包括服务端 `edge-tts` 兜底。
 */
const speakWithLang = (text: string, lang: string) => {
    return speak(text, { lang, rate: speechRate.value })
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

    /*
     * ⚠️ 顺序不能反（2026-10-26 修）
     * ------------------------------------------------------------------
     * 先消费种子（会设置 pendingBookId），再加载词库列表 ——
     * 因为 `loadBookOptions` 内部要用 `pendingBookId` 决定选哪本书。
     *
     * 原来顺序是反的：loadBookOptions 先跑（pendingBookId 还是 null），
     * 于是永远选"第一本有词的"，URL 里的 bookId 被完全忽略。
     * 症状：从"四级核心词"（12 词）跳过来，却练的是"四级高频词汇"（20 词）。
     */
    /*
     * 串行执行：等种子消费完（含按 scope 请求后端取词）再加载词库列表。
     *
     * 并行不行 —— consumeSeedWords 内部要 await 一次接口，
     * 而 loadBookOptions 依赖它设置好的 pendingBookId。
     */
    void consumeSeedWords().then(() => loadBookOptions())

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

    startSeedWatcher()
})

/*
 * 错词种子监听（2026-10-26）
 * ---------------------------------------------------------------------------
 * 为什么不能只靠 `onMounted` 读：
 *
 * 本页在路由里带 `keepAlive: true`，从统计页跳回来时组件**已被缓存**，
 * 既不会重新 `mount`，也不会触发 `onActivated`（实测两者都不行 ——
 * 同一个路由第二次进入时 Vue 直接复用旧实例）。
 * 但 `sessionStorage` 的写入是立刻生效的。
 *
 * 所以只能轮询：每 400ms 看一眼有没有种子，有就读走并删掉。
 * 400ms 对用户无感，也不会带来可测的开销（同步内存操作）。
 * 这套方案与 `views/front/agent/chat.vue` 的 `consumeSeedQuestion` 一致。
 */
let seedTimer: number | null = null

/**
 * 已消费标记
 *
 * ⚠️ 不能只靠 `sessionStorage.removeItem` 去重 —— 实测出现过提示弹两次：
 *    轮询的第一次读到了值并删除，但 `startSeedWatcher()` 里那次同步调用
 *    与 `setInterval` 的首个 tick 之间没有顺序保证，在极短窗口内
 *    两次读到的都是"删除前"的值（浏览器里 removeItem 与 getItem
 *    之间若夹了渲染帧，这块内存视图可能还没刷新）。
 *    加个内存标记最省事，且语义正确：一个种子只消费一次。
 */
let seedConsumed = false

/**
 * 已消费过的 URL 种子「内容签名」（2026-10-26 新增，修重复消费/重复提示）
 * ============================================================================
 *
 * **为什么 `seedConsumed` 不够**
 *
 * `consumeSeedWords()` 有四个入口：onMounted(1811)、`startSeedWatcher()` 的同步调用
 * (1998)、400ms 轮询 (2001)、以及 URL watch (2055)。而 `beginPractice()` 会在
 * 1257 行调 `resetSeedFlag()` 把 `seedConsumed` **复位成 false** —— 它的本意是
 * 「允许下一批种子进来」。
 *
 * 于是就有这条时间线：
 *
 *   t0  onMounted → consumeSeedWords() 读到 URL 上的 auto/words，设 seedConsumed=true
 *   t1  router.replace 清 URL（**异步**，且 keep-alive 复用同路由时可能不生效）
 *   t2  开练 → beginPractice() → resetSeedFlag() → seedConsumed = false
 *   t3  400ms 轮询再次触发 → seedConsumed 是 false → 重新进入
 *   t4  route.query 若还留着旧值 → **用同一批种子再消费、再弹一次提示**
 *
 * 这就是用户说的「老是弹好多次」——不是提示写错了，是**同一批种子被反复当成新的**。
 *
 * **修法**：不再依赖会被复位的布尔量，改记「这批种子的内容长什么样」。
 * 同一份 `auto/words/bookId/scope` 组合只消费一次；URL 真的换成另一批词
 * （内容签名变了）时才放行。这样即使 `seedConsumed` 被复位、轮询再多跑几轮，
 * 也不会重复消费。
 */
let urlSeedSignature: string | null = null

/**
 * 由当前 URL 种子参数算一个「内容签名」
 *
 * 只纳入**决定种子内容**的字段：`words` / `scope` / `bookId` / `mode`。
 * `auto` 只是"是否自动开练"的开关，不参与签名（同一批词 auto 与否是同一批词）。
 */
function buildUrlSeedSignature(q: Record<string, any>): string {
    return [
        String(q.words || ''),
        String(q.scope || ''),
        String(q.bookId || ''),
        String(q.mode || '')
    ].join('|')
}

/**
 * 消费「预置题目」—— 两种来源
 * ============================================================================
 *
 * **① URL 参数（2026-10-26 新增）**
 *    智能体 `english_practice(action=start)` 返回的 jumpUrl 长这样：
 *
 *      /front/english/listening?auto=1&bookId=128&mode=dictation
 *                              &scope=due&words=abandon,benefit,campaign
 *
 *    `auto=1` 表示"进来就直接开练"，用户不用再点一次「开始听写」。
 *    这条路径是**跨页面跳转**，所以必须走 URL —— sessionStorage 在
 *    router.push 时也能用，但 URL 可分享、可刷新、可回退，语义更对。
 *
 * **② sessionStorage（原有的错词重练）**
 *    统计页点「用这些错词练一轮」时写入，见 statistics/index.vue。
 *
 * 两者统一处理：都转成 `seedWords` + 可选的 `bookId/mode`，
 * 然后交给 `startPractice` 走同一套选词逻辑。
 */
async function consumeSeedWords() {
    if (seedConsumed) return

    // ---------- ① URL 参数 ----------
    const q = route.query || {}
    if (q.auto === '1' || q.words) {
        /*
         * 同一批种子只消费一次（2026-10-26 修重复消费）
         *
         * `seedConsumed` 会被 `beginPractice() → resetSeedFlag()` 复位，
         * 而 400ms 轮询会一直跑 —— 光靠它挡不住"同一批种子被反复消费"。
         * 这里用内容签名兜住：URL 还是那批词就直接返回，绝不二次消费。
         * （背景与完整时间线见 `urlSeedSignature` 的注释。）
         */
        const signature = buildUrlSeedSignature(q)
        if (urlSeedSignature === signature) return
        urlSeedSignature = signature

        seedConsumed = true

        const rawWords = String(q.words || '').trim()
        const urlScope = String(q.scope || '')
        /*
         * ⚠️ `bid` 必须在这里定义（2026-10-26 修 TDZ）
         *
         * 原先它定义在下面「设置 pendingBookId」那一段，
         * 但上面的 scope 分支（`getDueWords({ bookId: bid })`）先用到了它 ——
         * `const` 有暂时性死区，于是抛 ReferenceError，
         * 被外层 try/catch 静默吞掉 → list 一直是空 → 退化成"练整本"。
         *
         * 症状：点「今天该复习 5 个」结果练了 12 个，且没有任何报错提示。
         */
        const bid = Number(q.bookId || 0)
        let list = rawWords
            ? rawWords.split(',').map((x) => decodeURIComponent(x).trim()).filter(Boolean)
            : []

        /*
         * 没有明确词表时，按 scope 向后端要（2026-10-26）
         * ---------------------------------------------------------------
         * 词库页的「开始听写」只传 `scope=due`（今天该复习的），
         * 不带 words —— 因为它不知道到期的是哪几个，那是后端的判断。
         *
         * 之前只认 `words`，于是这类跳转退化成"练整本"，
         * 用户点「今天该复习 5 个」结果练了 12 个，预期完全不对。
         */
        if (!list.length && urlScope) {
            try {
                if (urlScope === 'due') {
                    const res: any = await getDueWords({
                        bookId: bid || undefined,
                        limit: 100
                    })
                    const data = res?.data ?? res
                    list = (data?.items || []).map((it: any) => String(it.word || '')).filter(Boolean)
                    if (!list.length) {
                        ElMessage.info('今天没有到期该复习的词，改为练整本')
                    }
                } else if (urlScope === 'new') {
                    const res: any = await getNewWords({
                        bookId: bid || 0,
                        limit: 100
                    })
                    const data = res?.data ?? res
                    list = (data?.items || []).map((it: any) => String(it.word || '')).filter(Boolean)
                    if (!list.length) {
                        ElMessage.success('这本词书的词都学过了，换成复习吧')
                    }
                }
            } catch (e) {
                console.warn('按 scope 取词失败:', e)
            }
        }

        // 模式：URL 指定了就覆盖设置
        const m = String(q.mode || '')
        if (m === 'dictation' || m === 'input' || m === 'listen') {
            practiceMode.value = m as any
        }
        // 词书：URL 指定了就切过去（等词库列表加载完再切，见 pendingBookId）
        if (bid) pendingBookId.value = bid

        if (list.length) {
            seedWords.value = list
            seedFromUrl.value = true
            /*
             * ⚠️ 这里**不再弹**「已为你准备好 N 个词的练习」（2026-10-26 删除）
             *
             * 用户反馈：这条提示会连着弹 2~3 次，专门盖住词库选择下拉框，
             * 而且"很难复现/很难修"。
             *
             * 根因不在这一行：`beginPractice()` 会把 `seedConsumed` 复位，
             * 而 400ms 轮询与 watch 都可能再次进入本函数；只要 `router.replace`
             * 没能及时把 URL 上的 `auto/words` 清掉，就会**用同一批种子再弹一次**。
             * 真正的修复见下面 `urlSeedSignature` —— 用"内容签名"去重，
             * 不再依赖 `seedConsumed` 这个会被复位的布尔量。
             *
             * 提示本身也是冗余的：种子进到页面后，词库下拉框与「总单词 N」
             * 已经把这个事实显示出来了，用户不需要再被一个浮层告知一次。
             */
        }

        /*
         * 清掉 URL 上的这些参数
         *
         * 为什么要清：用户练完刷新页面时，如果再读一次 `auto=1`，
         * 会被强行再开一轮 —— 而用户刷新可能只是想看看结果面板。
         * 用 replace 不留历史记录。
         */
        const rest = { ...q }
        delete rest.auto
        delete rest.words
        delete rest.mode
        delete rest.scope
        delete rest.bookId
        router.replace({ path: route.path, query: rest })

        urlAutoStart.value = q.auto === '1'
        return
    }

    // ---------- ② sessionStorage（错词重练） ----------
    try {
        const raw = sessionStorage.getItem('practiceSeedWords')
        if (!raw) return
        seedConsumed = true
        // 立刻删掉 —— 否则用户下次正常进来还会被这组错词拦住
        sessionStorage.removeItem('practiceSeedWords')
        const parsed = JSON.parse(raw)
        if (!Array.isArray(parsed)) return
        const list = parsed.map((s) => String(s)).filter(Boolean)
        if (!list.length) return

        seedWords.value = list
        ElMessage.success(`已带上 ${list.length} 个错词，点「开始听写」即可`)
    } catch {
        /* 解析失败就当没有种子，不影响正常使用 */
    }
}

function startSeedWatcher() {
    /*
     * 注意：`consumeSeedWords` 是 async（要按 scope 请求后端取词），
     * 但 setInterval 的回调**不能 await**，也没必要 ——
     * 它内部靠 `seedConsumed` 标记防重入，异步期间再次进入会被挡掉。
     */
    void consumeSeedWords()
    if (seedTimer !== null) return
    seedTimer = window.setInterval(() => {
        void consumeSeedWords()
    }, 400)
}

/**
 * 本页被 keep-alive 复用时，重置"一次性状态"（2026-10-26）
 * ============================================================================
 * 实测踩到的坑：连着用不同参数打开本页三次
 *
 *     ?scope=due   → 1 / 2
 *     ?scope=new   → 1 / 2   ← 应该变成 7 个新词，但没变
 *     ?words=a,b   → 1 / 2   ← 应该只有 2 个，也没变
 *
 * 原因是本页带 `keepAlive: true`，第二次进入时组件被**复用**：
 *   · `seedConsumed` 还是上一次的 true → `consumeSeedWords` 直接 return；
 *   · `isPracticing` 还是 true → 页面停在上次的练习态。
 *
 * 所以每次被激活且 URL 里带了 `auto=1` 时，把状态清干净再重新消费。
 */
function resetForNewUrlRun() {
    seedConsumed = false
    /*
     * 同时清掉内容签名（2026-10-26）
     *
     * `resetForNewUrlRun` 是**真的换了一批词**（watch 到 URL 变了）才会走到，
     * 所以必须放行；但若不清签名，`consumeSeedWords()` 里的签名比对会把
     * 「新的一批」误判成「老的重复」，于是第二次跳转过来什么都不练。
     */
    urlSeedSignature = null
    seedWords.value = []
    seedFromUrl.value = false
    pendingBookId.value = null
    urlAutoStart.value = false
    // 退出上一次的练习态，回到"选词库 + 设置"的起点
    isPracticing.value = false
    hasResult.value = false
    practiceResults.value = []
    practiceWords.value = []
    currentIndex.value = 0
    stopSpeaking()
    clearAutoNextTimer()
}

/*
 * 监听 URL 里的 `auto` / `words`（2026-10-26）
 * ============================================================================
 * 为什么不用 `onActivated`：实测在本页**不触发**。
 *
 * 本页路由带 `keepAlive: true`，但连续用不同参数导航到同一路由时，
 * Vue Router 认为是"同一条路由"，既不重新 mount，也不一定触发 activated。
 * 而 `route.query` 的变化一定能被 watch 捕获 —— 这是唯一可靠的入口。
 *
 * 这也是本项目第四次在 keep-alive 上栽跟头（前三次：智能体预填问题、
 * 听写页错词种子、统计页 tab 参数）。规律已经很清楚：
 * **凡是要"根据外部传参改变已缓存页面的状态"，都不能只依赖生命周期钩子。**
 */
watch(
    () => [route.query.auto, route.query.words, route.query.bookId, route.query.scope],
    (nv) => {
        const [auto, words] = nv as any[]
        if (auto !== '1' && !words) return
        resetForNewUrlRun()
        void consumeSeedWords().then(() => loadBookOptions())
    }
)

/*
 * 允许"第二次带种子进来"
 *
 * 用户可能：统计页点错词练一轮 → 退出 → 又点了另一个错词。这时组件没重建，
 * `seedConsumed` 还是 true，会拒绝消费。所以每次开始练习（beginPractice）
 * 之后复位，让下一批种子能进来。
 */
function resetSeedFlag() {
    seedConsumed = false
}

// 监听页面离开
watch(() => isPracticing.value, (val) => {
    if (!val) {
        stopSpeaking()
    }
})

onBeforeUnmount(() => {
    if (seedTimer !== null) {
        clearInterval(seedTimer)
        seedTimer = null
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

    /*
     * 词库选择（2026-10-26 融合改造）
     * -----------------------------------------------------------------
     * 改前：`flex: 1` + `justify-content: center` + `min-height: calc(100vh-220px)`
     *       —— 它被设计成"占满整页"的独占状态，因为当时它和练习界面互斥。
     * 改后：它是常驻顶部的选择条，练习中也一直在，所以不能再撑满高度，
     *       否则练习区会被挤到屏幕外。
     */
    .book-select-section {
        flex: none;
        padding: 0;
        max-width: 560px;
        margin: 0 auto 14px;
        width: 100%;

        .select-label {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: .02em;
            color: #6b7280;
            margin-bottom: 8px;
        }

        /* 练习中的提示徽标：告诉用户这里还能切 */
        .select-label__badge {
            padding: 1px 7px;
            border-radius: 20px;
            background: #eff6ff;
            color: #2563eb;
            font-size: 11px;
            font-weight: 500;
            letter-spacing: 0;
        }

        .book-select-row {
            display: flex;
            align-items: center;
            gap: 8px;

            .book-select-el {
                flex: 1;
                min-width: 0;
            }

            .book-refresh-btn {
                flex: none;
            }
        }

        .book-option {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;

            .book-option__count {
                font-size: 12px;
                color: #9ca3af;
            }
        }

        /*
         * 空状态卡片（2026-10-26）
         * 改前未选词库时页面只有一个孤立下拉框，下方空无一物。
         *
         * ⚠️ 2026-10-26 二次调整：词库选择区改成顶部常驻条后，
         *    空状态已经**不再**嵌在它里面（它是独立的一段），
         *    所以样式也从 `.book-select-section` 里提出来，见下方顶级 `.start-empty`。
         */
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

    }

    /*
     * ========================================================================
     * 以下三块（practice-settings / start-empty / start-section）
     * 原来是嵌在 `.book-select-section` 里的 —— **这是错的**。
     * ========================================================================
     *
     * 2026-10-26 融合改造把词库选择区限制成 560px 的顶部条，
     * 模板里这三个块已经移到了它的**兄弟位置**，
     * 但样式还留在 `.book-select-section { ... }` 的括号里，
     * 于是被编译成 `.book-select-section .practice-settings` 之类 ——
     * 选择器根本匹配不到（它们是兄弟，不是后代）。
     *
     * 后果（截图实测）：设置区完全没有样式约束，
     * 直接按内容撑满整个视口宽度，左边被裁切、右边溢出、中间一片空白。
     *
     * 现在把它们提到 `.listening-page` 的直接子级，与 DOM 结构对齐。
     * ⚠️ 以后往模板里加块、或调整层级，务必同步检查这里的嵌套深度。
     */

    /*
     * 练习设置（2026-10-26：三模式 + 可调参数）
     * 与词库选择条同宽（560px）并居中，页面左右边缘对齐。
     */
    .practice-settings {
        width: 100%;
        max-width: 560px;
        margin: 0 auto;
        padding: 18px 20px;
        background: #fff;
        border-radius: 14px;
        border: 1px solid #e5e7eb;

        /*
         * 模式选择卡片
         * 用卡片而不是 radio：三个模式差别大、各需一句说明。
         */
        .mode-picker {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-bottom: 18px;
        }

        .mode-card {
            display: flex;
            align-items: center;
            gap: 11px;
            padding: 10px 12px;
            border: 1.5px solid #e5e7eb;
            border-radius: 11px;
            cursor: pointer;
            transition: border-color .18s, background .18s;

            &:hover {
                border-color: #c7d2fe;
                background: #f8faff;
            }

            &.is-active {
                border-color: #3b82f6;
                background: #eff6ff;
            }

            .mode-card__icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 30px;
                height: 30px;
                flex: none;
                border-radius: 8px;
                background: #f1f5f9;
                color: #64748b;
            }

            &.is-active .mode-card__icon {
                background: #dbeafe;
                color: #2563eb;
            }

            .mode-card__title {
                font-size: 13px;
                font-weight: 600;
                color: #111827;
            }

            .mode-card__desc {
                margin-top: 1px;
                font-size: 11.5px;
                line-height: 1.45;
                color: #9ca3af;
            }
        }

        /* 两列网格：左标签 88px、右控件自适应 */
        .setting-item {
            display: grid;
            grid-template-columns: 88px minmax(0, 1fr);
            align-items: center;
            gap: 14px;
            margin-bottom: 14px;

            &:last-child {
                margin-bottom: 0;
            }

            .setting-label {
                font-size: 13px;
                font-weight: 500;
                color: #374151;
                white-space: nowrap;
            }

            :deep(.el-radio) {
                margin-right: 16px;

                &:last-child {
                    margin-right: 0;
                }
            }

            /*
             * 题目范围行：单选框 + 数量下拉横向排列
             *
             * ⚠️ 这段必须在 `.setting-item` 这一级，不能嵌进 `.setting-item--slider`。
             *    「题目范围」用的是普通 `.setting-item`（不带 `--slider`，
             *    因为它不需要滑块那种顶部对齐）。第一次写在了 `--slider` 里面，
             *    编译成 `.setting-item--slider .scope-row` → 匹配不到 →
             *    `.scope-limit` 的 `width: 86px` 失效，下拉撑满整行 416px。
             *    这是本项目第四次踩「嵌套层级与 DOM 不符」的坑。
             */
            .scope-row {
                display: flex;
                align-items: center;
                gap: 10px;
                flex-wrap: wrap;
                min-width: 0;

                .scope-limit {
                    width: 86px;
                    flex: none;
                }
            }

            /* 带说明的设置项要能竖排（题目范围 / 播放内容都用） */
            .setting-control {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;

                &--stack {
                    gap: 6px;
                }
            }

            .setting-hint {
                font-size: 11.5px;
                line-height: 1.5;
                color: #9ca3af;
            }
        }

        /* 滑块行：顶部对齐，滑块占满右列 */
        .setting-item--slider {
            align-items: start;

            .setting-label {
                padding-top: 2px;
            }

            :deep(.el-slider) {
                padding: 0 6px;
            }
        }

        .mode-note {
            display: flex;
            align-items: flex-start;
            gap: 6px;
            margin-top: 12px;
            padding: 9px 11px;
            border-radius: 9px;
            background: #f8fafc;
            font-size: 11.5px;
            line-height: 1.55;
            color: #64748b;

            .el-icon {
                margin-top: 2px;
                flex: none;
                color: #94a3b8;
            }
        }
    }

    /* 空状态卡片 */
    .start-empty {
        width: 100%;
        max-width: 560px;
        margin: 0 auto;
        padding: 40px 24px;
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 6px;
        background: #fff;
        border: 1px dashed #e2e8f0;
        border-radius: 14px;

        .start-empty__icon {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 52px;
            height: 52px;
            margin-bottom: 6px;
            border-radius: 13px;
            background: #f1f5f9;
            color: #94a3b8;
        }

        .start-empty__title {
            margin: 0;
            font-size: 14.5px;
            font-weight: 600;
            color: #374151;
        }

        .start-empty__desc {
            max-width: 340px;
            font-size: 12.5px;
            line-height: 1.7;
            color: #9ca3af;
        }

        .start-empty__btn {
            margin-top: 8px;
        }
    }

    /* 开始按钮 */
    .start-section {
        width: 100%;
        max-width: 560px;
        margin: 16px auto 0;
        text-align: center;

        .el-button {
            width: 200px;
            height: 46px;
            font-size: 15px;
            border-radius: 10px;
        }
    }

    .practice-section {
        /*
         * 2026-10-26：`flex: 1` 改为 `flex: none`。
         *
         * 词库选择区从"独占整页"改成顶部常驻条后，练习区不再是页面上
         * 唯一的 flex 子项；继续 `flex: 1` 会把它拉到剩余高度，
         * 但它的内容（进度条 + 实时设置 + 题卡）是固定高度的，
         * 拉长只会让底部多出一块无意义的空白。
         */
        flex: none;
        display: flex;
        flex-direction: column;
        padding: 0 20px;
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
