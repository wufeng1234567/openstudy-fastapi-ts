package com.deepseek.llm.proxy.persistence.sql;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.persistence.ColumnDescriptor;
import com.deepseek.llm.proxy.persistence.TableDescriptor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.*;

/**
 * 表存在性与 schema 兼容性检查器（JDBC 实现）
 */
public class SchemaCompatibilityChecker {

    private static final Logger log = LoggerFactory.getLogger(SchemaCompatibilityChecker.class);

    private final JdbcTemplate jdbcTemplate;
    private final Dialect dialect;

    public SchemaCompatibilityChecker(JdbcTemplate jdbcTemplate, Dialect dialect) {
        this.jdbcTemplate = jdbcTemplate;
        this.dialect = dialect;
    }

    /** 检测表是否存在 */
    public boolean tableExists(String tableName) throws PersistenceException {
        try {
            List<Integer> rows = jdbcTemplate.query(
                    dialect.tableExistsSql(),
                    (rs, rowNum) -> 1,
                    tableName);
            return !rows.isEmpty();
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_INIT_FAILED,
                    "检测表 " + tableName + " 是否存在失败：" + e.getMessage(), e);
        }
    }

    /** 读取实际表的所有列信息 */
    public Map<String, String> describeColumns(String tableName) throws PersistenceException {
        try {
            Map<String, String> columns = new LinkedHashMap<>();
            switch (dialect) {
                case SQLITE:
                    // PRAGMA table_info 返回列：cid, name, type, notnull, dflt_value, pk
                    jdbcTemplate.query(
                            "PRAGMA table_info(" + tableName + ")",
                            rs -> {
                                String name = rs.getString("name");
                                String type = rs.getString("type");
                                columns.put(name.toLowerCase(Locale.ROOT), type != null ? type.toUpperCase(Locale.ROOT) : "");
                            });
                    break;
                default:
                    jdbcTemplate.query(
                            dialect.describeColumnsSql(),
                            rs -> {
                                String name = rs.getString(1);
                                String type = rs.getString(2);
                                columns.put(name.toLowerCase(Locale.ROOT), type != null ? type.toUpperCase(Locale.ROOT) : "");
                            },
                            tableName);
            }
            return columns;
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_INIT_FAILED,
                    "读取表 " + tableName + " 的列信息失败：" + e.getMessage(), e);
        }
    }

    /**
     * 比对实际表结构与期望结构，返回差异
     */
    public ComparisonResult compare(String tableName, TableDescriptor expected) throws PersistenceException {
        if (!tableExists(tableName)) {
            return ComparisonResult.tableNotExists(tableName);
        }

        Map<String, String> actualCols = describeColumns(tableName);
        List<String> missing = new ArrayList<>();
        List<String> mismatch = new ArrayList<>();
        List<String> extra = new ArrayList<>();

        for (ColumnDescriptor expectedCol : expected.getColumns()) {
            String key = expectedCol.getName().toLowerCase(Locale.ROOT);
            if (!actualCols.containsKey(key)) {
                missing.add(expectedCol.getName());
            } else {
                String actualType = actualCols.get(key);
                if (!typeMatches(expectedCol.getType(), actualType)) {
                    mismatch.add(expectedCol.getName() + "(期望 " + expectedCol.getType() + " / 实际 " + actualType + ")");
                }
            }
        }

        // 检查多出的字段（允许，不阻塞）
        Set<String> expectedKeys = new HashSet<>();
        for (ColumnDescriptor c : expected.getColumns()) {
            expectedKeys.add(c.getName().toLowerCase(Locale.ROOT));
        }
        for (Map.Entry<String, String> entry : actualCols.entrySet()) {
            if (!expectedKeys.contains(entry.getKey())) {
                extra.add(entry.getKey());
            }
        }

        boolean match = missing.isEmpty() && mismatch.isEmpty();
        return new ComparisonResult(tableName, true, match, missing, mismatch, extra);
    }

    /** 类型匹配检查（放宽比较：仅前缀匹配） */
    private boolean typeMatches(String expectedType, String actualType) {
        if (expectedType == null || actualType == null) {
            return false;
        }
        String e = expectedType.toUpperCase(Locale.ROOT).replaceAll("\\(\\d+(,\\d+)?\\)", "").trim();
        String a = actualType.toUpperCase(Locale.ROOT).replaceAll("\\(\\d+(,\\d+)?\\)", "").trim();

        // LONGTEXT/TEXT/CLOB 互通
        if (isTextType(e) && isTextType(a)) {
            return true;
        }
        // VARCHAR/CHAR 互通
        if (e.startsWith("VARCHAR") && a.startsWith("VARCHAR")) {
            return true;
        }
        if (e.startsWith("CHAR") && (a.startsWith("CHAR") || a.startsWith("VARCHAR"))) {
            return true;
        }
        // TIMESTAMP/DATETIME 互通
        if ((e.startsWith("TIMESTAMP") || e.startsWith("DATETIME"))
                && (a.startsWith("TIMESTAMP") || a.startsWith("DATETIME"))) {
            return true;
        }

        return e.equals(a);
    }

    private boolean isTextType(String t) {
        return t.startsWith("LONGTEXT") || t.startsWith("TEXT") || t.startsWith("CLOB");
    }

    /** 比对结果 */
    public static class ComparisonResult {
        private final String tableName;
        private final boolean tableExists;
        private final boolean match;
        private final List<String> missingColumns;
        private final List<String> mismatchColumns;
        private final List<String> extraColumns;

        public ComparisonResult(String tableName, boolean tableExists, boolean match,
                                List<String> missingColumns, List<String> mismatchColumns,
                                List<String> extraColumns) {
            this.tableName = tableName;
            this.tableExists = tableExists;
            this.match = match;
            this.missingColumns = missingColumns;
            this.mismatchColumns = mismatchColumns;
            this.extraColumns = extraColumns;
        }

        public static ComparisonResult tableNotExists(String tableName) {
            return new ComparisonResult(tableName, false, false,
                    Collections.emptyList(), Collections.emptyList(), Collections.emptyList());
        }

        public String getTableName() { return tableName; }
        public boolean isTableExists() { return tableExists; }
        public boolean isMatch() { return match; }
        public List<String> getMissingColumns() { return missingColumns; }
        public List<String> getMismatchColumns() { return mismatchColumns; }
        public List<String> getExtraColumns() { return extraColumns; }
    }
}
