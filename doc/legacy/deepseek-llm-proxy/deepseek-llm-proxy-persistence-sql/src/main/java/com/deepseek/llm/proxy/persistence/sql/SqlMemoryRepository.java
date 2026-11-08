package com.deepseek.llm.proxy.persistence.sql;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.MemoryRecord;
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
 * SQL 记忆仓库实现
 */
public class SqlMemoryRepository implements MemoryRepository {

    private static final Logger log = LoggerFactory.getLogger(SqlMemoryRepository.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final JdbcTemplate jdbcTemplate;
    private final String tableName;

    public SqlMemoryRepository(JdbcTemplate jdbcTemplate, String tableName) {
        this.jdbcTemplate = jdbcTemplate;
        this.tableName = tableName;
    }

    @Override
    public void save(MemoryRecord memory) throws PersistenceException {
        if (memory == null || memory.getUserId() == null || memory.getProviderId() == null) {
            throw new PersistenceException(ErrorCode.INVALID_REQUEST,
                    "Memory / userId / providerId 不能为空");
        }
        try {
            String metadataJson = memory.getMetadata() != null
                    ? MAPPER.writeValueAsString(memory.getMetadata()) : null;
            Timestamp now = Timestamp.from(Instant.now());
            Timestamp createdAt = memory.getCreatedAt() != null
                    ? Timestamp.from(memory.getCreatedAt()) : now;
            Timestamp updatedAt = memory.getUpdatedAt() != null
                    ? Timestamp.from(memory.getUpdatedAt()) : now;

            int updated = jdbcTemplate.update(
                    "UPDATE " + tableName + " SET tenant_id=?, content=?, metadata=?, updated_at=? "
                            + "WHERE user_id=? AND provider_id=?",
                    memory.getTenantId(), memory.getContent(), metadataJson, updatedAt,
                    memory.getUserId(), memory.getProviderId());

            if (updated == 0) {
                jdbcTemplate.update(
                        "INSERT INTO " + tableName + " (user_id, tenant_id, provider_id, content, "
                                + "metadata, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                        memory.getUserId(), memory.getTenantId(), memory.getProviderId(),
                        memory.getContent(), metadataJson, createdAt, updatedAt);
            }
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_WRITE_FAILED,
                    "保存记忆失败：" + e.getMessage(), e);
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.SERIALIZATION_ERROR,
                    "序列化记忆失败：" + e.getMessage(), e);
        }
    }

    @Override
    public Optional<MemoryRecord> findByUserIdAndProvider(String userId, String providerId)
            throws PersistenceException {
        try {
            List<MemoryRecord> list = jdbcTemplate.query(
                    "SELECT * FROM " + tableName + " WHERE user_id = ? AND provider_id = ?",
                    new MemoryRowMapper(), userId, providerId);
            return list.isEmpty() ? Optional.empty() : Optional.of(list.get(0));
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_READ_FAILED,
                    "查询记忆失败：" + e.getMessage(), e);
        }
    }

    @Override
    public boolean clear(String userId, String providerId) throws PersistenceException {
        try {
            int rows = jdbcTemplate.update(
                    "DELETE FROM " + tableName + " WHERE user_id = ? AND provider_id = ?",
                    userId, providerId);
            return rows > 0;
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_WRITE_FAILED,
                    "清空记忆失败：" + e.getMessage(), e);
        }
    }

    private static class MemoryRowMapper implements RowMapper<MemoryRecord> {
        @Override
        public MemoryRecord mapRow(java.sql.ResultSet rs, int rowNum) throws java.sql.SQLException {
            MemoryRecord m = new MemoryRecord();
            m.setUserId(rs.getString("user_id"));
            m.setTenantId(rs.getString("tenant_id"));
            m.setProviderId(rs.getString("provider_id"));
            m.setContent(rs.getString("content"));

            String metadataJson = rs.getString("metadata");
            if (metadataJson != null && !metadataJson.isEmpty()) {
                try {
                    Map<String, Object> meta = MAPPER.readValue(metadataJson,
                            new TypeReference<Map<String, Object>>() {});
                    m.setMetadata(meta);
                } catch (Exception e) {
                    log.warn("反序列化 metadata 失败：{}", e.getMessage());
                }
            }

            Timestamp ca = rs.getTimestamp("created_at");
            if (ca != null) m.setCreatedAt(ca.toInstant());
            Timestamp ua = rs.getTimestamp("updated_at");
            if (ua != null) m.setUpdatedAt(ua.toInstant());
            return m;
        }
    }
}
