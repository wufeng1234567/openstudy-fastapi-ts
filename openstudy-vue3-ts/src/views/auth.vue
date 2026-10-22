<template>
  <div class="auth-container">
    <div class="auth-wrapper" :class="{ 'is-register-mode': !isLogin }">
      <!-- Left: Visual Decoration -->
      <div class="auth-visual">
        <div class="visual-content">
          <div class="geometric-shapes">
            <div class="shape shape-1"></div>
            <div class="shape shape-2"></div>
            <div class="shape shape-3"></div>
            <div class="shape shape-4"></div>
            <div class="shape shape-6"></div>
          </div>
          <div class="visual-text">
            <h2>探索知识，启迪未来</h2>
            <p>智能学习 · AI 题库 · 知识管理</p>
          </div>
        </div>
      </div>

      <!-- Right: Form -->
      <div class="auth-form-panel">
        <div class="form-wrapper">
          <div class="logo">OpenStudy</div>

          <!-- Tabs -->
          <div class="auth-tabs">
            <div class="tab-header">
              <button class="tab-btn" :class="{ active: isLogin }" @click="switchToLogin">登录</button>
              <button class="tab-btn" :class="{ active: !isLogin }" @click="switchToRegister">注册</button>
              <div class="tab-indicator" :class="{ 'indicator-right': !isLogin }"></div>
            </div>
          </div>

          <!-- Forms -->
          <div class="forms-container">
            <div class="forms-track" :class="{ 'track-register': !isLogin }">
              <!-- Login Form -->
              <div class="form-panel">
                <!-- 视图一：演示账号一键登录（仅 demoMode 时显示） -->
                <div v-if="demoMode" v-show="!showAccountForm" class="quick-login-view">
                  <div class="quick-header">
                    <h3>演示账号 · 一键登录</h3>
                    <p>点击下方任一账号即可直接进入系统</p>
                  </div>

                  <div class="quick-list">
                    <button class="quick-card" :class="{ 'is-loading': quickLoading === 'user1' }"
                      :disabled="!!quickLoading || loading" @click.prevent="handleQuickLogin('user1')">
                      <span class="quick-avatar qa-user1">用1</span>
                      <span class="quick-info">
                        <span class="quick-name">演示用户1</span>
                        <span class="quick-desc">拥有私有题库（10 题），可发起分享</span>
                      </span>
                      <span class="quick-arrow">
                        <span v-if="quickLoading === 'user1'" class="quick-spinner"></span>
                        <span v-else class="chev chev-right"></span>
                      </span>
                    </button>

                    <button class="quick-card" :class="{ 'is-loading': quickLoading === 'user2' }"
                      :disabled="!!quickLoading || loading" @click.prevent="handleQuickLogin('user2')">
                      <span class="quick-avatar qa-user2">用2</span>
                      <span class="quick-info">
                        <span class="quick-name">演示用户2</span>
                        <span class="quick-desc">接收方，领取分享后进入收藏题库</span>
                      </span>
                      <span class="quick-arrow">
                        <span v-if="quickLoading === 'user2'" class="quick-spinner"></span>
                        <span v-else class="chev chev-right"></span>
                      </span>
                    </button>

                    <button class="quick-card quick-card-guest" :class="{ 'is-loading': quickLoading === 'guest' }"
                      :disabled="!!quickLoading || loading" @click.prevent="handleQuickLogin('guest')">
                      <span class="quick-avatar qa-guest">游</span>
                      <span class="quick-info">
                        <span class="quick-name">游客</span>
                        <span class="quick-desc">只读浏览公开内容，刷题 / 写笔记 / 点赞等操作需登录</span>
                      </span>
                      <span class="quick-arrow">
                        <span v-if="quickLoading === 'guest'" class="quick-spinner"></span>
                        <span v-else class="chev chev-right"></span>
                      </span>
                    </button>
                  </div>

                  <el-button class="switch-account-btn" :disabled="!!quickLoading || loading"
                    @click.prevent="showAccountForm = true">
                    使用账号密码登录
                  </el-button>
                </div>

                <!-- 视图二：账号密码登录（演示新注册用户登录） -->
                <div v-show="showAccountForm" class="account-login-view">
                  <!-- 返回一键登录：仅演示模式（demoMode）显示；体验版不暴露 -->
                  <div v-if="demoMode" class="account-back" @click="showAccountForm = false">
                    <span class="chev chev-left"></span>
                    <span>返回一键登录</span>
                  </div>

                  <el-form ref="loginRef" :model="loginForm" :rules="loginRules">
                    <el-form-item prop="username">
                      <el-input v-model="loginForm.username" type="text" size="large" auto-complete="off"
                        placeholder="账号">
                        <template #prefix><svg-icon icon-class="user" class="el-input__icon input-icon" /></template>
                      </el-input>
                    </el-form-item>
                    <el-form-item prop="password">
                      <el-input v-model="loginForm.password" type="password" size="large" auto-complete="off"
                        placeholder="密码" show-password @keyup.enter="handleLogin">
                        <template #prefix><svg-icon icon-class="password" class="el-input__icon input-icon" /></template>
                      </el-input>
                    </el-form-item>
                    <el-form-item prop="code" v-if="captchaEnabled">
                      <div class="captcha-wrap">
                        <el-input v-model="loginForm.code" size="large" auto-complete="off" placeholder="验证码"
                          @keyup.enter="handleLogin">
                          <template #prefix><svg-icon icon-class="validCode"
                              class="el-input__icon input-icon" /></template>
                        </el-input>
                        <img :src="codeUrl" @click="getCode" class="captcha-img" />
                      </div>
                    </el-form-item>
                    <el-checkbox v-model="loginForm.rememberMe" class="remember-checkbox">记住密码</el-checkbox>
                    <el-form-item>
                      <el-button :loading="loading" size="large" class="submit-btn" @click.prevent="handleLogin">
                        <span v-if="!loading">登 录</span>
                        <span v-else>登 录 中...</span>
                      </el-button>
                    </el-form-item>
                  </el-form>
                </div>
              </div>

              <!-- Register Form -->
              <div class="form-panel">
                <el-form ref="registerRef" :model="registerForm" :rules="registerRules">
                  <el-form-item prop="username">
                    <el-input v-model="registerForm.username" type="text" size="large" auto-complete="off"
                      placeholder="账号">
                      <template #prefix><svg-icon icon-class="user" class="el-input__icon input-icon" /></template>
                    </el-input>
                  </el-form-item>
                  <el-form-item prop="password">
                    <el-input v-model="registerForm.password" type="password" size="large" auto-complete="off"
                      placeholder="密码" show-password @keyup.enter="handleRegister">
                      <template #prefix><svg-icon icon-class="password" class="el-input__icon input-icon" /></template>
                    </el-input>
                  </el-form-item>
                  <el-form-item prop="confirmPassword">
                    <el-input v-model="registerForm.confirmPassword" type="password" size="large" auto-complete="off"
                      placeholder="确认密码" show-password @keyup.enter="handleRegister">
                      <template #prefix><svg-icon icon-class="password" class="el-input__icon input-icon" /></template>
                    </el-input>
                  </el-form-item>
                  <el-form-item prop="code" v-if="captchaEnabled">
                    <div class="captcha-wrap">
                      <el-input v-model="registerForm.code" size="large" auto-complete="off" placeholder="验证码"
                        @keyup.enter="handleRegister">
                        <template #prefix><svg-icon icon-class="validCode"
                            class="el-input__icon input-icon" /></template>
                      </el-input>
                      <img :src="codeUrl" @click="getCode" class="captcha-img" />
                    </div>
                  </el-form-item>
                  <el-form-item>
                    <el-button :loading="loading" size="large" class="submit-btn" @click.prevent="handleRegister">
                      <span v-if="!loading">注 册</span>
                      <span v-else>注 册 中...</span>
                    </el-button>
                  </el-form-item>
                </el-form>
              </div>
            </div>
          </div>

          <!-- Bottom Links -->
          <div class="form-footer">
            <span v-if="isLogin" class="link" @click="switchToRegister">没有账号？立即注册</span>
            <span v-else class="link" @click="switchToLogin">已有账号？立即登录</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getCodeImg, register as registerApi } from "@/api/login";
