package com.deepseek.llm.proxy.persistence.sql;

import com.deepseek.llm.proxy.persistence.ColumnDescriptor;
import com.deepseek.llm.proxy.persistence.TableDescriptor;

import java.util.ArrayList;
import java.util.List;

/**
 * 默认建表脚本生成器
 */
public class DefaultSchemaScript {

    private final Dialect dialect;

    public DefaultSchemaScript(Dialect dialect) {
        this.dialect = dialect;
    }

    /** 生成会话表 DDL */
    public String generateConversationDdl(String tableName) {
        StringBuilder sb = new StringBuilder();
        sb.append("CREATE TABLE ").append(quote(tableName)).append(" (\n");
        sb.append("  ").append(quote("session_id")).append(" VARCHAR(64) NOT NULL PRIMARY KEY,\n");
        sb.append("  ").append(quote("user_id")).append(" VARCHAR(64) NOT NULL,\n");
        sb.append("  ").append(quote("tenant_id")).append(" VARCHAR(64),\n");
        sb.append("  ").append(quote("provider_id")).append(" VARCHAR(64) NOT NULL,\n");
        sb.append("  ").append(quote("title")).append(" VARCHAR(255),\n");
        sb.append("  ").append(quote("messages")).append(" ").append(dialect.longTextType()).append(",\n");
        sb.append("  ").append(quote("metadata")).append(" ").append(dialect.longTextType()).append(",\n");
        sb.append("  ").append(quote("created_at")).append(" ").append(dialect.timestampType()).append(",\n");
        sb.append("  ").append(quote("updated_at")).append(" ").append(dialect.timestampType()).append("\n");
        sb.append(")");
        return sb.toString();
    }

    /** 生成记忆表 DDL */
    public String generateMemoryDdl(String tableName) {
        StringBuilder sb = new StringBuilder();
        sb.append("CREATE TABLE ").append(quote(tableName)).append(" (\n");
        sb.append("  ").append(quote("user_id")).append(" VARCHAR(64) NOT NULL,\n");
        sb.append("  ").append(quote("tenant_id")).append(" VARCHAR(64),\n");
        sb.append("  ").append(quote("provider_id")).append(" VARCHAR(64) NOT NULL,\n");
        sb.append("  ").append(quote("content")).append(" ").append(dialect.longTextType()).append(",\n");
        sb.append("  ").append(quote("metadata")).append(" ").append(dialect.longTextType()).append(",\n");
        sb.append("  ").append(quote("created_at")).append(" ").append(dialect.timestampType()).append(",\n");
        sb.append("  ").append(quote("updated_at")).append(" ").append(dialect.timestampType()).append(",\n");
        sb.append("  PRIMARY KEY (").append(quote("user_id")).append(", ").append(quote("provider_id")).append(")\n");
        sb.append(")");
        return sb.toString();
    }

    /** 期望的会话表结构（用于冲突检测） */
    public TableDescriptor expectedConversationSchema(String tableName) {
        List<ColumnDescriptor> cols = new ArrayList<>();
        cols.add(new ColumnDescriptor("session_id", "VARCHAR(64)", false, true));
        cols.add(new ColumnDescriptor("user_id", "VARCHAR(64)", false, false));
        cols.add(new ColumnDescriptor("tenant_id", "VARCHAR(64)", true, false));
        cols.add(new ColumnDescriptor("provider_id", "VARCHAR(64)", false, false));
        cols.add(new ColumnDescriptor("title", "VARCHAR(255)", true, false));
        cols.add(new ColumnDescriptor("messages", dialect.longTextType(), true, false));
        cols.add(new ColumnDescriptor("metadata", dialect.longTextType(), true, false));
        cols.add(new ColumnDescriptor("created_at", "TIMESTAMP", true, false));
        cols.add(new ColumnDescriptor("updated_at", "TIMESTAMP", true, false));
        return new TableDescriptor(tableName, cols);
    }

    /** 期望的记忆表结构 */
    public TableDescriptor expectedMemorySchema(String tableName) {
        List<ColumnDescriptor> cols = new ArrayList<>();
        cols.add(new ColumnDescriptor("user_id", "VARCHAR(64)", false, true));
        cols.add(new ColumnDescriptor("tenant_id", "VARCHAR(64)", true, false));
        cols.add(new ColumnDescriptor("provider_id", "VARCHAR(64)", false, true));
        cols.add(new ColumnDescriptor("content", dialect.longTextType(), true, false));
        cols.add(new ColumnDescriptor("metadata", dialect.longTextType(), true, false));
        cols.add(new ColumnDescriptor("created_at", "TIMESTAMP", true, false));
        cols.add(new ColumnDescriptor("updated_at", "TIMESTAMP", true, false));
        return new TableDescriptor(tableName, cols);
    }

    /** 字段引用（不同方言对大小写敏感的处理） */
    private String quote(String name) {
        switch (dialect) {
            case MYSQL:
                return "`" + name + "`";
            case POSTGRESQL:
            case ORACLE:
                return "\"" + name + "\"";
            case HSQLDB:
                return "\"" + name.toUpperCase() + "\"";
            case SQLITE:
                return "\"" + name + "\"";
            default:
                return name;
        }
    }

    public Dialect getDialect() {
        return dialect;
    }
}
