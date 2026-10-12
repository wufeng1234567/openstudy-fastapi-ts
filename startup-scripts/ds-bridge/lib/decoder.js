// decoder.js — DeepSeek 网页 SSE 解码器
//
// DS 的 /api/v0/chat/completion 返回 **JSON-patch over SSE**（真机抓到实况，2026-10-12）：
//   event: ready   → data {request_message_id, response_message_id, model_type}
//   event: message → data 是若干「patch 帧」之一：
//       ① 根快照：{"v":{"response":{...,"fragments":[{id,type,content},...]}}}
//       ② 片段创建：{"p":"response/fragments","o":"APPEND","v":[{id,type,content,...}]}
//       ③ 指定片段正文增量：{"p":"response/fragments/-1/content","o":"APPEND","v":"回答"}
//       ④ 裸增量：{"v":"用户"}   ← 沿用上一条的 p / o / 片段类型（正文几乎都走这条）
//       ⑤ 状态：{"p":"response/status","o":"SET","v":"FINISHED"} / response/fragments/-1/elapsed_secs
//   event: hint    → 限流/错误
//   event: close   → 收流
//
// ⚠️ **重连重放**（用户 2026-10-12 报「正文丢开头几个字 / 深度思考混进正文」的根因）：
//    一条流里 DS 会**先发一段被截断的前缀**，随后重新 `event: ready` 并**从头重放整段**。
//    若把两遍都当增量累加 → 正文重复、片段类型串味（正文开头被算成思考等）。
//    处理：**再次出现 ready 即「重开」，清空解码状态重新累积**（重放前缀是幂等的，
//    第二遍是完整的那一遍）。
//
// 片段类型：THINK / THINKING = 思考；RESPONSE = 正式正文（两者都靠片段自己的 type 区分）。

/** 极简 SSE 帧切分：按空行分隔，收集 event:/data: 行 */
class SseSplitter {
  constructor() {
    this.buf = '';
  }
  push(chunk) {
    this.buf += String(chunk || '').replace(/\r\n/g, '\n');
    const events = [];
    let idx;
    while ((idx = this.buf.indexOf('\n\n')) >= 0) {
      const raw = this.buf.slice(0, idx);
      this.buf = this.buf.slice(idx + 2);
      let event = 'message';
      const dataLines = [];
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
      }
      events.push({ event, data: dataLines.join('\n') });
    }
    return events;
  }
}

const THINK_TYPES = new Set(['THINK', 'THINKING']);

export class DeepSeekStreamDecoder {
  constructor(onDelta, onThink) {
    this.onDelta = onDelta || null;
    this.onThink = onThink || null;
    this.sse = new SseSplitter();
    this._reset();
    this.sawReady = false;
    this.receivedClose = false;
    this.failed = false;
    this.hintError = null;
  }

  /** 清空「本轮累积状态」（重连重放时调用） */
  _reset({ keepEmitFloor = false } = {}) {
    // emitFloor：已经**流式发出去**的正文/思考长度。重放时不清零 ——
    // 重放前缀与已发内容逐字相同，用 floor 抑制重复下发（否则客户端会看到重复的开头）。
    if (!keepEmitFloor) {
      this._floorText = 0;
      this._floorThink = 0;
    }
    this.text = '';
    this.thinking = '';
    this.responseStatus = null;
    this.finishReason = null;
    this.fragments = [];       // 顺序片段 {type, content}
    this.lastPath = '';        // 裸增量沿用
    this.lastOp = 'APPEND';
    this.lastType = 'RESPONSE';
    this.curIndex = -1;        // 当前「最后一段」下标（-1 解析目标）
  }

  push(chunk) {
    for (const ev of this.sse.push(chunk)) this._consumeEvent(ev);
  }