import Cookies from "js-cookie";
import { encrypt, decrypt } from "@/utils/jsencrypt";
import useUserStore from '@/store/modules/user'
import { ElMessageBox, ElMessage } from "element-plus";
import { toRaw } from 'vue'

const userStore = useUserStore()
const route = useRoute();
const router = useRouter();
const { proxy } = getCurrentInstance();

const isLogin = ref(true)
const redirect = ref(undefined)
// false = 一键登录视图（默认）；true = 账号密码登录视图
const showAccountForm = ref(false)

watch(() => route.path, (path) => {
  if (path === '/login') {
    isLogin.value = true
  } else if (path === '/register') {
    isLogin.value = false
  }
}, { immediate: true })

watch(route, (newRoute) => {
  redirect.value = newRoute.query && newRoute.query.redirect;
}, { immediate: true });

function switchToLogin(showAccount = false) {
  if (isLogin.value) return
  isLogin.value = true
  showAccountForm.value = showAccount
  router.replace('/login')
}

function switchToRegister() {
  if (!isLogin.value) return
  isLogin.value = false
  router.replace('/register')
}

// ===================== Login Logic =====================

const loginForm = ref({
  username: "",
  password: "",
  rememberMe: false,
  code: "",
  uuid: ""
});

const loginRules = {
  username: [{ required: true, trigger: "blur", message: "请输入您的账号" }],
  password: [{ required: true, trigger: "blur", message: "请输入您的密码" }],
  code: [{ required: true, trigger: "change", message: "请输入验证码" }]
};

