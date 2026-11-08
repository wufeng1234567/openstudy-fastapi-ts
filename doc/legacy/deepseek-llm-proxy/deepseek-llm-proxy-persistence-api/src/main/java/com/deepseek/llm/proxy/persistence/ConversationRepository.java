package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.Conversation;
import com.deepseek.llm.proxy.core.model.HistoryMessage;

import java.util.List;

/**
 * 会话仓库接口
 */
public interface ConversationRepository {

    /** 保存（全量覆盖） */
    void save(Conversation conversation) throws PersistenceException;

    /** 按 sessionId 查找 */
    Conversation findById(String sessionId) throws PersistenceException;

    /** 列出某用户的会话（按 updatedAt 倒序） */
    List<Conversation> findByUserId(String userId, int limit, int offset) throws PersistenceException;

    /** 按 sessionId 删除 */
    boolean deleteById(String sessionId) throws PersistenceException;

    /** 追加消息（避免 find+save 的全量读写开销） */
    default void appendMessage(String sessionId, HistoryMessage message) throws PersistenceException {
        Conversation conv = findById(sessionId);
        if (conv == null) {
            throw new PersistenceException(ErrorCode.CONVERSATION_NOT_FOUND,
                    "会话不存在: " + sessionId);
        }
        List<HistoryMessage> msgs = conv.getMessages();
        if (msgs == null) {
            msgs = new java.util.ArrayList<>();
            conv.setMessages(msgs);
        }
        msgs.add(message);
        save(conv);
    }

    /** 更新标题 */
    default void updateTitle(String sessionId, String title) throws PersistenceException {
        Conversation conv = findById(sessionId);
        if (conv == null) {
            throw new PersistenceException(ErrorCode.CONVERSATION_NOT_FOUND,
                    "会话不存在: " + sessionId);
        }
        conv.setTitle(title);
        save(conv);
    }

    /** 清空某用户在某 Provider 下的所有会话 */
    default int clearByUserId(String userId, String providerId) throws PersistenceException {
        int deleted = 0;
        // 默认实现：列出该用户所有会话（不限定 Provider），逐个删除匹配的
        // 子类可重写为批量 DELETE SQL
        int offset = 0;
        int limit = 100;
        while (true) {
            List<Conversation> batch = findByUserId(userId, limit, offset);
            if (batch == null || batch.isEmpty()) break;
            for (Conversation c : batch) {
                if (providerId == null || providerId.equals(c.getProviderId())) {
                    if (deleteById(c.getSessionId())) deleted++;
                }
            }
            if (batch.size() < limit) break;
            offset += limit;
        }
        return deleted;
    }
}

