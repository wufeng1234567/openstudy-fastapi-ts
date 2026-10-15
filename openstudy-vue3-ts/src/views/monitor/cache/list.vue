<template>
  <div class="app-container">
    <el-row :gutter="10">
      <el-col :span="8">
        <el-card style="height: calc(100vh - 125px)">
          <template #header>
            <Collection style="width: 1em; height: 1em; vertical-align: middle;" /> <span style="vertical-align: middle;">缓存列表</span>
            <el-button
              style="float: right; padding: 3px 0"
              link
              type="primary"
              icon="Refresh"
              @click="refreshCacheNames()"
            ></el-button>
          </template>
          <el-table
            v-loading="loading"
            :data="cacheNames"
            :height="tableHeight"
            highlight-current-row
            @row-click="getCacheKeys"
            style="width: 100%"
          >
            <el-table-column
              label="序号"
              width="60"
              type="index"
            ></el-table-column>

            <el-table-column
              label="缓存名称"
              align="center"
              prop="cacheName"
              :show-overflow-tooltip="true"
              :formatter="nameFormatter"
            ></el-table-column>

            <el-table-column
              label="备注"
              align="center"
              prop="remark"
              :show-overflow-tooltip="true"
            />
            <el-table-column
              label="操作"
              width="60"
              align="center"
              class-name="small-padding fixed-width"
            >
              <template #default="scope">
                <el-button
                  link
                  type="primary"
                  icon="Delete"
                  @click="handleClearCacheName(scope.row)"
                ></el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card style="height: calc(100vh - 125px)">
          <template #header>
            <Key style="width: 1em; height: 1em; vertical-align: middle;" /> <span style="vertical-align: middle;">键名列表</span>
            <el-button
              style="float: right; padding: 3px 0"
              link
              type="primary"
              icon="Refresh"
              @click="refreshCacheKeys()"
            ></el-button>
          </template>
          <el-table
            v-loading="subLoading"
            :data="cacheKeys"
            :height="tableHeight"
            highlight-current-row
            @row-click="handleCacheValue"
            style="width: 100%"
          >
            <el-table-column
              label="序号"
              width="60"
              type="index"
            ></el-table-column>
            <el-table-column
              label="缓存键名"
              align="center"
              :show-overflow-tooltip="true"
              :formatter="keyFormatter"
            >
            </el-table-column>
            <el-table-column
              label="操作"
              width="60"
              align="center"
              class-name="small-padding fixed-width"
            >
              <template #default="scope">
                <el-button
                  link
                  type="primary"
                  icon="Delete"
                  @click="handleClearCacheKey(scope.row)"
                ></el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card :bordered="false" style="height: calc(100vh - 125px)">
          <template #header>
            <Document style="width: 1em; height: 1em; vertical-align: middle;" /> <span style="vertical-align: middle;">缓存内容</span>
            <el-button
              style="float: right; padding: 3px 0"
              link
              type="primary"
              icon="Refresh"
              @click="handleClearCacheAll()"
              >清理全部</el-button
            >
          </template>
          <el-form :model="cacheForm">
            <el-row :gutter="32">
              <el-col :offset="1" :span="22">
                <el-form-item label="缓存名称:" prop="cacheName">
                  <el-input v-model="cacheForm.cacheName" :readOnly="true" />
                </el-form-item>
              </el-col>
              <el-col :offset="1" :span="22">
                <el-form-item label="缓存键名:" prop="cacheKey">
                  <el-input v-model="cacheForm.cacheKey" :readOnly="true" />
                </el-form-item>
              </el-col>
              <el-col :offset="1" :span="22">
                <el-form-item label="缓存内容:" prop="cacheValue">
                  <el-input
                    v-model="cacheForm.cacheValue"
                    type="textarea"
                    :rows="8"
                    :readOnly="true"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts" name="CacheList">
import { listCacheName, listCacheKey, getCacheValue, clearCacheName, clearCacheKey, clearCacheAll } from "@/api/monitor/cache";

const { proxy } = getCurrentInstance() as any;

const cacheNames = ref<any[]>([]);
const cacheKeys = ref<any[]>([]);
const cacheForm = ref<any>({});
const loading = ref(true);
const subLoading = ref(false);
const nowCacheName = ref("");
const tableHeight = ref(window.innerHeight - 200);

function getCacheNames() {
  loading.value = true;
  listCacheName().then((response: any) => {
    cacheNames.value = response.data;
    loading.value = false;
  });
}

function refreshCacheNames() {
  getCacheNames();
  proxy.$modal.msgSuccess("刷新缓存列表成功");
}

function handleClearCacheName(row: any) {
  clearCacheName(row.cacheName).then((response: any) => {
    proxy.$modal.msgSuccess("清理缓存名称[" + row.cacheName + "]成功");
    getCacheKeys();
  });
}

function getCacheKeys(row?: any) {
  const cacheName = row !== undefined ? row.cacheName : nowCacheName.value;
  if (cacheName === "") {
    return;
  }
  subLoading.value = true;
  listCacheKey(cacheName).then((response: any) => {
    cacheKeys.value = response.data;
    subLoading.value = false;
    nowCacheName.value = cacheName;
  });
}

function refreshCacheKeys() {
  getCacheKeys();
  proxy.$modal.msgSuccess("刷新键名列表成功");
}

function handleClearCacheKey(cacheKey: string) {
  clearCacheKey(cacheKey).then((response: any) => {
    proxy.$modal.msgSuccess("清理缓存键名[" + cacheKey + "]成功");
    getCacheKeys();
  });
}

function nameFormatter(row: any) {
  return row.cacheName.replace(":", "");
}

function keyFormatter(cacheKey: string) {
  return cacheKey.replace(nowCacheName.value, "");
}

function handleCacheValue(cacheKey: string) {
  getCacheValue(nowCacheName.value, cacheKey).then((response: any) => {
    cacheForm.value = response.data;
  });
}

function handleClearCacheAll() {
  clearCacheAll().then((response: any) => {
    proxy.$modal.msgSuccess("清理全部缓存成功");
  });
}

getCacheNames();
</script>