const codeUrl = ref("");
const loading = ref(false);
const captchaEnabled = ref(true);
// 演示模式：true=显示「演示账号一键登录」入口（自用/演示）；false=上线体验版，
// 默认走账号密码登录/注册，不暴露演示账号。由后端 /captchaImage 的 demoMode 下发。
// ⚠️ 初始值取 false（安全优先）：接口返回前先按「体验版」渲染，避免闪出一键登录入口。
const demoMode = ref(false);

function handleLogin() {
  if (quickLoading.value) return
  proxy.$refs.loginRef.validate(valid => {
    if (valid) {
      loading.value = true

      if (loginForm.value.rememberMe) {
        Cookies.set("username", loginForm.value.username, { expires: 30 })
        Cookies.set("password", encrypt(loginForm.value.password), { expires: 30 })
        Cookies.set("rememberMe", loginForm.value.rememberMe, { expires: 30 })
      } else {
        Cookies.remove("username")
        Cookies.remove("password")
        Cookies.remove("rememberMe")
      }

      userStore.login(loginForm.value).then(() => {
        redirectAfterLogin()
      }).catch((error) => {
        console.error('登录失败:', error)
        loading.value = false
        if (captchaEnabled.value) {
          getCode()
        }
      })
    }
  })
}

// 登录成功后的跳转：管理员进后台，普通用户进前台
function redirectAfterLogin() {
  const query = route.query
  const otherQueryParams = Object.keys(query).reduce((acc, cur) => {
    if (cur !== "redirect") {
      acc[cur] = query[cur]
    }
    return acc
  }, {})

  let targetPath = redirect.value
  const isGuest = userStore.isGuest

  // 进站即智能体：登录成功后统一落在对话页（管理员也从这里进，后台走侧栏「后台管理」）
  const HOME_PATH = '/front/agent/chat'
  if (!targetPath || targetPath === '/' || targetPath === '/index/home' || targetPath === '/front/index') {
    targetPath = HOME_PATH
  }

  // 游客只读：redirect 指向需要登录的页面时，退回对话页
  if (isGuest && targetPath) {
    const publicPrefixes = ['/front/agent', '/front/questionPractice', '/front/notes', '/front/share']
    if (!publicPrefixes.some(prefix => targetPath.startsWith(prefix))) {
      targetPath = HOME_PATH
    }
  }

  router.push({ path: targetPath, query: otherQueryParams })
}

