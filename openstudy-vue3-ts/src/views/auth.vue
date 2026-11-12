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

<style lang='scss' scoped src="./auth.style1.css"></style>
