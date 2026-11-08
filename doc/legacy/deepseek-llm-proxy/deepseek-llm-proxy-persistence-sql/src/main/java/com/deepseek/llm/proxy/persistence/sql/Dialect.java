package com.deepseek.llm.proxy.persistence.sql;

import java.util.Locale;

/**
 * 数据库方言
 */
public enum Dialect {

    /** MySQL / MariaDB */
    MYSQL,
    /** PostgreSQL */
    POSTGRESQL,
    /** HSQLDB（嵌入式，测试用） */
    HSQLDB,
    /** SQLite */
    SQLITE,
    /** Oracle */
    ORACLE;

    /** 从字符串解析方言，未识别时抛出 IllegalArgumentException */
    public static Dialect fromString(String name) {
        if (name == null || name.isEmpty()) {
            return MYSQL;
        }
        String lower = name.toLowerCase(Locale.ROOT);
        switch (lower) {
            case "mysql":
            case "mariadb":
                return MYSQL;
            case "postgresql":
            case "postgres":
            case "pg":
                return POSTGRESQL;
            case "hsqldb":
            case "hsql":
                return HSQLDB;
            case "sqlite":
                return SQLITE;
            case "oracle":
                return ORACLE;
            default:
                throw new IllegalArgumentException("Unsupported dialect: " + name
                        + ". Supported: mysql, postgresql, hsqldb, sqlite, oracle");
        }
    }

    /** 长文本类型（用于 content / messages 等大字段） */
    public String longTextType() {
        switch (this) {
            case MYSQL:
            case HSQLDB:
                return "LONGTEXT";
            case POSTGRESQL:
                return "TEXT";
            case SQLITE:
                return "TEXT";
            case ORACLE:
                return "CLOB";
            default:
                return "TEXT";
        }
    }

    /** 时间戳类型 */
    public String timestampType() {
        switch (this) {
            case MYSQL:
                return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP";
            case POSTGRESQL:
                return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP";
            case HSQLDB:
                return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP";
            case ORACLE:
                return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP";
            case SQLITE:
                return "DATETIME DEFAULT CURRENT_TIMESTAMP";
            default:
                return "TIMESTAMP";
        }
    }

    /** 检测表是否存在的 SQL（参数：表名） */
    public String tableExistsSql() {
        switch (this) {
            case MYSQL:
            case HSQLDB:
                return "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1";
            case POSTGRESQL:
                return "SELECT 1 FROM information_schema.tables WHERE table_name = $1 LIMIT 1";
            case SQLITE:
                return "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1";
            case ORACLE:
                return "SELECT 1 FROM user_tables WHERE table_name = ? ROWNUM = 1";
            default:
                return "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1";
        }
    }

    /** 查询表所有列信息 SQL（参数：表名） */
    public String describeColumnsSql() {
        switch (this) {
            case MYSQL:
                return "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?";
            case POSTGRESQL:
                return "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = $1";
            case HSQLDB:
                return "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?";
            case SQLITE:
                return "PRAGMA table_info(?)";
            case ORACLE:
                return "SELECT column_name, data_type FROM user_tab_columns WHERE table_name = ?";
            default:
                return "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?";
        }
    }
}