// ===================== Demo One-click Login =====================

const quickLoading = ref("");

function handleQuickLogin(account) {
  if (quickLoading.value || loading.value) return
  quickLoading.value = account
  userStore.quickLogin(account).then(() => {
    redirectAfterLogin()
  }).catch((error) => {
    console.error('一键登录失败:', error)
    ElMessage.error(error?.msg || error?.message || '一键登录失败，请先导入 deploy/db-init/97_demo_seed.sql 初始化演示账号')
  }).finally(() => {
    quickLoading.value = ""
  })
}

// ===================== Register Logic =====================

const registerForm = ref({
  username: "",
  password: "",
  confirmPassword: "",
  code: "",
  uuid: ""
});

const equalToPassword = (rule, value, callback) => {
  if (registerForm.value.password !== value) {
    callback(new Error("两次输入的密码不一致"));
  } else {
    callback();
  }
};

const registerRules = {
  username: [
    { required: true, trigger: "blur", message: "请输入您的账号" },
    { min: 2, max: 20, message: "用户账号长度必须介于 2 和 20 之间", trigger: "blur" }
  ],
  password: [
    { required: true, trigger: "blur", message: "请输入您的密码" },
    { min: 5, max: 20, message: "用户密码长度必须介于 5 和 20 之间", trigger: "blur" }
  ],
  confirmPassword: [
    { required: true, trigger: "blur", message: "请再次输入您的密码" },
    { required: true, validator: equalToPassword, trigger: "blur" }
  ],
  code: [{ required: true, trigger: "change", message: "请输入验证码" }]
};

function handleRegister() {
  proxy.$refs.registerRef.validate(valid => {
    if (valid) {
      loading.value = true;
      registerApi(registerForm.value).then(res => {
        const username = registerForm.value.username;
        ElMessageBox.alert("<font color='red'>恭喜你，您的账号 " + username + " 注册成功！</font>", "系统提示", {
          dangerouslyUseHTMLString: true,
          type: "success",
        }).then(() => {
          // 注册成功后切到「账号密码登录」视图，并回填刚注册的账号，方便直接演示登录
          loginForm.value.username = username
          loginForm.value.password = ""
          loginForm.value.code = ""
          if (captchaEnabled.value) {
            getCode()
          }
          switchToLogin(true)
        }).catch(() => { });
      }).catch(() => {
        loading.value = false;
        if (captchaEnabled) {
          getCode();
        }
      });
    }
  });
}

// ===================== Shared Logic =====================

function getCode() {
  getCodeImg().then(res => {
    captchaEnabled.value = res.data.captchaEnabled === undefined ? true : res.data.captchaEnabled;
    // 体验版（demoMode=false）默认直接进「账号密码登录」，隐藏演示账号一键登录
    if (res.data.demoMode !== undefined) {
      demoMode.value = res.data.demoMode === true;
      if (!demoMode.value) {
        showAccountForm.value = true;
      }
    }
    if (captchaEnabled.value) {
      codeUrl.value = "data:image/gif;base64," + res.data.img;
      loginForm.value.uuid = res.data.uuid;
      registerForm.value.uuid = res.data.uuid;
    }
    // demoMode 已确定后再决定是否预填账号密码（体验版不预填）
    getCookie();
  });
}

