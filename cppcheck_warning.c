#include <stdio.h>

void trigger_cppcheck_warning(void) {
    int uninitialized_var;
    /*
     * Cppcheck 等级: warning
     * 触发规则: uninitvar
     * 说明: 局部变量 uninitialized_var 声明后未初始化即被条件判断读取，行为未定义。
     */
    if (uninitialized_var > 10) {
        printf("Value is large\n");
    }
}
