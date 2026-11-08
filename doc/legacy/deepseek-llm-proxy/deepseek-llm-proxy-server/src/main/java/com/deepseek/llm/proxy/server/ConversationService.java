package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.Conversation;
import com.deepseek.llm.proxy.core.model.HistoryMessage;
import com.deepseek.llm.proxy.persistence.ConversationRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * 会话业务服务
 * <p>
 * 封装 {@link ConversationRepository}，对外提供：
 * <ul>
 *   <li>会话生命周期管理（创建/查询/列表/删除/清空）</li>
 *   <li>消息追加（与 ChatService 联动）</li>
 *   <li>历史加载（ChatService 在 enableMemory=true 时调用）</li>
 *   <li>标题更新</li>
 * </ul>
 * </p>
 * <p>
 * 所有持久化操作均捕获 {@link PersistenceException}，记录日志后降级返回，
 * 避免持久化故障影响核心对话流程。
 * </p>
 */
public class ConversationService {

    private static final Logger log = LoggerFactory.getLogger(ConversationService.class);

    /** 默认列表大小 */
    private static final int DEFAULT_LIMIT = 20;
    /** 最大列表大小 */
    private static final int MAX_LIMIT = 100;
    /** 自动加载历史的最大条数 */
    private static final int MAX_HISTORY_LOAD = 50;

    private final ConversationRepository repository;

    public ConversationService(ConversationRepository repository) {
        this.repository = repository;
    }

    /**
     * 创建新会话
     *
     * @param userId     用户 ID
     * @param providerId Provider ID
     * @param tenantId   租户 ID（可选）
     * @param title      会话标题（可选，默认"新对话"）
     * @return 新建的 sessionId
     */
    public String createSession(String userId, String providerId, String tenantId, String title) {
        String sessionId = "conv_" + UUID.randomUUID().toString().replace("-", "");
        Conversation conv = new Conversation();
        conv.setSessionId(sessionId);
        conv.setUserId(userId);
        conv.setProviderId(providerId);
        conv.setTenantId(tenantId);
        conv.setTitle(title == null ? "新对话" : title);
        conv.setMessages(new ArrayList<>());
        conv.setCreatedAt(Instant.now());
        conv.setUpdatedAt(Instant.now());

        try {
            repository.save(conv);
            log.info("创建会话: sessionId={}, userId={}, provider={}", sessionId, userId, providerId);
        } catch (PersistenceException e) {
            log.error("创建会话失败（降级返回 sessionId，但未持久化）: {}", e.getMessage(), e);
        }
        return sessionId;
    }

    /**
     * 加载会话历史（用于 ChatService 在 enableMemory=true 时自动注入）
     * <p>
     * 加载最近 {@value #MAX_HISTORY_LOAD} 条历史消息，按时间正序返回。
     * </p>
     *
     * @param sessionId 会话 ID
     * @return 历史消息列表（空列表表示无历史或会话不存在）
     */
    public List<HistoryMessage> loadHistory(String sessionId) {
        if (sessionId == null || sessionId.isEmpty()) {
            return Collections.emptyList();
        }
        try {
            Conversation conv = repository.findById(sessionId);
            if (conv == null || conv.getMessages() == null) {
                return Collections.emptyList();
            }
            List<HistoryMessage> all = conv.getMessages();
            if (all.size() <= MAX_HISTORY_LOAD) {
                return new ArrayList<>(all);
            }
            // 截取最近 N 条
            return new ArrayList<>(all.subList(all.size() - MAX_HISTORY_LOAD, all.size()));
        } catch (PersistenceException e) {
            log.warn("加载历史失败（返回空历史）: sessionId={}, err={}", sessionId, e.getMessage());
            return Collections.emptyList();
        }
    }

    /**
     * 追加用户消息（聊天发起时调用）
     *
     * @return 是否成功
     */
    public boolean appendUserMessage(String sessionId, String content) {
        return appendMessage(sessionId, HistoryMessage.user(content));
    }

    /**
     * 追加 assistant 回复（聊天完成时调用）
     *
     * @param thinkingContent 深度思考内容（可选）
     * @return 是否成功
     */
    public boolean appendAssistantMessage(String sessionId, String content, String thinkingContent) {
        HistoryMessage msg = HistoryMessage.assistant(content);
        if (thinkingContent != null && !thinkingContent.isEmpty()) {
            msg.setThinkingContent(thinkingContent);
        }
        return appendMessage(sessionId, msg);
    }

    /**
     * 追加任意消息（内部通用方法）
     */
    public boolean appendMessage(String sessionId, HistoryMessage message) {
        if (sessionId == null || sessionId.isEmpty()) {
            return false;
        }
        try {
            repository.appendMessage(sessionId, message);
            return true;
        } catch (PersistenceException e) {
            log.warn("追加消息失败: sessionId={}, err={}", sessionId, e.getMessage());
            return false;
        }
    }

