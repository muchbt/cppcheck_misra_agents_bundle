# 人工复核清单

| issue_key | 文件 | 规则 | 状态 | edit_ids | 复核原因 |
| --- | --- | --- | --- | --- | --- |
| cppcheck_error.c:10:bufferAccessOutOfBounds:afec5dc6 |  |  | needs_manual_review | - | No rule-specific auto-fix policy is configured. Buffer access out of bounds is a high-risk memory safety issue. |
| cppcheck_error.c:10:misra-c2012-17.7:4a2c80d8 |  |  | needs_manual_review | - | Return-value handling can change error handling semantics. |
| cppcheck_error.c:3:misra-c2012-8.4:4a2c80d8 |  |  | needs_manual_review | - | No rule-specific auto-fix policy is configured. Strategy action explicitly set to needs_manual_review. |
| cppcheck_info.c:13:misra-c2012-8.4:4a2c80d8 |  |  | needs_manual_review | - | No rule-specific auto-fix policy is configured. |
| cppcheck_info.c:1:misra-c2012-21.6:4a2c80d8 |  |  | needs_manual_review | - | No rule-specific auto-fix policy is configured. |
| cppcheck_warning.c:11:misra-c2012-17.7:4a2c80d8 |  |  | needs_manual_review | - | Return-value handling can change error handling semantics. MISRA C2012-17.7 requires explicit decision on whether to check printf return value. Fixing requires understanding the intended error handling strategy. |
| cppcheck_warning.c:1:misra-c2012-21.6:4a2c80d8 |  |  | needs_manual_review | - | MISRA C2012 Rule 21.6 prohibits use of standard library I/O functions. Auto-fix would require replacing <stdio.h> with project-specific I/O abstraction, which needs architecture decisions. No rule-specific auto-fix policy is configured. |
| cppcheck_warning.c:3:misra-c2012-8.4:4a2c80d8 |  |  | needs_manual_review | - | No rule-specific auto-fix policy is configured. |
| cppcheck_warning.c:4:unassignedVariable:b3783ebc |  |  | needs_manual_review | - | No rule-specific auto-fix policy is configured. |

## 修改点索引
- 没有记录到修改点。
