<template>
  <div class="user-info-head" :class="{ editable: isSelf }" @click="isSelf && editCropper()">
    <UserAvatar v-if="!resolvedImg" :name="userName" :size="80" />
    <img v-else :src="resolvedImg" class="img-circle img-lg" />
    <el-dialog v-if="isSelf" :title="title" v-model="open" width="800px" append-to-body @opened="modalOpened"
      @close="closeDialog">
      <el-row>
        <el-col :xs="24" :md="12" :style="{ height: '350px' }">
          <vue-cropper ref="cropper" :img="options.img" :info="true" :autoCrop="options.autoCrop"
            :autoCropWidth="options.autoCropWidth" :autoCropHeight="options.autoCropHeight"
            :fixedBox="options.fixedBox" :outputType="options.outputType" @realTime="realTime" v-if="visible" />
        </el-col>
        <el-col :xs="24" :md="12" :style="{ height: '350px' }">
          <div class="avatar-upload-preview">
            <img :src="options.previews.url" :style="options.previews.img" />
          </div>
        </el-col>
      </el-row>
      <br />
      <el-row>
        <el-col :lg="2" :md="2">
          <el-upload action="#" :http-request="requestUpload" :show-file-list="false" :before-upload="beforeUpload">
            <el-button>
              选择
              <el-icon class="el-icon--right">
                <Upload />
              </el-icon>
            </el-button>
          </el-upload>
        </el-col>
        <el-col :lg="{ span: 1, offset: 2 }" :md="2">
          <el-button icon="Plus" @click="changeScale(1)"></el-button>
        </el-col>
        <el-col :lg="{ span: 1, offset: 1 }" :md="2">
          <el-button icon="Minus" @click="changeScale(-1)"></el-button>
        </el-col>
        <el-col :lg="{ span: 1, offset: 1 }" :md="2">
          <el-button icon="RefreshLeft" @click="rotateLeft()"></el-button>
        </el-col>
        <el-col :lg="{ span: 1, offset: 1 }" :md="2">
          <el-button icon="RefreshRight" @click="rotateRight()"></el-button>
        </el-col>
        <el-col :lg="{ span: 2, offset: 6 }" :md="2">
          <el-button type="primary" @click="uploadImg()">提 交</el-button>
        </el-col>
      </el-row>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import "vue-cropper/dist/index.css";
import { VueCropper } from "vue-cropper";
import { uploadAvatar } from "@/api/system/user";
import useUserStore from "@/store/modules/user";
import UserAvatar from '@/components/UserAvatar/index.vue';

const props = defineProps({
  avatar: { type: String, default: '' },
  userName: { type: String, default: '' },
  isSelf: { type: Boolean, default: true }
})

watch(() => props.avatar, (newVal) => {
  options.img = resolveAvatarUrl(newVal) || resolveAvatarUrl(userStore.avatar)
  resolvedImg.value = resolveAvatarUrl(newVal)
})

const userStore = useUserStore();
const { proxy } = getCurrentInstance();

const open = ref(false);
const visible = ref(false);
const title = ref("修改头像");

const baseUrl = import.meta.env.VITE_APP_BASE_API || ''

const resolveAvatarUrl = (url) => {
  if (!url) return ''
  if (url.startsWith('http') || url.startsWith('data:')) return url
  return baseUrl + url
}

const resolvedImg = ref(resolveAvatarUrl(props.avatar))

const options = reactive({
  img: resolveAvatarUrl(props.avatar) || resolveAvatarUrl(userStore.avatar),
  autoCrop: true,
  autoCropWidth: 200,
  autoCropHeight: 200,
  fixedBox: true,
  outputType: "png",
  filename: 'avatar',
  previews: {}
});

function editCropper() {
  open.value = true;
}
function modalOpened() {
  visible.value = true;
}
function requestUpload() {}
function rotateLeft() {
  proxy.$refs.cropper.rotateLeft();
}
function rotateRight() {
  proxy.$refs.cropper.rotateRight();
}
function changeScale(num) {
  num = num || 1;
  proxy.$refs.cropper.changeScale(num);
}
function beforeUpload(file) {
  if (file.type.indexOf("image/") == -1) {
    proxy.$modal.msgError("文件格式错误，请上传图片类型,如：JPG，PNG后缀的文件。");
  } else {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      options.img = reader.result;
      options.filename = file.name;
    };
  }
}
function uploadImg() {
  proxy.$refs.cropper.getCropBlob(data => {
    let formData = new FormData();
    formData.append("avatarfile", data, options.filename);
    uploadAvatar(formData).then(response => {
      open.value = false;
      const newUrl = import.meta.env.VITE_APP_BASE_API + response.imgUrl;
      options.img = newUrl;
      resolvedImg.value = newUrl;
      userStore.avatar = newUrl;
      proxy.$modal.msgSuccess("修改成功");
      visible.value = false;
    });
  });
}
function realTime(data) {
  options.previews = data;
}
function closeDialog() {
  options.img = resolveAvatarUrl(props.avatar) || resolveAvatarUrl(userStore.avatar);
  visible.value = false;
}
</script>

<style lang='scss' scoped>
.user-info-head {
  position: relative;
  display: inline-block;
  height: 80px;
  width: 80px;
  border-radius: 50%;
  overflow: hidden;

  img {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    object-fit: cover;
    display: block;
  }
}

.user-info-head.editable:hover:after {
  content: "+";
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  color: #eee;
  background: rgba(0, 0, 0, 0.5);
  font-size: 24px;
  font-style: normal;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  cursor: pointer;
  line-height: 80px;
  border-radius: 50%;
  text-align: center;
}
</style>
