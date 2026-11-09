<template>
  <el-form ref="userRef" :model="form" :rules="rules" label-width="80px">
    <el-form-item label="用户昵称" prop="nickName">
      <el-input v-model="form.nickName" maxlength="30" />
    </el-form-item>
    <el-form-item label="电话号码" prop="phonenumber">
      <el-input v-model="form.phonenumber" maxlength="20" />
    </el-form-item>
    <el-form-item label="邮箱" prop="email">
      <el-input v-model="form.email" maxlength="50" />
    </el-form-item>
    <el-form-item label="性别">
      <el-radio-group v-model="form.sex">
        <el-radio label="0">男</el-radio>
        <el-radio label="1">女</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item>
      <el-button type="primary" @click="submit">保存</el-button>
      <el-button type="danger" @click="close">关闭</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { updateUserProfile } from "@/api/system/user";

const props = defineProps({
  user: {
    type: Object
  }
});

const emit = defineEmits(['close', 'saved'])
const { proxy } = getCurrentInstance();

const form = ref<any>({});
const validateOptionalEmail = (_rule: any, value: string, callback: (error?: Error) => void) => {
  if (!value) return callback();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) return callback(new Error("请输入正确的邮箱地址"));
  callback();
};
const validateOptionalPhone = (_rule: any, value: string, callback: (error?: Error) => void) => {
  if (!value) return callback();
  if (!/^[0-9+\-() ]{5,20}$/.test(value)) return callback(new Error("请输入正确的电话号码"));
  callback();
};
const rules = ref({
  nickName: [{ required: true, message: "用户昵称不能为空", trigger: "blur" }],
  email: [{ validator: validateOptionalEmail, trigger: ["blur", "change"] }],
  phonenumber: [{ validator: validateOptionalPhone, trigger: ["blur", "change"] }],
});

/** 提交按钮 */
function submit() {
  proxy.$refs.userRef.validate(valid => {
    if (valid) {
      updateUserProfile(form.value).then(response => {
        proxy.$modal.msgSuccess("修改成功");
        emit('saved')
      });
    }
  });
};

/** 关闭按钮 */
function close() {
  emit('close')
};

// 回显当前登录用户信息
watch(() => props.user, user => {
  if (user) {
    form.value = { nickName: user.nickName, phonenumber: user.phonenumber, email: user.email, sex: user.sex };
  }
}, { immediate: true });
</script>
