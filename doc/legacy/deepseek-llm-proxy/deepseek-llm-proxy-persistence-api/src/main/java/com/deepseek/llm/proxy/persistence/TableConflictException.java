package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;

import java.util.List;

/**
 * 表冲突异常
 * <p>携带冲突详情和可选解决方案，供开发者选择处理方式。</p>
 */
public class TableConflictException extends PersistenceException {

    private static final long serialVersionUID = 1L;

    private final TableConflictDetector.ConflictResult conflictResult;
    private final List<TableConflictDetector.ResolutionOption> options;

    public TableConflictException(TableConflictDetector.ConflictResult conflictResult,
                                  List<TableConflictDetector.ResolutionOption> options) {
        super(ErrorCode.TABLE_CONFLICT,
                buildDetail(conflictResult, options));
        this.conflictResult = conflictResult;
        this.options = options;
    }

    private static String buildDetail(TableConflictDetector.ConflictResult conflict,
                                      List<TableConflictDetector.ResolutionOption> options) {
        StringBuilder sb = new StringBuilder();
        sb.append("表 ").append(conflict.getTableName()).append(" 存在冲突：\n");

        if (!conflict.isTableExists()) {
            sb.append("  - 表不存在\n");
        }
        if (!conflict.getMissingColumns().isEmpty()) {
            sb.append("  - 缺失字段: ").append(String.join(", ", conflict.getMissingColumns())).append("\n");
        }
        if (!conflict.getMismatchColumns().isEmpty()) {
            sb.append("  - 类型不匹配: ").append(String.join(", ", conflict.getMismatchColumns())).append("\n");
        }
        if (!conflict.getExtraColumns().isEmpty()) {
            sb.append("  - 多出字段(允许): ").append(String.join(", ", conflict.getExtraColumns())).append("\n");
        }

        if (!conflict.getRepairSqls().isEmpty()) {
            sb.append("\n修复 SQL:\n");
            for (String sql : conflict.getRepairSqls()) {
                sb.append("  ").append(sql).append("\n");
            }
        }

        if (options != null && !options.isEmpty()) {
            sb.append("\n可选解决方案:\n");
            for (TableConflictDetector.ResolutionOption opt : options) {
                sb.append("  [").append(opt.getId()).append("] ").append(opt.getDescription()).append("\n");
            }
        }

        return sb.toString();
    }

    public TableConflictDetector.ConflictResult getConflictResult() {
        return conflictResult;
    }

    public List<TableConflictDetector.ResolutionOption> getOptions() {
        return options;
    }
}
