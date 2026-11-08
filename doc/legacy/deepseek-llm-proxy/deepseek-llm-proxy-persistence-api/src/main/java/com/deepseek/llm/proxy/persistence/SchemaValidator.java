package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;

import java.util.List;

/**
 * Schema 校验器
 * <p>用于校验已有表的结构是否符合 SDK 期望。</p>
 */
public interface SchemaValidator {

    /**
     * 校验表结构
     *
     * @param tableName 目标表名
     * @param expected  期望的表结构
     * @return 校验结果
     */
    ValidationResult validate(String tableName, TableDescriptor expected) throws PersistenceException;

    /**
     * 生成修复 SQL
     */
    List<String> generateRepairSqls(String tableName, ValidationResult result);

    /**
     * 校验结果
     */
    class ValidationResult {
        private final boolean valid;
        private final List<String> missingColumns;
        private final List<String> mismatchColumns;
        private final List<String> extraColumns;
        private final String message;

        public ValidationResult(boolean valid, List<String> missingColumns, List<String> mismatchColumns,
                                List<String> extraColumns, String message) {
            this.valid = valid;
            this.missingColumns = missingColumns;
            this.mismatchColumns = mismatchColumns;
            this.extraColumns = extraColumns;
            this.message = message;
        }

        public boolean isValid() { return valid; }
        public List<String> getMissingColumns() { return missingColumns; }
        public List<String> getMismatchColumns() { return mismatchColumns; }
        public List<String> getExtraColumns() { return extraColumns; }
        public String getMessage() { return message; }

        public ErrorCode toErrorCode() {
            if (!missingColumns.isEmpty() || !mismatchColumns.isEmpty()) {
                return ErrorCode.TABLE_SCHEMA_MISMATCH;
            }
            return null;
        }
    }
}
