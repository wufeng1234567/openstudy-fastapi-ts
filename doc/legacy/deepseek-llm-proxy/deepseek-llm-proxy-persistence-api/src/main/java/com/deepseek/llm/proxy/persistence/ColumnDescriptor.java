package com.deepseek.llm.proxy.persistence;

/**
 * 表字段描述符
 */
public class ColumnDescriptor {

    /** 列名 */
    private String name;
    /** 列类型（如 VARCHAR(64)、LONGTEXT、TIMESTAMP） */
    private String type;
    /** 是否可空 */
    private boolean nullable;
    /** 是否主键 */
    private boolean primaryKey;
    /** 默认值（DDL 片段，如 "DEFAULT 'deepseek-free'"） */
    private String defaultValue;

    public ColumnDescriptor() {
    }

    public ColumnDescriptor(String name, String type) {
        this.name = name;
        this.type = type;
    }

    public ColumnDescriptor(String name, String type, boolean nullable, boolean primaryKey) {
        this.name = name;
        this.type = type;
        this.nullable = nullable;
        this.primaryKey = primaryKey;
    }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public boolean isNullable() { return nullable; }
    public void setNullable(boolean nullable) { this.nullable = nullable; }
    public boolean isPrimaryKey() { return primaryKey; }
    public void setPrimaryKey(boolean primaryKey) { this.primaryKey = primaryKey; }
    public String getDefaultValue() { return defaultValue; }
    public void setDefaultValue(String defaultValue) { this.defaultValue = defaultValue; }
}
