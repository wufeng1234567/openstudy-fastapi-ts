package com.deepseek.llm.proxy.persistence.sql;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.Conversation;
import com.deepseek.llm.proxy.core.model.HistoryMessage;
import com.deepseek.llm.proxy.core.model.MemoryRecord;
import com.deepseek.llm.proxy.persistence.ConversationRepository;
import com.deepseek.llm.proxy.persistence.MemoryRepository;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * SQL 会话仓库实现（基于 JdbcTemplate）
 */
public class SqlConversationRepository implements ConversationRepository {

    private static final Logger log = LoggerFactory.getLogger(SqlConversationRepository.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final JdbcTemplate jdbcTemplate;
    private final String tableName;

    public SqlConversationRepository(JdbcTemplate jdbcTemplate, String tableName) {
        this.jdbcTemplate = jdbcTemplate;
        this.tableName = tableName;
    }

    @Override
    public void save(Conversation conversation) throws PersistenceException {
        if (conversation == null || conversation.getSessionId() == null) {
            throw new PersistenceException(ErrorCode.INVALID_REQUEST, "Conversation 或 sessionId 不能为空");
        }
        try {
            String messagesJson = conversation.getMessages() != null
                    ? MAPPER.writeValueAsString(conversation.getMessages()) : null;
            String metadataJson = conversation.getMetadata() != null
                    ? MAPPER.writeValueAsString(conversation.getMetadata()) : null;
            Timestamp now = Timestamp.from(Instant.now());
            Timestamp createdAt = conversation.getCreatedAt() != null
                    ? Timestamp.from(conversation.getCreatedAt()) : now;
            Timestamp updatedAt = conversation.getUpdatedAt() != null
                    ? Timestamp.from(conversation.getUpdatedAt()) : now;

            int updated = jdbcTemplate.update(
                    "UPDATE " + tableName + " SET user_id=?, tenant_id=?, provider_id=?, title=?, "
                            + "messages=?, metadata=?, updated_at=? WHERE session_id=?",
                    conversation.getUserId(), conversation.getTenantId(),
                    conversation.getProviderId(), conversation.getTitle(),
                    messagesJson, metadataJson, updatedAt, conversation.getSessionId());

            if (updated == 0) {
                jdbcTemplate.update(
                        "INSERT INTO " + tableName + " (session_id, user_id, tenant_id, provider_id, "
                                + "title, messages, metadata, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        conversation.getSessionId(), conversation.getUserId(), conversation.getTenantId(),
                        conversation.getProviderId(), conversation.getTitle(),
                        messagesJson, metadataJson, createdAt, updatedAt);
            }
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_WRITE_FAILED,
                    "保存会话失败：" + e.getMessage(), e);
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.SERIALIZATION_ERROR,
                    "序列化会话失败：" + e.getMessage(), e);
        }
    }

    @Override
    public Conversation findById(String sessionId) throws PersistenceException {
        try {
            List<Conversation> list = jdbcTemplate.query(
                    "SELECT * FROM " + tableName + " WHERE session_id = ?",
                    new ConversationRowMapper(), sessionId);
            return list.isEmpty() ? null : list.get(0);
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_READ_FAILED,
                    "查询会话失败：" + e.getMessage(), e);
        }
    }

    @Override
    public List<Conversation> findByUserId(String userId, int limit, int offset) throws PersistenceException {
        try {
            return jdbcTemplate.query(
                    "SELECT * FROM " + tableName + " WHERE user_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    new ConversationRowMapper(), userId, limit, offset);
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_READ_FAILED,
                    "查询用户会话列表失败：" + e.getMessage(), e);
        }
    }

    @Override
    public boolean deleteById(String sessionId) throws PersistenceException {
        try {
            int rows = jdbcTemplate.update("DELETE FROM " + tableName + " WHERE session_id = ?", sessionId);
            return rows > 0;
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_WRITE_FAILED,
                    "删除会话失败：" + e.getMessage(), e);
        }
    }

    private static class ConversationRowMapper implements RowMapper<Conversation> {
        @Override
        public Conversation mapRow(java.sql.ResultSet rs, int rowNum) throws java.sql.SQLException {
            Conversation c = new Conversation();
            c.setSessionId(rs.getString("session_id"));
            c.setUserId(rs.getString("user_id"));
            c.setTenantId(rs.getString("tenant_id"));
            c.setProviderId(rs.getString("provider_id"));
            c.setTitle(rs.getString("title"));

            String messagesJson = rs.getString("messages");
            if (messagesJson != null && !messagesJson.isEmpty()) {
                try {
                    List<HistoryMessage> msgs = MAPPER.readValue(messagesJson,
                            new TypeReference<List<HistoryMessage>>() {});
                    c.setMessages(msgs);
                } catch (Exception e) {
                    log.warn("反序列化 messages 失败：{}", e.getMessage());
                }
            }

            String metadataJson = rs.getString("metadata");
            if (metadataJson != null && !metadataJson.isEmpty()) {
                try {
                    Map<String, Object> meta = MAPPER.readValue(metadataJson,
                            new TypeReference<Map<String, Object>>() {});
                    c.setMetadata(meta);
                } catch (Exception e) {
                    log.warn("反序列化 metadata 失败：{}", e.getMessage());
                }
            }

            Timestamp ca = rs.getTimestamp("created_at");
            if (ca != null) c.setCreatedAt(ca.toInstant());
            Timestamp ua = rs.getTimestamp("updated_at");
            if (ua != null) c.setUpdatedAt(ua.toInstant());
            return c;
        }
    }
}