function getCookie() {
  // 体验版（demoMode=false）：不预填任何账号密码，避免把管理员凭据暴露给访问者
  if (!demoMode.value) {
    loginForm.value = { username: "", password: "", rememberMe: false, code: "", uuid: "" };
    return;
  }
  const username = Cookies.get("username");
  const password = Cookies.get("password");
  const rememberMe = Cookies.get("rememberMe");
  loginForm.value = {
    username: username === undefined ? loginForm.value.username : username,
    password: password === undefined ? loginForm.value.password : decrypt(password),
    rememberMe: rememberMe === undefined ? false : Boolean(rememberMe)
  };
}

// 先取验证码配置（拿到 demoMode），再按 demoMode 决定是否读 cookie 预填
getCode();
</script>

<style lang='scss' scoped>
.auth-container {
  display: flex;
  /* 用 min-height + padding 代替固定 100vh，任何缩放/分辨率下内容都不会被裁掉；
     用 100% 而不是 100vw，避免滚动条占宽导致横向溢出 */
  min-height: 100vh;
  min-height: 100dvh;
  width: 100%;
  box-sizing: border-box;
  padding: clamp(12px, 2.4vh, 32px) clamp(12px, 2vw, 32px);
  background: #f5f7fa;
  /* 溢出时允许滚动，而不是 overflow: hidden 直接裁掉 */
  overflow: auto;
}

