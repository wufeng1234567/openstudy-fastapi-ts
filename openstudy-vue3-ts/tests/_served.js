import { createHotContext as __vite__createHotContext } from "/@vite/client";import.meta.hot = __vite__createHotContext("/src/components/KnowledgeBaseDrawer/index.vue");import { defineComponent as _defineComponent } from "/node_modules/.vite/deps/vue.js?v=42eb0c92";
import { ref, computed, onBeforeUnmount, onMounted } from "/node_modules/.vite/deps/vue.js?v=42eb0c92";
import { ElMessage, ElMessageBox } from "/node_modules/.vite/deps/element-plus.js?v=42eb0c92";
import { Close, Delete, DocumentCopy, EditPen, Plus, RefreshRight, UploadFilled, View } from "/node_modules/.vite/deps/@element-plus_icons-vue.js?v=42eb0c92";
import {
  DOC_FAILED,
  DOC_PARSED,
  KB_FILE_ACCEPT,
  KB_FILE_EXTENSIONS,
  canReprocessDocument,
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  documentTagType,
  getDocumentChunks,
  getDocumentStatus,
  importDocumentText,
  isDocumentProcessing,
  isDocumentSearchable,
  isSupportedKbFile,
  listDocuments,
  listKnowledgeBases,
  reprocessDocument,
  searchKnowledge,
  updateKnowledgeBase,
  uploadDocument
} from "/src/api/ai/rag.ts?t=1789909138368";
const POLL_INTERVAL = 2e3;
const POLL_MAX_ROUNDS = 90;
const _sfc_main = /* @__PURE__ */ _defineComponent({
  ...{ name: "KnowledgeBaseDrawer" },
  __name: "index",
  setup(__props, { expose: __expose }) {
    const visible = ref(false);
    const loading = ref(false);
    const creating = ref(false);
    const uploading = ref(false);
    const uploadTip = ref("");
    const importing = ref(false);
    const textImportVisible = ref(false);
    const textImportContent = ref("");
    const textImportFileName = ref("");
    const kbs = ref([]);
    const activeKbId = ref(null);
    const documents = ref([]);
    const docsLoading = ref(false);
    const kbFilter = ref("");
    const kbLoadFailed = ref(false);
    const chunksVisible = ref(false);
    const chunksLoading = ref(false);
    const chunks = ref([]);
    const chunkDocName = ref("");
    const fileInputRef = ref(null);
    const probeQuery = ref("");
    const probing = ref(false);
    const probeDone = ref(false);
    const probeHits = ref([]);
    let pollTimers = [];
    const pollingDocs = /* @__PURE__ */ new Set();
    const kbCount = computed(() => kbs.value.length);
    const activeKb = computed(() => kbs.value.find((k) => k.kbId === activeKbId.value) || null);
    const filteredKbs = computed(() => {
      const q = kbFilter.value.trim().toLowerCase();
      if (!q)
        return kbs.value;
      return kbs.value.filter((k) => String(k.name || "").toLowerCase().includes(q));
    });
    const kbTitle = computed(
      () => kbCount.value ? `\u77E5\u8BC6\u5E93\uFF08${kbCount.value} \u4E2A\uFF09\u2014\u2014 \u4F20\u8D44\u6599\u3001\u8BA9\u667A\u80FD\u4F53\u81EA\u5DF1\u68C0\u7D22` : "\u77E5\u8BC6\u5E93 \u2014\u2014 \u4F20\u8D44\u6599\uFF0C\u8BA9\u667A\u80FD\u4F53\u68C0\u7D22\u540E\u56DE\u7B54"
    );
    const busy = computed(() => uploading.value || importing.value);
    const clearPollTimers = () => {
      pollTimers.forEach((t) => window.clearTimeout(t));
      pollTimers = [];
      pollingDocs.clear();
    };
    const pollDocument = (docId, round = 0) => {
      if (round === 0) {
        if (pollingDocs.has(docId))
          return;
        pollingDocs.add(docId);
      }
      const timer = window.setTimeout(async () => {
        try {
          const res = await getDocumentStatus(docId);
          if (res?.code !== 200)
            return;
          const info = res.data || {};
          const row = documents.value.find((d) => d.docId === docId);
          if (row) {
            row.status = info.status;
            row.statusText = info.statusText;
            row.chunkCount = info.chunkCount;
            row.errorMsg = info.errorMsg;
          }
          if (!info.done && round < POLL_MAX_ROUNDS) {
            pollDocument(docId, round + 1);
            return;
          }
          pollingDocs.delete(docId);
          if (info.ok) {
            uploadTip.value = "";
            loadKbs();
          } else if (round >= POLL_MAX_ROUNDS) {
            uploadTip.value = "\u6587\u6863\u8FD8\u5728\u5904\u7406\u4E2D\uFF0C\u7A0D\u540E\u56DE\u6765\u5237\u65B0\u770B\u770B";
          } else {
            uploadTip.value = `\u300C${row?.fileName || "\u6587\u6863"}\u300D\u5904\u7406\u5931\u8D25\uFF1A${info.errorMsg || "\u672A\u77E5\u539F\u56E0"}`;
          }
        } catch {
          pollingDocs.delete(docId);
        }
      }, POLL_INTERVAL);
      pollTimers.push(timer);
    };
    const loadKbs = async (autoSelect = true) => {
      loading.value = true;
      try {
        const res = await listKnowledgeBases();
        if (res?.code === 200 && Array.isArray(res.data)) {
          kbLoadFailed.value = false;
          kbs.value = res.data;
          if (activeKbId.value && !kbs.value.some((k) => k.kbId === activeKbId.value)) {
            activeKbId.value = null;
            documents.value = [];
          }
          if (autoSelect && !activeKbId.value && kbs.value.length)
            await selectKb(kbs.value[0]);
        } else {
          kbLoadFailed.value = true;
          console.warn("[kb] \u77E5\u8BC6\u5E93\u5217\u8868\u54CD\u5E94\u4E0D\u662F\u6570\u7EC4", res);
        }
      } catch (e) {
        kbLoadFailed.value = true;
        console.warn("[kb] \u52A0\u8F7D\u77E5\u8BC6\u5E93\u5931\u8D25", e);
      } finally {
        loading.value = false;
      }
    };
    const loadDocs = async (kbId) => {
      docsLoading.value = true;
      try {
        const res = await listDocuments(kbId);
        if (res?.code === 200 && Array.isArray(res.data)) {
          documents.value = res.data;
          documents.value.filter((d) => isDocumentProcessing(d.status)).forEach((d) => pollDocument(d.docId));
        }
      } catch (e) {
        console.warn("[kb] \u52A0\u8F7D\u6587\u6863\u5931\u8D25", e);
      } finally {
        docsLoading.value = false;
      }
    };
    const selectKb = async (kb) => {
      activeKbId.value = kb.kbId;
      uploadTip.value = "";
      resetProbe();
      await loadDocs(kb.kbId);
    };
    const resetProbe = () => {
      probeQuery.value = "";
      probeDone.value = false;
      probeHits.value = [];
    };
    const runProbe = async () => {
      const q = probeQuery.value.trim();
      if (!q || !activeKbId.value)
        return;
      probing.value = true;
      try {
        const res = await searchKnowledge(q, [activeKbId.value]);
        if (res?.code === 200) {
          probeHits.value = res.data?.hits || [];
          probeDone.value = true;
        } else {
          ElMessage.error(res?.msg || "\u68C0\u7D22\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u68C0\u7D22\u5931\u8D25");
      } finally {
        probing.value = false;
      }
    };
    const onOpen = async () => {
      activeKbId.value = null;
      documents.value = [];
      await loadKbs();
    };
    const open = () => {
      visible.value = true;
    };
    const promptCreate = async () => {
      let name = "";
      try {
        const r = await ElMessageBox.prompt("\u7ED9\u77E5\u8BC6\u5E93\u8D77\u4E2A\u540D\u5B57", "\u65B0\u5EFA\u77E5\u8BC6\u5E93", {
          confirmButtonText: "\u521B\u5EFA",
          cancelButtonText: "\u53D6\u6D88",
          inputPlaceholder: "\u4F8B\u5982\uFF1A\u6570\u636E\u7ED3\u6784\u671F\u672B\u590D\u4E60",
          inputValidator: (v) => v && v.trim() ? true : "\u540D\u5B57\u4E0D\u80FD\u4E3A\u7A7A"
        });
        name = String(r?.value || "").trim();
      } catch {
        return;
      }
      if (!name)
        return;
      creating.value = true;
      try {
        const res = await createKnowledgeBase({ name });
        if (res?.code === 200) {
          ElMessage.success("\u77E5\u8BC6\u5E93\u5DF2\u521B\u5EFA");
          await loadKbs();
          const created = kbs.value.find((k) => k.kbId === res.data?.kbId);
          if (created)
            await selectKb(created);
        } else {
          ElMessage.error(res?.msg || "\u521B\u5EFA\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u521B\u5EFA\u5931\u8D25");
      } finally {
        creating.value = false;
      }
    };
    const promptRename = async (kb) => {
      let name = "";
      try {
        const r = await ElMessageBox.prompt("\u6539\u6210\u4EC0\u4E48\u540D\u5B57\uFF1F", "\u91CD\u547D\u540D\u77E5\u8BC6\u5E93", {
          confirmButtonText: "\u4FDD\u5B58",
          cancelButtonText: "\u53D6\u6D88",
          inputValue: kb.name,
          inputValidator: (v) => v && v.trim() ? true : "\u540D\u5B57\u4E0D\u80FD\u4E3A\u7A7A"
        });
        name = String(r?.value || "").trim();
      } catch {
        return;
      }
      if (!name || name === kb.name)
        return;
      try {
        const res = await updateKnowledgeBase(kb.kbId, { name });
        if (res?.code === 200) {
          ElMessage.success("\u5DF2\u91CD\u547D\u540D");
          await loadKbs();
        } else {
          ElMessage.error(res?.msg || "\u91CD\u547D\u540D\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u91CD\u547D\u540D\u5931\u8D25");
      }
    };
    const removeKb = async (kb) => {
      try {
        await ElMessageBox.confirm(
          `\u5220\u9664\u300C${kb.name}\u300D\uFF1F\u5E93\u91CC\u7684 ${kb.docCount || 0} \u7BC7\u6587\u6863\u4E0E\u5206\u5757\u4F1A\u4E00\u5E76\u6E05\u6389\uFF0C\u4E0D\u53EF\u64A4\u9500\u3002`,
          "\u5220\u9664\u786E\u8BA4",
          { confirmButtonText: "\u5220\u9664", cancelButtonText: "\u53D6\u6D88", type: "warning" }
        );
      } catch {
        return;
      }
      try {
        const res = await deleteKnowledgeBase(kb.kbId);
        if (res?.code === 200) {
          ElMessage.success("\u77E5\u8BC6\u5E93\u5DF2\u5220\u9664");
          if (activeKbId.value === kb.kbId) {
            activeKbId.value = null;
            documents.value = [];
          }
          await loadKbs();
        } else {
          ElMessage.error(res?.msg || "\u5220\u9664\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u5220\u9664\u5931\u8D25");
      }
    };
    const togglingKbId = ref(null);
    const kbEnabled = (kb) => kb.disabled !== 1;
    const toggleKbDisabled = async (kb, on) => {
      const want = on ? 0 : 1;
      if ((kbEnabled(kb) ? 0 : 1) === want)
        return;
      togglingKbId.value = kb.kbId;
      try {
        const res = await updateKnowledgeBase(kb.kbId, { disabled: want });
        if (res?.code === 200) {
          await loadKbs();
          ElMessage.success(
            want === 1 ? `\u5DF2\u5C4F\u853D\u300C${kb.name}\u300D\u2014\u2014 \u667A\u80FD\u4F53\u63D0\u95EE\u4E0E\u8BD5\u68C0\u7D22\u90FD\u4E0D\u4F1A\u518D\u67E5\u8FD9\u4E2A\u5E93` : `\u5DF2\u6062\u590D\u300C${kb.name}\u300D\u2014\u2014 \u667A\u80FD\u4F53\u63D0\u95EE\u4E0E\u8BD5\u68C0\u7D22\u90FD\u4F1A\u6B63\u5E38\u67E5\u5B83`
          );
        } else {
          ElMessage.error(res?.msg || "\u64CD\u4F5C\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u64CD\u4F5C\u5931\u8D25");
      } finally {
        togglingKbId.value = null;
      }
    };
    const onFilesPicked = async (evt) => {
      const input = evt.target;
      const files = Array.from(input.files || []);
      input.value = "";
      if (!files.length || !activeKbId.value || busy.value)
        return;
      const bad = files.filter((f) => !isSupportedKbFile(f.name));
      if (bad.length) {
        ElMessage.warning(`\u8DF3\u8FC7\u4E0D\u652F\u6301\u7684\u6587\u4EF6\uFF1A${bad.map((f) => f.name).join("\u3001")}`);
      }
      const ok = files.filter((f) => isSupportedKbFile(f.name));
      if (!ok.length)
        return;
      uploading.value = true;
      const kbId = activeKbId.value;
      try {
        for (const file of ok) {
          uploadTip.value = `\u6B63\u5728\u4E0A\u4F20\u5E76\u89E3\u6790\u300C${file.name}\u300D\u2026`;
          try {
            const res = await uploadDocument(kbId, file);
            if (res?.code === 200 && res.data?.docId) {
              uploadTip.value = `\u300C${file.name}\u300D\u5DF2\u4E0A\u4F20\uFF0C\u6B63\u5728\u5411\u91CF\u5316\u2026`;
              await loadDocs(kbId);
              pollDocument(res.data.docId);
            } else {
              uploadTip.value = "";
              ElMessage.error(res?.msg || `\u300C${file.name}\u300D\u4E0A\u4F20\u5931\u8D25`);
            }
          } catch (e) {
            uploadTip.value = "";
            ElMessage.error(e?.message || `\u300C${file.name}\u300D\u4E0A\u4F20\u5931\u8D25`);
          }
        }
      } finally {
        uploading.value = false;
      }
    };
    const openTextImport = () => {
      if (busy.value)
        return;
      textImportVisible.value = true;
    };
    const resetTextImport = () => {
      textImportContent.value = "";
      textImportFileName.value = "";
    };
    const submitTextImport = async () => {
      const kbId = activeKbId.value;
      const content = textImportContent.value.trim();
      if (!kbId || !content || busy.value)
        return;
      importing.value = true;
      try {
        const name = textImportFileName.value.trim();
        const res = await importDocumentText(kbId, content, name || void 0);
        if (res?.code === 200 && res.data?.docId) {
          textImportVisible.value = false;
          uploadTip.value = `\u300C${res.data.fileName || name || "\u672A\u547D\u540D\u6587\u6863.txt"}\u300D\u5DF2\u5BFC\u5165\uFF0C\u6B63\u5728\u5411\u91CF\u5316\u2026`;
          await loadDocs(kbId);
          pollDocument(res.data.docId);
        } else {
          ElMessage.error(res?.msg || "\u5BFC\u5165\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u5BFC\u5165\u5931\u8D25");
      } finally {
        importing.value = false;
      }
    };
    const removeDoc = async (doc) => {
      try {
        await ElMessageBox.confirm(`\u5220\u9664\u6587\u6863\u300C${doc.fileName}\u300D\uFF1F`, "\u5220\u9664\u786E\u8BA4", {
          confirmButtonText: "\u5220\u9664",
          cancelButtonText: "\u53D6\u6D88",
          type: "warning"
        });
      } catch {
        return;
      }
      try {
        const res = await deleteDocument(doc.docId);
        if (res?.code === 200) {
          ElMessage.success("\u6587\u6863\u5DF2\u5220\u9664");
          if (activeKbId.value)
            await loadDocs(activeKbId.value);
          await loadKbs();
        } else {
          ElMessage.error(res?.msg || "\u5220\u9664\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u5220\u9664\u5931\u8D25");
      }
    };
    const reprocess = async (doc) => {
      try {
        const res = await reprocessDocument(doc.docId);
        if (res?.code === 200) {
          ElMessage.success("\u5DF2\u91CD\u65B0\u5F00\u59CB\u5904\u7406");
          if (activeKbId.value)
            await loadDocs(activeKbId.value);
          pollDocument(doc.docId);
        } else {
          ElMessage.error(res?.msg || "\u91CD\u8BD5\u5931\u8D25");
        }
      } catch (e) {
        ElMessage.error(e?.message || "\u91CD\u8BD5\u5931\u8D25");
      }
    };
    const showChunks = async (doc) => {
      chunkDocName.value = doc.fileName;
      chunksVisible.value = true;
      chunksLoading.value = true;
      chunks.value = [];
      try {
        const res = await getDocumentChunks(doc.docId);
        if (res?.code === 200 && Array.isArray(res.data))
          chunks.value = res.data;
      } catch (e) {
        console.warn("[kb] \u52A0\u8F7D\u5206\u5757\u5931\u8D25", e);
      } finally {
        chunksLoading.value = false;
      }
    };
    onBeforeUnmount(clearPollTimers);
    onMounted(() => {
      loadKbs(false);
    });
    __expose({ open });
    const __returned__ = { POLL_INTERVAL, POLL_MAX_ROUNDS, visible, loading, creating, uploading, uploadTip, importing, textImportVisible, textImportContent, textImportFileName, kbs, activeKbId, documents, docsLoading, kbFilter, kbLoadFailed, chunksVisible, chunksLoading, chunks, chunkDocName, fileInputRef, probeQuery, probing, probeDone, probeHits, get pollTimers() {
      return pollTimers;
    }, set pollTimers(v) {
      pollTimers = v;
    }, pollingDocs, kbCount, activeKb, filteredKbs, kbTitle, busy, clearPollTimers, pollDocument, loadKbs, loadDocs, selectKb, resetProbe, runProbe, onOpen, open, promptCreate, promptRename, removeKb, togglingKbId, kbEnabled, toggleKbDisabled, onFilesPicked, openTextImport, resetTextImport, submitTextImport, removeDoc, reprocess, showChunks, get Close() {
      return Close;
    }, get Delete() {
      return Delete;
    }, get DocumentCopy() {
      return DocumentCopy;
    }, get EditPen() {
      return EditPen;
    }, get Plus() {
      return Plus;
    }, get RefreshRight() {
      return RefreshRight;
    }, get UploadFilled() {
      return UploadFilled;
    }, get View() {
      return View;
    }, get DOC_FAILED() {
      return DOC_FAILED;
    }, get DOC_PARSED() {
      return DOC_PARSED;
    }, get KB_FILE_ACCEPT() {
      return KB_FILE_ACCEPT;
    }, get KB_FILE_EXTENSIONS() {
      return KB_FILE_EXTENSIONS;
    }, get canReprocessDocument() {
      return canReprocessDocument;
    }, get documentTagType() {
      return documentTagType;
    }, get isDocumentProcessing() {
      return isDocumentProcessing;
    }, get isDocumentSearchable() {
      return isDocumentSearchable;
    } };
    Object.defineProperty(__returned__, "__isScriptSetup", { enumerable: false, value: true });
    return __returned__;
  }
});
import { createCommentVNode as _createCommentVNode, createElementVNode as _createElementVNode, openBlock as _openBlock, createElementBlock as _createElementBlock, toDisplayString as _toDisplayString, withModifiers as _withModifiers, createTextVNode as _createTextVNode, resolveComponent as _resolveComponent, withCtx as _withCtx, createVNode as _createVNode, vModelText as _vModelText, withDirectives as _withDirectives, renderList as _renderList, Fragment as _Fragment, normalizeClass as _normalizeClass, resolveDirective as _resolveDirective, withKeys as _withKeys, createBlock as _createBlock, pushScopeId as _pushScopeId, popScopeId as _popScopeId } from "/node_modules/.vite/deps/vue.js?v=42eb0c92";

import { h } from "/node_modules/.vite/deps/vue.js?v=42eb0c92";
const _withScopeId = (n) => (_pushScopeId("data-v-fccbca24"), n = n(), _popScopeId(), n);
const _hoisted_1 = ["title"];
const _hoisted_2 = /* @__PURE__ */ _withScopeId(() => /* @__PURE__ */ _createElementVNode(
  "svg",
  {
    viewBox: "0 0 24 24",
    width: "15",
    height: "15",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": "2",
    "stroke-linecap": "round",
    "stroke-linejoin": "round"
  },
  [
    /* @__PURE__ */ _createElementVNode("path", { d: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20" }),
    /* @__PURE__ */ _createElementVNode("path", { d: "M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" })
  ],
  -1
  /* HOISTED */
));
const _hoisted_3 = {
  key: 0,
  class: "kb-entry-badge"
};
const _hoisted_4 = { class: "kb-body" };
const _hoisted_5 = { class: "kb-head" };
const _hoisted_6 = /* @__PURE__ */ _withScopeId(() => /* @__PURE__ */ _createElementVNode(
  "div",
  { class: "kb-head-left" },
  [
    /* @__PURE__ */ _createElementVNode("span", { class: "kb-title" }, "\u77E5\u8BC6\u5E93"),
    /* @__PURE__ */ _createElementVNode("span", { class: "kb-sub" }, "\u4F20\u8FDB\u6765\u7684\u8D44\u6599\uFF0C\u667A\u80FD\u4F53\u4F1A\u81EA\u5DF1\u68C0\u7D22\u540E\u56DE\u7B54")
  ],
  -1
  /* HOISTED */
));
const _hoisted_7 = { class: "kb-head-right" };
const _hoisted_8 = { class: "kb-main" };
const _hoisted_9 = {
  key: 0,
  class: "kb-load-failed"
};
const _hoisted_10 = /* @__PURE__ */ _withScopeId(() => /* @__PURE__ */ _createElementVNode(
  "span",
  null,
  "\u77E5\u8BC6\u5E93\u5217\u8868\u8FD9\u6B21\u6CA1\u53D6\u5230\uFF0C\u4E0B\u9762\u663E\u793A\u7684\u53EF\u80FD\u4E0D\u662F\u6700\u65B0\u7684\u3002",
  -1
  /* HOISTED */
));
const _hoisted_11 = {
  key: 1,
  class: "kb-filter"
};
const _hoisted_12 = { class: "kb-list-wrap" };
const _hoisted_13 = ["onClick"];
const _hoisted_14 = { class: "kb-item-main" };
const _hoisted_15 = ["title"];
const _hoisted_16 = { class: "kb-item-meta" };
const _hoisted_17 = {
  key: 0,
  class: "kb-item-blocked"
};
const _hoisted_18 = ["title"];
const _hoisted_19 = { class: "kb-item-ops" };
const _hoisted_20 = ["onClick"];
const _hoisted_21 = ["onClick"];
const _hoisted_22 = {
  key: 0,
  class: "kb-empty"
};
const _hoisted_23 = /* @__PURE__ */ _withScopeId(() => /* @__PURE__ */ _createElementVNode(
  "div",
  { class: "kb-empty-title" },
  "\u8FD8\u6CA1\u6709\u77E5\u8BC6\u5E93",
  -1
  /* HOISTED */
));
const _hoisted_24 = /* @__PURE__ */ _withScopeId(() => /* @__PURE__ */ _createElementVNode(
  "div",
  { class: "kb-empty-desc" },
  " \u65B0\u5EFA\u4E00\u4E2A\uFF0C\u628A\u8BFE\u4EF6 / \u8BB2\u4E49 / \u7B14\u8BB0\u4F20\u8FDB\u53BB\uFF0C\u4E4B\u540E\u76F4\u63A5\u63D0\u95EE\u5C31\u884C \u2014\u2014 \u667A\u80FD\u4F53\u4F1A\u5148\u5728\u8D44\u6599\u91CC\u627E\uFF0C\u518D\u56DE\u7B54\u4F60\uFF0C\u5E76\u544A\u8BC9\u4F60\u7B54\u6848\u51FA\u81EA\u54EA\u4E00\u6BB5\u3002 ",
  -1
  /* HOISTED */
));
const _hoisted_25 = {
  key: 1,
  class: "kb-empty"
};
const _hoisted_26 = { class: "kb-empty-title" };
const _hoisted_27 = { class: "kb-empty-desc" };
const _hoisted_28 = {
  key: 2,
  class: "kb-docs"
};
const _hoisted_29 = { class: "kb-docs-head" };
const _hoisted_30 = { class: "kb-docs-title" };
const _hoisted_31 = { class: "kb-docs-hint" };
const _hoisted_32 = ["accept", "disabled"];
const _hoisted_33 = ["disabled", "title"];
const _hoisted_34 = {
  key: 0,
  class: "kb-tip"
};
const _hoisted_35 = { class: "kb-doc-list" };
const _hoisted_36 = { class: "kb-doc-main" };
const _hoisted_37 = ["title"];
const _hoisted_38 = { class: "kb-doc-meta" };
const _hoisted_39 = {
  key: 0,
  class: "kb-doc-chunks"
};
const _hoisted_40 = {
  key: 1,
  class: "kb-doc-chunks"
};
const _hoisted_41 = {
  key: 2,
  class: "kb-doc-chunks is-warn"
};
const _hoisted_42 = {
  key: 3,
  class: "kb-doc-chunks is-error"
};
const _hoisted_43 = { class: "kb-doc-ops" };
const _hoisted_44 = ["onClick"];
const _hoisted_45 = ["onClick"];
const _hoisted_46 = ["onClick"];
const _hoisted_47 = {
  key: 0,
  class: "kb-doc-empty"
};
const _hoisted_48 = { class: "kb-probe" };
const _hoisted_49 = { class: "kb-probe-row" };
const _hoisted_50 = ["disabled"];
const _hoisted_51 = {
  key: 0,
  class: "kb-probe-result"
};
const _hoisted_52 = {
  key: 0,
  class: "kb-probe-empty"
};
const _hoisted_53 = {
  key: 1,
  class: "kb-probe-hits"
};
const _hoisted_54 = { class: "kb-probe-count" };
const _hoisted_55 = { class: "kb-probe-source" };
const _hoisted_56 = { class: "kb-probe-text" };
const _hoisted_57 = { class: "kb-chunks" };
const _hoisted_58 = { class: "kb-chunk-head" };
const _hoisted_59 = { class: "kb-chunk-idx" };
const _hoisted_60 = { class: "kb-chunk-len" };
const _hoisted_61 = { class: "kb-chunk-text" };
const _hoisted_62 = {
  key: 0,
  class: "kb-doc-empty"
};
const _hoisted_63 = { class: "kb-import" };
const _hoisted_64 = /* @__PURE__ */ _withScopeId(() => /* @__PURE__ */ _createElementVNode(
  "div",
  { class: "kb-import-hint" },
  " \u628A\u6B63\u6587\u76F4\u63A5\u7C98\u8FDB\u6765\u5C31\u884C \u2014\u2014 \u4E0D\u7528\u5148\u5B58\u6210 txt / Word \u518D\u4E0A\u4F20\uFF0C\u4E5F\u4E0D\u7ECF\u8FC7\u6587\u4EF6\u89E3\u6790\u3002 \u5BFC\u5165\u540E\u667A\u80FD\u4F53\u4E00\u6837\u80FD\u68C0\u7D22\u5230\u5B83\u3002 ",
  -1
  /* HOISTED */
));
const _hoisted_65 = { class: "kb-import-count" };
function _sfc_render(_ctx, _cache, $props, $setup, $data, $options) {
  const _component_el_button = _resolveComponent("el-button");
  const _component_el_icon = _resolveComponent("el-icon");
  const _component_el_switch = _resolveComponent("el-switch");
  const _component_el_tag = _resolveComponent("el-tag");
  const _component_el_drawer = _resolveComponent("el-drawer");
  const _component_el_dialog = _resolveComponent("el-dialog");
  const _component_el_input = _resolveComponent("el-input");
  const _directive_loading = _resolveDirective("loading");
  return _openBlock(), _createElementBlock(
    _Fragment,
    null,
    [
      _createCommentVNode(" \u5165\u53E3\u6309\u94AE\uFF1A\u7ED3\u6784\u4E0E\u89C2\u611F\u5BF9\u9F50 ChatInputArea \u7684 .toolbar-btn\uFF08\u90A3\u8FB9\u662F scoped\uFF0C\n       \u8FD9\u91CC\u7528\u4E0D\u4E86\u5B83\u7684 class\uFF0C\u6240\u4EE5\u81EA\u5DF1\u5199\u4E00\u4EFD\u540C\u6837\u7684\u6837\u5F0F\uFF09 "),
      _createElementVNode("button", {
        class: "kb-entry",
        title: $setup.kbTitle,
        onClick: _withModifiers($setup.open, ["stop"])
      }, [
        _hoisted_2,
        $setup.kbCount ? (_openBlock(), _createElementBlock(
          "span",
          _hoisted_3,
          _toDisplayString($setup.kbCount),
          1
          /* TEXT */
        )) : _createCommentVNode("v-if", true)
      ], 8, _hoisted_1),
      _createVNode(_component_el_drawer, {
        modelValue: $setup.visible,
        "onUpdate:modelValue": _cache[7] || (_cache[7] = ($event) => $setup.visible = $event),
        direction: "rtl",
        size: "560px",
        "with-header": false,
        "append-to-body": "",
        class: "kb-drawer",
        onOpen: $setup.onOpen,
        onClosed: $setup.clearPollTimers
      }, {
        default: _withCtx(() => [
          _createElementVNode("div", _hoisted_4, [
            _createCommentVNode(" \u2500\u2500 \u5934\u90E8 \u2500\u2500 "),
            _createElementVNode("div", _hoisted_5, [
              _hoisted_6,
              _createElementVNode("div", _hoisted_7, [
                _createVNode(_component_el_button, {
                  size: "small",
                  icon: $setup.Plus,
                  disabled: $setup.creating,
                  onClick: $setup.promptCreate
                }, {
                  default: _withCtx(() => [
                    _createTextVNode("\u65B0\u5EFA")
                  ]),
                  _: 1
                  /* STABLE */
                }, 8, ["icon", "disabled"]),
                _createElementVNode("span", {
                  class: "kb-close",
                  title: "\u6536\u8D77",
                  onClick: _cache[0] || (_cache[0] = ($event) => $setup.visible = false)
                }, [
                  _createVNode(_component_el_icon, null, {
                    default: _withCtx(() => [
                      _createVNode($setup["Close"])
                    ]),
                    _: 1
                    /* STABLE */
                  })
                ])
              ])
            ]),
            _withDirectives((_openBlock(), _createElementBlock("div", _hoisted_8, [
              _createCommentVNode(" \u300C\u5217\u8868\u6CA1\u53D6\u5230\u300D\u4E0D\u662F\u300C\u6CA1\u6709\u77E5\u8BC6\u5E93\u300D\uFF0C\u5FC5\u987B\u663E\u5F0F\u8BF4\u51FA\u6765\u3002\n             \u9759\u9ED8\u8DF3\u8FC7\u7684\u8BDD\u4E0B\u9762 `.kb-empty` \u4F1A\u9000\u5316\u6210\u300C\u8FD8\u6CA1\u6709\u77E5\u8BC6\u5E93\uFF0C\u65B0\u5EFA\u4E00\u4E2A\u2026\u300D\u2014\u2014\n             \u4E00\u4E2A\u6709\u5341\u51E0\u4E2A\u5E93\u7684\u7528\u6237\u4F1A\u88AB\u544A\u77E5\u4ED6\u4E00\u4E2A\u5E93\u90FD\u6CA1\u6709\u3002 "),
              !$setup.loading && $setup.kbLoadFailed ? (_openBlock(), _createElementBlock("div", _hoisted_9, [
                _hoisted_10,
                _createVNode(_component_el_button, {
                  size: "small",
                  text: "",
                  type: "primary",
                  onClick: _cache[1] || (_cache[1] = ($event) => $setup.loadKbs())
                }, {
                  default: _withCtx(() => [
                    _createTextVNode("\u91CD\u8BD5")
                  ]),
                  _: 1
                  /* STABLE */
                })
              ])) : _createCommentVNode("v-if", true),
              _createCommentVNode(" \u2500\u2500 \u77E5\u8BC6\u5E93\u5217\u8868 \u2500\u2500 "),
              _createCommentVNode(" \u641C\u7D22\u6846\u7559\u5728\u5217\u8868**\u5916\u9762**\uFF1A\u5217\u8868\u81EA\u5DF1\u6709 max-height + \u6EDA\u52A8\u6761\uFF08\u5E93\u591A\u4E86\u8981\u80FD\u6EDA\uFF09\uFF0C\n             \u641C\u7D22\u6846\u8DDF\u7740\u4E00\u8D77\u6EDA\u7684\u8BDD\uFF0C\u7FFB\u5230\u4E00\u534A\u5C31\u6CA1\u6CD5\u6539\u5173\u952E\u8BCD\u4E86 "),
              $setup.kbs.length ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
                _withDirectives(_createElementVNode(
                  "input",
                  {
                    "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => $setup.kbFilter = $event),
                    class: "kb-filter-input",
                    placeholder: "\u641C\u7D22\u77E5\u8BC6\u5E93\u540D\u5B57\u2026"
                  },
                  null,
                  512
                  /* NEED_PATCH */
                ), [
                  [_vModelText, $setup.kbFilter]
                ]),
                $setup.kbFilter ? (_openBlock(), _createElementBlock("span", {
                  key: 0,
                  class: "kb-filter-clear",
                  title: "\u6E05\u7A7A\u641C\u7D22",
                  onClick: _cache[3] || (_cache[3] = ($event) => $setup.kbFilter = "")
                }, [
                  _createVNode(_component_el_icon, null, {
                    default: _withCtx(() => [
                      _createVNode($setup["Close"])
                    ]),
                    _: 1
                    /* STABLE */
                  })
                ])) : _createCommentVNode("v-if", true)
              ])) : _createCommentVNode("v-if", true),
              _createElementVNode("div", _hoisted_12, [
                (_openBlock(true), _createElementBlock(
                  _Fragment,
                  null,
                  _renderList($setup.filteredKbs, (kb) => {
                    return _openBlock(), _createElementBlock("div", {
                      key: kb.kbId,
                      class: _normalizeClass(["kb-item", { active: kb.kbId === $setup.activeKbId, blocked: kb.disabled === 1 }]),
                      onClick: ($event) => $setup.selectKb(kb)
                    }, [
                      _createElementVNode("div", _hoisted_14, [
                        _createElementVNode("div", {
                          class: "kb-item-name",
                          title: kb.name
                        }, _toDisplayString(kb.name), 9, _hoisted_15),
                        _createElementVNode("div", _hoisted_16, [
                          _createElementVNode(
                            "span",
                            null,
                            _toDisplayString(kb.docCount || 0) + " \u7BC7\u6587\u6863",
                            1
                            /* TEXT */
                          ),
                          _createElementVNode(
                            "span",
                            null,
                            _toDisplayString(kb.chunkCount || 0) + " \u4E2A\u5206\u5757",
                            1
                            /* TEXT */
                          ),
                          _createCommentVNode(" \u5C4F\u853D\u72B6\u6001**\u5E38\u9A7B**\u663E\u793A\uFF1A\u7528\u6237\u8981\u80FD\u4E00\u773C\u770B\u51FA\u300C\u54EA\u4E9B\u5E93\u667A\u80FD\u4F53\u73B0\u5728\u770B\u4E0D\u5230\u300D "),
                          kb.disabled === 1 ? (_openBlock(), _createElementBlock("span", _hoisted_17, "\u5DF2\u5C4F\u853D")) : _createCommentVNode("v-if", true)
                        ])
                      ]),
                      _createCommentVNode(" \u5C4F\u853D\u5F00\u5173\u653E\u5728 .kb-item-ops **\u5916\u9762**\uFF1A\u90A3\u8FB9\u662F `opacity: 0`\uFF08hover \u624D\u663E\u5F62\uFF09\uFF0C\n                 \u5F00\u5173\u653E\u8FDB\u53BB\u7684\u8BDD\u300C\u54EA\u4E2A\u5E93\u88AB\u5C4F\u853D\u4E86\u300D\u5728\u5217\u8868\u4E0A\u6839\u672C\u770B\u4E0D\u51FA\u6765 \u2014\u2014\n                 \u800C\u300C\u4E00\u773C\u770B\u51FA\u54EA\u4E9B\u5E93\u88AB\u5C4F\u853D\u300D\u6B63\u662F\u7528\u6237\u62E8\u5B83\u7684\u76EE\u7684\u3002\n                 \u88AB\u5C4F\u853D\u7684\u5E93**\u4ECD\u7136\u7559\u5728\u5217\u8868\u91CC**\uFF08\u540E\u7AEF\u4E5F\u6545\u610F\u4FDD\u7559\uFF09\uFF0C\u5426\u5219\u5C31\u6CA1\u6CD5\u53D6\u6D88\u5C4F\u853D\u4E86\u3002\n\n                 \u5F00\u5173\u300C\u5F00\u300D= \u667A\u80FD\u4F53**\u53EF\u4EE5**\u67E5\u5230\uFF08`kbEnabled`\uFF09\u3002\u9ED8\u8BA4\u5168\u5F00\uFF0C\u6240\u4EE5\u540E\u7AEF\u8FD8\u6CA1\u4E0B\u53D1\n                 `disabled` \u65F6\uFF08undefined\uFF09\u770B\u5230\u7684\u662F\u4E00\u7247\u300C\u53EF\u67E5\u300D\uFF0C\u4E0D\u4F1A\u88AB\u8BEF\u8BFB\u6210\u300C\u5168\u88AB\u5C4F\u853D\u4E86\u300D\u3002\n\n                 \u26A0\uFE0F `:model-value` \u7ED1\u7684\u662F**\u5E03\u5C14\u8868\u8FBE\u5F0F**\uFF0C\u4E0D\u662F `kb.disabled` \u672C\u8EAB\uFF0C\u4E5F**\u4E0D\u8981**\u52A0\n                    `:active-value` / `:inactive-value` \u2014\u2014 \u89C1 `kbEnabled` \u7684\u6CE8\u91CA\uFF1A\u7ED1\u5B9A\u503C\u4E00\u65E6\u4E0D\u5728\n                    `[activeValue, inactiveValue]` \u91CC\uFF0Cel-switch \u4F1A\u5728\u6302\u8F7D\u671F**\u65E0\u7528\u6237\u64CD\u4F5C\u5730** emit \u4E00\u6B21\u3002 "),
                      _createElementVNode("span", {
                        class: "kb-block",
                        onClick: _cache[4] || (_cache[4] = _withModifiers(() => {
                        }, ["stop"])),
                        title: $setup.kbEnabled(kb) ? "\u667A\u80FD\u4F53\u63D0\u95EE\u4E0E\u8BD5\u68C0\u7D22\u90FD\u4F1A\u67E5\u8FD9\u4E2A\u5E93\uFF1B\u5173\u6389\u5B83\u5C31\u4E0D\u518D\u67E5" : "\u5DF2\u5C4F\u853D\uFF1A\u667A\u80FD\u4F53\u63D0\u95EE\u4E0E\u8BD5\u68C0\u7D22\u90FD\u4E0D\u4F1A\u518D\u67E5\u8FD9\u4E2A\u5E93"
                      }, [
                        _createVNode(_component_el_switch, {
                          "model-value": $setup.kbEnabled(kb),
                          size: "small",
                          loading: $setup.togglingKbId === kb.kbId,
                          "onUpdate:modelValue": ($event) => $setup.toggleKbDisabled(kb, $event)
                        }, null, 8, ["model-value", "loading", "onUpdate:modelValue"])
                      ], 8, _hoisted_18),
                      _createElementVNode("div", _hoisted_19, [
                        _createElementVNode("span", {
                          class: "kb-op",
                          title: "\u91CD\u547D\u540D",
                          onClick: _withModifiers(($event) => $setup.promptRename(kb), ["stop"])
                        }, [
                          _createVNode(_component_el_icon, null, {
                            default: _withCtx(() => [
                              _createVNode($setup["EditPen"])
                            ]),
                            _: 1
                            /* STABLE */
                          })
                        ], 8, _hoisted_20),
                        _createElementVNode("span", {
                          class: "kb-op danger",
                          title: "\u5220\u9664\u77E5\u8BC6\u5E93",
                          onClick: _withModifiers(($event) => $setup.removeKb(kb), ["stop"])
                        }, [
                          _createVNode(_component_el_icon, null, {
                            default: _withCtx(() => [
                              _createVNode($setup["Delete"])
                            ]),
                            _: 1
                            /* STABLE */
                          })
                        ], 8, _hoisted_21)
                      ])
                    ], 10, _hoisted_13);
                  }),
                  128
                  /* KEYED_FRAGMENT */
                )),
                !$setup.loading && !$setup.kbLoadFailed && !$setup.kbs.length ? (_openBlock(), _createElementBlock("div", _hoisted_22, [
                  _hoisted_23,
                  _hoisted_24,
                  _createVNode(_component_el_button, {
                    type: "primary",
                    size: "small",
                    icon: $setup.Plus,
                    onClick: $setup.promptCreate
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode("\u65B0\u5EFA\u77E5\u8BC6\u5E93")
                    ]),
                    _: 1
                    /* STABLE */
                  }, 8, ["icon"])
                ])) : _createCommentVNode("v-if", true),
                _createCommentVNode(" \u300C\u641C\u7D22\u6CA1\u547D\u4E2D\u300D\u4E0E\u300C\u4E00\u4E2A\u77E5\u8BC6\u5E93\u90FD\u6CA1\u6709\u300D\u662F\u4E24\u4EF6\u4E8B\uFF0C\u6587\u6848\u5FC5\u987B\u5206\u5F00 \u2014\u2014\n               \u5171\u7528\u540C\u4E00\u53E5\u300C\u8FD8\u6CA1\u6709\u77E5\u8BC6\u5E93\u300D\u4F1A\u8BA9\u7528\u6237\u4EE5\u4E3A\u81EA\u5DF1\u7684\u5E93\u88AB\u6E05\u7A7A\u4E86\u3002\n               \u6CE8\u610F\u8FD9\u91CC\u5199\u6210\u72EC\u7ACB\u7684 v-if \u800C\u4E0D\u662F v-else-if\uFF1A\u6761\u4EF6\u91CC\u5E26 kbs.length\uFF0C\n               \u4E24\u8005\u672C\u6765\u5C31\u4E92\u65A5\uFF0C\u4E0D\u4F9D\u8D56\u5144\u5F1F\u94FE\u7684\u8BED\u4E49\u3002 "),
                !$setup.loading && $setup.kbs.length && !$setup.filteredKbs.length ? (_openBlock(), _createElementBlock("div", _hoisted_25, [
                  _createElementVNode(
                    "div",
                    _hoisted_26,
                    "\u6CA1\u6709\u540D\u5B57\u5305\u542B\u300C" + _toDisplayString($setup.kbFilter.trim()) + "\u300D\u7684\u77E5\u8BC6\u5E93",
                    1
                    /* TEXT */
                  ),
                  _createElementVNode(
                    "div",
                    _hoisted_27,
                    "\u6362\u4E2A\u5173\u952E\u8BCD\u8BD5\u8BD5\uFF0C\u6216\u8005\u6E05\u7A7A\u641C\u7D22\u770B\u5168\u90E8 " + _toDisplayString($setup.kbCount) + " \u4E2A\u77E5\u8BC6\u5E93\u3002",
                    1
                    /* TEXT */
                  ),
                  _createVNode(_component_el_button, {
                    size: "small",
                    onClick: _cache[5] || (_cache[5] = ($event) => $setup.kbFilter = "")
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode("\u6E05\u7A7A\u641C\u7D22")
                    ]),
                    _: 1
                    /* STABLE */
                  })
                ])) : _createCommentVNode("v-if", true)
              ]),
              _createCommentVNode(" \u2500\u2500 \u9009\u4E2D\u5E93\u7684\u6587\u6863 \u2500\u2500 "),
              $setup.activeKbId ? (_openBlock(), _createElementBlock("div", _hoisted_28, [
                _createElementVNode("div", _hoisted_29, [
                  _createElementVNode(
                    "span",
                    _hoisted_30,
                    _toDisplayString($setup.activeKb?.name),
                    1
                    /* TEXT */
                  ),
                  _createElementVNode(
                    "span",
                    _hoisted_31,
                    "\u652F\u6301 " + _toDisplayString($setup.KB_FILE_EXTENSIONS.join(" / ")),
                    1
                    /* TEXT */
                  ),
                  _createElementVNode(
                    "label",
                    {
                      class: _normalizeClass(["kb-upload-btn", { disabled: $setup.busy }])
                    },
                    [
                      _createElementVNode("input", {
                        ref: "fileInputRef",
                        type: "file",
                        accept: $setup.KB_FILE_ACCEPT,
                        multiple: "",
                        disabled: $setup.busy,
                        onChange: $setup.onFilesPicked
                      }, null, 40, _hoisted_32),
                      _createVNode(_component_el_icon, null, {
                        default: _withCtx(() => [
                          _createVNode($setup["UploadFilled"])
                        ]),
                        _: 1
                        /* STABLE */
                      }),
                      _createElementVNode(
                        "span",
                        null,
                        _toDisplayString($setup.uploading ? "\u4E0A\u4F20\u4E2D\u2026" : "\u4E0A\u4F20\u6587\u6863"),
                        1
                        /* TEXT */
                      )
                    ],
                    2
                    /* CLASS */
                  ),
                  _createCommentVNode(" \u7C98\u8D34\u6587\u672C\uFF1A\u7528\u6237\u81EA\u5DF1\u6572/\u7C98\u7684\u6587\u5B57\u76F4\u63A5\u5165\u5E93\uFF0C**\u4E0D\u7ECF\u8FC7\u6587\u4EF6\u89E3\u6790**\u3002\n                 \u4E0E\u300C\u4E0A\u4F20\u6587\u6863\u300D\u5171\u7528 busy \u4E92\u65A5 \u2014\u2014 \u4E24\u4E2A\u5165\u53E3\u5F80\u540C\u4E00\u4E2A\u5E93\u91CC\u5199\u6587\u6863\uFF0C\n                 \u540C\u65F6\u8DD1\u8D77\u6765\u7684\u8BDD\u8FDB\u5EA6\u63D0\u793A\u4E0E\u8F6E\u8BE2\u4F1A\u4E92\u76F8\u8986\u76D6\u3002 "),
                  _createElementVNode("button", {
                    type: "button",
                    class: _normalizeClass(["kb-import-btn", { disabled: $setup.busy }]),
                    disabled: $setup.busy,
                    title: $setup.busy ? "\u6709\u5BFC\u5165\u6B63\u5728\u8FDB\u884C\uFF0C\u7B49\u5B83\u8DD1\u5B8C" : "\u628A\u6587\u5B57\u76F4\u63A5\u7C98\u8FDB\u6765\uFF0C\u4E0D\u7528\u5148\u5B58\u6210\u6587\u4EF6",
                    onClick: $setup.openTextImport
                  }, [
                    _createVNode(_component_el_icon, null, {
                      default: _withCtx(() => [
                        _createVNode($setup["DocumentCopy"])
                      ]),
                      _: 1
                      /* STABLE */
                    }),
                    _createElementVNode(
                      "span",
                      null,
                      _toDisplayString($setup.importing ? "\u5BFC\u5165\u4E2D\u2026" : "\u7C98\u8D34\u6587\u672C"),
                      1
                      /* TEXT */
                    )
                  ], 10, _hoisted_33)
                ]),
                _createCommentVNode(" \u4E0A\u4F20\u8FDB\u5EA6\u63D0\u793A\uFF08\u540E\u7AEF\u662F\u540C\u6B65\u89E3\u6790 + \u540E\u53F0\u5411\u91CF\u5316\uFF0C\u6240\u4EE5\u8FD9\u91CC\u8BF4\u660E\u6E05\u695A\uFF09 "),
                $setup.uploadTip ? (_openBlock(), _createElementBlock(
                  "div",
                  _hoisted_34,
                  _toDisplayString($setup.uploadTip),
                  1
                  /* TEXT */
                )) : _createCommentVNode("v-if", true),
                _withDirectives((_openBlock(), _createElementBlock("div", _hoisted_35, [
                  (_openBlock(true), _createElementBlock(
                    _Fragment,
                    null,
                    _renderList($setup.documents, (doc) => {
                      return _openBlock(), _createElementBlock("div", {
                        key: doc.docId,
                        class: "kb-doc"
                      }, [
                        _createElementVNode("div", _hoisted_36, [
                          _createElementVNode("div", {
                            class: "kb-doc-name",
                            title: doc.fileName
                          }, _toDisplayString(doc.fileName), 9, _hoisted_37),
                          _createElementVNode("div", _hoisted_38, [
                            _createVNode(_component_el_tag, {
                              type: $setup.documentTagType(doc.status),
                              size: "small",
                              effect: "light"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(
                                  _toDisplayString(doc.statusText || doc.status),
                                  1
                                  /* TEXT */
                                )
                              ]),
                              _: 2
                              /* DYNAMIC */
                            }, 1032, ["type"]),
                            $setup.isDocumentSearchable(doc.status) ? (_openBlock(), _createElementBlock(
                              "span",
                              _hoisted_39,
                              _toDisplayString(doc.chunkCount || 0) + " \u4E2A\u5206\u5757 ",
                              1
                              /* TEXT */
                            )) : $setup.isDocumentProcessing(doc.status) ? (_openBlock(), _createElementBlock("span", _hoisted_40, " \u5904\u7406\u4E2D\uFF0C\u7A0D\u7B49\u7247\u523B\u2026 ")) : doc.status === $setup.DOC_PARSED ? (_openBlock(), _createElementBlock("span", _hoisted_41, " \u5DF2\u63D0\u53D6\u6B63\u6587\uFF0C\u5C1A\u672A\u5411\u91CF\u5316 \u2014\u2014 \u73B0\u5728\u68C0\u7D22\u4E0D\u5230\u5B83 ")) : doc.status === $setup.DOC_FAILED ? (_openBlock(), _createElementBlock(
                              "span",
                              _hoisted_42,
                              _toDisplayString(doc.errorMsg || "\u5904\u7406\u5931\u8D25"),
                              1
                              /* TEXT */
                            )) : _createCommentVNode("v-if", true)
                          ])
                        ]),
                        _createElementVNode("div", _hoisted_43, [
                          $setup.isDocumentSearchable(doc.status) ? (_openBlock(), _createElementBlock("span", {
                            key: 0,
                            class: "kb-op",
                            title: "\u770B\u770B\u5206\u5757\u5207\u5F97\u5BF9\u4E0D\u5BF9",
                            onClick: ($event) => $setup.showChunks(doc)
                          }, [
                            _createVNode(_component_el_icon, null, {
                              default: _withCtx(() => [
                                _createVNode($setup["View"])
                              ]),
                              _: 1
                              /* STABLE */
                            })
                          ], 8, _hoisted_44)) : _createCommentVNode("v-if", true),
                          $setup.canReprocessDocument(doc.status) ? (_openBlock(), _createElementBlock("span", {
                            key: 1,
                            class: "kb-op",
                            title: "\u91CD\u65B0\u89E3\u6790\u5E76\u5411\u91CF\u5316",
                            onClick: ($event) => $setup.reprocess(doc)
                          }, [
                            _createVNode(_component_el_icon, null, {
                              default: _withCtx(() => [
                                _createVNode($setup["RefreshRight"])
                              ]),
                              _: 1
                              /* STABLE */
                            })
                          ], 8, _hoisted_45)) : _createCommentVNode("v-if", true),
                          _createElementVNode("span", {
                            class: "kb-op danger",
                            title: "\u5220\u9664\u6587\u6863",
                            onClick: ($event) => $setup.removeDoc(doc)
                          }, [
                            _createVNode(_component_el_icon, null, {
                              default: _withCtx(() => [
                                _createVNode($setup["Delete"])
                              ]),
                              _: 1
                              /* STABLE */
                            })
                          ], 8, _hoisted_46)
                        ])
                      ]);
                    }),
                    128
                    /* KEYED_FRAGMENT */
                  )),
                  !$setup.docsLoading && !$setup.documents.length ? (_openBlock(), _createElementBlock("div", _hoisted_47, " \u8FD9\u4E2A\u77E5\u8BC6\u5E93\u8FD8\u6CA1\u6709\u6587\u6863\uFF0C\u70B9\u53F3\u4E0A\u89D2\u300C\u4E0A\u4F20\u6587\u6863\u300D ")) : _createCommentVNode("v-if", true)
                ])), [
                  [_directive_loading, $setup.docsLoading]
                ]),
                _createCommentVNode(" \u8BD5\u68C0\u7D22\uFF1A\u4F20\u5B8C\u8D44\u6599\u80FD\u7ACB\u523B\u9A8C\u4E00\u4E0B\u300C\u5230\u5E95\u641C\u4E0D\u641C\u5F97\u5230\u300D\u3002\n               \u771F\u6B63\u7684\u95EE\u7B54\u8FD8\u662F\u5728\u8F93\u5165\u6846\u91CC\u95EE\uFF08Agent \u4F1A\u81EA\u5DF1\u8C03 knowledge_search\uFF09\uFF0C\n               \u8FD9\u91CC\u53EA\u662F\u8BA9\u300C\u4E0A\u4F20 \u2192 \u80FD\u4E0D\u80FD\u7528\u300D\u8FD9\u6761\u53CD\u9988\u95ED\u73AF\u53D8\u77ED\u3002 "),
                _createElementVNode("div", _hoisted_48, [
                  _createElementVNode("div", _hoisted_49, [
                    _withDirectives(_createElementVNode("input", {
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => $setup.probeQuery = $event),
                      class: "kb-probe-input",
                      placeholder: "\u8BD5\u8BD5\u80FD\u4E0D\u80FD\u641C\u5230\uFF0C\u4F8B\u5982\uFF1A\u4E8C\u53C9\u641C\u7D22\u6811\u7684\u65F6\u95F4\u590D\u6742\u5EA6",
                      disabled: $setup.probing,
                      onKeydown: _withKeys($setup.runProbe, ["enter"])
                    }, null, 40, _hoisted_50), [
                      [_vModelText, $setup.probeQuery]
                    ]),
                    _createVNode(_component_el_button, {
                      size: "small",
                      type: "primary",
                      loading: $setup.probing,
                      disabled: !$setup.probeQuery.trim(),
                      onClick: $setup.runProbe
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(" \u68C0\u7D22 ")
                      ]),
                      _: 1
                      /* STABLE */
                    }, 8, ["loading", "disabled"])
                  ]),
                  $setup.probeDone ? (_openBlock(), _createElementBlock("div", _hoisted_51, [
                    !$setup.probeHits.length ? (_openBlock(), _createElementBlock("div", _hoisted_52, " \u6CA1\u68C0\u7D22\u5230\u76F8\u5173\u5185\u5BB9\u3002\u53EF\u80FD\u662F\u8D44\u6599\u91CC\u786E\u5B9E\u6CA1\u6709\uFF0C\u4E5F\u53EF\u80FD\u6362\u4E2A\u8BF4\u6CD5\u5C31\u884C\u4E86\u3002 ")) : (_openBlock(), _createElementBlock("div", _hoisted_53, [
                      _createElementVNode(
                        "div",
                        _hoisted_54,
                        "\u547D\u4E2D " + _toDisplayString($setup.probeHits.length) + " \u6BB5",
                        1
                        /* TEXT */
                      ),
                      (_openBlock(true), _createElementBlock(
                        _Fragment,
                        null,
                        _renderList($setup.probeHits, (h) => {
                          return _openBlock(), _createElementBlock("div", {
                            key: h.chunkId,
                            class: "kb-probe-hit"
                          }, [
                            _createElementVNode(
                              "div",
                              _hoisted_55,
                              _toDisplayString(h.source || h.docName),
                              1
                              /* TEXT */
                            ),
                            _createElementVNode(
                              "div",
                              _hoisted_56,
                              _toDisplayString(h.content),
                              1
                              /* TEXT */
                            )
                          ]);
                        }),
                        128
                        /* KEYED_FRAGMENT */
                      ))
                    ]))
                  ])) : _createCommentVNode("v-if", true)
                ])
              ])) : _createCommentVNode("v-if", true)
            ])), [
              [_directive_loading, $setup.loading]
            ])
          ])
        ]),
        _: 1
        /* STABLE */
      }, 8, ["modelValue"]),
      _createCommentVNode(" \u5206\u5757\u9884\u89C8 "),
      _createVNode(_component_el_dialog, {
        modelValue: $setup.chunksVisible,
        "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => $setup.chunksVisible = $event),
        title: `\u5206\u5757\u9884\u89C8 \xB7 ${$setup.chunkDocName}`,
        width: "680px",
        "append-to-body": ""
      }, {
        default: _withCtx(() => [
          _withDirectives((_openBlock(), _createElementBlock("div", _hoisted_57, [
            (_openBlock(true), _createElementBlock(
              _Fragment,
              null,
              _renderList($setup.chunks, (c) => {
                return _openBlock(), _createElementBlock("div", {
                  key: c.chunkId,
                  class: "kb-chunk"
                }, [
                  _createElementVNode("div", _hoisted_58, [
                    _createElementVNode(
                      "span",
                      _hoisted_59,
                      "\u7B2C " + _toDisplayString(c.chunkIndex + 1) + " \u6BB5",
                      1
                      /* TEXT */
                    ),
                    _createElementVNode(
                      "span",
                      _hoisted_60,
                      _toDisplayString(c.contentLength || c.content.length) + " \u5B57",
                      1
                      /* TEXT */
                    ),
                    c.vectorized === false ? (_openBlock(), _createBlock(_component_el_tag, {
                      key: 0,
                      type: "warning",
                      size: "small",
                      effect: "light"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode("\u65E0\u5411\u91CF")
                      ]),
                      _: 1
                      /* STABLE */
                    })) : _createCommentVNode("v-if", true)
                  ]),
                  _createElementVNode(
                    "div",
                    _hoisted_61,
                    _toDisplayString(c.content),
                    1
                    /* TEXT */
                  )
                ]);
              }),
              128
              /* KEYED_FRAGMENT */
            )),
            !$setup.chunksLoading && !$setup.chunks.length ? (_openBlock(), _createElementBlock("div", _hoisted_62, "\u6CA1\u6709\u5206\u5757")) : _createCommentVNode("v-if", true)
          ])), [
            [_directive_loading, $setup.chunksLoading]
          ])
        ]),
        _: 1
        /* STABLE */
      }, 8, ["modelValue", "title"]),
      _createCommentVNode(" \u7C98\u8D34\u6587\u672C\u5BFC\u5165\uFF1A\u628A\u7528\u6237\u81EA\u5DF1\u8F93\u5165\u7684\u6B63\u6587\u76F4\u63A5\u6536\u8FDB\u77E5\u8BC6\u5E93\uFF08\u540E\u7AEF `/document/uploadText`\uFF0C\u4E0D\u8D70\u6587\u4EF6\u89E3\u6790\uFF09 "),
      _createVNode(_component_el_dialog, {
        modelValue: $setup.textImportVisible,
        "onUpdate:modelValue": _cache[12] || (_cache[12] = ($event) => $setup.textImportVisible = $event),
        title: "\u7C98\u8D34\u6587\u672C",
        width: "640px",
        "append-to-body": "",
        onClosed: $setup.resetTextImport
      }, {
        footer: _withCtx(() => [
          _createVNode(_component_el_button, {
            onClick: _cache[11] || (_cache[11] = ($event) => $setup.textImportVisible = false)
          }, {
            default: _withCtx(() => [
              _createTextVNode("\u53D6\u6D88")
            ]),
            _: 1
            /* STABLE */
          }),
          _createVNode(_component_el_button, {
            type: "primary",
            loading: $setup.importing,
            disabled: !$setup.textImportContent.trim(),
            onClick: $setup.submitTextImport
          }, {
            default: _withCtx(() => [
              _createTextVNode(" \u5BFC\u5165 ")
            ]),
            _: 1
            /* STABLE */
          }, 8, ["loading", "disabled"])
        ]),
        default: _withCtx(() => [
          _createElementVNode("div", _hoisted_63, [
            _hoisted_64,
            _createVNode(_component_el_input, {
              modelValue: $setup.textImportFileName,
              "onUpdate:modelValue": _cache[9] || (_cache[9] = ($event) => $setup.textImportFileName = $event),
              class: "kb-import-name",
              placeholder: "\u672A\u547D\u540D\u6587\u6863.txt",
              clearable: ""
            }, {
              prepend: _withCtx(() => [
                _createTextVNode("\u6587\u4EF6\u540D")
              ]),
              _: 1
              /* STABLE */
            }, 8, ["modelValue"]),
            _createVNode(_component_el_input, {
              modelValue: $setup.textImportContent,
              "onUpdate:modelValue": _cache[10] || (_cache[10] = ($event) => $setup.textImportContent = $event),
              class: "kb-import-text",
              type: "textarea",
              autosize: { minRows: 10, maxRows: 18 },
              resize: "vertical",
              placeholder: "\u628A\u8981\u6536\u8FDB\u77E5\u8BC6\u5E93\u7684\u6B63\u6587\u7C98\u5728\u8FD9\u91CC\uFF0C\u4F8B\u5982\u8BFE\u4EF6\u6587\u5B57\u3001\u7B14\u8BB0\u3001\u9519\u9898\u89E3\u6790\u2026"
            }, null, 8, ["modelValue"]),
            _createElementVNode(
              "div",
              _hoisted_65,
              _toDisplayString($setup.textImportContent.trim().length) + " \u5B57",
              1
              /* TEXT */
            )
          ])
        ]),
        _: 1
        /* STABLE */
      }, 8, ["modelValue"])
    ],
    64
    /* STABLE_FRAGMENT */
  );
}
import "/src/components/KnowledgeBaseDrawer/index.vue?t=1789908106338&vue&type=style&index=0&scoped=fccbca24&lang.css";
_sfc_main.__hmrId = "fccbca24";
typeof __VUE_HMR_RUNTIME__ !== "undefined" && __VUE_HMR_RUNTIME__.createRecord(_sfc_main.__hmrId, _sfc_main);
export const _rerender_only = true;
import.meta.hot.accept((mod) => {
  if (!mod)
    return;
  const { default: updated, _rerender_only: _rerender_only2 } = mod;
  if (_rerender_only2) {
    __VUE_HMR_RUNTIME__.rerender(updated.__hmrId, updated.render);
  } else {
    __VUE_HMR_RUNTIME__.reload(updated.__hmrId, updated);
  }
});
import _export_sfc from "/@id/__x00__plugin-vue:export-helper";
export default /* @__PURE__ */ _export_sfc(_sfc_main, [["render", _sfc_render], ["__scopeId", "data-v-fccbca24"], ["__file", "D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts/src/components/KnowledgeBaseDrawer/index.vue"]]);

