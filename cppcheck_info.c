#include <stdio.h>

/*
 * Cppcheck 等级: information
 * 触发规则: unusedFunction
 * 说明: static 函数 internal_helper 仅在本文件定义，但从未被调用。
 * 注意: 需使用 --enable=information 或 --enable=all 参数才会报告此级别。
 */
static void internal_helper(void) {
    printf("This function is never called.\n");
}

void trigger_cppcheck_info(void) {
    int redundant = 5;
    redundant = 5; /* 冗余赋值，部分配置下也可能报 information */
    (void)redundant;
}