  _consumeEvent(ev) {
    if (ev.event === 'close') {
      this.receivedClose = true;
      return;
    }
    if (ev.event === 'ready') {
      // ⚠️ 重连重放：第二次及以后出现的 ready = 整段从头重放 → 清空重来。
      //    第一次 ready 只是首连握手（此时本就无内容）。
      if (this.sawReady && (this.text || this.thinking || this.fragments.length)) {
        this._reset({ keepEmitFloor: true });
      }
      this.sawReady = true;
      return;
    }
    if (ev.event === 'error') {
      this.failed = true;
      return;
    }
    let payload;
    try {
      payload = JSON.parse(ev.data);
    } catch {
      this.failed = true;
      return;
    }
    if (ev.event === 'hint') {
      if (payload && payload.type === 'error') {
        this.hintError = {
          content: payload.content || '',
          finish_reason: payload.finish_reason || '',
        };
      }
      return;
    }
    if (ev.event !== 'message') return;
    this._consumeDelta(payload);
  }

  /**
   * 据根快照「重建」本轮状态（重连重放的关键）。
   * 快照是该时刻的权威全量片段；据此重算 text/thinking，后续增量再叠加。
   * 流式下发用 floor（已发长度）抑制重放前缀，避免客户端看到重复开头。
   */
  _rebuildFromFragments(list) {
    this.fragments = [];
    let text = '';
    let thinking = '';
    for (const f of list) {
      const type = String((f || {}).type || '').toUpperCase();
      if (!type) continue;
      const content = typeof f.content === 'string' ? f.content : '';
      this.fragments.push({ id: f.id, type, content });
      if (type === 'RESPONSE') text += content;
      else thinking += content;
    }
    this.text = text;
    this.thinking = thinking;
    if (this.fragments.length) {
      this.curIndex = this.fragments.length - 1;
      this.lastType = this.fragments[this.curIndex].type;
    }
    // floor 保持单调（只增不减）：重放前缀已被发过，重建后仍要抑制重复下发。
  }

  _emit(type, appended) {
    if (!appended) return;
    if (type === 'RESPONSE') {
      this.text += appended;
      // 只把「超出已发长度」的部分流式下发（重放前缀被 floor 抑制）
      const total = this.text.length;
      if (total > this._floorText) {
        const start = Math.max(this._floorText, total - appended.length);
        const chunk = this.text.slice(start, total);
        this._floorText = total;
        if (chunk) this.onDelta?.(chunk);
      }
    } else {
      this.thinking += appended;
      const total = this.thinking.length;
      if (total > this._floorThink) {
        const start = Math.max(this._floorThink, total - appended.length);
        const chunk = this.thinking.slice(start, total);
        this._floorThink = total;
        if (chunk) this.onThink?.(chunk);
      }
    }
  }