//# sourceMappingURL=data:application/json;base64,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QUFBQSxjQUFpQixNQUFLO0FBQUEsY0FDL0QsVUFBVTtBQUFBLGNBQThCLFFBQU87QUFBQSxjQUNoRCxhQUFZO0FBQUE7WUFDZDtBQUFBLGNBQTBFO0FBQUEsY0FBMUU7QUFBQSxjQUEwRSxpQkFBMUMseUJBQWtCLEtBQUksRUFBRyxNQUFNLElBQUc7QUFBQSxjQUFFO0FBQUE7QUFBQTtBQUFBIiwibmFtZXMiOltdLCJzb3VyY2VzIjpbImluZGV4LnZ1ZSJdLCJzb3VyY2VzQ29udGVudCI6WyI8IS0tIGNvbXBvbmVudHMvS25vd2xlZGdlQmFzZURyYXdlci9pbmRleC52dWUgLS0+XG48IS0tXG4gIOefpeivhuW6k++8iOW1jOWcqOaZuuiDveS9k+mhtemdoumHjO+8iVxuXG4gIOS4uuS7gOS5iOWBmuaIkOOAjOi+k+WFpeagj+aMiemSriArIOaKveWxieOAjeiAjOS4jeaYr+eLrOeri+mhtemdou+8mlxuICAgIMK3IOefpeivhuW6k+aYryoq57uZ6L+Z5qyh5o+Q6Zeu55So55qE6LWE5paZKirvvIzlhaXlj6PlsLHor6XlnKjjgIzlj5Hmtojmga/jgI3nmoTlnLDmlrkg4oCU4oCUXG4gICAgICDnlKjmiLfkvKDlrozotYTmlpnpqazkuIrog73pl67vvIzkuI3nlKjot7PpobXpnaLjgIHot7Plm57mnaXjgIHlho3mib7kvJror53vvJtcbiAgICDCtyDmir3lsYnkuI3ljaDluIPlsYDvvIzkuI7pobXpnaLml6LmnInnmoTljoblj7LkvJror53kvqfmoI/vvIjlt6bkvqfvvInliIblt6XmuIXmpZrvvJpcbiAgICAgIOW3pui+ueaYr+OAjOiBiui/h+S7gOS5iOOAje+8jOWPs+i+ueaYr+OAjOaJi+S4iuacieS7gOS5iOi1hOaWmeOAjeOAglxuXG4gIOi/memHjOeahOiBjOi0o+aYryoq566h55CG6LWE5paZKirvvIjlu7rlupMgLyDkvKDmlofmoaMgLyDnnIvnirbmgIEgLyDliKDvvInjgIIqKumXruetlOS4jeWcqOi/memHjOWBmioqIOKAlOKAlFxuICDnlKjmiLfnm7TmjqXlnKjovpPlhaXmoYbmj5Dpl67vvIxBZ2VudCDkvJroh6rlt7HnlKggYGtub3dsZWRnZV9zZWFyY2hgIOWOu+ajgOe0olxuICDvvIjlkI7nq68gTDEg5rOo5YWl6L+Y5Lya5oqK55+l6K+G5bqT5riF5Y2V5aGe6L+b57O757uf5o+Q56S66K+N77yM5qih5Z6L55+l6YGT5pyJ5ZOq5Lqb5bqT5Y+v5p+l77yJ44CCXG4tLT5cbjx0ZW1wbGF0ZT5cbiAgPCEtLSDlhaXlj6PmjInpkq7vvJrnu5PmnoTkuI7op4LmhJ/lr7npvZAgQ2hhdElucHV0QXJlYSDnmoQgLnRvb2xiYXItYnRu77yI6YKj6L655pivIHNjb3BlZO+8jFxuICAgICAgIOi/memHjOeUqOS4jeS6huWug+eahCBjbGFzc++8jOaJgOS7peiHquW3seWGmeS4gOS7veWQjOagt+eahOagt+W8j++8iSAtLT5cbiAgPGJ1dHRvbiBjbGFzcz1cImtiLWVudHJ5XCIgOnRpdGxlPVwia2JUaXRsZVwiIEBjbGljay5zdG9wPVwib3BlblwiPlxuICAgIDxzdmcgdmlld0JveD1cIjAgMCAyNCAyNFwiIHdpZHRoPVwiMTVcIiBoZWlnaHQ9XCIxNVwiIGZpbGw9XCJub25lXCIgc3Ryb2tlPVwiY3VycmVudENvbG9yXCIgc3Ryb2tlLXdpZHRoPVwiMlwiXG4gICAgICBzdHJva2UtbGluZWNhcD1cInJvdW5kXCIgc3Ryb2tlLWxpbmVqb2luPVwicm91bmRcIj5cbiAgICAgIDxwYXRoIGQ9XCJNNCAxOS41QTIuNSAyLjUgMCAwIDEgNi41IDE3SDIwXCIgLz5cbiAgICAgIDxwYXRoIGQ9XCJNNi41IDJIMjB2MjBINi41QTIuNSAyLjUgMCAwIDEgNCAxOS41di0xNUEyLjUgMi41IDAgMCAxIDYuNSAyelwiIC8+XG4gICAgPC9zdmc+XG4gICAgPHNwYW4gdi1pZj1cImtiQ291bnRcIiBjbGFzcz1cImtiLWVudHJ5LWJhZGdlXCI+e3sga2JDb3VudCB9fTwvc3Bhbj5cbiAgPC9idXR0b24+XG5cbiAgPGVsLWRyYXdlciB2LW1vZGVsPVwidmlzaWJsZVwiIGRpcmVjdGlvbj1cInJ0bFwiIHNpemU9XCI1NjBweFwiIDp3aXRoLWhlYWRlcj1cImZhbHNlXCIgYXBwZW5kLXRvLWJvZHlcbiAgICBjbGFzcz1cImtiLWRyYXdlclwiIEBvcGVuPVwib25PcGVuXCIgQGNsb3NlZD1cImNsZWFyUG9sbFRpbWVyc1wiPlxuICAgIDxkaXYgY2xhc3M9XCJrYi1ib2R5XCI+XG4gICAgICA8IS0tIOKUgOKUgCDlpLTpg6gg4pSA4pSAIC0tPlxuICAgICAgPGRpdiBjbGFzcz1cImtiLWhlYWRcIj5cbiAgICAgICAgPGRpdiBjbGFzcz1cImtiLWhlYWQtbGVmdFwiPlxuICAgICAgICAgIDxzcGFuIGNsYXNzPVwia2ItdGl0bGVcIj7nn6Xor4blupM8L3NwYW4+XG4gICAgICAgICAgPHNwYW4gY2xhc3M9XCJrYi1zdWJcIj7kvKDov5vmnaXnmoTotYTmlpnvvIzmmbrog73kvZPkvJroh6rlt7Hmo4DntKLlkI7lm57nrZQ8L3NwYW4+XG4gICAgICAgIDwvZGl2PlxuICAgICAgICA8ZGl2IGNsYXNzPVwia2ItaGVhZC1yaWdodFwiPlxuICAgICAgICAgIDxlbC1idXR0b24gc2l6ZT1cInNtYWxsXCIgOmljb249XCJQbHVzXCIgOmRpc2FibGVkPVwiY3JlYXRpbmdcIiBAY2xpY2s9XCJwcm9tcHRDcmVhdGVcIj7mlrDlu7o8L2VsLWJ1dHRvbj5cbiAgICAgICAgICA8c3BhbiBjbGFzcz1cImtiLWNsb3NlXCIgdGl0bGU9XCLmlLbotbdcIiBAY2xpY2s9XCJ2aXNpYmxlID0gZmFsc2VcIj5cbiAgICAgICAgICAgIDxlbC1pY29uPjxDbG9zZSAvPjwvZWwtaWNvbj5cbiAgICAgICAgICA8L3NwYW4+XG4gICAgICAgIDwvZGl2PlxuICAgICAgPC9kaXY+XG5cbiAgICAgIDxkaXYgY2xhc3M9XCJrYi1tYWluXCIgdi1sb2FkaW5nPVwibG9hZGluZ1wiPlxuICAgICAgICA8IS0tIOOAjOWIl+ihqOayoeWPluWIsOOAjeS4jeaYr+OAjOayoeacieefpeivhuW6k+OAje+8jOW/hemhu+aYvuW8j+ivtOWHuuadpeOAglxuICAgICAgICAgICAgIOmdmem7mOi3s+i/h+eahOivneS4i+mdoiBgLmtiLWVtcHR5YCDkvJrpgIDljJbmiJDjgIzov5jmsqHmnInnn6Xor4blupPvvIzmlrDlu7rkuIDkuKrigKbjgI3igJTigJRcbiAgICAgICAgICAgICDkuIDkuKrmnInljYHlh6DkuKrlupPnmoTnlKjmiLfkvJrooqvlkYrnn6Xku5bkuIDkuKrlupPpg73msqHmnInjgIIgLS0+XG4gICAgICAgIDxkaXYgdi1pZj1cIiFsb2FkaW5nICYmIGtiTG9hZEZhaWxlZFwiIGNsYXNzPVwia2ItbG9hZC1mYWlsZWRcIj5cbiAgICAgICAgICA8c3Bhbj7nn6Xor4blupPliJfooajov5nmrKHmsqHlj5bliLDvvIzkuIvpnaLmmL7npLrnmoTlj6/og73kuI3mmK/mnIDmlrDnmoTjgII8L3NwYW4+XG4gICAgICAgICAgPGVsLWJ1dHRvbiBzaXplPVwic21hbGxcIiB0ZXh0IHR5cGU9XCJwcmltYXJ5XCIgQGNsaWNrPVwibG9hZEticygpXCI+6YeN6K+VPC9lbC1idXR0b24+XG4gICAgICAgIDwvZGl2PlxuXG4gICAgICAgIDwhLS0g4pSA4pSAIOefpeivhuW6k+WIl+ihqCDilIDilIAgLS0+XG4gICAgICAgIDwhLS0g5pCc57Si5qGG55WZ5Zyo5YiX6KGoKirlpJbpnaIqKu+8muWIl+ihqOiHquW3seaciSBtYXgtaGVpZ2h0ICsg5rua5Yqo5p2h77yI5bqT5aSa5LqG6KaB6IO95rua77yJ77yMXG4gICAgICAgICAgICAg5pCc57Si5qGG6Lef552A5LiA6LW35rua55qE6K+d77yM57+75Yiw5LiA5Y2K5bCx5rKh5rOV5pS55YWz6ZSu6K+N5LqGIC0tPlxuICAgICAgICA8ZGl2IHYtaWY9XCJrYnMubGVuZ3RoXCIgY2xhc3M9XCJrYi1maWx0ZXJcIj5cbiAgICAgICAgICA8aW5wdXQgdi1tb2RlbD1cImtiRmlsdGVyXCIgY2xhc3M9XCJrYi1maWx0ZXItaW5wdXRcIiBwbGFjZWhvbGRlcj1cIuaQnOe0ouefpeivhuW6k+WQjeWtl+KAplwiIC8+XG4gICAgICAgICAgPHNwYW4gdi1pZj1cImtiRmlsdGVyXCIgY2xhc3M9XCJrYi1maWx0ZXItY2xlYXJcIiB0aXRsZT1cIua4heepuuaQnOe0olwiIEBjbGljaz1cImtiRmlsdGVyID0gJydcIj5cbiAgICAgICAgICAgIDxlbC1pY29uPjxDbG9zZSAvPjwvZWwtaWNvbj5cbiAgICAgICAgICA8L3NwYW4+XG4gICAgICAgIDwvZGl2PlxuXG4gICAgICAgIDxkaXYgY2xhc3M9XCJrYi1saXN0LXdyYXBcIj5cbiAgICAgICAgICA8ZGl2IHYtZm9yPVwia2IgaW4gZmlsdGVyZWRLYnNcIiA6a2V5PVwia2Iua2JJZFwiXG4gICAgICAgICAgICA6Y2xhc3M9XCJbJ2tiLWl0ZW0nLCB7IGFjdGl2ZToga2Iua2JJZCA9PT0gYWN0aXZlS2JJZCwgYmxvY2tlZDoga2IuZGlzYWJsZWQgPT09IDEgfV1cIiBAY2xpY2s9XCJzZWxlY3RLYihrYilcIj5cbiAgICAgICAgICAgIDxkaXYgY2xhc3M9XCJrYi1pdGVtLW1haW5cIj5cbiAgICAgICAgICAgICAgPGRpdiBjbGFzcz1cImtiLWl0ZW0tbmFtZVwiIDp0aXRsZT1cImtiLm5hbWVcIj57eyBrYi5uYW1lIH19PC9kaXY+XG4gICAgICAgICAgICAgIDxkaXYgY2xhc3M9XCJrYi1pdGVtLW1ldGFcIj5cbiAgICAgICAgICAgICAgICA8c3Bhbj57eyBrYi5kb2NDb3VudCB8fCAwIH19IOevh+aWh+ahozwvc3Bhbj5cbiAgICAgICAgICAgICAgICA8c3Bhbj57eyBrYi5jaHVua0NvdW50IHx8IDAgfX0g5Liq5YiG5Z2XPC9zcGFuPlxuICAgICAgICAgICAgICAgIDwhLS0g5bGP6JS954q25oCBKirluLjpqbsqKuaYvuekuu+8mueUqOaIt+imgeiDveS4gOecvOeci+WHuuOAjOWTquS6m+W6k+aZuuiDveS9k+eOsOWcqOeci+S4jeWIsOOAjSAtLT5cbiAgICAgICAgICAgICAgICA8c3BhbiB2LWlmPVwia2IuZGlzYWJsZWQgPT09IDFcIiBjbGFzcz1cImtiLWl0ZW0tYmxvY2tlZFwiPuW3suWxj+iUvTwvc3Bhbj5cbiAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICA8L2Rpdj5cblxuICAgICAgICAgICAgPCEtLSDlsY/olL3lvIDlhbPmlL7lnKggLmtiLWl0ZW0tb3BzICoq5aSW6Z2iKirvvJrpgqPovrnmmK8gYG9wYWNpdHk6IDBg77yIaG92ZXIg5omN5pi+5b2i77yJ77yMXG4gICAgICAgICAgICAgICAgIOW8gOWFs+aUvui/m+WOu+eahOivneOAjOWTquS4quW6k+iiq+Wxj+iUveS6huOAjeWcqOWIl+ihqOS4iuagueacrOeci+S4jeWHuuadpSDigJTigJRcbiAgICAgICAgICAgICAgICAg6ICM44CM5LiA55y855yL5Ye65ZOq5Lqb5bqT6KKr5bGP6JS944CN5q2j5piv55So5oi35ouo5a6D55qE55uu55qE44CCXG4gICAgICAgICAgICAgICAgIOiiq+Wxj+iUveeahOW6kyoq5LuN54S255WZ5Zyo5YiX6KGo6YeMKirvvIjlkI7nq6/kuZ/mlYXmhI/kv53nlZnvvInvvIzlkKbliJnlsLHmsqHms5Xlj5bmtojlsY/olL3kuobjgIJcblxuICAgICAgICAgICAgICAgICDlvIDlhbPjgIzlvIDjgI09IOaZuuiDveS9kyoq5Y+v5LulKirmn6XliLDvvIhga2JFbmFibGVkYO+8ieOAgum7mOiupOWFqOW8gO+8jOaJgOS7peWQjuerr+i/mOayoeS4i+WPkVxuICAgICAgICAgICAgICAgICBgZGlzYWJsZWRgIOaXtu+8iHVuZGVmaW5lZO+8ieeci+WIsOeahOaYr+S4gOeJh+OAjOWPr+afpeOAje+8jOS4jeS8muiiq+ivr+ivu+aIkOOAjOWFqOiiq+Wxj+iUveS6huOAjeOAglxuXG4gICAgICAgICAgICAgICAgIOKaoO+4jyBgOm1vZGVsLXZhbHVlYCDnu5HnmoTmmK8qKuW4g+WwlOihqOi+vuW8jyoq77yM5LiN5pivIGBrYi5kaXNhYmxlZGAg5pys6Lqr77yM5LmfKirkuI3opoEqKuWKoFxuICAgICAgICAgICAgICAgICAgICBgOmFjdGl2ZS12YWx1ZWAgLyBgOmluYWN0aXZlLXZhbHVlYCDigJTigJQg6KeBIGBrYkVuYWJsZWRgIOeahOazqOmHiu+8mue7keWumuWAvOS4gOaXpuS4jeWcqFxuICAgICAgICAgICAgICAgICAgICBgW2FjdGl2ZVZhbHVlLCBpbmFjdGl2ZVZhbHVlXWAg6YeM77yMZWwtc3dpdGNoIOS8muWcqOaMgui9veacnyoq5peg55So5oi35pON5L2c5ZywKiogZW1pdCDkuIDmrKHjgIIgLS0+XG4gICAgICAgICAgICA8c3BhbiBjbGFzcz1cImtiLWJsb2NrXCIgQGNsaWNrLnN0b3BcbiAgICAgICAgICAgICAgOnRpdGxlPVwia2JFbmFibGVkKGtiKSA/ICfmmbrog73kvZPmj5Dpl67kuI7or5Xmo4DntKLpg73kvJrmn6Xov5nkuKrlupPvvJvlhbPmjonlroPlsLHkuI3lho3mn6UnIDogJ+W3suWxj+iUve+8muaZuuiDveS9k+aPkOmXruS4juivleajgOe0oumDveS4jeS8muWGjeafpei/meS4quW6kydcIj5cbiAgICAgICAgICAgICAgPGVsLXN3aXRjaCA6bW9kZWwtdmFsdWU9XCJrYkVuYWJsZWQoa2IpXCIgc2l6ZT1cInNtYWxsXCIgOmxvYWRpbmc9XCJ0b2dnbGluZ0tiSWQgPT09IGtiLmtiSWRcIlxuICAgICAgICAgICAgICAgIEB1cGRhdGU6bW9kZWwtdmFsdWU9XCJ0b2dnbGVLYkRpc2FibGVkKGtiLCAkZXZlbnQpXCIgLz5cbiAgICAgICAgICAgIDwvc3Bhbj5cblxuICAgICAgICAgICAgPGRpdiBjbGFzcz1cImtiLWl0ZW0tb3BzXCI+XG4gICAgICAgICAgICAgIDxzcGFuIGNsYXNzPVwia2Itb3BcIiB0aXRsZT1cIumHjeWRveWQjVwiIEBjbGljay5zdG9wPVwicHJvbXB0UmVuYW1lKGtiKVwiPlxuICAgICAgICAgICAgICAgIDxlbC1pY29uPjxFZGl0UGVuIC8+PC9lbC1pY29uPlxuICAgICAgICAgICAgICA8L3NwYW4+XG4gICAgICAgICAgICAgIDxzcGFuIGNsYXNzPVwia2Itb3AgZGFuZ2VyXCIgdGl0bGU9XCLliKDpmaTnn6Xor4blupNcIiBAY2xpY2suc3RvcD1cInJlbW92ZUtiKGtiKVwiPlxuICAgICAgICAgICAgICAgIDxlbC1pY29uPjxEZWxldGUgLz48L2VsLWljb24+XG4gICAgICAgICAgICAgIDwvc3Bhbj5cbiAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICAgIDwvZGl2PlxuXG4gICAgICAgICAgPGRpdiB2LWlmPVwiIWxvYWRpbmcgJiYgIWtiTG9hZEZhaWxlZCAmJiAha2JzLmxlbmd0aFwiIGNsYXNzPVwia2ItZW1wdHlcIj5cbiAgICAgICAgICAgIDxkaXYgY2xhc3M9XCJrYi1lbXB0eS10aXRsZVwiPui/mOayoeacieefpeivhuW6kzwvZGl2PlxuICAgICAgICAgICAgPGRpdiBjbGFzcz1cImtiLWVtcHR5LWRlc2NcIj5cbiAgICAgICAgICAgICAg5paw5bu65LiA5Liq77yM5oqK6K++5Lu2IC8g6K6y5LmJIC8g56yU6K6w5Lyg6L+b5Y6777yM5LmL5ZCO55u05o6l5o+Q6Zeu5bCx6KGMIOKAlOKAlFxuICAgICAgICAgICAgICDmmbrog73kvZPkvJrlhYjlnKjotYTmlpnph4zmib7vvIzlho3lm57nrZTkvaDvvIzlubblkYror4nkvaDnrZTmoYjlh7roh6rlk6rkuIDmrrXjgIJcbiAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICAgICAgPGVsLWJ1dHRvbiB0eXBlPVwicHJpbWFyeVwiIHNpemU9XCJzbWFsbFwiIDppY29uPVwiUGx1c1wiIEBjbGljaz1cInByb21wdENyZWF0ZVwiPuaWsOW7uuefpeivhuW6kzwvZWwtYnV0dG9uPlxuICAgICAgICAgIDwvZGl2PlxuXG4gICAgICAgICAgPCEtLSDjgIzmkJzntKLmsqHlkb3kuK3jgI3kuI7jgIzkuIDkuKrnn6Xor4blupPpg73msqHmnInjgI3mmK/kuKTku7bkuovvvIzmlofmoYjlv4XpobvliIblvIAg4oCU4oCUXG4gICAgICAgICAgICAgICDlhbHnlKjlkIzkuIDlj6XjgIzov5jmsqHmnInnn6Xor4blupPjgI3kvJrorqnnlKjmiLfku6XkuLroh6rlt7HnmoTlupPooqvmuIXnqbrkuobjgIJcbiAgICAgICAgICAgICAgIOazqOaEj+i/memHjOWGmeaIkOeLrOeri+eahCB2LWlmIOiAjOS4jeaYryB2LWVsc2UtaWbvvJrmnaHku7bph4zluKYga2JzLmxlbmd0aO+8jFxuICAgICAgICAgICAgICAg5Lik6ICF5pys5p2l5bCx5LqS5pal77yM5LiN5L6d6LWW5YWE5byf6ZO+55qE6K+t5LmJ44CCIC0tPlxuICAgICAgICAgIDxkaXYgdi1pZj1cIiFsb2FkaW5nICYmIGticy5sZW5ndGggJiYgIWZpbHRlcmVkS2JzLmxlbmd0aFwiIGNsYXNzPVwia2ItZW1wdHlcIj5cbiAgICAgICAgICAgIDxkaXYgY2xhc3M9XCJrYi1lbXB0eS10aXRsZVwiPuayoeacieWQjeWtl+WMheWQq+OAjHt7IGtiRmlsdGVyLnRyaW0oKSB9feOAjeeahOefpeivhuW6kzwvZGl2PlxuICAgICAgICAgICAgPGRpdiBjbGFzcz1cImtiLWVtcHR5LWRlc2NcIj7mjaLkuKrlhbPplK7or43or5Xor5XvvIzmiJbogIXmuIXnqbrmkJzntKLnnIvlhajpg6gge3sga2JDb3VudCB9fSDkuKrnn6Xor4blupPjgII8L2Rpdj5cbiAgICAgICAgICAgIDxlbC1idXR0b24gc2l6ZT1cInNtYWxsXCIgQGNsaWNrPVwia2JGaWx0ZXIgPSAnJ1wiPua4heepuuaQnOe0ojwvZWwtYnV0dG9uPlxuICAgICAgICAgIDwvZGl2PlxuICAgICAgICA8L2Rpdj5cblxuICAgICAgICA8IS0tIOKUgOKUgCDpgInkuK3lupPnmoTmlofmoaMg4pSA4pSAIC0tPlxuICAgICAgICA8ZGl2IHYtaWY9XCJhY3RpdmVLYklkXCIgY2xhc3M9XCJrYi1kb2NzXCI+XG4gICAgICAgICAgPGRpdiBjbGFzcz1cImtiLWRvY3MtaGVhZFwiPlxuICAgICAgICAgICAgPHNwYW4gY2xhc3M9XCJrYi1kb2NzLXRpdGxlXCI+e3sgYWN0aXZlS2I/Lm5hbWUgfX08L3NwYW4+XG4gICAgICAgICAgICA8c3BhbiBjbGFzcz1cImtiLWRvY3MtaGludFwiPuaUr+aMgSB7eyBLQl9GSUxFX0VYVEVOU0lPTlMuam9pbignIC8gJykgfX08L3NwYW4+XG4gICAgICAgICAgICA8bGFiZWwgY2xhc3M9XCJrYi11cGxvYWQtYnRuXCIgOmNsYXNzPVwieyBkaXNhYmxlZDogYnVzeSB9XCI+XG4gICAgICAgICAgICAgIDxpbnB1dCByZWY9XCJmaWxlSW5wdXRSZWZcIiB0eXBlPVwiZmlsZVwiIDphY2NlcHQ9XCJLQl9GSUxFX0FDQ0VQVFwiIG11bHRpcGxlIDpkaXNhYmxlZD1cImJ1c3lcIlxuICAgICAgICAgICAgICAgIEBjaGFuZ2U9XCJvbkZpbGVzUGlja2VkXCIgLz5cbiAgICAgICAgICAgICAgPGVsLWljb24+XG4gICAgICAgICAgICAgICAgPFVwbG9hZEZpbGxlZCAvPlxuICAgICAgICAgICAgICA8L2VsLWljb24+XG4gICAgICAgICAgICAgIDxzcGFuPnt7IHVwbG9hZGluZyA/ICfkuIrkvKDkuK3igKYnIDogJ+S4iuS8oOaWh+ahoycgfX08L3NwYW4+XG4gICAgICAgICAgICA8L2xhYmVsPlxuICAgICAgICAgICAgPCEtLSDnspjotLTmlofmnKzvvJrnlKjmiLfoh6rlt7HmlbIv57KY55qE5paH5a2X55u05o6l5YWl5bqT77yMKirkuI3nu4/ov4fmlofku7bop6PmnpAqKuOAglxuICAgICAgICAgICAgICAgICDkuI7jgIzkuIrkvKDmlofmoaPjgI3lhbHnlKggYnVzeSDkupLmlqUg4oCU4oCUIOS4pOS4quWFpeWPo+W+gOWQjOS4gOS4quW6k+mHjOWGmeaWh+aho++8jFxuICAgICAgICAgICAgICAgICDlkIzml7bot5HotbfmnaXnmoTor53ov5vluqbmj5DnpLrkuI7ova7or6LkvJrkupLnm7jopobnm5bjgIIgLS0+XG4gICAgICAgICAgICA8YnV0dG9uIHR5cGU9XCJidXR0b25cIiBjbGFzcz1cImtiLWltcG9ydC1idG5cIiA6Y2xhc3M9XCJ7IGRpc2FibGVkOiBidXN5IH1cIiA6ZGlzYWJsZWQ9XCJidXN5XCJcbiAgICAgICAgICAgICAgOnRpdGxlPVwiYnVzeSA/ICfmnInlr7zlhaXmraPlnKjov5vooYzvvIznrYnlroPot5HlrownIDogJ+aKiuaWh+Wtl+ebtOaOpeeymOi/m+adpe+8jOS4jeeUqOWFiOWtmOaIkOaWh+S7tidcIiBAY2xpY2s9XCJvcGVuVGV4dEltcG9ydFwiPlxuICAgICAgICAgICAgICA8ZWwtaWNvbj5cbiAgICAgICAgICAgICAgICA8RG9jdW1lbnRDb3B5IC8+XG4gICAgICAgICAgICAgIDwvZWwtaWNvbj5cbiAgICAgICAgICAgICAgPHNwYW4+e3sgaW1wb3J0aW5nID8gJ+WvvOWFpeS4reKApicgOiAn57KY6LS05paH5pysJyB9fTwvc3Bhbj5cbiAgICAgICAgICAgIDwvYnV0dG9uPlxuICAgICAgICAgIDwvZGl2PlxuXG4gICAgICAgICAgPCEtLSDkuIrkvKDov5vluqbmj5DnpLrvvIjlkI7nq6/mmK/lkIzmraXop6PmnpAgKyDlkI7lj7DlkJHph4/ljJbvvIzmiYDku6Xov5nph4zor7TmmI7muIXmpZrvvIkgLS0+XG4gICAgICAgICAgPGRpdiB2LWlmPVwidXBsb2FkVGlwXCIgY2xhc3M9XCJrYi10aXBcIj57eyB1cGxvYWRUaXAgfX08L2Rpdj5cblxuICAgICAgICAgIDxkaXYgY2xhc3M9XCJrYi1kb2MtbGlzdFwiIHYtbG9hZGluZz1cImRvY3NMb2FkaW5nXCI+XG4gICAgICAgICAgICA8ZGl2IHYtZm9yPVwiZG9jIGluIGRvY3VtZW50c1wiIDprZXk9XCJkb2MuZG9jSWRcIiBjbGFzcz1cImtiLWRvY1wiPlxuICAgICAgICAgICAgICA8ZGl2IGNsYXNzPVwia2ItZG9jLW1haW5cIj5cbiAgICAgICAgICAgICAgICA8ZGl2IGNsYXNzPVwia2ItZG9jLW5hbWVcIiA6dGl0bGU9XCJkb2MuZmlsZU5hbWVcIj57eyBkb2MuZmlsZU5hbWUgfX08L2Rpdj5cbiAgICAgICAgICAgICAgICA8ZGl2IGNsYXNzPVwia2ItZG9jLW1ldGFcIj5cbiAgICAgICAgICAgICAgICAgIDxlbC10YWcgOnR5cGU9XCJkb2N1bWVudFRhZ1R5cGUoZG9jLnN0YXR1cylcIiBzaXplPVwic21hbGxcIiBlZmZlY3Q9XCJsaWdodFwiPlxuICAgICAgICAgICAgICAgICAgICB7eyBkb2Muc3RhdHVzVGV4dCB8fCBkb2Muc3RhdHVzIH19XG4gICAgICAgICAgICAgICAgICA8L2VsLXRhZz5cbiAgICAgICAgICAgICAgICAgIDxzcGFuIHYtaWY9XCJpc0RvY3VtZW50U2VhcmNoYWJsZShkb2Muc3RhdHVzKVwiIGNsYXNzPVwia2ItZG9jLWNodW5rc1wiPlxuICAgICAgICAgICAgICAgICAgICB7eyBkb2MuY2h1bmtDb3VudCB8fCAwIH19IOS4quWIhuWdl1xuICAgICAgICAgICAgICAgICAgPC9zcGFuPlxuICAgICAgICAgICAgICAgICAgPHNwYW4gdi1lbHNlLWlmPVwiaXNEb2N1bWVudFByb2Nlc3NpbmcoZG9jLnN0YXR1cylcIiBjbGFzcz1cImtiLWRvYy1jaHVua3NcIj5cbiAgICAgICAgICAgICAgICAgICAg5aSE55CG5Lit77yM56iN562J54mH5Yi74oCmXG4gICAgICAgICAgICAgICAgICA8L3NwYW4+XG4gICAgICAgICAgICAgICAgICA8c3BhbiB2LWVsc2UtaWY9XCJkb2Muc3RhdHVzID09PSBET0NfUEFSU0VEXCIgY2xhc3M9XCJrYi1kb2MtY2h1bmtzIGlzLXdhcm5cIj5cbiAgICAgICAgICAgICAgICAgICAg5bey5o+Q5Y+W5q2j5paH77yM5bCa5pyq5ZCR6YeP5YyWIOKAlOKAlCDnjrDlnKjmo4DntKLkuI3liLDlroNcbiAgICAgICAgICAgICAgICAgIDwvc3Bhbj5cbiAgICAgICAgICAgICAgICAgIDxzcGFuIHYtZWxzZS1pZj1cImRvYy5zdGF0dXMgPT09IERPQ19GQUlMRURcIiBjbGFzcz1cImtiLWRvYy1jaHVua3MgaXMtZXJyb3JcIj5cbiAgICAgICAgICAgICAgICAgICAge3sgZG9jLmVycm9yTXNnIHx8ICflpITnkIblpLHotKUnIH19XG4gICAgICAgICAgICAgICAgICA8L3NwYW4+XG4gICAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICAgIDwvZGl2PlxuXG4gICAgICAgICAgICAgIDxkaXYgY2xhc3M9XCJrYi1kb2Mtb3BzXCI+XG4gICAgICAgICAgICAgICAgPHNwYW4gdi1pZj1cImlzRG9jdW1lbnRTZWFyY2hhYmxlKGRvYy5zdGF0dXMpXCIgY2xhc3M9XCJrYi1vcFwiIHRpdGxlPVwi55yL55yL5YiG5Z2X5YiH5b6X5a+55LiN5a+5XCJcbiAgICAgICAgICAgICAgICAgIEBjbGljaz1cInNob3dDaHVua3MoZG9jKVwiPlxuICAgICAgICAgICAgICAgICAgPGVsLWljb24+PFZpZXcgLz48L2VsLWljb24+XG4gICAgICAgICAgICAgICAgPC9zcGFuPlxuICAgICAgICAgICAgICAgIDxzcGFuIHYtaWY9XCJjYW5SZXByb2Nlc3NEb2N1bWVudChkb2Muc3RhdHVzKVwiIGNsYXNzPVwia2Itb3BcIiB0aXRsZT1cIumHjeaWsOino+aekOW5tuWQkemHj+WMllwiXG4gICAgICAgICAgICAgICAgICBAY2xpY2s9XCJyZXByb2Nlc3MoZG9jKVwiPlxuICAgICAgICAgICAgICAgICAgPGVsLWljb24+PFJlZnJlc2hSaWdodCAvPjwvZWwtaWNvbj5cbiAgICAgICAgICAgICAgICA8L3NwYW4+XG4gICAgICAgICAgICAgICAgPHNwYW4gY2xhc3M9XCJrYi1vcCBkYW5nZXJcIiB0aXRsZT1cIuWIoOmZpOaWh+aho1wiIEBjbGljaz1cInJlbW92ZURvYyhkb2MpXCI+XG4gICAgICAgICAgICAgICAgICA8ZWwtaWNvbj48RGVsZXRlIC8+PC9lbC1pY29uPlxuICAgICAgICAgICAgICAgIDwvc3Bhbj5cbiAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICA8L2Rpdj5cblxuICAgICAgICAgICAgPGRpdiB2LWlmPVwiIWRvY3NMb2FkaW5nICYmICFkb2N1bWVudHMubGVuZ3RoXCIgY2xhc3M9XCJrYi1kb2MtZW1wdHlcIj5cbiAgICAgICAgICAgICAg6L+Z5Liq55+l6K+G5bqT6L+Y5rKh5pyJ5paH5qGj77yM54K55Y+z5LiK6KeS44CM5LiK5Lyg5paH5qGj44CNXG4gICAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgICA8L2Rpdj5cblxuICAgICAgICAgIDwhLS0g6K+V5qOA57Si77ya5Lyg5a6M6LWE5paZ6IO956uL5Yi76aqM5LiA5LiL44CM5Yiw5bqV5pCc5LiN5pCc5b6X5Yiw44CN44CCXG4gICAgICAgICAgICAgICDnnJ/mraPnmoTpl67nrZTov5jmmK/lnKjovpPlhaXmoYbph4zpl67vvIhBZ2VudCDkvJroh6rlt7HosIMga25vd2xlZGdlX3NlYXJjaO+8ie+8jFxuICAgICAgICAgICAgICAg6L+Z6YeM5Y+q5piv6K6p44CM5LiK5LygIOKGkiDog73kuI3og73nlKjjgI3ov5nmnaHlj43ppojpl63njq/lj5jnn63jgIIgLS0+XG4gICAgICAgICAgPGRpdiBjbGFzcz1cImtiLXByb2JlXCI+XG4gICAgICAgICAgICA8ZGl2IGNsYXNzPVwia2ItcHJvYmUtcm93XCI+XG4gICAgICAgICAgICAgIDxpbnB1dCB2LW1vZGVsPVwicHJvYmVRdWVyeVwiIGNsYXNzPVwia2ItcHJvYmUtaW5wdXRcIiBwbGFjZWhvbGRlcj1cIuivleivleiDveS4jeiDveaQnOWIsO+8jOS+i+Wmgu+8muS6jOWPieaQnOe0ouagkeeahOaXtumXtOWkjeadguW6plwiXG4gICAgICAgICAgICAgICAgOmRpc2FibGVkPVwicHJvYmluZ1wiIEBrZXlkb3duLmVudGVyPVwicnVuUHJvYmVcIiAvPlxuICAgICAgICAgICAgICA8ZWwtYnV0dG9uIHNpemU9XCJzbWFsbFwiIHR5cGU9XCJwcmltYXJ5XCIgOmxvYWRpbmc9XCJwcm9iaW5nXCIgOmRpc2FibGVkPVwiIXByb2JlUXVlcnkudHJpbSgpXCJcbiAgICAgICAgICAgICAgICBAY2xpY2s9XCJydW5Qcm9iZVwiPlxuICAgICAgICAgICAgICAgIOajgOe0olxuICAgICAgICAgICAgICA8L2VsLWJ1dHRvbj5cbiAgICAgICAgICAgIDwvZGl2PlxuXG4gICAgICAgICAgICA8ZGl2IHYtaWY9XCJwcm9iZURvbmVcIiBjbGFzcz1cImtiLXByb2JlLXJlc3VsdFwiPlxuICAgICAgICAgICAgICA8ZGl2IHYtaWY9XCIhcHJvYmVIaXRzLmxlbmd0aFwiIGNsYXNzPVwia2ItcHJvYmUtZW1wdHlcIj5cbiAgICAgICAgICAgICAgICDmsqHmo4DntKLliLDnm7jlhbPlhoXlrrnjgILlj6/og73mmK/otYTmlpnph4znoa7lrp7msqHmnInvvIzkuZ/lj6/og73mjaLkuKror7Tms5XlsLHooYzkuobjgIJcbiAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICAgIDxkaXYgdi1lbHNlIGNsYXNzPVwia2ItcHJvYmUtaGl0c1wiPlxuICAgICAgICAgICAgICAgIDxkaXYgY2xhc3M9XCJrYi1wcm9iZS1jb3VudFwiPuWRveS4rSB7eyBwcm9iZUhpdHMubGVuZ3RoIH19IOautTwvZGl2PlxuICAgICAgICAgICAgICAgIDxkaXYgdi1mb3I9XCJoIGluIHByb2JlSGl0c1wiIDprZXk9XCJoLmNodW5rSWRcIiBjbGFzcz1cImtiLXByb2JlLWhpdFwiPlxuICAgICAgICAgICAgICAgICAgPGRpdiBjbGFzcz1cImtiLXByb2JlLXNvdXJjZVwiPnt7IGguc291cmNlIHx8IGguZG9jTmFtZSB9fTwvZGl2PlxuICAgICAgICAgICAgICAgICAgPGRpdiBjbGFzcz1cImtiLXByb2JlLXRleHRcIj57eyBoLmNvbnRlbnQgfX08L2Rpdj5cbiAgICAgICAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgPC9kaXY+XG4gICAgICA8L2Rpdj5cbiAgICA8L2Rpdj5cbiAgPC9lbC1kcmF3ZXI+XG5cbiAgPCEtLSDliIblnZfpooTop4ggLS0+XG4gIDxlbC1kaWFsb2cgdi1tb2RlbD1cImNodW5rc1Zpc2libGVcIiA6dGl0bGU9XCJg5YiG5Z2X6aKE6KeIIMK3ICR7Y2h1bmtEb2NOYW1lfWBcIiB3aWR0aD1cIjY4MHB4XCIgYXBwZW5kLXRvLWJvZHk+XG4gICAgPGRpdiBjbGFzcz1cImtiLWNodW5rc1wiIHYtbG9hZGluZz1cImNodW5rc0xvYWRpbmdcIj5cbiAgICAgIDxkaXYgdi1mb3I9XCJjIGluIGNodW5rc1wiIDprZXk9XCJjLmNodW5rSWRcIiBjbGFzcz1cImtiLWNodW5rXCI+XG4gICAgICAgIDxkaXYgY2xhc3M9XCJrYi1jaHVuay1oZWFkXCI+XG4gICAgICAgICAgPHNwYW4gY2xhc3M9XCJrYi1jaHVuay1pZHhcIj7nrKwge3sgYy5jaHVua0luZGV4ICsgMSB9fSDmrrU8L3NwYW4+XG4gICAgICAgICAgPHNwYW4gY2xhc3M9XCJrYi1jaHVuay1sZW5cIj57eyBjLmNvbnRlbnRMZW5ndGggfHwgYy5jb250ZW50Lmxlbmd0aCB9fSDlrZc8L3NwYW4+XG4gICAgICAgICAgPGVsLXRhZyB2LWlmPVwiYy52ZWN0b3JpemVkID09PSBmYWxzZVwiIHR5cGU9XCJ3YXJuaW5nXCIgc2l6ZT1cInNtYWxsXCIgZWZmZWN0PVwibGlnaHRcIj7ml6DlkJHph488L2VsLXRhZz5cbiAgICAgICAgPC9kaXY+XG4gICAgICAgIDxkaXYgY2xhc3M9XCJrYi1jaHVuay10ZXh0XCI+e3sgYy5jb250ZW50IH19PC9kaXY+XG4gICAgICA8L2Rpdj5cbiAgICAgIDxkaXYgdi1pZj1cIiFjaHVua3NMb2FkaW5nICYmICFjaHVua3MubGVuZ3RoXCIgY2xhc3M9XCJrYi1kb2MtZW1wdHlcIj7msqHmnInliIblnZc8L2Rpdj5cbiAgICA8L2Rpdj5cbiAgPC9lbC1kaWFsb2c+XG5cbiAgPCEtLSDnspjotLTmlofmnKzlr7zlhaXvvJrmiornlKjmiLfoh6rlt7HovpPlhaXnmoTmraPmlofnm7TmjqXmlLbov5vnn6Xor4blupPvvIjlkI7nq68gYC9kb2N1bWVudC91cGxvYWRUZXh0YO+8jOS4jei1sOaWh+S7tuino+aekO+8iSAtLT5cbiAgPGVsLWRpYWxvZyB2LW1vZGVsPVwidGV4dEltcG9ydFZpc2libGVcIiB0aXRsZT1cIueymOi0tOaWh+acrFwiIHdpZHRoPVwiNjQwcHhcIiBhcHBlbmQtdG8tYm9keSBAY2xvc2VkPVwicmVzZXRUZXh0SW1wb3J0XCI+XG4gICAgPGRpdiBjbGFzcz1cImtiLWltcG9ydFwiPlxuICAgICAgPGRpdiBjbGFzcz1cImtiLWltcG9ydC1oaW50XCI+XG4gICAgICAgIOaKiuato+aWh+ebtOaOpeeymOi/m+adpeWwseihjCDigJTigJQg5LiN55So5YWI5a2Y5oiQIHR4dCAvIFdvcmQg5YaN5LiK5Lyg77yM5Lmf5LiN57uP6L+H5paH5Lu26Kej5p6Q44CCXG4gICAgICAgIOWvvOWFpeWQjuaZuuiDveS9k+S4gOagt+iDveajgOe0ouWIsOWug+OAglxuICAgICAgPC9kaXY+XG4gICAgICA8ZWwtaW5wdXQgdi1tb2RlbD1cInRleHRJbXBvcnRGaWxlTmFtZVwiIGNsYXNzPVwia2ItaW1wb3J0LW5hbWVcIiBwbGFjZWhvbGRlcj1cIuacquWRveWQjeaWh+ahoy50eHRcIiBjbGVhcmFibGU+XG4gICAgICAgIDx0ZW1wbGF0ZSAjcHJlcGVuZD7mlofku7blkI08L3RlbXBsYXRlPlxuICAgICAgPC9lbC1pbnB1dD5cbiAgICAgIDxlbC1pbnB1dCB2LW1vZGVsPVwidGV4dEltcG9ydENvbnRlbnRcIiBjbGFzcz1cImtiLWltcG9ydC10ZXh0XCIgdHlwZT1cInRleHRhcmVhXCJcbiAgICAgICAgOmF1dG9zaXplPVwieyBtaW5Sb3dzOiAxMCwgbWF4Um93czogMTggfVwiIHJlc2l6ZT1cInZlcnRpY2FsXCJcbiAgICAgICAgcGxhY2Vob2xkZXI9XCLmioropoHmlLbov5vnn6Xor4blupPnmoTmraPmlofnspjlnKjov5nph4zvvIzkvovlpoLor77ku7bmloflrZfjgIHnrJTorrDjgIHplJnpopjop6PmnpDigKZcIiAvPlxuICAgICAgPGRpdiBjbGFzcz1cImtiLWltcG9ydC1jb3VudFwiPnt7IHRleHRJbXBvcnRDb250ZW50LnRyaW0oKS5sZW5ndGggfX0g5a2XPC9kaXY+XG4gICAgPC9kaXY+XG4gICAgPHRlbXBsYXRlICNmb290ZXI+XG4gICAgICA8ZWwtYnV0dG9uIEBjbGljaz1cInRleHRJbXBvcnRWaXNpYmxlID0gZmFsc2VcIj7lj5bmtog8L2VsLWJ1dHRvbj5cbiAgICAgIDxlbC1idXR0b24gdHlwZT1cInByaW1hcnlcIiA6bG9hZGluZz1cImltcG9ydGluZ1wiIDpkaXNhYmxlZD1cIiF0ZXh0SW1wb3J0Q29udGVudC50cmltKClcIiBAY2xpY2s9XCJzdWJtaXRUZXh0SW1wb3J0XCI+XG4gICAgICAgIOWvvOWFpVxuICAgICAgPC9lbC1idXR0b24+XG4gICAgPC90ZW1wbGF0ZT5cbiAgPC9lbC1kaWFsb2c+XG48L3RlbXBsYXRlPlxuXG48c2NyaXB0IHNldHVwIGxhbmc9XCJ0c1wiPlxuZGVmaW5lT3B0aW9ucyh7IG5hbWU6ICdLbm93bGVkZ2VCYXNlRHJhd2VyJyB9KVxuXG5pbXBvcnQgeyByZWYsIGNvbXB1dGVkLCBvbkJlZm9yZVVubW91bnQsIG9uTW91bnRlZCB9IGZyb20gJ3Z1ZSdcbmltcG9ydCB7IEVsTWVzc2FnZSwgRWxNZXNzYWdlQm94IH0gZnJvbSAnZWxlbWVudC1wbHVzJ1xuaW1wb3J0IHsgQ2xvc2UsIERlbGV0ZSwgRG9jdW1lbnRDb3B5LCBFZGl0UGVuLCBQbHVzLCBSZWZyZXNoUmlnaHQsIFVwbG9hZEZpbGxlZCwgVmlldyB9IGZyb20gJ0BlbGVtZW50LXBsdXMvaWNvbnMtdnVlJ1xuaW1wb3J0IHtcbiAgRE9DX0ZBSUxFRCxcbiAgRE9DX1BBUlNFRCxcbiAgS0JfRklMRV9BQ0NFUFQsXG4gIEtCX0ZJTEVfRVhURU5TSU9OUyxcbiAgY2FuUmVwcm9jZXNzRG9jdW1lbnQsXG4gIGNyZWF0ZUtub3dsZWRnZUJhc2UsXG4gIGRlbGV0ZURvY3VtZW50LFxuICBkZWxldGVLbm93bGVkZ2VCYXNlLFxuICBkb2N1bWVudFRhZ1R5cGUsXG4gIGdldERvY3VtZW50Q2h1bmtzLFxuICBnZXREb2N1bWVudFN0YXR1cyxcbiAgaW1wb3J0RG9jdW1lbnRUZXh0LFxuICBpc0RvY3VtZW50UHJvY2Vzc2luZyxcbiAgaXNEb2N1bWVudFNlYXJjaGFibGUsXG4gIGlzU3VwcG9ydGVkS2JGaWxlLFxuICBsaXN0RG9jdW1lbnRzLFxuICBsaXN0S25vd2xlZGdlQmFzZXMsXG4gIHJlcHJvY2Vzc0RvY3VtZW50LFxuICBzZWFyY2hLbm93bGVkZ2UsXG4gIHVwZGF0ZUtub3dsZWRnZUJhc2UsXG4gIHVwbG9hZERvY3VtZW50LFxuICB0eXBlIFJhZ0NodW5rLFxuICB0eXBlIFJhZ0RvY3VtZW50LFxuICB0eXBlIFJhZ0tub3dsZWRnZUJhc2UsXG4gIHR5cGUgUmFnU2VhcmNoSGl0XG59IGZyb20gJ0AvYXBpL2FpL3JhZydcblxuLyoqIOi9ruivoumXtOmalOS4juS4iumZkO+8muWQkemHj+WMluimgeiwgyBlbWJlZGRpbmfvvIzkuIDnr4fplb/mlofmoaPlh6DljYHnp5Lph4/nuqcgKi9cbmNvbnN0IFBPTExfSU5URVJWQUwgPSAyMDAwXG5jb25zdCBQT0xMX01BWF9ST1VORFMgPSA5MFxuXG5jb25zdCB2aXNpYmxlID0gcmVmKGZhbHNlKVxuY29uc3QgbG9hZGluZyA9IHJlZihmYWxzZSlcbmNvbnN0IGNyZWF0aW5nID0gcmVmKGZhbHNlKVxuY29uc3QgdXBsb2FkaW5nID0gcmVmKGZhbHNlKVxuY29uc3QgdXBsb2FkVGlwID0gcmVmKCcnKVxuXG4vKiA9PT09PSDnspjotLTmlofmnKzvvIjnlKjmiLfoh6rlt7HovpPlhaXnmoTmraPmlofvvIzkuI3otbDmlofku7bop6PmnpDvvIkgPT09PT0gKi9cbmNvbnN0IGltcG9ydGluZyA9IHJlZihmYWxzZSlcbmNvbnN0IHRleHRJbXBvcnRWaXNpYmxlID0gcmVmKGZhbHNlKVxuY29uc3QgdGV4dEltcG9ydENvbnRlbnQgPSByZWYoJycpXG5jb25zdCB0ZXh0SW1wb3J0RmlsZU5hbWUgPSByZWYoJycpXG5cbmNvbnN0IGticyA9IHJlZjxSYWdLbm93bGVkZ2VCYXNlW10+KFtdKVxuY29uc3QgYWN0aXZlS2JJZCA9IHJlZjxudW1iZXIgfCBudWxsPihudWxsKVxuY29uc3QgZG9jdW1lbnRzID0gcmVmPFJhZ0RvY3VtZW50W10+KFtdKVxuY29uc3QgZG9jc0xvYWRpbmcgPSByZWYoZmFsc2UpXG5cbi8qID09PT09IOefpeivhuW6k+aQnOe0ou+8iOW6k+WkmuS6huS7peWQjumdoOWug+aJvu+8iSA9PT09PSAqL1xuLyoqIOaMieWQjeWtl+etm+efpeivhuW6k+eahOWFs+mUruivjSAqL1xuY29uc3Qga2JGaWx0ZXIgPSByZWYoJycpXG5cbi8qKlxuICog5YiX6KGo6L+Z5qyhKirmsqHlj5bliLAqKu+8iOWTjeW6lOS4jeaYr+aVsOe7hCAvIOivt+axguaKm+mUme+8ieKAlOKAlCDkuI7jgIzkuIDkuKrnn6Xor4blupPpg73msqHmnInjgI3mmK/kuKTku7bkuotcbiAqXG4gKiDimqDvuI8g5ZCO56uv55qEIGNhdGNoLWFsbO+8iGBhcHAvYXBpL3YxL2NhdGNoX2FsbC5weWDvvInmjIkqKui3r+W+hOWFs+mUruWtlyoq5YiG5rWB77yM6L+U5Zue55qE5pivXG4gKiAgICBge2NvZGU6MjAwLHRvdGFsOjAscm93czpbXX1g77yIKirmsqHmnIkgYGRhdGFgIOmUrioq77yJ5oiWIGBzdWNjZXNzKE5vbmUpYCDov5nnsbvkv6HlsIEg4oCU4oCUXG4gKiAgICDkuo7mmK/jgIzot6/nlLHooqvmjKrotbAgLyDmi7zplJnjgI3nmoTooajnjrDmmK8gKipjb2RlIDIwMCArIGBkYXRhYCDkuI3mmK/mlbDnu4QqKuOAglxuICogICAg5Y6f5p2l55qEIGBpZiAoY29kZSA9PT0gMjAwICYmIEFycmF5LmlzQXJyYXkoZGF0YSkpYCDkvJrmiorov5nnp43lk43lupQqKuaVtOWdl+i3s+i/hyoq77yaXG4gKiAgICDmsqHmnIkgZWxzZeOAgeayoeacieaKpemUmeOAgummluasoeaJk+W8gOaXtiBga2JzYCDkv53mjIHnqbrvvIzmqKHmnb/kvr/nlLvlh7rjgIzov5jmsqHmnInnn6Xor4blupPvvIzmlrDlu7rkuIDkuKrigKbjgI3igJTigJRcbiAqICAgICoq5LiA5Liq5pyJ5Y2B5Yeg5Liq5bqT55qE55So5oi36KKr5ZGK55+l5LuW5LiA5Liq5bqT6YO95rKh5pyJKirjgILlt7Lnu4/liqDovb3ov4fnmoTmg4XlhrXmm7TpmpDolL3vvJpcbiAqICAgIOWIl+ihqOmdmem7mOeVmeedgCoq6L+H5pyf5pWw5o2uKirvvIznnIvotbfmnaXkuIDliIfmraPluLjjgIJcbiAqL1xuY29uc3Qga2JMb2FkRmFpbGVkID0gcmVmKGZhbHNlKVxuXG5jb25zdCBjaHVua3NWaXNpYmxlID0gcmVmKGZhbHNlKVxuY29uc3QgY2h1bmtzTG9hZGluZyA9IHJlZihmYWxzZSlcbmNvbnN0IGNodW5rcyA9IHJlZjxSYWdDaHVua1tdPihbXSlcbmNvbnN0IGNodW5rRG9jTmFtZSA9IHJlZignJylcblxuY29uc3QgZmlsZUlucHV0UmVmID0gcmVmPEhUTUxJbnB1dEVsZW1lbnQgfCBudWxsPihudWxsKVxuXG4vKiA9PT09PSDor5Xmo4DntKIgPT09PT0gKi9cbmNvbnN0IHByb2JlUXVlcnkgPSByZWYoJycpXG5jb25zdCBwcm9iaW5nID0gcmVmKGZhbHNlKVxuY29uc3QgcHJvYmVEb25lID0gcmVmKGZhbHNlKVxuY29uc3QgcHJvYmVIaXRzID0gcmVmPFJhZ1NlYXJjaEhpdFtdPihbXSlcblxuLyoqIOi9ruivouWumuaXtuWZqO+8mue7hOS7tuWNuOi9vSAvIOaKveWxieWFs+mXremDveimgea4heaOie+8jOWQpuWImeS8muS4gOebtOaJk+aOpeWPoyAqL1xubGV0IHBvbGxUaW1lcnM6IG51bWJlcltdID0gW11cbi8qKlxuICog5q2j5Zyo6L2u6K+i55qEIGRvY0lkXG4gKlxuICog4pqg77iPIOW/hemhu+WOu+mHje+8mmBsb2FkRG9jc2Ag5Lya5a+55omA5pyJ44CM5aSE55CG5Lit44CN55qE5paH5qGj5byA6L2u6K+i77yM6ICM5a6D5Lya6KKr5Y+N5aSN6LCD55SoXG4gKiDvvIjkuIrkvKDlkI7kuIDmrKHjgIHmir3lsYnph43lvIDkuIDmrKHjgIHliKDlrozmlofmoaPlho3kuIDmrKHvvInigJTigJQg5ZCM5LiA56+H5paH5qGj5LqO5piv5oyC552A5aW95Yeg5Liq5a6a5pe25Zmo77yMXG4gKiDmr4/kuKrpg73lnKjmiZMgYC9kb2N1bWVudC9zdGF0dXNg44CC5paH5qGj6LaK5aSa44CB5pON5L2c6LaK5aSa77yM6K+35rGC6YeP5oiQ5YCN5rao44CCXG4gKi9cbmNvbnN0IHBvbGxpbmdEb2NzID0gbmV3IFNldDxudW1iZXI+KClcblxuY29uc3Qga2JDb3VudCA9IGNvbXB1dGVkKCgpID0+IGticy52YWx1ZS5sZW5ndGgpXG5jb25zdCBhY3RpdmVLYiA9IGNvbXB1dGVkKCgpID0+IGticy52YWx1ZS5maW5kKChrKSA9PiBrLmtiSWQgPT09IGFjdGl2ZUtiSWQudmFsdWUpIHx8IG51bGwpXG5cbi8qKlxuICog5oyJ5ZCN5a2X562b6L+H55qE55+l6K+G5bqT5YiX6KGo77yIKirliJfooajmuLLmn5PnlKjlroMqKu+8iVxuICpcbiAqIGBrYkZpbHRlcmAg5Li656m65pe2Kirljp/moLfov5Tlm54gYGtic2AqKu+8iOS4jeaWsOW7uuaVsOe7hO+8ie+8muecgeS4gOasoeaXoOiwk+eahOmHjea4suafk++8jFxuICog5Lmf6K6p44CM5rKh5pyJ5pCc57Si6K+N44CN6L+Z5p2h6Lev5b6E5Zyo5pat6KiA6YeM5ZKM44CM5pCc57Si5Yia5aW95ZG95Lit5YWo6YOo44CN5Yy65YiG5b6X5byA44CCXG4gKlxuICog4pqg77iPIOWPquacieWIl+ihqOeUqOWug+OAgmBrYkNvdW50YO+8iOWFpeWPo+W+veagh++8ieW/hemhu+S7jeeEtuaYryoq5YWo6YOoKirlupPnmoTmnaHmlbAg4oCU4oCUXG4gKiAgICDlvr3moIflm57nrZTnmoTmmK/jgIzmiJHmnInlh6DkuKrlupPjgI3vvIzkuI3mmK/jgIzov5nmrKHmkJzliLDlh6DkuKrjgI3jgIJcbiAqL1xuY29uc3QgZmlsdGVyZWRLYnMgPSBjb21wdXRlZCgoKSA9PiB7XG4gIGNvbnN0IHEgPSBrYkZpbHRlci52YWx1ZS50cmltKCkudG9Mb3dlckNhc2UoKVxuICBpZiAoIXEpIHJldHVybiBrYnMudmFsdWVcbiAgcmV0dXJuIGticy52YWx1ZS5maWx0ZXIoKGspID0+IFN0cmluZyhrLm5hbWUgfHwgJycpLnRvTG93ZXJDYXNlKCkuaW5jbHVkZXMocSkpXG59KVxuY29uc3Qga2JUaXRsZSA9IGNvbXB1dGVkKCgpID0+XG4gIGtiQ291bnQudmFsdWUgPyBg55+l6K+G5bqT77yIJHtrYkNvdW50LnZhbHVlfSDkuKrvvInigJTigJQg5Lyg6LWE5paZ44CB6K6p5pm66IO95L2T6Ieq5bex5qOA57SiYCA6ICfnn6Xor4blupMg4oCU4oCUIOS8oOi1hOaWme+8jOiuqeaZuuiDveS9k+ajgOe0ouWQjuWbnuetlCdcbilcblxuLyoqXG4gKiDkuKTkuKrlr7zlhaXlhaXlj6PvvIjkuIrkvKDmlofmoaMgLyDnspjotLTmlofmnKzvvIkqKuWFseeUqCoq55qE5b+Z5qCH6K6wXG4gKlxuICog4pqg77iPIOW/hemhu+WFseeUqO+8muWug+S7rOW+gCoq5ZCM5LiA5Liq55+l6K+G5bqTKirlhpnmlofmoaPjgILlkIToh6rlj6rnnIvoh6rlt7HpgqPkuKogcmVmIOeahOivne+8jFxuICog44CM5LiK5Lyg5paH5qGj44CN6LeR552A55qE5pe25YCZ6L+Y6IO95YaN5byA5LiA5qyh57KY6LS05a+85YWlIOKAlOKAlCDkuKTmrKHlr7zlhaXnmoTov5vluqbmj5DnpLrkuI7ova7or6LkupLnm7jopobnm5bvvIxcbiAqIOeUqOaIt+eci+WIsOeahOeKtuaAgeWwseaYr+mUmeeahOOAglxuICovXG5jb25zdCBidXN5ID0gY29tcHV0ZWQoKCkgPT4gdXBsb2FkaW5nLnZhbHVlIHx8IGltcG9ydGluZy52YWx1ZSlcblxuLyogPT09PT09PT09PT09PT09PT09PT09IOi9ruivoiA9PT09PT09PT09PT09PT09PT09PT0gKi9cblxuY29uc3QgY2xlYXJQb2xsVGltZXJzID0gKCkgPT4ge1xuICBwb2xsVGltZXJzLmZvckVhY2goKHQpID0+IHdpbmRvdy5jbGVhclRpbWVvdXQodCkpXG4gIHBvbGxUaW1lcnMgPSBbXVxuICBwb2xsaW5nRG9jcy5jbGVhcigpXG59XG5cbi8qKlxuICog5LiK5Lyg5ZCO6L2u6K+i5aSE55CG54q25oCB77yM55u05Yiw5oiQ5YqfIC8g5aSx6LSlIC8g6LaF5pe2XG4gKlxuICog5ZCO56uvIGAvZG9jdW1lbnQvdXBsb2FkYCDmmK/jgIzlkIzmraXop6PmnpAgKyDlkI7lj7DlkJHph4/ljJbjgI3vvIzov5Tlm57ml7blj6rmmK8gc3RhdHVzPTHvvIxcbiAqIOecn+ato+eahOOAjOiDveS4jeiDveajgOe0ouWIsOOAjeimgeetiSBzdGF0dXM9NeOAguS4jei9ruivoueahOivneeUqOaIt+S8muS7peS4uuS8oOWksei0peS6huOAglxuICovXG5jb25zdCBwb2xsRG9jdW1lbnQgPSAoZG9jSWQ6IG51bWJlciwgcm91bmQgPSAwKSA9PiB7XG4gIC8vIOW3sue7j+WcqOebr+edgOi/meevh+S6hiDihpIg5LiN5YaN5Y+g5Yqg5LiA5Liq5a6a5pe25Zmo77yI6KeBIHBvbGxpbmdEb2NzIOeahOivtOaYju+8iVxuICBpZiAocm91bmQgPT09IDApIHtcbiAgICBpZiAocG9sbGluZ0RvY3MuaGFzKGRvY0lkKSkgcmV0dXJuXG4gICAgcG9sbGluZ0RvY3MuYWRkKGRvY0lkKVxuICB9XG5cbiAgY29uc3QgdGltZXIgPSB3aW5kb3cuc2V0VGltZW91dChhc3luYyAoKSA9PiB7XG4gICAgdHJ5IHtcbiAgICAgIGNvbnN0IHJlczogYW55ID0gYXdhaXQgZ2V0RG9jdW1lbnRTdGF0dXMoZG9jSWQpXG4gICAgICBpZiAocmVzPy5jb2RlICE9PSAyMDApIHJldHVyblxuICAgICAgY29uc3QgaW5mbyA9IHJlcy5kYXRhIHx8IHt9XG4gICAgICBjb25zdCByb3cgPSBkb2N1bWVudHMudmFsdWUuZmluZCgoZCkgPT4gZC5kb2NJZCA9PT0gZG9jSWQpXG4gICAgICBpZiAocm93KSB7XG4gICAgICAgIHJvdy5zdGF0dXMgPSBpbmZvLnN0YXR1c1xuICAgICAgICByb3cuc3RhdHVzVGV4dCA9IGluZm8uc3RhdHVzVGV4dFxuICAgICAgICByb3cuY2h1bmtDb3VudCA9IGluZm8uY2h1bmtDb3VudFxuICAgICAgICByb3cuZXJyb3JNc2cgPSBpbmZvLmVycm9yTXNnXG4gICAgICB9XG4gICAgICBpZiAoIWluZm8uZG9uZSAmJiByb3VuZCA8IFBPTExfTUFYX1JPVU5EUykge1xuICAgICAgICBwb2xsRG9jdW1lbnQoZG9jSWQsIHJvdW5kICsgMSlcbiAgICAgICAgcmV0dXJuXG4gICAgICB9XG4gICAgICBwb2xsaW5nRG9jcy5kZWxldGUoZG9jSWQpXG4gICAgICBpZiAoaW5mby5vaykge1xuICAgICAgICB1cGxvYWRUaXAudmFsdWUgPSAnJ1xuICAgICAgICAvLyDliIblnZfmlbDlj5jkuoYg4oaSIOW6k+S4iueahOiuoeaVsOS5n+imgeWIt+aWsFxuICAgICAgICBsb2FkS2JzKClcbiAgICAgIH0gZWxzZSBpZiAocm91bmQgPj0gUE9MTF9NQVhfUk9VTkRTKSB7XG4gICAgICAgIHVwbG9hZFRpcC52YWx1ZSA9ICfmlofmoaPov5jlnKjlpITnkIbkuK3vvIznqI3lkI7lm57mnaXliLfmlrDnnIvnnIsnXG4gICAgICB9IGVsc2Uge1xuICAgICAgICB1cGxvYWRUaXAudmFsdWUgPSBg44CMJHtyb3c/LmZpbGVOYW1lIHx8ICfmlofmoaMnfeOAjeWkhOeQhuWksei0pe+8miR7aW5mby5lcnJvck1zZyB8fCAn5pyq55+l5Y6f5ZugJ31gXG4gICAgICB9XG4gICAgfSBjYXRjaCB7XG4gICAgICAvLyDova7or6LlpLHotKXkuI3miZPmibDnlKjmiLfvvJrmlL7lvIDljrvph43moIforrDvvIzkuIvmrKEgbG9hZERvY3Mg5Lya6YeN5paw55uv5LiK5a6DXG4gICAgICBwb2xsaW5nRG9jcy5kZWxldGUoZG9jSWQpXG4gICAgfVxuICB9LCBQT0xMX0lOVEVSVkFMKVxuICBwb2xsVGltZXJzLnB1c2godGltZXIpXG59XG5cbi8qID09PT09PT09PT09PT09PT09PT09PSDmlbDmja7liqDovb0gPT09PT09PT09PT09PT09PT09PT09ICovXG5cbi8qKlxuICog5Yqg6L2955+l6K+G5bqT5YiX6KGoXG4gKlxuICogYGF1dG9TZWxlY3Q9ZmFsc2VgIOWPquaKiuWIl+ihqOWPluWbnuadpe+8iOWkn+WFpeWPo+W+veagh+eUqOS6hu+8ie+8mioq5LiN6YCJ5bqT44CB5LiN5ouJ5paH5qGj44CB5LiN6LW36L2u6K+iKirjgIJcbiAqXG4gKiDimqDvuI8g5oyC6L295pyf5b+F6aG76LWwIGBmYWxzZWAg6L+Z5p2h6Lev44CCYGF1dG9TZWxlY3Q9dHJ1ZWAg5Lya6L+e6ZSB5YiwXG4gKiAgICBgc2VsZWN0S2Ig4oaSIGxvYWREb2NzIOKGkiBwb2xsRG9jdW1lbnRg77yM5LqO5piv44CM6L+b6L+H6aG16Z2i5L2G5LuO5rKh5omT5byA5oq95bGJ44CN55qE55So5oi3XG4gKiAgICDkuZ/kvJrooqvmjILkuIrkuIDkuLLlkI7lj7Dova7or6Ig4oCU4oCUIOiAjOmCo+S6m+WumuaXtuWZqOWPquWcqOaKveWxiSBgQGNsb3NlZGAg5pe25omN5riF55CG44CCXG4gKlxuICog5aSx6LSl55qE5a6J6Z2Z5oCn6LSo6KaB5L+d5L2P77yaKirkuI3lvLnmj5DnpLrjgIHkuI3mipvlh7rljrsqKu+8iOWPluS4jeWIsOWIl+ihqOWwseS4jeaYvuekuuW+veagh+aVsOWtl++8jFxuICog5Yir5Li65LqG5LiA5qyh5ZCO5Y+w6K+35rGC5omT5omw55So5oi377yJ44CC5L2G44CM5a6J6Z2Z44CN5LiN562J5LqO44CM5LiN55WZ55eV44CN4oCU4oCUXG4gKiDlj5bkuI3liLDml7bmioogYGtiTG9hZEZhaWxlZGAg56uL6LW35p2l77ya5oq95bGJ6YeM6YKj5p2h56m65oCBL+i/h+acn+aVsOaNrueahOaPkOekuuWwseaYr+mdoOWug++8jFxuICog5ZCm5YiZ55So5oi355yL5Yiw55qE5Lya5piv44CM6L+Y5rKh5pyJ55+l6K+G5bqT44CN77yI5YGH5L+h5oGv77yJ44CCXG4gKi9cbmNvbnN0IGxvYWRLYnMgPSBhc3luYyAoYXV0b1NlbGVjdCA9IHRydWUpID0+IHtcbiAgbG9hZGluZy52YWx1ZSA9IHRydWVcbiAgdHJ5IHtcbiAgICBjb25zdCByZXM6IGFueSA9IGF3YWl0IGxpc3RLbm93bGVkZ2VCYXNlcygpXG4gICAgaWYgKHJlcz8uY29kZSA9PT0gMjAwICYmIEFycmF5LmlzQXJyYXkocmVzLmRhdGEpKSB7XG4gICAgICBrYkxvYWRGYWlsZWQudmFsdWUgPSBmYWxzZVxuICAgICAga2JzLnZhbHVlID0gcmVzLmRhdGFcbiAgICAgIC8vIOmAieS4reeahOW6k+iiq+WIoOaOieS6hiDihpIg6YCA5Zue56ys5LiA5LiqXG4gICAgICBpZiAoYWN0aXZlS2JJZC52YWx1ZSAmJiAha2JzLnZhbHVlLnNvbWUoKGspID0+IGsua2JJZCA9PT0gYWN0aXZlS2JJZC52YWx1ZSkpIHtcbiAgICAgICAgYWN0aXZlS2JJZC52YWx1ZSA9IG51bGxcbiAgICAgICAgZG9jdW1lbnRzLnZhbHVlID0gW11cbiAgICAgIH1cbiAgICAgIGlmIChhdXRvU2VsZWN0ICYmICFhY3RpdmVLYklkLnZhbHVlICYmIGticy52YWx1ZS5sZW5ndGgpIGF3YWl0IHNlbGVjdEtiKGticy52YWx1ZVswXSlcbiAgICB9IGVsc2Uge1xuICAgICAgLy8gKirkuI3pnZnpu5jpgJrov4cqKu+8mui/meS4jeaYr+OAjOmbtuS4quefpeivhuW6k+OAje+8jOi/meaYr+OAjOayoeWPluWIsOWIl+ihqOOAje+8iOingSBrYkxvYWRGYWlsZWQg55qE5rOo6YeK77yJXG4gICAgICBrYkxvYWRGYWlsZWQudmFsdWUgPSB0cnVlXG4gICAgICBjb25zb2xlLndhcm4oJ1trYl0g55+l6K+G5bqT5YiX6KGo5ZON5bqU5LiN5piv5pWw57uEJywgcmVzKVxuICAgIH1cbiAgfSBjYXRjaCAoZSkge1xuICAgIGtiTG9hZEZhaWxlZC52YWx1ZSA9IHRydWVcbiAgICBjb25zb2xlLndhcm4oJ1trYl0g5Yqg6L2955+l6K+G5bqT5aSx6LSlJywgZSlcbiAgfSBmaW5hbGx5IHtcbiAgICBsb2FkaW5nLnZhbHVlID0gZmFsc2VcbiAgfVxufVxuXG5jb25zdCBsb2FkRG9jcyA9IGFzeW5jIChrYklkOiBudW1iZXIpID0+IHtcbiAgZG9jc0xvYWRpbmcudmFsdWUgPSB0cnVlXG4gIHRyeSB7XG4gICAgY29uc3QgcmVzOiBhbnkgPSBhd2FpdCBsaXN0RG9jdW1lbnRzKGtiSWQpXG4gICAgaWYgKHJlcz8uY29kZSA9PT0gMjAwICYmIEFycmF5LmlzQXJyYXkocmVzLmRhdGEpKSB7XG4gICAgICBkb2N1bWVudHMudmFsdWUgPSByZXMuZGF0YVxuICAgICAgLy8g5pyJ5paH5qGj6L+Y5Zyo5aSE55CGIOKGkiDnu6fnu63ova7or6LvvIjopobnm5bjgIzkuIrmrKHmsqHnnIvlrozlsLHlhbPkuobmir3lsYnjgI3nmoTmg4XlhrXvvIlcbiAgICAgIGRvY3VtZW50cy52YWx1ZS5maWx0ZXIoKGQpID0+IGlzRG9jdW1lbnRQcm9jZXNzaW5nKGQuc3RhdHVzKSkuZm9yRWFjaCgoZCkgPT4gcG9sbERvY3VtZW50KGQuZG9jSWQpKVxuICAgIH1cbiAgfSBjYXRjaCAoZSkge1xuICAgIGNvbnNvbGUud2FybignW2tiXSDliqDovb3mlofmoaPlpLHotKUnLCBlKVxuICB9IGZpbmFsbHkge1xuICAgIGRvY3NMb2FkaW5nLnZhbHVlID0gZmFsc2VcbiAgfVxufVxuXG5jb25zdCBzZWxlY3RLYiA9IGFzeW5jIChrYjogUmFnS25vd2xlZGdlQmFzZSkgPT4ge1xuICBhY3RpdmVLYklkLnZhbHVlID0ga2Iua2JJZFxuICB1cGxvYWRUaXAudmFsdWUgPSAnJ1xuICByZXNldFByb2JlKClcbiAgYXdhaXQgbG9hZERvY3Moa2Iua2JJZClcbn1cblxuY29uc3QgcmVzZXRQcm9iZSA9ICgpID0+IHtcbiAgcHJvYmVRdWVyeS52YWx1ZSA9ICcnXG4gIHByb2JlRG9uZS52YWx1ZSA9IGZhbHNlXG4gIHByb2JlSGl0cy52YWx1ZSA9IFtdXG59XG5cbi8qKiDlnKjlvZPliY3nn6Xor4blupPph4zor5Xmo4DntKLvvIjlj6rmo4DntKLjgIHkuI3osIPmqKHlnovvvIkgKi9cbmNvbnN0IHJ1blByb2JlID0gYXN5bmMgKCkgPT4ge1xuICBjb25zdCBxID0gcHJvYmVRdWVyeS52YWx1ZS50cmltKClcbiAgaWYgKCFxIHx8ICFhY3RpdmVLYklkLnZhbHVlKSByZXR1cm5cbiAgcHJvYmluZy52YWx1ZSA9IHRydWVcbiAgdHJ5IHtcbiAgICBjb25zdCByZXM6IGFueSA9IGF3YWl0IHNlYXJjaEtub3dsZWRnZShxLCBbYWN0aXZlS2JJZC52YWx1ZV0pXG4gICAgaWYgKHJlcz8uY29kZSA9PT0gMjAwKSB7XG4gICAgICBwcm9iZUhpdHMudmFsdWUgPSByZXMuZGF0YT8uaGl0cyB8fCBbXVxuICAgICAgcHJvYmVEb25lLnZhbHVlID0gdHJ1ZVxuICAgIH0gZWxzZSB7XG4gICAgICBFbE1lc3NhZ2UuZXJyb3IocmVzPy5tc2cgfHwgJ+ajgOe0ouWksei0pScpXG4gICAgfVxuICB9IGNhdGNoIChlOiBhbnkpIHtcbiAgICBFbE1lc3NhZ2UuZXJyb3IoZT8ubWVzc2FnZSB8fCAn5qOA57Si5aSx6LSlJylcbiAgfSBmaW5hbGx5IHtcbiAgICBwcm9iaW5nLnZhbHVlID0gZmFsc2VcbiAgfVxufVxuXG5jb25zdCBvbk9wZW4gPSBhc3luYyAoKSA9PiB7XG4gIGFjdGl2ZUtiSWQudmFsdWUgPSBudWxsXG4gIGRvY3VtZW50cy52YWx1ZSA9IFtdXG4gIGF3YWl0IGxvYWRLYnMoKVxufVxuXG5jb25zdCBvcGVuID0gKCkgPT4ge1xuICB2aXNpYmxlLnZhbHVlID0gdHJ1ZVxufVxuXG4vKiA9PT09PT09PT09PT09PT09PT09PT0g55+l6K+G5bqT5aKe5Yig5pS5ID09PT09PT09PT09PT09PT09PT09PSAqL1xuXG5jb25zdCBwcm9tcHRDcmVhdGUgPSBhc3luYyAoKSA9PiB7XG4gIGxldCBuYW1lID0gJydcbiAgdHJ5IHtcbiAgICBjb25zdCByOiBhbnkgPSBhd2FpdCBFbE1lc3NhZ2VCb3gucHJvbXB0KCfnu5nnn6Xor4blupPotbfkuKrlkI3lrZcnLCAn5paw5bu655+l6K+G5bqTJywge1xuICAgICAgY29uZmlybUJ1dHRvblRleHQ6ICfliJvlu7onLFxuICAgICAgY2FuY2VsQnV0dG9uVGV4dDogJ+WPlua2iCcsXG4gICAgICBpbnB1dFBsYWNlaG9sZGVyOiAn5L6L5aaC77ya5pWw5o2u57uT5p6E5pyf5pyr5aSN5LmgJyxcbiAgICAgIGlucHV0VmFsaWRhdG9yOiAodjogc3RyaW5nKSA9PiAodiAmJiB2LnRyaW0oKSA/IHRydWUgOiAn5ZCN5a2X5LiN6IO95Li656m6JylcbiAgICB9KVxuICAgIG5hbWUgPSBTdHJpbmcocj8udmFsdWUgfHwgJycpLnRyaW0oKVxuICB9IGNhdGNoIHtcbiAgICByZXR1cm5cbiAgfVxuICBpZiAoIW5hbWUpIHJldHVyblxuXG4gIGNyZWF0aW5nLnZhbHVlID0gdHJ1ZVxuICB0cnkge1xuICAgIGNvbnN0IHJlczogYW55ID0gYXdhaXQgY3JlYXRlS25vd2xlZGdlQmFzZSh7IG5hbWUgfSlcbiAgICBpZiAocmVzPy5jb2RlID09PSAyMDApIHtcbiAgICAgIEVsTWVzc2FnZS5zdWNjZXNzKCfnn6Xor4blupPlt7LliJvlu7onKVxuICAgICAgYXdhaXQgbG9hZEticygpXG4gICAgICBjb25zdCBjcmVhdGVkID0ga2JzLnZhbHVlLmZpbmQoKGspID0+IGsua2JJZCA9PT0gcmVzLmRhdGE/LmtiSWQpXG4gICAgICBpZiAoY3JlYXRlZCkgYXdhaXQgc2VsZWN0S2IoY3JlYXRlZClcbiAgICB9IGVsc2Uge1xuICAgICAgRWxNZXNzYWdlLmVycm9yKHJlcz8ubXNnIHx8ICfliJvlu7rlpLHotKUnKVxuICAgIH1cbiAgfSBjYXRjaCAoZTogYW55KSB7XG4gICAgRWxNZXNzYWdlLmVycm9yKGU/Lm1lc3NhZ2UgfHwgJ+WIm+W7uuWksei0pScpXG4gIH0gZmluYWxseSB7XG4gICAgY3JlYXRpbmcudmFsdWUgPSBmYWxzZVxuICB9XG59XG5cbmNvbnN0IHByb21wdFJlbmFtZSA9IGFzeW5jIChrYjogUmFnS25vd2xlZGdlQmFzZSkgPT4ge1xuICBsZXQgbmFtZSA9ICcnXG4gIHRyeSB7XG4gICAgY29uc3QgcjogYW55ID0gYXdhaXQgRWxNZXNzYWdlQm94LnByb21wdCgn5pS55oiQ5LuA5LmI5ZCN5a2X77yfJywgJ+mHjeWRveWQjeefpeivhuW6kycsIHtcbiAgICAgIGNvbmZpcm1CdXR0b25UZXh0OiAn5L+d5a2YJyxcbiAgICAgIGNhbmNlbEJ1dHRvblRleHQ6ICflj5bmtognLFxuICAgICAgaW5wdXRWYWx1ZToga2IubmFtZSxcbiAgICAgIGlucHV0VmFsaWRhdG9yOiAodjogc3RyaW5nKSA9PiAodiAmJiB2LnRyaW0oKSA/IHRydWUgOiAn5ZCN5a2X5LiN6IO95Li656m6JylcbiAgICB9KVxuICAgIG5hbWUgPSBTdHJpbmcocj8udmFsdWUgfHwgJycpLnRyaW0oKVxuICB9IGNhdGNoIHtcbiAgICByZXR1cm5cbiAgfVxuICBpZiAoIW5hbWUgfHwgbmFtZSA9PT0ga2IubmFtZSkgcmV0dXJuXG5cbiAgdHJ5IHtcbiAgICBjb25zdCByZXM6IGFueSA9IGF3YWl0IHVwZGF0ZUtub3dsZWRnZUJhc2Uoa2Iua2JJZCwgeyBuYW1lIH0pXG4gICAgaWYgKHJlcz8uY29kZSA9PT0gMjAwKSB7XG4gICAgICBFbE1lc3NhZ2Uuc3VjY2Vzcygn5bey6YeN5ZG95ZCNJylcbiAgICAgIGF3YWl0IGxvYWRLYnMoKVxuICAgIH0gZWxzZSB7XG4gICAgICBFbE1lc3NhZ2UuZXJyb3IocmVzPy5tc2cgfHwgJ+mHjeWRveWQjeWksei0pScpXG4gICAgfVxuICB9IGNhdGNoIChlOiBhbnkpIHtcbiAgICBFbE1lc3NhZ2UuZXJyb3IoZT8ubWVzc2FnZSB8fCAn6YeN5ZG95ZCN5aSx6LSlJylcbiAgfVxufVxuXG5jb25zdCByZW1vdmVLYiA9IGFzeW5jIChrYjogUmFnS25vd2xlZGdlQmFzZSkgPT4ge1xuICB0cnkge1xuICAgIGF3YWl0IEVsTWVzc2FnZUJveC5jb25maXJtKFxuICAgICAgYOWIoOmZpOOAjCR7a2IubmFtZX3jgI3vvJ/lupPph4znmoQgJHtrYi5kb2NDb3VudCB8fCAwfSDnr4fmlofmoaPkuI7liIblnZfkvJrkuIDlubbmuIXmjonvvIzkuI3lj6/mkqTplIDjgIJgLFxuICAgICAgJ+WIoOmZpOehruiupCcsXG4gICAgICB7IGNvbmZpcm1CdXR0b25UZXh0OiAn5Yig6ZmkJywgY2FuY2VsQnV0dG9uVGV4dDogJ+WPlua2iCcsIHR5cGU6ICd3YXJuaW5nJyB9XG4gICAgKVxuICB9IGNhdGNoIHtcbiAgICByZXR1cm5cbiAgfVxuICB0cnkge1xuICAgIGNvbnN0IHJlczogYW55ID0gYXdhaXQgZGVsZXRlS25vd2xlZGdlQmFzZShrYi5rYklkKVxuICAgIGlmIChyZXM/LmNvZGUgPT09IDIwMCkge1xuICAgICAgRWxNZXNzYWdlLnN1Y2Nlc3MoJ+efpeivhuW6k+W3suWIoOmZpCcpXG4gICAgICBpZiAoYWN0aXZlS2JJZC52YWx1ZSA9PT0ga2Iua2JJZCkge1xuICAgICAgICBhY3RpdmVLYklkLnZhbHVlID0gbnVsbFxuICAgICAgICBkb2N1bWVudHMudmFsdWUgPSBbXVxuICAgICAgfVxuICAgICAgYXdhaXQgbG9hZEticygpXG4gICAgfSBlbHNlIHtcbiAgICAgIEVsTWVzc2FnZS5lcnJvcihyZXM/Lm1zZyB8fCAn5Yig6Zmk5aSx6LSlJylcbiAgICB9XG4gIH0gY2F0Y2ggKGU6IGFueSkge1xuICAgIEVsTWVzc2FnZS5lcnJvcihlPy5tZXNzYWdlIHx8ICfliKDpmaTlpLHotKUnKVxuICB9XG59XG5cbi8qID09PT09PT09PT09PT09PT09PT09PSDlsY/olL3vvIjnu5kgTExNIOeahOS4gOmBk+mXuOmXqO+8iSA9PT09PT09PT09PT09PT09PT09PT0gKi9cblxuLyoqIOato+WcqOWGmSBgZGlzYWJsZWRgIOeahOmCo+S4quW6kyDigJTigJQg5Y+q55So5p2l57uZ6YKj5LiA6KGM55qE5byA5YWz5LiKIGxvYWRpbmcgKi9cbmNvbnN0IHRvZ2dsaW5nS2JJZCA9IHJlZjxudW1iZXIgfCBudWxsPihudWxsKVxuXG4vKipcbiAqIOi/meS4quW6k+eOsOWcqCoq6IO96KKr5pm66IO95L2T5p+l5Yiw5ZCXKirvvIzkuZ/lsLHmmK/lvIDlhbPnmoTjgIzlvIDjgI3nirbmgIFcbiAqXG4gKiDimqDvuI8g5Yik5o2u5Y+q6IO95pivIGBkaXNhYmxlZCAhPT0gMWDvvIwqKuS4jeiDvSoq5YaZ5oiQ44CMYD09PSAwYCDmiY3nrpfmraPluLjjgI3vvJpcbiAqICAgIGBkaXNhYmxlZGAg5YiX5piv5ZCO5Yqg55qE77yM5Zyo6L+Z5LiA54mI5ZCO56uv5LiK57q/5LmL5YmN5q+P5LiA6KGM55qE6L+Q6KGM5pe25YC86YO95pivIGB1bmRlZmluZWRg77yMXG4gKiAgICBgPT09IDBgIOS8muaKiioq5q+P5LiA5Liq546w5a2Y55+l6K+G5bqTKirpg73nlLvmiJDjgIzlt7LlsY/olL3jgI3igJTigJQg55So5oi35Lya5Lul5Li66Ieq5bex55qE6LWE5paZ5YWo6KKr5bGP6JS95LqG44CCXG4gKiAgICBgIT09IDFgIOWcqCBgdW5kZWZpbmVkYCAvIGAwYCDml7bpg73liKTjgIzmraPluLjjgI3vvIzkuI7liqDov5nkuKrlip/og73kuYvliY3nmoTooYzkuLrkuIDoh7TjgIJcbiAqICAgIO+8iOS5n+S4jeimgeeUqCBgISFrYi5kaXNhYmxlZGDvvJpgISF1bmRlZmluZWRgIOiZveeEtuWQjOagt+aYryBmYWxzZe+8jOS9huWug+S8muaKiuWwhuadpeeahFxuICogICAgICBgMmAgLyBgJzEnYCDkuYvnsbvkuIDlvovnrpfmiJDjgIzlt7LlsY/olL3jgI3vvIzogIwgYCE9PSAxYCDkuI3kvJrjgILvvIlcbiAqXG4gKiDimqDvuI/imqDvuI8g6L+U5ZueKirluIPlsJQqKuiAjOS4jeaYryBgMGAvYDFg77yM6L+Z5pivKirlv4XpnIAqKueahO+8iOS4jeaYr+mhuuaJi+WGmeeahO+8ie+8mmBlbC1zd2l0Y2hgIOWcqCBzZXR1cCDmnJ9cbiAqICAgIOS8muajgOafpee7keWumuWAvOaYr+WQpuiQveWcqCBgW2FjdGl2ZVZhbHVlLCBpbmFjdGl2ZVZhbHVlXWAg6YeM77yM5LiN5Zyo5bCxKirlnKjmsqHmnInnlKjmiLfmk43kvZznmoTmg4XlhrXkuIsqKlxuICogICAgZW1pdCDkuIDmrKEgYHVwZGF0ZTptb2RlbFZhbHVlYCAvIGBjaGFuZ2Vg77yI5a6e5rWL5bey5a6J6KOF55qEIGBlbGVtZW50LXBsdXNAMi4xNC41YO+8mlxuICogICAgYGVzL2NvbXBvbmVudHMvc3dpdGNoL3NyYy9zd2l0Y2gudnVlX3Z1ZV90eXBlX3NjcmlwdF9zZXR1cF90cnVlX2xhbmcubWpzOjcxLTc2YO+8jFxuICogICAg6buY6K6kIGBhY3RpdmVWYWx1ZSA9IHRydWVgIC8gYGluYWN0aXZlVmFsdWUgPSBmYWxzZWDvvInjgIJcbiAqICAgIOaJgOS7peWmguaenOaKiiBga2IuZGlzYWJsZWRgICoq5Y6f5qC3Kirnu5HkuIrljrvvvIxgdW5kZWZpbmVkYO+8iOWQjuerr+i/mOayoeS4iue6v+i/meS4gOWIl++8ieWSjOWtl+espuS4siBgJzEnYFxuICogICAg77yI57G75Z6L5LiN5Yy56YWN77yM6YKj6L655piv5Lil5qC8IGA9PT1g77yJ6YO95Lya5ZG95Lit6YKj5LiA5qC8IOKHkiAqKuWIl+ihqOmHjOavj+S4gOihjOWQhCBlbWl0IOS4gOasoSoqIOKHklxuICogICAg5omT5byA5oq95bGJ5bCx5Y+v6IO95a+55q+P5LiA6KGM5Y+R5LiA5qyhIFBVVOOAgue7keaBkuS4uiBgdHJ1ZWAvYGZhbHNlYCDnmoTooajovr7lvI/liJnmsLjov5zokL3lnKjpu5jorqTlj5blgLzln5/ph4zvvIxcbiAqICAgIOS4jeWPr+iDveinpuWPkeOAgu+8iOaooeadv+mHjOWQjOaXtioq5LiN6KaBKirlhpkgYDphY3RpdmUtdmFsdWVgIC8gYDppbmFjdGl2ZS12YWx1ZWDjgILvvIlcbiAqL1xuY29uc3Qga2JFbmFibGVkID0gKGtiOiBSYWdLbm93bGVkZ2VCYXNlKSA9PiBrYi5kaXNhYmxlZCAhPT0gMVxuXG4vKipcbiAqIOWxj+iUvSAvIOWPlua2iOWxj+iUveS4gOS4quefpeivhuW6k1xuICpcbiAqICoq5Y+X5o6n5byPKirvvJrmnKzlnLAqKuS4jSoq5pS5IGBrYi5kaXNhYmxlZGDvvIzmmL7npLrlgLzmsLjov5zmnaXoh6rmnI3liqHnq68g4oCU4oCUIOWGmeaIkOWKn+S5i+WQjiBgbG9hZEticygpYCDph43lj5bjgIJcbiAqXG4gKiDimqDvuI8g5Li65LuA5LmI5LiN55So44CM5LmQ6KeC5byP44CN77yI5YWI5pys5Zyw57+76L+H5Y6744CB5aSx6LSl5YaN57+75Zue5p2l77yMYHZpZXdzL2Zyb250L2VuZ2xpc2gvdm9jYWJ1bGFyeS9kZXRhaWwudnVlYFxuICogICAg5piv6YKj56eN5YaZ5rOV77yJ77ya6YKj56eN5Zue5rua5Y+q5ZyoIGBjb2RlICE9PSAyMDBgIOaIluaKm+W8guW4uOaXtuWPkeeUn++8jOiAjOWQjuerryBjYXRjaC1hbGwg5Lya5oqKXG4gKiAgICDjgIzot6/nlLHooqvmjKrotbAgLyDlrZfmrrXlkI3kuI3kuIDoh7TjgI3ooajnjrDmiJAgKipgY29kZSAyMDBgICsgYGRhdGE6IG51bGxgIOeahOWBh+aIkOWKnyoqIOKAlOKAlFxuICogICAg5LqO5piv5pyN5Yqh56uv5LuA5LmI6YO95rKh5a2Y77yMVUkg5Y205oqK5byA5YWz55WZ5Zyo44CM5bey5bGP6JS944CN5LiK77ya55So5oi35Lul5Li66L+Z5Liq5bqT6KKr5bGP6JS95LqG77yMXG4gKiAgICDkuIvkuIDmrKHmj5Dpl67nhafmoLfmlbTlupPlloLnu5nmqKHlnovjgILov5nmraPmmK/mnKzpobnnm67mnIDlv4zorrPnmoTjgIznnIvotbfmnaXlnKjpmLLjgIHlhbblrp7msqHpmLLjgI3jgIJcbiAqICAgIOWPl+aOp+W8j+acgOWdj+WPquiuqeW8gOWFsyoq5by55Zue5Y6f5L2NKirvvIzkuI3lj6/og73kvKrpgKDnirbmgIHjgIJcbiAqXG4gKiDimqDvuI8gYG9uYCDmmK8qKuW8gOWFs+imgeWOu+eahOW8gC/lhbPnirbmgIEqKu+8iGB0cnVlYCA9IOaZuuiDveS9k+WPr+afpe+8ie+8jOWGmeWbnuacjeWKoeerr+eahCBgZGlzYWJsZWRgIOato+WlveebuOWPjeOAglxuICogICAg5Y+W5YC85p2l6IeqIGBlbC1zd2l0Y2hgIOeahCBgdXBkYXRlOm1vZGVsLXZhbHVlYCDkuovku7bvvIjpgqPkuKrkuovku7bluKbnmoTlsLHmmK8qKuaWsOWAvCoq77yJ77yMXG4gKiAgICDmiYDku6Xov5nph4zkuI3kvp3otZbjgIx2LW1vZGVsIOacieayoeacieWFiOWGmeWbnuOAjei/meenjeWPkeWwhOmhuuW6j+OAglxuICovXG5jb25zdCB0b2dnbGVLYkRpc2FibGVkID0gYXN5bmMgKGtiOiBSYWdLbm93bGVkZ2VCYXNlLCBvbjogYm9vbGVhbikgPT4ge1xuICBjb25zdCB3YW50OiAwIHwgMSA9IG9uID8gMCA6IDFcbiAgLy8g4pGgIOimgeWOu+eahOeKtuaAgeWwseaYr+Wug+eOsOWcqOeahOeKtuaAgSDihpIg6L+Z5LiN5piv55So5oi35pON5L2c77yM5LiA5Liq5a2X6YO95LiN5YaZ44CCXG4gIC8vICAgIOi/meaMoeS9j+S4pOenjeS4nOilv++8muW8gOWFsyoq56iL5bqP5YyWKirnmoQgZW1pdO+8iOWug+aKpeeahOWwseaYr+W9k+WJjeeKtuaAge+8ie+8jFxuICAvLyAgICDku6Xlj4rjgIzkuIrkuIDmrKEgUFVUIOi/mOWcqOmjnuOAgeeUqOaIt+WPiOeCueS4gOS4i+OAjemAoOaIkOeahOmHjeWkjeaPkOS6pOOAglxuICAvL1xuICAvLyAgICDimqDvuI8g5rOo5oSP6L+Z6YGT5a6I5Y2rKirmjKHkuI3kvY8qKuOAjOWAvOS4jeWcqOWPluWAvOWfn+aXtumCo+asoSBlbWl044CN77ya6YKj56eNIGVtaXQg5oql55qE5pivKirnm7jlj40qKueahOeKtuaAge+8jFxuICAvLyAgICAgICDor63kuYnkuIrlkozjgIznlKjmiLfnnJ/nmoTopoHlsY/olL3jgI3kuIDmqKHkuIDmoLfvvIzlrojljavml6Dku47liIbovqgg4oCU4oCUIOmCo+asoSBlbWl0IOWPquiDvemdoFxuICAvLyAgICAgICBga2JFbmFibGVkYCDov5Tlm57luIPlsJTvvIjmqKHmnb/nu5Hooajovr7lvI/vvInmnaXku47mupDlpLTmtojpmaTvvIzkuI3og73pnaDov5nph4zlhZzjgIJcbiAgaWYgKChrYkVuYWJsZWQoa2IpID8gMCA6IDEpID09PSB3YW50KSByZXR1cm5cbiAgdG9nZ2xpbmdLYklkLnZhbHVlID0ga2Iua2JJZFxuICB0cnkge1xuICAgIGNvbnN0IHJlczogYW55ID0gYXdhaXQgdXBkYXRlS25vd2xlZGdlQmFzZShrYi5rYklkLCB7IGRpc2FibGVkOiB3YW50IH0pXG4gICAgaWYgKHJlcz8uY29kZSA9PT0gMjAwKSB7XG4gICAgICAvLyDikaEg6YeN5Y+W5YiX6KGo77ya5pi+56S65YC85Y+q6K6k5pyN5Yqh56uv5Zue5YC877yI6KeB5LiK6Z2i44CM5Li65LuA5LmI5LiN55So5LmQ6KeC5byP44CN77yJXG4gICAgICBhd2FpdCBsb2FkS2JzKClcbiAgICAgIEVsTWVzc2FnZS5zdWNjZXNzKFxuICAgICAgICB3YW50ID09PSAxXG4gICAgICAgICAgPyBg5bey5bGP6JS944CMJHtrYi5uYW1lfeOAjeKAlOKAlCDmmbrog73kvZPmj5Dpl67kuI7or5Xmo4DntKLpg73kuI3kvJrlho3mn6Xov5nkuKrlupNgXG4gICAgICAgICAgOiBg5bey5oGi5aSN44CMJHtrYi5uYW1lfeOAjeKAlOKAlCDmmbrog73kvZPmj5Dpl67kuI7or5Xmo4DntKLpg73kvJrmraPluLjmn6XlroNgXG4gICAgICApXG4gICAgfSBlbHNlIHtcbiAgICAgIEVsTWVzc2FnZS5lcnJvcihyZXM/Lm1zZyB8fCAn5pON5L2c5aSx6LSlJylcbiAgICB9XG4gIH0gY2F0Y2ggKGU6IGFueSkge1xuICAgIEVsTWVzc2FnZS5lcnJvcihlPy5tZXNzYWdlIHx8ICfmk43kvZzlpLHotKUnKVxuICB9IGZpbmFsbHkge1xuICAgIHRvZ2dsaW5nS2JJZC52YWx1ZSA9IG51bGxcbiAgfVxufVxuXG4vKiA9PT09PT09PT09PT09PT09PT09PT0g5paH5qGjID09PT09PT09PT09PT09PT09PT09PSAqL1xuXG5jb25zdCBvbkZpbGVzUGlja2VkID0gYXN5bmMgKGV2dDogRXZlbnQpID0+IHtcbiAgY29uc3QgaW5wdXQgPSBldnQudGFyZ2V0IGFzIEhUTUxJbnB1dEVsZW1lbnRcbiAgY29uc3QgZmlsZXMgPSBBcnJheS5mcm9tKGlucHV0LmZpbGVzIHx8IFtdKVxuICAvLyDmuIXnqbogdmFsdWXvvIzlkKbliJnpgInlkIzkuIDkuKrmlofku7bkuI3kvJrlho3op6blj5EgY2hhbmdlXG4gIGlucHV0LnZhbHVlID0gJydcbiAgLy8gYnVzeSDph4zlkKvjgIznspjotLTlr7zlhaXmraPlnKjov5vooYzjgI3igJTigJQg6L6T5YWl5qGG6YKj5pe25pivIGRpc2FibGVkIOeahO+8jOi/memHjOaYr+esrOS6jOmBk1xuICBpZiAoIWZpbGVzLmxlbmd0aCB8fCAhYWN0aXZlS2JJZC52YWx1ZSB8fCBidXN5LnZhbHVlKSByZXR1cm5cblxuICBjb25zdCBiYWQgPSBmaWxlcy5maWx0ZXIoKGYpID0+ICFpc1N1cHBvcnRlZEtiRmlsZShmLm5hbWUpKVxuICBpZiAoYmFkLmxlbmd0aCkge1xuICAgIEVsTWVzc2FnZS53YXJuaW5nKGDot7Pov4fkuI3mlK/mjIHnmoTmlofku7bvvJoke2JhZC5tYXAoKGYpID0+IGYubmFtZSkuam9pbign44CBJyl9YClcbiAgfVxuICBjb25zdCBvayA9IGZpbGVzLmZpbHRlcigoZikgPT4gaXNTdXBwb3J0ZWRLYkZpbGUoZi5uYW1lKSlcbiAgaWYgKCFvay5sZW5ndGgpIHJldHVyblxuXG4gIHVwbG9hZGluZy52YWx1ZSA9IHRydWVcbiAgY29uc3Qga2JJZCA9IGFjdGl2ZUtiSWQudmFsdWVcbiAgdHJ5IHtcbiAgICBmb3IgKGNvbnN0IGZpbGUgb2Ygb2spIHtcbiAgICAgIHVwbG9hZFRpcC52YWx1ZSA9IGDmraPlnKjkuIrkvKDlubbop6PmnpDjgIwke2ZpbGUubmFtZX3jgI3igKZgXG4gICAgICB0cnkge1xuICAgICAgICBjb25zdCByZXM6IGFueSA9IGF3YWl0IHVwbG9hZERvY3VtZW50KGtiSWQsIGZpbGUpXG4gICAgICAgIGlmIChyZXM/LmNvZGUgPT09IDIwMCAmJiByZXMuZGF0YT8uZG9jSWQpIHtcbiAgICAgICAgICB1cGxvYWRUaXAudmFsdWUgPSBg44CMJHtmaWxlLm5hbWV944CN5bey5LiK5Lyg77yM5q2j5Zyo5ZCR6YeP5YyW4oCmYFxuICAgICAgICAgIGF3YWl0IGxvYWREb2NzKGtiSWQpXG4gICAgICAgICAgcG9sbERvY3VtZW50KHJlcy5kYXRhLmRvY0lkKVxuICAgICAgICB9IGVsc2Uge1xuICAgICAgICAgIHVwbG9hZFRpcC52YWx1ZSA9ICcnXG4gICAgICAgICAgRWxNZXNzYWdlLmVycm9yKHJlcz8ubXNnIHx8IGDjgIwke2ZpbGUubmFtZX3jgI3kuIrkvKDlpLHotKVgKVxuICAgICAgICB9XG4gICAgICB9IGNhdGNoIChlOiBhbnkpIHtcbiAgICAgICAgdXBsb2FkVGlwLnZhbHVlID0gJydcbiAgICAgICAgRWxNZXNzYWdlLmVycm9yKGU/Lm1lc3NhZ2UgfHwgYOOAjCR7ZmlsZS5uYW1lfeOAjeS4iuS8oOWksei0pWApXG4gICAgICB9XG4gICAgfVxuICB9IGZpbmFsbHkge1xuICAgIHVwbG9hZGluZy52YWx1ZSA9IGZhbHNlXG4gIH1cbn1cblxuLyogPT09PT0g57KY6LS05paH5pys5a+85YWlID09PT09ICovXG5cbmNvbnN0IG9wZW5UZXh0SW1wb3J0ID0gKCkgPT4ge1xuICBpZiAoYnVzeS52YWx1ZSkgcmV0dXJuXG4gIHRleHRJbXBvcnRWaXNpYmxlLnZhbHVlID0gdHJ1ZVxufVxuXG5jb25zdCByZXNldFRleHRJbXBvcnQgPSAoKSA9PiB7XG4gIHRleHRJbXBvcnRDb250ZW50LnZhbHVlID0gJydcbiAgdGV4dEltcG9ydEZpbGVOYW1lLnZhbHVlID0gJydcbn1cblxuLyoqXG4gKiDmj5DkuqTnspjotLTnmoTmraPmlofvvIjlkI7nq68gYC9kb2N1bWVudC91cGxvYWRUZXh0YO+8jCoq5LiN57uP6L+H5paH5Lu26Kej5p6QKirvvIlcbiAqXG4gKiDimqDvuI8g56m65q2j5paHKirkuI3lj5Hor7fmsYIqKu+8muWQjuerr+S8muWbniBgY29kZSA0MDAg5YaF5a655LiN6IO95Li656m6YO+8jOS9humCo+WPquaYr+WFnOW6lSDigJTigJRcbiAqICAgIOi/memHjOaYr+esrOS4gOmBk++8iOaMiemSriBgOmRpc2FibGVkYCDlho3mjKHkuIDpgZPvvInjgILmiorlhZzlupXlvZPllK/kuIDpmLLnur/vvIxcbiAqICAgIOeUqOaIt+eci+WIsOeahOWwseaYr+S4gOWPpeOAjOWvvOWFpeWksei0peOAjeiAjOS4jeaYr+OAjOaMiemSrueCueS4jeWKqOOAjeOAglxuICpcbiAqIOKaoO+4jyDlpLHotKUqKuS4jeWFs+W8ueeql+OAgeS4jea4heato+aWhyoq77ya55So5oi35Y+v6IO95Yia57KY5LqG5Yeg5Y2D5a2X77yM6YeN5p2l5LiA5qyh55qE5Luj5Lu35aSq5aSn44CCXG4gKi9cbmNvbnN0IHN1Ym1pdFRleHRJbXBvcnQgPSBhc3luYyAoKSA9PiB7XG4gIGNvbnN0IGtiSWQgPSBhY3RpdmVLYklkLnZhbHVlXG4gIGNvbnN0IGNvbnRlbnQgPSB0ZXh0SW1wb3J0Q29udGVudC52YWx1ZS50cmltKClcbiAgaWYgKCFrYklkIHx8ICFjb250ZW50IHx8IGJ1c3kudmFsdWUpIHJldHVyblxuXG4gIGltcG9ydGluZy52YWx1ZSA9IHRydWVcbiAgdHJ5IHtcbiAgICAvLyDmlofku7blkI3nlZnnqbrlsLHkuqTnu5kgYXBpIOWxgu+8iGByYWcudHNgIOmHjCBgZmlsZU5hbWUgfHwgJ+acquWRveWQjeaWh+ahoy50eHQnYO+8ieKAlOKAlFxuICAgIC8vIOm7mOiupOWAvOWPqueVmeS4gOS4quWHuuWkhO+8jOWJjeerr+S4jeWGjeaKhOS4gOS7veWtl+mdoumHj1xuICAgIGNvbnN0IG5hbWUgPSB0ZXh0SW1wb3J0RmlsZU5hbWUudmFsdWUudHJpbSgpXG4gICAgY29uc3QgcmVzOiBhbnkgPSBhd2FpdCBpbXBvcnREb2N1bWVudFRleHQoa2JJZCwgY29udGVudCwgbmFtZSB8fCB1bmRlZmluZWQpXG4gICAgaWYgKHJlcz8uY29kZSA9PT0gMjAwICYmIHJlcy5kYXRhPy5kb2NJZCkge1xuICAgICAgdGV4dEltcG9ydFZpc2libGUudmFsdWUgPSBmYWxzZVxuICAgICAgdXBsb2FkVGlwLnZhbHVlID0gYOOAjCR7cmVzLmRhdGEuZmlsZU5hbWUgfHwgbmFtZSB8fCAn5pyq5ZG95ZCN5paH5qGjLnR4dCd944CN5bey5a+85YWl77yM5q2j5Zyo5ZCR6YeP5YyW4oCmYFxuICAgICAgYXdhaXQgbG9hZERvY3Moa2JJZClcbiAgICAgIHBvbGxEb2N1bWVudChyZXMuZGF0YS5kb2NJZClcbiAgICB9IGVsc2Uge1xuICAgICAgRWxNZXNzYWdlLmVycm9yKHJlcz8ubXNnIHx8ICflr7zlhaXlpLHotKUnKVxuICAgIH1cbiAgfSBjYXRjaCAoZTogYW55KSB7XG4gICAgRWxNZXNzYWdlLmVycm9yKGU/Lm1lc3NhZ2UgfHwgJ+WvvOWFpeWksei0pScpXG4gIH0gZmluYWxseSB7XG4gICAgaW1wb3J0aW5nLnZhbHVlID0gZmFsc2VcbiAgfVxufVxuXG5jb25zdCByZW1vdmVEb2MgPSBhc3luYyAoZG9jOiBSYWdEb2N1bWVudCkgPT4ge1xuICB0cnkge1xuICAgIGF3YWl0IEVsTWVzc2FnZUJveC5jb25maXJtKGDliKDpmaTmlofmoaPjgIwke2RvYy5maWxlTmFtZX3jgI3vvJ9gLCAn5Yig6Zmk56Gu6K6kJywge1xuICAgICAgY29uZmlybUJ1dHRvblRleHQ6ICfliKDpmaQnLFxuICAgICAgY2FuY2VsQnV0dG9uVGV4dDogJ+WPlua2iCcsXG4gICAgICB0eXBlOiAnd2FybmluZydcbiAgICB9KVxuICB9IGNhdGNoIHtcbiAgICByZXR1cm5cbiAgfVxuICB0cnkge1xuICAgIGNvbnN0IHJlczogYW55ID0gYXdhaXQgZGVsZXRlRG9jdW1lbnQoZG9jLmRvY0lkKVxuICAgIGlmIChyZXM/LmNvZGUgPT09IDIwMCkge1xuICAgICAgRWxNZXNzYWdlLnN1Y2Nlc3MoJ+aWh+aho+W3suWIoOmZpCcpXG4gICAgICBpZiAoYWN0aXZlS2JJZC52YWx1ZSkgYXdhaXQgbG9hZERvY3MoYWN0aXZlS2JJZC52YWx1ZSlcbiAgICAgIGF3YWl0IGxvYWRLYnMoKVxuICAgIH0gZWxzZSB7XG4gICAgICBFbE1lc3NhZ2UuZXJyb3IocmVzPy5tc2cgfHwgJ+WIoOmZpOWksei0pScpXG4gICAgfVxuICB9IGNhdGNoIChlOiBhbnkpIHtcbiAgICBFbE1lc3NhZ2UuZXJyb3IoZT8ubWVzc2FnZSB8fCAn5Yig6Zmk5aSx6LSlJylcbiAgfVxufVxuXG5jb25zdCByZXByb2Nlc3MgPSBhc3luYyAoZG9jOiBSYWdEb2N1bWVudCkgPT4ge1xuICB0cnkge1xuICAgIGNvbnN0IHJlczogYW55ID0gYXdhaXQgcmVwcm9jZXNzRG9jdW1lbnQoZG9jLmRvY0lkKVxuICAgIGlmIChyZXM/LmNvZGUgPT09IDIwMCkge1xuICAgICAgRWxNZXNzYWdlLnN1Y2Nlc3MoJ+W3sumHjeaWsOW8gOWni+WkhOeQhicpXG4gICAgICBpZiAoYWN0aXZlS2JJZC52YWx1ZSkgYXdhaXQgbG9hZERvY3MoYWN0aXZlS2JJZC52YWx1ZSlcbiAgICAgIHBvbGxEb2N1bWVudChkb2MuZG9jSWQpXG4gICAgfSBlbHNlIHtcbiAgICAgIEVsTWVzc2FnZS5lcnJvcihyZXM/Lm1zZyB8fCAn6YeN6K+V5aSx6LSlJylcbiAgICB9XG4gIH0gY2F0Y2ggKGU6IGFueSkge1xuICAgIEVsTWVzc2FnZS5lcnJvcihlPy5tZXNzYWdlIHx8ICfph43or5XlpLHotKUnKVxuICB9XG59XG5cbmNvbnN0IHNob3dDaHVua3MgPSBhc3luYyAoZG9jOiBSYWdEb2N1bWVudCkgPT4ge1xuICBjaHVua0RvY05hbWUudmFsdWUgPSBkb2MuZmlsZU5hbWVcbiAgY2h1bmtzVmlzaWJsZS52YWx1ZSA9IHRydWVcbiAgY2h1bmtzTG9hZGluZy52YWx1ZSA9IHRydWVcbiAgY2h1bmtzLnZhbHVlID0gW11cbiAgdHJ5IHtcbiAgICBjb25zdCByZXM6IGFueSA9IGF3YWl0IGdldERvY3VtZW50Q2h1bmtzKGRvYy5kb2NJZClcbiAgICBpZiAocmVzPy5jb2RlID09PSAyMDAgJiYgQXJyYXkuaXNBcnJheShyZXMuZGF0YSkpIGNodW5rcy52YWx1ZSA9IHJlcy5kYXRhXG4gIH0gY2F0Y2ggKGUpIHtcbiAgICBjb25zb2xlLndhcm4oJ1trYl0g5Yqg6L295YiG5Z2X5aSx6LSlJywgZSlcbiAgfSBmaW5hbGx5IHtcbiAgICBjaHVua3NMb2FkaW5nLnZhbHVlID0gZmFsc2VcbiAgfVxufVxuXG5vbkJlZm9yZVVubW91bnQoY2xlYXJQb2xsVGltZXJzKVxuXG4vKipcbiAqIOi/m+mhtemdouWwseaKiuWFpeWPo+W+veagh+eahOaVsOWtl+S6ruWHuuadpVxuICpcbiAqIOWOn+adpeWPquWcqOOAjOaJk+W8gOaKveWxieOAjeaXtuaJjeWPluWIl+ihqO+8jOaJgOS7peeUqOaIt+S4jeeCueaKveWxieWwseawuOi/nOeci+S4jeWIsOiHquW3seacieWHoOS4quW6k1xuICog77yI55yL6LW35p2l5YOP5rKh5pyJ55+l6K+G5bqT77yJ44CC6L+Z6YeM5oyC6L295pyf6KGl5LiA5qyhKirlj6rlj5bliJfooagqKueahOivt+axguOAglxuICpcbiAqIOS4juOAjOaJk+W8gOaKveWxieOAjemCo+adoei3r+W+hOWPr+iDveaSnuS4iu+8iOaMgui9veivt+axgui/mOayoeWbnuadpeWwseeCueW8gOaKveWxiSDihpIg5aSa5LiA5qyhIEdFVO+8ie+8mlxuICog6L+Z6YeMKirmlYXmhI/kuI3lhbHnlKggaW4tZmxpZ2h0IHByb21pc2UqKiDigJTigJQg5YWx55So55qE6K+d5YWI5Yiw55qE5oyC6L296K+35rGC77yIYXV0b1NlbGVjdD1mYWxzZe+8iVxuICog5Lya5oqK5oq95bGJ6YKj5qyh6LCD55So5LiA6LW35ZCD5o6J77yM5oq95bGJ5omT5byA5ZCO5bCx5rKh5pyJ6YCJ5Lit55qE5bqT44CB5Lmf5rKh5pyJ5paH5qGj5YiX6KGo77yM6YKj5piv55yfIGJ1Z++8m1xuICog5aSa5LiA5qyhIEdFVCDkuI3mmK/jgILkuKTmnaHot6/lvoTkuZ/kuI3kvJrkupLnm7jmiZPohLjvvJrmjILovb3ov5nmnaEqKuWPquWGmSBga2JzYCoq77yMXG4gKiDku47kuI3norAgYWN0aXZlS2JJZCAvIGRvY3VtZW50cyAvIOi9ruivouOAglxuICovXG5vbk1vdW50ZWQoKCkgPT4ge1xuICBsb2FkS2JzKGZhbHNlKVxufSlcblxuZGVmaW5lRXhwb3NlKHsgb3BlbiB9KVxuPC9zY3JpcHQ+XG5cbjxzdHlsZSBzY29wZWQ+XG4vKiA9PT09PT09PT09IOWFpeWPo+aMiemSru+8iOWvuem9kCBDaGF0SW5wdXRBcmVhIOeahCAudG9vbGJhci1idG7vvIkgPT09PT09PT09PSAqL1xuLmtiLWVudHJ5IHtcbiAgcG9zaXRpb246IHJlbGF0aXZlO1xuICBkaXNwbGF5OiBpbmxpbmUtZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAganVzdGlmeS1jb250ZW50OiBjZW50ZXI7XG4gIHdpZHRoOiAyOHB4O1xuICBoZWlnaHQ6IDI4cHg7XG4gIGJvcmRlcjogMXB4IHNvbGlkIHRyYW5zcGFyZW50O1xuICBib3JkZXItcmFkaXVzOiA4cHg7XG4gIGJhY2tncm91bmQ6IHRyYW5zcGFyZW50O1xuICBjb2xvcjogIzZiNzI4MDtcbiAgY3Vyc29yOiBwb2ludGVyO1xuICB0cmFuc2l0aW9uOiBhbGwgMC4xNXMgZWFzZTtcbiAgZmxleC1zaHJpbms6IDA7XG4gIHBhZGRpbmc6IDA7XG59XG5cbi5rYi1lbnRyeTpob3ZlciB7XG4gIGJhY2tncm91bmQ6ICNmZmY7XG4gIGJvcmRlci1jb2xvcjogI2U1ZTdlYjtcbiAgY29sb3I6ICMxZjI5Mzc7XG59XG5cbi5rYi1lbnRyeS1iYWRnZSB7XG4gIHBvc2l0aW9uOiBhYnNvbHV0ZTtcbiAgdG9wOiAtM3B4O1xuICByaWdodDogLTNweDtcbiAgbWluLXdpZHRoOiAxNHB4O1xuICBoZWlnaHQ6IDE0cHg7XG4gIHBhZGRpbmc6IDAgM3B4O1xuICBib3JkZXItcmFkaXVzOiA3cHg7XG4gIGJhY2tncm91bmQ6ICM0ZjZlZjc7XG4gIGNvbG9yOiAjZmZmO1xuICBmb250LXNpemU6IDlweDtcbiAgbGluZS1oZWlnaHQ6IDE0cHg7XG4gIHRleHQtYWxpZ246IGNlbnRlcjtcbiAgZm9udC13ZWlnaHQ6IDYwMDtcbn1cblxuLyogPT09PT09PT09PSDmir3lsYkgPT09PT09PT09PSAqL1xuLmtiLWJvZHkge1xuICBkaXNwbGF5OiBmbGV4O1xuICBmbGV4LWRpcmVjdGlvbjogY29sdW1uO1xuICBoZWlnaHQ6IDEwMCU7XG59XG5cbi5rYi1oZWFkIHtcbiAgZGlzcGxheTogZmxleDtcbiAgYWxpZ24taXRlbXM6IGZsZXgtc3RhcnQ7XG4gIGp1c3RpZnktY29udGVudDogc3BhY2UtYmV0d2VlbjtcbiAgZ2FwOiAxMnB4O1xuICBwYWRkaW5nOiAxNnB4IDE4cHggMTJweDtcbiAgYm9yZGVyLWJvdHRvbTogMXB4IHNvbGlkICNlZWYyZjc7XG59XG5cbi5rYi1oZWFkLWxlZnQge1xuICBkaXNwbGF5OiBmbGV4O1xuICBmbGV4LWRpcmVjdGlvbjogY29sdW1uO1xuICBtaW4td2lkdGg6IDA7XG59XG5cbi5rYi10aXRsZSB7XG4gIGZvbnQtc2l6ZTogMTVweDtcbiAgZm9udC13ZWlnaHQ6IDY1MDtcbiAgY29sb3I6ICMxZjJkM2Q7XG59XG5cbi5rYi1zdWIge1xuICBtYXJnaW4tdG9wOiAycHg7XG4gIGZvbnQtc2l6ZTogMTJweDtcbiAgY29sb3I6ICM5YWE1YjU7XG59XG5cbi5rYi1oZWFkLXJpZ2h0IHtcbiAgZGlzcGxheTogZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAgZ2FwOiA4cHg7XG4gIGZsZXgtc2hyaW5rOiAwO1xufVxuXG4ua2ItY2xvc2Uge1xuICBjdXJzb3I6IHBvaW50ZXI7XG4gIGNvbG9yOiAjOWFhNWI1O1xuICBkaXNwbGF5OiBpbmxpbmUtZmxleDtcbiAgcGFkZGluZzogNHB4O1xuICBib3JkZXItcmFkaXVzOiA2cHg7XG59XG5cbi5rYi1jbG9zZTpob3ZlciB7XG4gIGJhY2tncm91bmQ6ICNmMWY1Zjk7XG4gIGNvbG9yOiAjNGE1YTcyO1xufVxuXG4ua2ItbWFpbiB7XG4gIGZsZXg6IDE7XG4gIG1pbi1oZWlnaHQ6IDA7XG4gIG92ZXJmbG93LXk6IGF1dG87XG4gIHBhZGRpbmc6IDEycHggMThweCAxOHB4O1xufVxuXG4vKiA9PT09PT09PT09IOWIl+ihqOayoeWPluWIsCA9PT09PT09PT09ICovXG4vKiDjgIzliJfooajmsqHlj5bliLDjgI3nmoTmqKrluYXvvJrkuI7jgIzkuIDkuKrlupPpg73msqHmnInjgI3nmoTnqbrmgIHmlofmoYjmmK/kuKTku7bkuovvvIzkuI3og73lhbHnlKggKi9cbi5rYi1sb2FkLWZhaWxlZCB7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIGdhcDogOHB4O1xuICBtYXJnaW4tYm90dG9tOiA4cHg7XG4gIHBhZGRpbmc6IDZweCAxMHB4O1xuICBib3JkZXI6IDFweCBzb2xpZCAjZjBkOWE4O1xuICBib3JkZXItcmFkaXVzOiA3cHg7XG4gIGJhY2tncm91bmQ6ICNmZmZhZjA7XG4gIGZvbnQtc2l6ZTogMTJweDtcbiAgY29sb3I6ICM4YTZkM2I7XG59XG5cbi5rYi1sb2FkLWZhaWxlZCBzcGFuIHtcbiAgZmxleDogMTtcbiAgbWluLXdpZHRoOiAwO1xufVxuXG4vKiA9PT09PT09PT09IOefpeivhuW6k+aQnOe0oiA9PT09PT09PT09ICovXG4vKiDmkJzntKLmoYblnKjliJfooagqKuWklumdoioq77yI6KeB5qih5p2/5rOo6YeK77yJ77yM5omA5Lul5a6D6Ieq5bex6YKj6KGM55SoIGZsZXgg5o6S77yMXG4gICDkuI3nlKjnu53lr7nlrprkvY0g4oCU4oCUIOe7neWvueWumuS9jeeahOa4hemZpOaMiemSruWcqOeqhOWxjy/lpJrooYzml7bkvJrot5HkvY0gKi9cbi5rYi1maWx0ZXIge1xuICBkaXNwbGF5OiBmbGV4O1xuICBhbGlnbi1pdGVtczogY2VudGVyO1xuICBnYXA6IDZweDtcbiAgbWFyZ2luLWJvdHRvbTogOHB4O1xufVxuXG4ua2ItZmlsdGVyLWlucHV0IHtcbiAgZmxleDogMTtcbiAgbWluLXdpZHRoOiAwO1xuICBoZWlnaHQ6IDMwcHg7XG4gIHBhZGRpbmc6IDAgMTBweDtcbiAgYm9yZGVyOiAxcHggc29saWQgI2U1ZTdlYjtcbiAgYm9yZGVyLXJhZGl1czogOHB4O1xuICBmb250LXNpemU6IDEyLjVweDtcbiAgY29sb3I6ICMxZjJkM2Q7XG4gIG91dGxpbmU6IG5vbmU7XG4gIGJhY2tncm91bmQ6ICNmZmY7XG59XG5cbi5rYi1maWx0ZXItaW5wdXQ6Zm9jdXMge1xuICBib3JkZXItY29sb3I6ICNiM2IzYjM7XG59XG5cbi5rYi1maWx0ZXItY2xlYXIge1xuICBkaXNwbGF5OiBpbmxpbmUtZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAganVzdGlmeS1jb250ZW50OiBjZW50ZXI7XG4gIHdpZHRoOiAyMnB4O1xuICBoZWlnaHQ6IDIycHg7XG4gIGZsZXgtc2hyaW5rOiAwO1xuICBib3JkZXItcmFkaXVzOiA1MCU7XG4gIGNvbG9yOiAjOWFhNWI1O1xuICBjdXJzb3I6IHBvaW50ZXI7XG4gIGZvbnQtc2l6ZTogMTJweDtcbn1cblxuLmtiLWZpbHRlci1jbGVhcjpob3ZlciB7XG4gIGJhY2tncm91bmQ6ICNlZWYyZjg7XG4gIGNvbG9yOiAjNGE1YTcyO1xufVxuXG4vKiA9PT09PT09PT09IOefpeivhuW6k+WIl+ihqCA9PT09PT09PT09ICovXG4ua2ItbGlzdC13cmFwIHtcbiAgZGlzcGxheTogZmxleDtcbiAgZmxleC1kaXJlY3Rpb246IGNvbHVtbjtcbiAgZ2FwOiA2cHg7XG4gIC8qIOW6k+WkmuS6hu+8iOWNgeWHoOS4qu+8ieaXtuWIl+ihqCoq6Ieq5bex5ruaKirvvJrkuI3orqnlroPmiormlofmoaPljLrkuI7jgIzor5Xmo4DntKLjgI3ovpPlhaXmoYbmlbTkuKrmjqjlh7rop4blj6Mg4oCU4oCUXG4gICAgIOWQpuWImeeUqOaIt+imgeaKiuaJgOacieefpeivhuW6k+a7muWujOaJjeaRuOW+l+WIsOajgOe0ouaMiemSruOAglxuICAgICDimqDvuI8g55SoIGBtYXgtaGVpZ2h0YCDoh6rlt7Hnu5nlh7rnoa7lrprkuIrnlYzvvIwqKuS4jeS+nei1lioq5oq95bGJ6auY5bqm77yIYC5lbC1kcmF3ZXJfX2JvZHlgIOWcqOacrCBTRkMg5LmL5aSW77yMXG4gICAgICAgIOWug+aAjuS5iOino+aekOWcqOemu+e6v+S4i+ayoeazlemqjOivge+8ie+8jOaJgOS7pei/memHjOS5n+S4jemcgOimgSBgOmRlZXAoKWDjgIIgKi9cbiAgbWF4LWhlaWdodDogNDB2aDtcbiAgb3ZlcmZsb3cteTogYXV0bztcbiAgcGFkZGluZy1yaWdodDogMnB4O1xufVxuXG4ua2ItaXRlbSB7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIGdhcDogOHB4O1xuICBwYWRkaW5nOiA5cHggMTBweDtcbiAgYm9yZGVyOiAxcHggc29saWQgI2VlZjJmNztcbiAgYm9yZGVyLXJhZGl1czogOXB4O1xuICBjdXJzb3I6IHBvaW50ZXI7XG4gIHRyYW5zaXRpb246IGFsbCAwLjE1cztcbn1cblxuLmtiLWl0ZW06aG92ZXIge1xuICBiYWNrZ3JvdW5kOiAjZjhmYWZjO1xuICBib3JkZXItY29sb3I6ICNkZmU2ZjA7XG59XG5cbi5rYi1pdGVtLmFjdGl2ZSB7XG4gIGJhY2tncm91bmQ6ICNlZWY0ZmY7XG4gIGJvcmRlci1jb2xvcjogI2JjZDBmNztcbn1cblxuLmtiLWl0ZW0tbWFpbiB7XG4gIGZsZXg6IDE7XG4gIG1pbi13aWR0aDogMDtcbn1cblxuLmtiLWl0ZW0tbmFtZSB7XG4gIGZvbnQtc2l6ZTogMTMuNXB4O1xuICBjb2xvcjogIzFmMmQzZDtcbiAgZm9udC13ZWlnaHQ6IDU1MDtcbiAgb3ZlcmZsb3c6IGhpZGRlbjtcbiAgdGV4dC1vdmVyZmxvdzogZWxsaXBzaXM7XG4gIHdoaXRlLXNwYWNlOiBub3dyYXA7XG59XG5cbi5rYi1pdGVtLW1ldGEge1xuICBkaXNwbGF5OiBmbGV4O1xuICBnYXA6IDEwcHg7XG4gIG1hcmdpbi10b3A6IDJweDtcbiAgZm9udC1zaXplOiAxMS41cHg7XG4gIGNvbG9yOiAjOWFhNWI1O1xufVxuXG4vKiDjgIzlt7LlsY/olL3jgI3nirbmgIHvvJoqKuW4uOmpuyoq5Y+v6KeB77yM5LiN5Y+C5LiO5LiK6Z2i55qEIC5rYi1pdGVtLW9wcyDmgqzlgZzmnLrliLYg4oCU4oCUXG4gICDnlKjmiLfopoHog73kuIDnnLznnIvlh7rjgIzlk6rkupvlupPmmbrog73kvZPnjrDlnKjnnIvkuI3liLDjgI3vvIzpgqPmmK/ku5blvIDov5nkuKrlvIDlhbPnmoTnm67nmoQgKi9cbi5rYi1pdGVtLWJsb2NrZWQge1xuICBwYWRkaW5nOiAwIDVweDtcbiAgYm9yZGVyLXJhZGl1czogNHB4O1xuICBiYWNrZ3JvdW5kOiAjZjFmM2Y1O1xuICBjb2xvcjogIzhhOTRhNjtcbiAgZm9udC1zaXplOiAxMXB4O1xuICBsaW5lLWhlaWdodDogMTZweDtcbn1cblxuLyog6KKr5bGP6JS955qE5bqT77ya5ZCN5a2X5Y6L5pqX77yM5L2GKirkuI3pmpDol4/jgIHkuI3nva7ngbDliLDngrnkuI3liqgqKiDigJTigJQg5a6D6L+Y6KaB6IO96KKr6YCJ5Lit44CB6IO95Y+W5raI5bGP6JS944CCXG4gICDimqDvuI8g6L+Z6YeM5pWF5oSP5LiN6KaG55uWIGJhY2tncm91bmTvvJpgLmtiLWl0ZW0uYWN0aXZlYO+8iOmAieS4reaAge+8ieWcqOWQjumdou+8jOS4pOi+ueeJueW8guaAp+ebuOWQjOOAgVxuICAg6Z2g5rqQ56CB6aG65bqP5Yaz6IOc77yM5Yqg5LiA5p2hIGJhY2tncm91bmQg5Lya5oqK6YCJ5Lit6auY5Lqu5ZCD5o6J44CC5omA5Lul54q25oCB5Y+q55Sx5ZCN5a2X6aKc6ImyICsg5LiK6Z2i6YKj5p6a5qCH562+6KGo6L6+44CCICovXG4ua2ItaXRlbS5ibG9ja2VkIC5rYi1pdGVtLW5hbWUge1xuICBjb2xvcjogIzlhYTViNTtcbn1cblxuLyog5bGP6JS95byA5YWz77ya5b+F6aG75bi46am75Y+v6KeBIOKGkiDmlL7lnKggLmtiLWl0ZW0tb3BzICoq5aSW6Z2iKirvvIjpgqPph4wgYG9wYWNpdHk6IDBg77yM5oKs5YGc5omN5pi+5b2i77yJICovXG4ua2ItYmxvY2sge1xuICBkaXNwbGF5OiBpbmxpbmUtZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAgZmxleC1zaHJpbms6IDA7XG59XG5cbi5rYi1pdGVtLW9wcyB7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIGdhcDogMnB4O1xuICBvcGFjaXR5OiAwO1xuICB0cmFuc2l0aW9uOiBvcGFjaXR5IDAuMTVzO1xufVxuXG4ua2ItaXRlbTpob3ZlciAua2ItaXRlbS1vcHMge1xuICBvcGFjaXR5OiAxO1xufVxuXG4ua2Itb3Age1xuICBkaXNwbGF5OiBpbmxpbmUtZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAganVzdGlmeS1jb250ZW50OiBjZW50ZXI7XG4gIHdpZHRoOiAyNHB4O1xuICBoZWlnaHQ6IDI0cHg7XG4gIGJvcmRlci1yYWRpdXM6IDZweDtcbiAgY29sb3I6ICM5YWE1YjU7XG4gIGN1cnNvcjogcG9pbnRlcjtcbiAgZm9udC1zaXplOiAxM3B4O1xufVxuXG4ua2Itb3A6aG92ZXIge1xuICBiYWNrZ3JvdW5kOiAjZWVmMmY4O1xuICBjb2xvcjogIzRhNWE3Mjtcbn1cblxuLmtiLW9wLmRhbmdlcjpob3ZlciB7XG4gIGJhY2tncm91bmQ6ICNmZWUyZTI7XG4gIGNvbG9yOiAjZWY0NDQ0O1xufVxuXG4ua2ItZW1wdHkge1xuICBwYWRkaW5nOiAyOHB4IDE2cHg7XG4gIHRleHQtYWxpZ246IGNlbnRlcjtcbn1cblxuLmtiLWVtcHR5LXRpdGxlIHtcbiAgZm9udC1zaXplOiAxNHB4O1xuICBmb250LXdlaWdodDogNjAwO1xuICBjb2xvcjogIzMzNDE1Yztcbn1cblxuLmtiLWVtcHR5LWRlc2Mge1xuICBtYXJnaW46IDhweCBhdXRvIDE0cHg7XG4gIG1heC13aWR0aDogMzQwcHg7XG4gIGZvbnQtc2l6ZTogMTIuNXB4O1xuICBsaW5lLWhlaWdodDogMS43NTtcbiAgY29sb3I6ICM5YWE1YjU7XG59XG5cbi8qID09PT09PT09PT0g5paH5qGj5Yy6ID09PT09PT09PT0gKi9cbi5rYi1kb2NzIHtcbiAgbWFyZ2luLXRvcDogMTZweDtcbiAgYm9yZGVyLXRvcDogMXB4IHNvbGlkICNlZWYyZjc7XG4gIHBhZGRpbmctdG9wOiAxNHB4O1xufVxuXG4ua2ItZG9jcy1oZWFkIHtcbiAgZGlzcGxheTogZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAgZ2FwOiA4cHg7XG59XG5cbi5rYi1kb2NzLXRpdGxlIHtcbiAgZm9udC1zaXplOiAxMy41cHg7XG4gIGZvbnQtd2VpZ2h0OiA2MDA7XG4gIGNvbG9yOiAjMWYyZDNkO1xuICBvdmVyZmxvdzogaGlkZGVuO1xuICB0ZXh0LW92ZXJmbG93OiBlbGxpcHNpcztcbiAgd2hpdGUtc3BhY2U6IG5vd3JhcDtcbn1cblxuLmtiLWRvY3MtaGludCB7XG4gIGZvbnQtc2l6ZTogMTEuNXB4O1xuICBjb2xvcjogI2I2YmRjOTtcbn1cblxuLmtiLXVwbG9hZC1idG4ge1xuICBtYXJnaW4tbGVmdDogYXV0bztcbiAgZGlzcGxheTogaW5saW5lLWZsZXg7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIGdhcDogNHB4O1xuICBwYWRkaW5nOiA0cHggMTJweDtcbiAgYm9yZGVyLXJhZGl1czogOHB4O1xuICBiYWNrZ3JvdW5kOiAjNGY2ZWY3O1xuICBjb2xvcjogI2ZmZjtcbiAgZm9udC1zaXplOiAxMi41cHg7XG4gIGN1cnNvcjogcG9pbnRlcjtcbiAgZmxleC1zaHJpbms6IDA7XG4gIHRyYW5zaXRpb246IGJhY2tncm91bmQgMC4xNXM7XG59XG5cbi5rYi11cGxvYWQtYnRuOmhvdmVyIHtcbiAgYmFja2dyb3VuZDogIzNmNWNlMDtcbn1cblxuLmtiLXVwbG9hZC1idG4uZGlzYWJsZWQge1xuICBiYWNrZ3JvdW5kOiAjYjZiZGM5O1xuICBjdXJzb3I6IG5vdC1hbGxvd2VkO1xufVxuXG4ua2ItdXBsb2FkLWJ0biBpbnB1dCB7XG4gIGRpc3BsYXk6IG5vbmU7XG59XG5cbi8qIOOAjOeymOi0tOaWh+acrOOAjeWFpeWPo++8mi5rYi11cGxvYWQtYnRuIOeahOW5s+e6p+WniuWmueaMiemSru+8iOasoee6p+inguaEn++8ieOAglxuICAg6L+Z6YeMKirlj6rliqDoh6rlt7HnmoTop4TliJkqKu+8jOS4jeWKqOS4iuS8oOaMiemSrueahOS7u+S9leWjsOaYjiDigJTigJQg5LiK5Lyg6YKj5p2h5qC35byP5piv5pei5pyJ55qE44CBXG4gICDnlKjmiLflt7Lnu4/nnIvmg6/nmoTvvJvkuKTkuKrmjInpkq7pnaAgLmtiLWRvY3MtaGVhZCDnmoQgZ2FwIOaOkuWcqOS4gOi1t+OAgiAqL1xuLmtiLWltcG9ydC1idG4ge1xuICBkaXNwbGF5OiBpbmxpbmUtZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAgZ2FwOiA0cHg7XG4gIHBhZGRpbmc6IDRweCAxMnB4O1xuICBib3JkZXI6IDFweCBzb2xpZCAjYmNkMGY3O1xuICBib3JkZXItcmFkaXVzOiA4cHg7XG4gIGJhY2tncm91bmQ6ICNmZmY7XG4gIGNvbG9yOiAjNGY2ZWY3O1xuICBmb250LXNpemU6IDEyLjVweDtcbiAgZm9udC1mYW1pbHk6IGluaGVyaXQ7XG4gIGN1cnNvcjogcG9pbnRlcjtcbiAgZmxleC1zaHJpbms6IDA7XG4gIHRyYW5zaXRpb246IGFsbCAwLjE1cztcbn1cblxuLmtiLWltcG9ydC1idG46aG92ZXIge1xuICBiYWNrZ3JvdW5kOiAjZWVmNGZmO1xufVxuXG4vKiDlv5nvvIjkuIrkvKDkuK0gLyDlr7zlhaXkuK3vvInml7bkuKTkuKrlhaXlj6PkuIDotbflj5jngbDvvIzop4LmhJ/kuI4gLmtiLXVwbG9hZC1idG4uZGlzYWJsZWQg5a+56b2QICovXG4ua2ItaW1wb3J0LWJ0bi5kaXNhYmxlZCxcbi5rYi1pbXBvcnQtYnRuOmRpc2FibGVkIHtcbiAgYm9yZGVyLWNvbG9yOiAjZGZlNmYwO1xuICBiYWNrZ3JvdW5kOiAjZjVmN2ZhO1xuICBjb2xvcjogI2I2YmRjOTtcbiAgY3Vyc29yOiBub3QtYWxsb3dlZDtcbn1cblxuLmtiLXRpcCB7XG4gIG1hcmdpbi10b3A6IDEwcHg7XG4gIHBhZGRpbmc6IDZweCAxMHB4O1xuICBmb250LXNpemU6IDEycHg7XG4gIGNvbG9yOiAjMjU2M2ViO1xuICBiYWNrZ3JvdW5kOiAjZjJmN2ZmO1xuICBib3JkZXI6IDFweCBzb2xpZCAjZDhlNWZmO1xuICBib3JkZXItcmFkaXVzOiA3cHg7XG59XG5cbi5rYi1kb2MtbGlzdCB7XG4gIG1hcmdpbi10b3A6IDEwcHg7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGZsZXgtZGlyZWN0aW9uOiBjb2x1bW47XG4gIGdhcDogNnB4O1xuICBtaW4taGVpZ2h0OiA2MHB4O1xufVxuXG4ua2ItZG9jIHtcbiAgZGlzcGxheTogZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAgZ2FwOiA4cHg7XG4gIHBhZGRpbmc6IDhweCAxMHB4O1xuICBib3JkZXI6IDFweCBzb2xpZCAjZWVmMmY3O1xuICBib3JkZXItcmFkaXVzOiA5cHg7XG59XG5cbi5rYi1kb2MtbWFpbiB7XG4gIGZsZXg6IDE7XG4gIG1pbi13aWR0aDogMDtcbn1cblxuLmtiLWRvYy1uYW1lIHtcbiAgZm9udC1zaXplOiAxM3B4O1xuICBjb2xvcjogIzMzNDE1YztcbiAgb3ZlcmZsb3c6IGhpZGRlbjtcbiAgdGV4dC1vdmVyZmxvdzogZWxsaXBzaXM7XG4gIHdoaXRlLXNwYWNlOiBub3dyYXA7XG59XG5cbi5rYi1kb2MtbWV0YSB7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIGdhcDogOHB4O1xuICBtYXJnaW4tdG9wOiA0cHg7XG4gIGZvbnQtc2l6ZTogMTEuNXB4O1xuICBjb2xvcjogIzlhYTViNTtcbn1cblxuLmtiLWRvYy1jaHVua3MuaXMtd2FybiB7XG4gIGNvbG9yOiAjYjQ1MzA5O1xufVxuXG4ua2ItZG9jLWNodW5rcy5pcy1lcnJvciB7XG4gIGNvbG9yOiAjYjkxYzFjO1xufVxuXG4ua2ItZG9jLW9wcyB7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIGdhcDogMnB4O1xuICBmbGV4LXNocmluazogMDtcbn1cblxuLmtiLWRvYy1lbXB0eSB7XG4gIHBhZGRpbmc6IDE4cHggMDtcbiAgdGV4dC1hbGlnbjogY2VudGVyO1xuICBmb250LXNpemU6IDEyLjVweDtcbiAgY29sb3I6ICNiNmJkYzk7XG59XG5cbi8qID09PT09PT09PT0g6K+V5qOA57SiID09PT09PT09PT0gKi9cbi5rYi1wcm9iZSB7XG4gIG1hcmdpbi10b3A6IDE0cHg7XG4gIHBhZGRpbmctdG9wOiAxMnB4O1xuICBib3JkZXItdG9wOiAxcHggZGFzaGVkICNlOGVkZjU7XG59XG5cbi5rYi1wcm9iZS1yb3cge1xuICBkaXNwbGF5OiBmbGV4O1xuICBhbGlnbi1pdGVtczogY2VudGVyO1xuICBnYXA6IDhweDtcbn1cblxuLmtiLXByb2JlLWlucHV0IHtcbiAgZmxleDogMTtcbiAgbWluLXdpZHRoOiAwO1xuICBoZWlnaHQ6IDMwcHg7XG4gIHBhZGRpbmc6IDAgMTBweDtcbiAgYm9yZGVyOiAxcHggc29saWQgI2U1ZTdlYjtcbiAgYm9yZGVyLXJhZGl1czogOHB4O1xuICBmb250LXNpemU6IDEyLjVweDtcbiAgY29sb3I6ICMxZjJkM2Q7XG4gIG91dGxpbmU6IG5vbmU7XG4gIGJhY2tncm91bmQ6ICNmZmY7XG59XG5cbi5rYi1wcm9iZS1pbnB1dDpmb2N1cyB7XG4gIGJvcmRlci1jb2xvcjogI2IzYjNiMztcbn1cblxuLmtiLXByb2JlLXJlc3VsdCB7XG4gIG1hcmdpbi10b3A6IDlweDtcbn1cblxuLmtiLXByb2JlLWVtcHR5IHtcbiAgZm9udC1zaXplOiAxMnB4O1xuICBjb2xvcjogIzlhYTViNTtcbiAgbGluZS1oZWlnaHQ6IDEuNztcbn1cblxuLmtiLXByb2JlLWNvdW50IHtcbiAgZm9udC1zaXplOiAxMS41cHg7XG4gIGNvbG9yOiAjOWFhNWI1O1xuICBtYXJnaW4tYm90dG9tOiA2cHg7XG59XG5cbi5rYi1wcm9iZS1oaXRzIHtcbiAgZGlzcGxheTogZmxleDtcbiAgZmxleC1kaXJlY3Rpb246IGNvbHVtbjtcbiAgZ2FwOiA3cHg7XG59XG5cbi5rYi1wcm9iZS1oaXQge1xuICBwYWRkaW5nOiA3cHggMTBweDtcbiAgYm9yZGVyOiAxcHggc29saWQgI2VlZjJmNztcbiAgYm9yZGVyLXJhZGl1czogOHB4O1xuICBiYWNrZ3JvdW5kOiAjZmJmY2ZlO1xufVxuXG4ua2ItcHJvYmUtc291cmNlIHtcbiAgZm9udC1zaXplOiAxMS41cHg7XG4gIGNvbG9yOiAjNGY2ZWY3O1xuICBtYXJnaW4tYm90dG9tOiAzcHg7XG59XG5cbi5rYi1wcm9iZS10ZXh0IHtcbiAgZm9udC1zaXplOiAxMnB4O1xuICBsaW5lLWhlaWdodDogMS43O1xuICBjb2xvcjogIzRhNWE3MjtcbiAgZGlzcGxheTogLXdlYmtpdC1ib3g7XG4gIC13ZWJraXQtbGluZS1jbGFtcDogMztcbiAgLXdlYmtpdC1ib3gtb3JpZW50OiB2ZXJ0aWNhbDtcbiAgb3ZlcmZsb3c6IGhpZGRlbjtcbn1cblxuLyogPT09PT09PT09PSDliIblnZfpooTop4ggPT09PT09PT09PSAqL1xuLmtiLWNodW5rcyB7XG4gIG1heC1oZWlnaHQ6IDU2dmg7XG4gIG92ZXJmbG93LXk6IGF1dG87XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGZsZXgtZGlyZWN0aW9uOiBjb2x1bW47XG4gIGdhcDogMTBweDtcbn1cblxuLmtiLWNodW5rIHtcbiAgYm9yZGVyOiAxcHggc29saWQgI2VlZjJmNztcbiAgYm9yZGVyLXJhZGl1czogOXB4O1xuICBwYWRkaW5nOiA5cHggMTFweDtcbiAgYmFja2dyb3VuZDogI2ZiZmNmZTtcbn1cblxuLmtiLWNodW5rLWhlYWQge1xuICBkaXNwbGF5OiBmbGV4O1xuICBhbGlnbi1pdGVtczogY2VudGVyO1xuICBnYXA6IDEwcHg7XG4gIG1hcmdpbi1ib3R0b206IDVweDtcbiAgZm9udC1zaXplOiAxMS41cHg7XG4gIGNvbG9yOiAjOWFhNWI1O1xufVxuXG4ua2ItY2h1bmstaWR4IHtcbiAgZm9udC13ZWlnaHQ6IDYwMDtcbiAgY29sb3I6ICM0YTVhNzI7XG59XG5cbi5rYi1jaHVuay10ZXh0IHtcbiAgZm9udC1zaXplOiAxMi41cHg7XG4gIGxpbmUtaGVpZ2h0OiAxLjc1O1xuICBjb2xvcjogIzMzNDE1YztcbiAgd2hpdGUtc3BhY2U6IHByZS13cmFwO1xuICB3b3JkLWJyZWFrOiBicmVhay13b3JkO1xufVxuXG4vKiA9PT09PT09PT09IOeymOi0tOaWh+acrCA9PT09PT09PT09ICovXG4ua2ItaW1wb3J0IHtcbiAgZGlzcGxheTogZmxleDtcbiAgZmxleC1kaXJlY3Rpb246IGNvbHVtbjtcbiAgZ2FwOiAxMHB4O1xufVxuXG4ua2ItaW1wb3J0LWhpbnQge1xuICBwYWRkaW5nOiA4cHggMTBweDtcbiAgYm9yZGVyOiAxcHggc29saWQgI2VlZjJmNztcbiAgYm9yZGVyLXJhZGl1czogOHB4O1xuICBiYWNrZ3JvdW5kOiAjZjhmYWZjO1xuICBmb250LXNpemU6IDEyLjVweDtcbiAgbGluZS1oZWlnaHQ6IDEuNztcbiAgY29sb3I6ICM2YjcyODA7XG59XG5cbi8qIGVsLWlucHV0IOeahOagueiKgueCueWwseWcqOi/meS4pOexu+S4iu+8iHRleHRhcmVhIOS5n+S4gOagt++8ie+8jOaYvuW8j+aSkea7oeW8ueeql+WuveW6piAqL1xuLmtiLWltcG9ydC1uYW1lLFxuLmtiLWltcG9ydC10ZXh0IHtcbiAgd2lkdGg6IDEwMCU7XG59XG5cbi5rYi1pbXBvcnQtY291bnQge1xuICB0ZXh0LWFsaWduOiByaWdodDtcbiAgZm9udC1zaXplOiAxMS41cHg7XG4gIGNvbG9yOiAjYjZiZGM5O1xufVxuPC9zdHlsZT5cbiJdLCJmaWxlIjoiRDovT3BlblN0dWR5L2FwcHMvZmFzdGFwaS12Mi9vcGVuc3R1ZHktdnVlMy10cy9zcmMvY29tcG9uZW50cy9Lbm93bGVkZ2VCYXNlRHJhd2VyL2luZGV4LnZ1ZSJ9