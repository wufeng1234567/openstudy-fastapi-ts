<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
         <el-form-item label="留言用户" prop="userName">
            <el-input v-model="queryParams.userName" placeholder="请输入留言用户" clearable style="width: 200px"
               @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item label="留言内容" prop="content">
            <el-input v-model="queryParams.content" placeholder="请输入留言内容" clearable style="width: 200px"
               @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-row :gutter="10" class="mb8">
         <el-col :span="1.5">
            <el-button type="primary" plain icon="Plus" @click="handleAdd"
               v-hasPermi="['system:message:add']">新增</el-button>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table v-loading="loading" :data="messageList">
         <el-table-column label="序号" align="center" prop="id" width="80" />
         <el-table-column label="用户昵称" align="center" prop="userName" width="120" />
         <el-table-column label="留言内容" align="center" prop="content" :show-overflow-tooltip="true" />
         <el-table-column label="IP地址" align="center" prop="ip" width="140" />
         <el-table-column label="留言时间" align="center" prop="createTime" width="180">
            <template #default="scope">
               <span>{{ parseTime(scope.row.createTime) }}</span>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)"
                  v-hasPermi="['system:message:edit']">修改</el-button>
               <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)"
                  v-hasPermi="['system:message:remove']">删除</el-button>
            </template>
         </el-table-column>
      </el-table>

      <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum"
         v-model:limit="queryParams.pageSize" @pagination="getList" />

      <!-- 添加或修改留言对话框 -->
      <el-dialog :title="title" v-model="open" width="500px" append-to-body>
         <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
            <el-form-item label="留言内容" prop="content">
               <el-input v-model="form.content" type="textarea" :rows="4" placeholder="请输入留言内容" />
            </el-form-item>
         </el-form>
         <template #footer>
            <el-button @click="cancel">取消</el-button>
            <el-button type="primary" @click="submitForm">确定</el-button>
         </template>
      </el-dialog>
   </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'MessageManage' })
import { listMessage, delMessage, updateMessage, addMessage } from '@/api/leaveMessage'
import { parseTime } from '@/utils/ruoyi'
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(true)
const showSearch = ref(true)
const messageList = ref([])
const total = ref(0)
const queryRef = ref(null)
const formRef = ref(null)

const queryParams = ref({
   pageNum: 1,
   pageSize: 10,
   userName: null,
   content: null
})

const open = ref(false)
const title = ref('')
const form = ref({
   id: null,
   content: ''
})
const rules = ref({
   content: [{ required: true, message: '留言内容不能为空', trigger: 'blur' }]
})

const handleQuery = () => {
   queryParams.value.pageNum = 1
   getList()
}

const resetQuery = () => {
   queryRef.value?.resetFields()
   handleQuery()
}

const getList = async () => {
   loading.value = true
   try {
      const res = await listMessage(queryParams.value.userName, queryParams.value.content)
      if (res.code === 200) {
         messageList.value = res.data || []
         total.value = messageList.value.length
      } else {
         ElMessage.error(res.msg || '获取留言列表失败')
      }
   } catch (error) {
      console.error('获取留言列表失败:', error)
      ElMessage.error('获取留言列表失败，请检查网络')
   } finally {
      loading.value = false
   }
}

const handleAdd = () => {
   reset()
   open.value = true
   title.value = '添加留言'
}

const handleUpdate = (row) => {
   reset()
   form.value.id = row.id
   form.value.content = row.content
   open.value = true
   title.value = '修改留言'
}

const cancel = () => {
   open.value = false
   reset()
}

const reset = () => {
   form.value = {
      id: null,
      content: ''
   }
   if (formRef.value) {
      formRef.value.resetFields()
   }
}

const submitForm = async () => {
   if (!formRef.value) return

   await formRef.value.validate(async (valid) => {
      if (valid) {
         try {
            let res
            if (form.value.id) {
               res = await updateMessage(form.value)
            } else {
               res = await addMessage(form.value)
            }
            if (res.code === 200) {
               ElMessage.success('操作成功')
               open.value = false
               getList()
            } else {
               ElMessage.error(res.msg || '操作失败')
            }
         } catch (error) {
            ElMessage.error('操作失败')
         }
      }
   })
}

const handleDelete = async (row) => {
   await ElMessageBox.confirm('是否确认删除序号为"' + row.id + '"的留言？', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
   })
   try {
      const res = await delMessage(row.id)
      if (res.code === 200) {
         ElMessage.success('删除成功')
         getList()
      } else {
         ElMessage.error(res.msg || '删除失败')
      }
   } catch (e) {
      if (e !== 'cancel') {
         ElMessage.error('删除失败')
      }
   }
}

getList()
</script>
