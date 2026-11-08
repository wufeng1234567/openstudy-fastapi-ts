package com.deepseek.llm.proxy.persistence;

import java.util.List;

/**
 * 表描述符（用于检测冲突时比对）
 */
public class TableDescriptor {

    /** 表名 */
    private String tableName;
    /** 列描述符列表 */
    private List<ColumnDescriptor> columns;
    /** 备注 */
    private String comment;

    public TableDescriptor() {
    }

    public TableDescriptor(String tableName, List<ColumnDescriptor> columns) {
        this.tableName = tableName;
        this.columns = columns;
    }

    public String getTableName() { return tableName; }
    public void setTableName(String tableName) { this.tableName = tableName; }
    public List<ColumnDescriptor> getColumns() { return columns; }
    public void setColumns(List<ColumnDescriptor> columns) { this.columns = columns; }
    public String getComment() { return comment; }
    public void setComment(String comment) { this.comment = comment; }

    /** 根据 column name 查找 */
    public ColumnDescriptor findColumn(String name) {
        if (columns == null || name == null) {
            return null;
        }
        return columns.stream()
                .filter(c -> name.equalsIgnoreCase(c.getName()))
                .findFirst()
                .orElse(null);
    }
}