  _consumeDelta(delta) {
    if (!delta || typeof delta !== 'object') return;

    // ① 根快照：{"v":{"response":{...fragments...}}} —— DS 会**重复**下发根快照
    //    （重连重放：先发截断前缀，再从头重放整段）。根快照是「该时刻的权威全量状态」，
    //    故这里**据快照重建** text/thinking（丢弃此前累积的增量），后续增量再往上加。
    //    这样重放天然幂等：不会出现「正文重复 / 思考混进正文 / 丢开头」。
    const value = delta.v;
    if (value && typeof value === 'object' && value.response && typeof value.response === 'object') {
      const resp = value.response;
      if (resp.status) this.responseStatus = resp.status;
      if (Array.isArray(resp.fragments)) this._rebuildFromFragments(resp.fragments);
      return;
    }

    const hasPath = typeof delta.p === 'string';
    const path = hasPath ? String(delta.p) : this.lastPath || '';
    const op = hasPath && typeof delta.o === 'string' ? String(delta.o).toUpperCase() : (this.lastOp || 'APPEND');
    if (hasPath) this.lastPath = String(delta.p);
    if (hasPath && typeof delta.o === 'string') this.lastOp = String(delta.o).toUpperCase();

    // 状态 / 元数据帧（非正文）
    if (path === 'response/status' && typeof value === 'string') {
      this.responseStatus = value;
      return;
    }
    if (path === 'response/finish_reason' && typeof value === 'string') {
      this.finishReason = value;
      return;
    }

    // ② 片段创建：p === 'response/fragments'，v 是数组 [{id,type,content,...}]
    //    ⚠️ 旧实现只认 `response/fragments/<i>/content`，把这一帧整个丢了
    //       → RESPONSE 片段的首段正文（如「9」）丢失 = 正文开头丢字。
    //    ⚠️ 该帧在**重放**时会重复出现（同一 id）→ 必须按 id 幂等，不能再 push 一个。
    if (path === 'response/fragments' && Array.isArray(value)) {
      const created = value[0] || {};
      const type = String(created.type || 'RESPONSE').toUpperCase();
      const content = typeof created.content === 'string' ? created.content : '';
      const id = created.id;
      // 已存在同 id 片段 → 覆盖内容（重放幂等），并 emit 差值；否则新建
      let existingIdx = -1;
      if (id !== undefined && id !== null) {
        existingIdx = this.fragments.findIndex((f) => f && f.id === id);
      }
      if (existingIdx >= 0) {
        // 同 id 的创建帧 = **重放**（真实创建帧只出现一次，内容也只含首段正文，
        // 后续增长走裸增量）。重放时**不再 emit**，否则会把首段正文重复算一遍。
        this.curIndex = existingIdx;
        this.lastType = type;
        this.fragments[existingIdx].type = type;
        this.lastPath = `response/fragments/${existingIdx}/content`;
      } else {
        this.fragments.push({ id, type, content });
        this.curIndex = this.fragments.length - 1;
        this.lastType = type;
        this.lastPath = `response/fragments/${this.curIndex}/content`;
        this._emit(type, content);
      }
      return;
    }

    // ③/④ 正文增量：定位目标片段
    let idx = this.curIndex;
    const m = /^response\/fragments\/(-1|\d+)\/content$/.exec(path);
    if (m) {
      idx = m[1] === '-1' ? this.fragments.length - 1 : Number(m[1]);
    }
    if (idx < 0 || idx >= this.fragments.length) {
      // 还没建片段就来的裸增量：兜底按 lastType 建一个
      if (typeof value === 'string' || (value && typeof value === 'object' && value.type)) {
        const type = (value && typeof value === 'object' && value.type)
          ? String(value.type).toUpperCase()
          : (this.lastType || 'RESPONSE');
        this.fragments.push({ type, content: '' });
        idx = this.fragments.length - 1;
      } else {
        return;
      }
    }

    let type = '';
    let content = '';
    if (value && typeof value === 'object') {
      type = String(value.type || '').toUpperCase() || (this.fragments[idx]?.type || this.lastType);
      content = typeof value.content === 'string' ? value.content : '';
    } else if (typeof value === 'string') {
      type = this.fragments[idx]?.type || this.lastType || 'RESPONSE';
      content = value;
    } else {
      return;
    }
    if (!content) return;

    const prev = this.fragments[idx] || { type, content: '' };
    const nextContent = op === 'SET' ? content : prev.content + content;
    // ⚠️ 保留 id：片段 id 是「创建帧重放去重」的键，丢掉它会导致重放时又新建一个片段
    //    （正文重复 / 开头丢字）。
    this.fragments[idx] = { id: prev.id, type: type || prev.type, content: nextContent };
    this.lastType = this.fragments[idx].type;

    const appended = op === 'SET'
      ? (nextContent.startsWith(prev.content) ? nextContent.slice(prev.content.length) : nextContent)
      : content;
    this._emit(this.fragments[idx].type, appended);
  }

  finish() {
    return {
      text: this.text,
      thinking: this.thinking,
      complete: this.receivedClose || this.responseStatus === 'FINISHED',
      status: this.responseStatus,
      hint: this.hintError ? this.hintError.content : null,
      rateLimited: Boolean(this.hintError && /频繁|rate|limit/i.test((this.hintError.finish_reason || '') + (this.hintError.content || ''))),
      failed: this.failed,
    };
  }
}