    /**
     * 查询会话详情
     */
    public Conversation get(String sessionId) {
        if (sessionId == null || sessionId.isEmpty()) {
            return null;
        }
        try {
            return repository.findById(sessionId);
        } catch (PersistenceException e) {
            log.warn("查询会话失败: sessionId={}, err={}", sessionId, e.getMessage());
            return null;
        }
    }

    /**
     * 列出某用户的会话（不含完整 messages，仅元信息）
     */
    public List<Conversation> listByUser(String userId, Integer limit, Integer offset) {
        if (userId == null || userId.isEmpty()) {
            return Collections.emptyList();
        }
        int l = limit == null ? DEFAULT_LIMIT : Math.min(Math.max(1, limit), MAX_LIMIT);
        int o = offset == null ? 0 : Math.max(0, offset);
        try {
            List<Conversation> list = repository.findByUserId(userId, l, o);
            // 出于隐私和带宽考虑，列表场景下清空 messages
            if (list != null) {
                for (Conversation c : list) {
                    if (c.getMessages() != null) {
                        c.setMessages(null);
                    }
                }
            }
            return list == null ? Collections.emptyList() : list;
        } catch (PersistenceException e) {
            log.warn("列表会话失败: userId={}, err={}", userId, e.getMessage());
            return Collections.emptyList();
        }
    }

    /**
     * 更新会话标题
     */
    public boolean updateTitle(String sessionId, String title) {
        if (sessionId == null || title == null) return false;
        try {
            repository.updateTitle(sessionId, title);
            return true;
        } catch (PersistenceException e) {
            log.warn("更新标题失败: sessionId={}, err={}", sessionId, e.getMessage());
            return false;
        }
    }

    /**
     * 删除会话
     */
    public boolean delete(String sessionId) {
        if (sessionId == null) return false;
        try {
            return repository.deleteById(sessionId);
        } catch (PersistenceException e) {
            log.warn("删除会话失败: sessionId={}, err={}", sessionId, e.getMessage());
            return false;
        }
    }

    /**
     * 清空某用户在某 Provider 下的所有会话
     *
     * @return 删除条数
     */
    public int clearByUser(String userId, String providerId) {
        if (userId == null) return 0;
        try {
            int n = repository.clearByUserId(userId, providerId);
            log.info("清空会话: userId={}, provider={}, count={}", userId, providerId, n);
            return n;
        } catch (PersistenceException e) {
            log.warn("清空会话失败: userId={}, err={}", userId, e.getMessage());
            return 0;
        }
    }

    /**
     * 确保会话存在（不存在则创建）
     * <p>
     * ChatService 在 enableMemory=true 且 sessionId 非空时调用，
     * 若 sessionId 不存在会自动创建，避免后续 appendMessage 失败。
     * </p>
     *
     * @return 实际使用的 sessionId（与传入相同）
     */
    public String ensureSession(String sessionId, String userId, String providerId, String tenantId) {
        try {
            Conversation existing = repository.findById(sessionId);
            if (existing != null) {
                return sessionId;
            }
        } catch (PersistenceException e) {
            log.debug("ensureSession 查询失败，继续创建: {}", e.getMessage());
        }
        // 不存在 → 创建
        return createSession(userId, providerId, tenantId, null);
    }

    /**
     * 校验会话归属权（防越权访问）
     * <p>
     * 检查 sessionId 是否确实属于该 userId，避免用户 A 用自己的 userId 配合
     * 用户 B 的 sessionId 偷看 B 的对话历史。
     * </p>
     *
     * @param sessionId 会话 ID
     * @param userId    当前请求的用户 ID
     * @return true 表示归属校验通过（会话不存在或属于该用户）；false 表示越权
     */
    public boolean checkOwnership(String sessionId, String userId) {
        if (sessionId == null || userId == null) {
            return true;  // 缺少参数时不拦截，由其他校验处理
        }
        try {
            Conversation conv = repository.findById(sessionId);
            if (conv == null) {
                return true;  // 会话不存在视为可创建，不拦截
            }
            return userId.equals(conv.getUserId());
        } catch (PersistenceException e) {
            log.warn("ownership 校验查询失败，降级放行: sessionId={}, err={}",
                    sessionId, e.getMessage());
            return true;  // 持久化故障时降级放行，不阻塞业务
        }
    }

    /**
     * 强制校验会话归属权（越权直接抛异常）
     *
     * @throws com.deepseek.llm.proxy.core.exception.LlmProxyException 越权时抛 AUTH_FAILED
     */
    public void requireOwnership(String sessionId, String userId)
            throws com.deepseek.llm.proxy.core.exception.LlmProxyException {
        if (!checkOwnership(sessionId, userId)) {
            throw new com.deepseek.llm.proxy.core.exception.LlmProxyException(
                    com.deepseek.llm.proxy.core.enums.ErrorCode.AUTH_FAILED,
                    "会话归属权校验失败：sessionId=" + sessionId + " 不属于 userId=" + userId);
        }
    }
}
