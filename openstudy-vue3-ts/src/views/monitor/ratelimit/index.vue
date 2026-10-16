<template>
  <div class="app-container">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="限流配置" name="config">
        <el-form :model="configForm" label-width="130px" style="max-width: 640px">
          <el-form-item label="开/关限流">
            <el-switch v-model="configForm.enabled" active-text="开启" inactive-text="关闭" />
            <el-tag class="source-tag" size="small" :type="sourceType(configSources.enabled)">
              {{ sourceLabel(configSources.enabled) }}
            </el-tag>
          </el-form-item>
          <el-form-item label="用户每分钟上限">
            <el-input-number v-model="configForm.userPerMinute" :min="1" :max="100000" controls-position="right" />
            <el-tag class="source-tag" size="small" :type="sourceType(configSources.userPerMinute)">
              {{ sourceLabel(configSources.userPerMinute) }}
            </el-tag>
            <el-tooltip content="单个用户每分钟最多调用 AI 接口多少次，超出返回 429" placement="right">
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-form-item>
          <el-form-item label="用户每日上限">
            <el-input-number v-model="configForm.dailyLimit" :min="1" :max="1000000" controls-position="right" />
            <el-tag class="source-tag" size="small" :type="sourceType(configSources.dailyLimit)">
              {{ sourceLabel(configSources.dailyLimit) }}
            </el-tag>
            <el-tooltip content="单个用户每天 AI 接口调用总上限，次日 0 点重置" placement="right">
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-form-item>
          <el-form-item label="IP 每分钟上限">
            <el-input-number v-model="configForm.ipPerMinute" :min="1" :max="1000000" controls-position="right" />
            <el-tag class="source-tag" size="small" :type="sourceType(configSources.ipPerMinute)">
              {{ sourceLabel(configSources.ipPerMinute) }}
            </el-tag>
            <el-tooltip content="同一 IP 所有用户合计每分钟上限，防止脚本刷接口" placement="right">
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSaveConfig" v-hasPermi="['monitor:ratelimit:edit']">保存</el-button>
            <el-button icon="Refresh" @click="getConfig">刷新</el-button>
          </el-form-item>
        </el-form>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="修改后立即生效，无需重启服务"
          style="max-width: 640px; margin-top: 10px"
        />
      </el-tab-pane>

      <el-tab-pane label="违规记录" name="violations">
        <el-form :model="queryParams" ref="queryRef" :inline="true" label-width="68px">
          <el-form-item label="用户ID" prop="userId">
            <el-input
              v-model="queryParams.userId"
              placeholder="请输入用户ID"
              clearable
              style="width: 160px"
              @keyup.enter="handleQuery"
            />
          </el-form-item>
          <el-form-item label="IP" prop="ip">
            <el-input
              v-model="queryParams.ip"
              placeholder="请输入IP"
              clearable
              style="width: 180px"
              @keyup.enter="handleQuery"
            />
          </el-form-item>
          <el-form-item label="限流类型" prop="limitType">
            <el-select v-model="queryParams.limitType" placeholder="限流类型" clearable style="width: 160px">
              <el-option label="IP分钟" value="ip" />
              <el-option label="用户分钟" value="user_min" />
              <el-option label="用户每日" value="user_day" />
            </el-select>
          </el-form-item>
          <el-form-item label="时间" style="width: 320px">
            <el-date-picker
              v-model="dateRange"
              value-format="YYYY-MM-DD HH:mm:ss"
              type="daterange"
              range-separator="-"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              :default-time="[new Date(2000, 1, 1, 0, 0, 0), new Date(2000, 1, 1, 23, 59, 59)]"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
          </el-form-item>
        </el-form>

        <el-row :gutter="10" class="mb8">
          <el-col :span="1.5">
            <el-button type="primary" plain icon="Refresh" @click="getViolations" v-hasPermi="['monitor:ratelimit:query']">
              刷新
            </el-button>
          </el-col>
        </el-row>

        <el-table v-loading="violationLoading" :data="violationList" :empty-text="'暂无违规记录'">
          <el-table-column label="序号" width="60" type="index" align="center">
            <template #default="scope">
              <span>{{ (queryParams.pageNum - 1) * queryParams.pageSize + scope.$index + 1 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="用户ID" align="center" prop="userId" width="90" />
          <el-table-column label="用户名称" align="center" prop="userName" :show-overflow-tooltip="true" />
          <el-table-column label="IP" align="center" prop="ip" :show-overflow-tooltip="true" />
          <el-table-column label="请求路径" align="center" prop="path" :show-overflow-tooltip="true" />
          <el-table-column label="限流类型" align="center" prop="limitType" width="110">
            <template #default="scope">
              <el-tag size="small">{{ limitTypeLabel(scope.row.limitType) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="当前次数" align="center" prop="currentCount" width="90" />
          <el-table-column label="限额" align="center" prop="limitValue" width="80" />
          <el-table-column label="时间" align="center" prop="createTime" width="170">
            <template #default="scope">
              <span>{{ parseTime(scope.row.createTime) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <pagination
          v-show="violationTotal > 0"
          :total="violationTotal"
          v-model:page="queryParams.pageNum"
          v-model:limit="queryParams.pageSize"
          @pagination="getViolations"
        />
      </el-tab-pane>

      <el-tab-pane label="当前计数器" name="counters">
        <el-form :inline="true">
          <el-form-item label="IP 筛选">
            <el-input
              v-model="counterIp"
              placeholder="按 IP 筛选"
              clearable
              style="width: 200px"
              @keyup.enter="getCounters"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="getCounters" v-hasPermi="['monitor:ratelimit:query']">查询</el-button>
            <el-button icon="Refresh" @click="getCounters">刷新</el-button>
            <el-button
              type="warning"
              v-if="counterIp"
              @click="handleClearIp"
              v-hasPermi="['monitor:ratelimit:edit']"
            >
              清空该IP
            </el-button>
            <el-button type="danger" @click="handleClearAll" v-hasPermi="['monitor:ratelimit:remove']">清空全部</el-button>
          </el-form-item>
        </el-form>

        <el-table v-loading="counterLoading" :data="counterList" :empty-text="'当前无限流计数器'">
          <el-table-column label="序号" width="60" type="index" align="center" />
          <el-table-column label="类型" align="center" prop="type" width="120">
            <template #default="scope">
              <el-tag size="small">{{ counterTypeLabel(scope.row.type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="目标" align="center" :show-overflow-tooltip="true">
            <template #default="scope">
              <span v-if="scope.row.userName">{{ scope.row.userName }} (ID: {{ scope.row.target }})</span>
              <span v-else>{{ scope.row.target }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计数" align="center" prop="count" width="90" />
          <el-table-column label="是否当前桶" align="center" prop="current" width="110">
            <template #default="scope">
              <el-tag size="small" :type="scope.row.current ? 'success' : 'info'">
                {{ scope.row.current ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="剩余时间" align="center" width="120">
            <template #default="scope">
              <span>{{ formatExpiresIn(scope.row.expiresIn) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="封禁/解封" name="ban">
        <el-form label-width="90px" style="max-width: 640px">
          <el-form-item label="用户ID">
            <el-input v-model="banForm.userId" placeholder="请输入用户ID" style="width: 240px" />
            <el-tag v-if="banJustBanned" type="danger" size="small" style="margin-left: 10px">已封禁</el-tag>
          </el-form-item>
          <el-form-item label="封禁原因">
            <el-input v-model="banForm.reason" placeholder="选填" style="width: 360px" />
          </el-form-item>
          <el-form-item>
            <el-button type="danger" @click="handleBan" v-hasPermi="['monitor:ratelimit:edit']">封禁</el-button>
            <el-button type="success" @click="handleUnban" v-hasPermi="['monitor:ratelimit:edit']">解封</el-button>
          </el-form-item>
        </el-form>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="封禁会将该用户所有会话踢下线（需重新登录）；不能封禁自己和管理员账号。"
        />

        <div style="margin-top: 20px">
          <el-text type="primary" tag="b">已封禁用户</el-text>
          <el-table v-loading="bannedLoading" :data="bannedList" style="margin-top: 10px" :empty-text="'当前无封禁用户'">
            <el-table-column label="用户ID" align="center" prop="userId" width="90" />
            <el-table-column label="用户名" align="center" prop="userName" />
            <el-table-column label="昵称" align="center" prop="nickName" />
            <el-table-column label="封禁时间" align="center" prop="updateTime" width="180">
              <template #default="scope">
                <span>{{ parseTime(scope.row.updateTime) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" align="center" width="100">
              <template #default="scope">
                <el-button type="success" size="small" @click="handleUnbanRow(scope.row)" v-hasPermi="['monitor:ratelimit:edit']">解封</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts" name="RateLimit">
import {
  getRateLimitConfig,
  updateRateLimitConfig,
  listViolations,
  listCounters,
  clearCounters,
  banUser,
  unbanUser,
  listBannedUsers
} from "@/api/monitor/ratelimit";

const { proxy } = getCurrentInstance() as any;

const activeTab = ref("config");

const configLoading = ref(false);
const configForm = ref<any>({ enabled: true, userPerMinute: 0, dailyLimit: 0, ipPerMinute: 0 });
const configSources = ref<any>({});

const violationLoading = ref(false);
const violationList = ref<any[]>([]);
const violationTotal = ref(0);
const dateRange = ref<any[]>([]);

const counterLoading = ref(false);
const counterList = ref<any[]>([]);
const counterIp = ref("");

const banForm = ref<any>({ userId: undefined, reason: "" });
const banJustBanned = ref(false);
const bannedLoading = ref(false);
const bannedList = ref<any[]>([]);

const queryParams = ref<any>({
  pageNum: 1,
  pageSize: 10,
  userId: undefined,
  ip: undefined,
  limitType: undefined
});

const LIMIT_TYPE_LABELS: Record<string, string> = {
  ip: "IP分钟",
  user_min: "用户分钟",
  user_day: "用户每日"
};

const COUNTER_TYPE_LABELS: Record<string, string> = {
  ipMin: "IP分钟",
  userMin: "用户分钟",
  userDay: "用户每日"
};

function limitTypeLabel(value: string) {
  return LIMIT_TYPE_LABELS[value] || value;
}

function counterTypeLabel(value: string) {
  return COUNTER_TYPE_LABELS[value] || value;
}

function sourceLabel(source: string) {
  return source === "redis" ? "已自定义" : "系统默认";
}

function sourceType(source: string) {
  return source === "redis" ? "success" : "info";
}

function formatExpiresIn(seconds: number) {
  if (!seconds || seconds <= 0) return "已过期";
  if (seconds < 60) return `${seconds}秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}时${m}分`;
}

function applyConfig(data: any) {
  if (!data) return;
  configForm.value = {
    enabled: data.enabled,
    userPerMinute: data.userPerMinute,
    dailyLimit: data.dailyLimit,
    ipPerMinute: data.ipPerMinute
  };
  configSources.value = data.sources || {};
}

function getConfig() {
  configLoading.value = true;
  getRateLimitConfig().then((res: any) => {
    applyConfig(res.data);
    configLoading.value = false;
  }).catch(() => {
    configLoading.value = false;
  });
}

function handleSaveConfig() {
  updateRateLimitConfig({
    enabled: configForm.value.enabled,
    userPerMinute: configForm.value.userPerMinute,
    dailyLimit: configForm.value.dailyLimit,
    ipPerMinute: configForm.value.ipPerMinute
  }).then((res: any) => {
    proxy.$modal.msgSuccess("保存成功");
    applyConfig(res.data);
  }).catch(() => {});
}

function getViolations() {
  violationLoading.value = true;
  listViolations(proxy.addDateRange(queryParams.value, dateRange.value)).then((res: any) => {
    violationList.value = res.rows;
    violationTotal.value = res.total;
    violationLoading.value = false;
  }).catch(() => {
    violationLoading.value = false;
  });
}

function handleQuery() {
  queryParams.value.pageNum = 1;
  getViolations();
}

function resetQuery() {
  dateRange.value = [];
  proxy.resetForm("queryRef");
  handleQuery();
}

function getCounters() {
  counterLoading.value = true;
  listCounters({ ip: counterIp.value || undefined }).then((res: any) => {
    counterList.value = res.data?.counters || [];
    counterLoading.value = false;
  }).catch(() => {
    counterLoading.value = false;
  });
}

function handleClearIp() {
  proxy.$modal.confirm('是否确认清空 IP "' + counterIp.value + '" 的限流计数器？').then(() => {
    return clearCounters({ ip: counterIp.value });
  }).then(() => {
    proxy.$modal.msgSuccess("清空成功");
    getCounters();
  }).catch(() => {});
}

function handleClearAll() {
  proxy.$modal.confirm("是否确认清空全部限流计数器？").then(() => {
    return clearCounters({});
  }).then((res: any) => {
    proxy.$modal.msgSuccess("已清空 " + (res.data?.deleted || 0) + " 个计数器");
    getCounters();
  }).catch(() => {});
}

function getBannedUsers() {
  bannedLoading.value = true;
  listBannedUsers().then((res: any) => {
    bannedList.value = res.data || [];
    bannedLoading.value = false;
  }).catch(() => {
    bannedLoading.value = false;
  });
}

function handleBan() {
  if (!banForm.value.userId) {
    proxy.$modal.msgWarning("请输入用户ID");
    return;
  }
  proxy.$modal.confirm('是否确认封禁用户ID为"' + banForm.value.userId + '"的用户？').then(() => {
    return banUser({ userId: Number(banForm.value.userId), reason: banForm.value.reason });
  }).then(() => {
    proxy.$modal.msgSuccess("封禁成功");
    banForm.value.reason = "";
    banJustBanned.value = true;
    getBannedUsers();
  }).catch(() => {});
}

function handleUnban() {
  if (!banForm.value.userId) {
    proxy.$modal.msgWarning("请输入用户ID");
    return;
  }
  proxy.$modal.confirm('是否确认解封用户ID为"' + banForm.value.userId + '"的用户？').then(() => {
    return unbanUser({ userId: Number(banForm.value.userId) });
  }).then(() => {
    proxy.$modal.msgSuccess("解封成功");
    banJustBanned.value = false;
    getBannedUsers();
  }).catch(() => {});
}

function handleUnbanRow(row: any) {
  proxy.$modal.confirm('是否确认解封用户"' + row.userName + '"？').then(() => {
    return unbanUser({ userId: row.userId });
  }).then(() => {
    proxy.$modal.msgSuccess("解封成功");
    getBannedUsers();
  }).catch(() => {});
}

function init() {
  getConfig();
  getViolations();
  getCounters();
  getBannedUsers();
}

init();
</script>

<style scoped>
.source-tag {
  margin-left: 10px;
}
.help-icon {
  margin-left: 6px;
  color: #909399;
  cursor: pointer;
  font-size: 16px;
}
</style>