.auth-wrapper {
  display: flex;
  /* margin: auto 是「flex 居中的同时溢出不被裁掉顶部」的标准写法 */
  margin: auto;
  width: 1000px;
  max-width: 100%;
  /* 高度 = max(视口自适应下限, 内容自然高度)：
     视口高时按 72vh 撑起大卡片观感；内容更高时自动被撑开，不做裁切；
     因此内部永远不会出现滚动条，只有最外层 .auth-container 一个滚动条 */
  height: auto;
  min-height: clamp(520px, 72vh, 760px);
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.06);
  overflow: hidden;
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ========== Left Visual ========== */
.auth-visual {
  flex: 0 0 50%;
  min-width: 0;
  position: relative;
  background: linear-gradient(135deg, #f8f9fb 0%, #eef1f5 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.is-register-mode .auth-visual {
  background: linear-gradient(135deg, #eef1f5 0%, #e8ecf2 100%);
}

.visual-content {
  position: relative;
  width: 100%;
  height: 100%;
  z-index: 1;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.visual-text {
  position: relative;
  z-index: 2;
  margin-top: 20px;

  h2 {
    font-size: 32px;
    font-weight: 700;
    color: #1f2937;
    margin: 0 0 10px 0;
    letter-spacing: 1px;
  }

  p {
    font-size: 24px;
    color: #9ca3af;
    margin: 0;
    letter-spacing: 2px;
  }
}

/* Geometric Shapes */
.geometric-shapes {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.shape {
  position: absolute;
  transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

.shape-1 {
  width: 480px;
  height: 480px;
  background: radial-gradient(circle, rgba(26, 58, 92, 0.08), transparent 70%);
  border-radius: 50%;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.shape-2 {
  width: 300px;
  height: 300px;
  border: 2px solid rgba(26, 58, 92, 0.06);
  border-radius: 50%;
  top: 50%;
  left: 50%;
  transform: translate(-80%, -80%);
}

.shape-3 {
  width: 120px;
  height: 120px;
  border: 2px solid rgba(45, 90, 135, 0.05);
  border-radius: 16px;
  top: 50%;
  left: 50%;
  transform: translate(60%, -100%) rotate(20deg);
}

.shape-4 {
  width: 200px;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(26, 58, 92, 0.06), transparent);
  top: 50%;
  left: 50%;
  transform: translate(-50%, 60%);
}

.shape-6 {
  width: 0;
  height: 0;
  border-left: 40px solid transparent;
  border-right: 40px solid transparent;
  border-bottom: 70px solid rgba(26, 58, 92, 0.06);
  top: 50%;
  left: 50%;
  transform: translate(110%, 60%) rotate(0deg);
}

.is-register-mode .shape-2 {
  transform: translate(-80%, -80%) rotate(10deg);
}

.is-register-mode .shape-3 {
  transform: translate(60%, -100%) rotate(35deg);
}

.is-register-mode .shape-6 {
  transform: translate(110%, 60%) rotate(15deg);
}

/* ========== Right Form ========== */
.auth-form-panel {
  flex: 1 1 50%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  /* 不做内部滚动：卡片高度由内容撑开，滚动只发生在最外层 .auth-container */
  padding: clamp(16px, 3vh, 40px) clamp(16px, 2.4vw, 40px);
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.form-wrapper {
  width: 100%;
  max-width: 360px;
  /* 配合父级 flex column：内容短时垂直居中，内容长时不会被裁掉顶部 */
  margin: auto;
}

.logo {
  font-size: clamp(22px, 3.4vh, 28px);
  font-weight: 800;
  color: #1f2937;
  text-align: center;
  margin-bottom: clamp(16px, 3.4vh, 32px);
  letter-spacing: 1px;
}

/* Tabs */
.auth-tabs {
  margin-bottom: clamp(16px, 3vh, 28px);
}

.tab-header {
  position: relative;
  display: flex;
  border-bottom: 2px solid #e5e7eb;
  padding-bottom: 0;
}

.tab-btn {
  flex: 1;
  padding: 0 0 12px 0;
  border: none;
  background: none;
  font-size: 15px;
  font-weight: 600;
  color: #9ca3af;
  cursor: pointer;
  transition: color 0.3s ease;
  outline: none;
  text-align: center;

  &.active {
    color: #1f2937;
  }

  &:hover {
    color: #6b7280;
  }
}

.tab-indicator {
  position: absolute;
  bottom: -2px;
  left: 0;
  width: 50%;
  height: 2px;
  background: #1f2937;
  transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 1px;

  &.indicator-right {
    transform: translateX(100%);
  }
}

/* Forms */
.forms-container {
  /* 只用于左右滑动切换，高度交给内容自然决定（卡片高度由 .auth-wrapper 固定） */
  overflow: hidden;
}

.forms-track {
  display: flex;
  width: 200%;
  transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);

  &.track-register {
    transform: translateX(-50%);
  }
}

.form-panel {
  flex: 0 0 50%;
  min-width: 0;
  padding: 4px 4px 0;

  .el-form {
    display: flex;
    flex-direction: column;

    .el-form-item:last-child {
      margin-bottom: 0;
    }
  }
}

.captcha-wrap {
  display: flex;
  width: 100%;
  gap: 12px;

  .el-input {
    flex: 1;
  }
}

.captcha-img {
  width: 110px;
  height: 44px;
  cursor: pointer;
  border-radius: 8px;
  flex-shrink: 0;
}

.remember-checkbox {
  margin: 0 0 20px 0;
  display: flex;

  .el-checkbox__label {
    color: #6b7280;
    font-size: 14px;
  }
}

.submit-btn {
  width: 100%;
  height: 48px;
  background: #1f2937;
  border: none;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  border-radius: 8px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: #1a3a5c;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(26, 58, 92, 0.2);
  }

  &:active {
    transform: translateY(0);
  }

  &.is-loading {
    background: #9ca3af;
  }
}

.form-footer {
  text-align: center;
  margin-top: clamp(14px, 2.6vh, 24px);
}

.link {
  font-size: 14px;
  color: #9ca3af;
  cursor: pointer;
  transition: color 0.3s ease;

  &:hover {
    color: #1a3a5c;
  }
}

/* ========== Quick Login (演示账号一键登录) ========== */
.quick-login-view {
  padding-top: 4px;
}

.quick-header {
  margin-bottom: 20px;
  text-align: center;

  h3 {
    margin: 0 0 6px;
    font-size: 17px;
    font-weight: 700;
    color: #1f2937;
    letter-spacing: 0.5px;
  }

  p {
    margin: 0;
    font-size: 12px;
    color: #9ca3af;
  }
}

.quick-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quick-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  outline: none;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover:not(:disabled) {
    border-color: #cbd5e1;
    background: #fafbfc;
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
  }

  &:active:not(:disabled) {
    transform: translateY(0);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.7;
  }

  &.is-loading {
    border-color: #1f2937;
    background: #f8fafc;
  }
}

.quick-avatar {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.5px;
}

.qa-user1 {
  background: linear-gradient(135deg, #2f6f9f, #1a3a5c);
}

.qa-user2 {
  background: linear-gradient(135deg, #4b86b4, #2d5a87);
}

.qa-guest {
  background: linear-gradient(135deg, #6b7280, #4b5563);
}

.quick-card-guest:hover {
  border-color: #6b7280;
}

.quick-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.quick-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  line-height: 1.2;
}

.quick-desc {
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.4;
  /* 不用 nowrap + 省略号：窄屏时让文字换行完整显示，避免内容被截断 */
  word-break: break-word;
}

.quick-arrow {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: #cbd5e1;
}

/* CSS 箭头（图标库无箭头图标） */
.chev {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-top: 2px solid currentColor;
  border-right: 2px solid currentColor;
  border-radius: 1px;
}

.chev-right {
  transform: rotate(45deg);
}

.chev-left {
  transform: rotate(-135deg);
}

.quick-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid #e5e7eb;
  border-top-color: #1f2937;
  border-radius: 50%;
  animation: quick-spin 0.7s linear infinite;
}

@keyframes quick-spin {
  to {
    transform: rotate(360deg);
  }
}

.switch-account-btn {
  width: 100%;
  height: 44px;
  margin-top: 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #4b5563;
  background: #fff;
  border: 1px dashed #d1d5db;
  transition: all 0.25s ease;

  &:hover:not(:disabled) {
    color: #1f2937;
    border-color: #1f2937;
    background: #f8fafc;
  }
}

/* ========== Account Login (账号密码登录) ========== */
.account-login-view {
  position: relative;
}

.account-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 18px;
  padding: 4px 2px;
  font-size: 13px;
  color: #9ca3af;
  cursor: pointer;
  user-select: none;
  transition: color 0.25s ease;

  .chev {
    width: 7px;
    height: 7px;
  }

  &:hover {
    color: #1a3a5c;
  }
}

/* ========== Input Overrides ========== */
:deep(.el-input) {
  height: 44px;

  input {
    height: 44px;
  }

  .el-input__wrapper {
    border-radius: 8px;
    box-shadow: 0 0 0 1px #e5e7eb;

    &:hover {
      box-shadow: 0 0 0 1px #d1d5db;
    }

    &.is-focus {
      box-shadow: 0 0 0 1px #1f2937;
    }
  }
}

:deep(.input-icon) {
  height: 44px;
  width: 16px;
  margin-left: 0;
  color: #9ca3af;
}

:deep(.el-form-item) {
  margin-bottom: 20px;
}

:deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

:deep(.el-checkbox) {
  .el-checkbox__inner {
    border-radius: 4px;
    border-color: #d1d5db;

    &::after {
      border-color: #fff;
    }
  }

  &.is-checked .el-checkbox__inner {
    background-color: #1f2937;
    border-color: #1f2937;
  }
}

/* ========== Responsive ==========
   原则：所有断点只调「宽度 / 装饰尺寸」，不再写死高度。
   卡片高度统一由上面的 clamp(...vh) + max-height:calc(100dvh - 64px) 计算，
   内容永远完整可见；实在放不下时由 .auth-container 页面级滚动兜底。 */

/* Large screens: 27-inch+ (2560px+) */
@media (min-width: 2000px) {
  .auth-wrapper {
    width: 1300px;
  }

  .form-wrapper {
    max-width: 440px;
  }

  .visual-text h2 {
    font-size: 40px;
  }

  .visual-text p {
    font-size: 30px;
  }

  .shape-1 {
    width: 600px;
    height: 600px;
  }

  .shape-2 {
    width: 380px;
    height: 380px;
  }

  .shape-3 {
    width: 160px;
    height: 160px;
  }

  .shape-6 {
    border-left-width: 50px;
    border-right-width: 50px;
    border-bottom-width: 88px;
  }
}

/* Large screens: 24-inch (1920px+) */
@media (min-width: 1600px) and (max-width: 1999px) {
  .auth-wrapper {
    width: 1200px;
  }

  .form-wrapper {
    max-width: 400px;
  }

  .visual-text h2 {
    font-size: 36px;
  }

  .shape-1 {
    width: 540px;
    height: 540px;
  }

  .shape-2 {
    width: 340px;
    height: 340px;
  }
}

/* Medium-large: 16-inch laptop (1440px-1600px) */
@media (min-width: 1200px) and (max-width: 1599px) {
  .auth-wrapper {
    width: 1100px;
  }

  .form-wrapper {
    max-width: 380px;
  }

  .shape-1 {
    width: 500px;
    height: 500px;
  }

  .shape-2 {
    width: 300px;
    height: 300px;
  }
}

/* Default: 1000-1200px fits most 16-inch at 1920×1080 scaling */

/* Compact: 14-inch laptop / small desktop */
@media (max-width: 1100px) {
  .auth-wrapper {
    width: 960px;
  }

  .form-wrapper {
    max-width: 330px;
  }

  .shape-1 {
    width: 420px;
    height: 420px;
  }

  .shape-2 {
    width: 260px;
    height: 260px;
  }
}

/* 视口偏矮：缩小左侧装饰文字（表单字号已用 vh 缩放，无需额外处理） */
@media (max-height: 640px) {
  .visual-text h2 {
    font-size: 24px;
  }

  .visual-text p {
    font-size: 18px;
  }
}

/* 空间极小：左侧只保留装饰图形 */
@media (max-height: 540px) {
  .visual-text {
    display: none;
  }
}

/* Tablet / narrow desktop */
@media (max-width: 1024px) {
  .auth-wrapper {
    width: 900px;
  }

  .form-wrapper {
    max-width: 300px;
  }

  .visual-text h2 {
    font-size: 28px;
  }

  .visual-text p {
    font-size: 22px;
  }

  .shape-1 {
    width: 320px;
    height: 320px;
  }

  .shape-2 {
    width: 200px;
    height: 200px;
  }

  .shape-3 {
    width: 100px;
    height: 100px;
  }

  .shape-4 {
    width: 140px;
  }
}

/* Small tablet */
@media (max-width: 900px) {
  .auth-wrapper {
    width: 100%;
  }

  .form-wrapper {
    max-width: 280px;
  }

  .shape-1 {
    width: 280px;
    height: 280px;
  }

  .shape-2 {
    width: 160px;
    height: 160px;
  }
}

/* Mobile landscape / portrait：单列，卡片高度交给内容 + 页面滚动 */
@media (max-width: 768px) {
  .auth-container {
    padding: 0;
  }

  .auth-visual {
    display: none;
  }

  .auth-form-panel {
    flex: 1 1 100%;
  }

  .form-wrapper {
    max-width: 360px;
  }

  .auth-wrapper {
    width: 100%;
    height: auto;
    min-height: 100vh;
    min-height: 100dvh;
    max-height: none;
    border-radius: 0;
  }
}

/* Mobile portrait */
@media (max-width: 480px) {
  .form-wrapper {
    max-width: 100%;
  }
}
</style>
