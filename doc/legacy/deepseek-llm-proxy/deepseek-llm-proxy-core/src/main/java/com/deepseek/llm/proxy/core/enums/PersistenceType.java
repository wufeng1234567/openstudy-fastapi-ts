package com.deepseek.llm.proxy.core.enums;

/**
 * 持久化存储类型
 * <p>开发者通过此枚举选择存储范式，SDK 根据类型自动装配对应实现。</p>
 */
public enum PersistenceType {
    /** 不持久化（默认） */
    NONE,
    /** 浏览器本地化存储（IndexedDB / chrome.storage，由扩展 JS 实现） */
    BROWSER,
    /** SQL 数据库存储（JDBC，由后端 Java 实现） */
    SQL
}
