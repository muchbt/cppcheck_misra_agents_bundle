#!/usr/bin/env python3
"""
生成 C 语言静态分析测试文件脚本
覆盖 Cppcheck (error, warning, information) 与 MISRA C:2012 (Mandatory, Required, Advisory)
"""

import os

# 文件内容映射字典
FILES_CONTENT = {
    "cppcheck_error.c": """\
#include <string.h>

void trigger_cppcheck_error(void) {
    char buffer[5];
    /*
     * Cppcheck 等级: error
     * 触发规则: bufferAccessOutOfBounds / strcpyOutOfBounds
     * 说明: 目标缓冲区容量仅 5 字节，strcpy 写入超长字符串会导致确定的内存越界。
     */
    strcpy(buffer, "TooLongString");
}
""",

    "cppcheck_warning.c": """\
#include <stdio.h>

void trigger_cppcheck_warning(void) {
    int uninitialized_var;
    /*
     * Cppcheck 等级: warning
     * 触发规则: uninitvar
     * 说明: 局部变量 uninitialized_var 声明后未初始化即被条件判断读取，行为未定义。
     */
    if (uninitialized_var > 10) {
        printf("Value is large\\n");
    }
}
""",

    "cppcheck_info.c": """\
#include <stdio.h>

/*
 * Cppcheck 等级: information
 * 触发规则: unusedFunction
 * 说明: static 函数 internal_helper 仅在本文件定义，但从未被调用。
 * 注意: 需使用 --enable=information 或 --enable=all 参数才会报告此级别。
 */
static void internal_helper(void) {
    printf("This function is never called.\\n");
}

void trigger_cppcheck_info(void) {
    int redundant = 5;
    redundant = 5; /* 冗余赋值，部分配置下也可能报 information */
    (void)redundant;
}
""",

    "misra_mandatory.c": """\
/*
 * MISRA C:2012 Rule 11.1 [Mandatory]
 * 规则原文: Conversions shall not be performed between a pointer to a function
 *           and any other type.
 * 说明: 函数指针与整型/数据指针之间的转换属于强制禁止项，不允许申请偏离。
 */
void misra_mandatory_example(void) {
    void (*func_ptr)(void);
    /* 违规点: 将函数指针强制转换为无符号整型，违反 Mandatory 规则 */
    unsigned long addr = (unsigned long)misra_mandatory_example;
    func_ptr = (void (*)(void))addr;
    func_ptr();
}
""",

    "misra_required.c": """\
/*
 * MISRA C:2012 Rule 10.4 [Required]
 * 规则原文: The value of an expression shall not be assigned to an object with
 *           a narrower essential type or of a different essential type category.
 * 说明: 要求等级必须遵守，但可通过正式偏离流程豁免。隐式窄化转换是典型违规。
 */
void misra_required_example(void) {
    unsigned char narrow_var;
    int wide_var = 300;
    /* 违规点: int (通常32位) 隐式赋值给 unsigned char (8位)，可能丢失数据 */
    narrow_var = wide_var;
}
""",

    "misra_advisory.c": """\
/*
 * MISRA C:2012 Rule 8.7 [Advisory]
 * 规则原文: Functions and objects should be defined with static storage-class
 *           specifier if they are only used in one translation unit.
 * 说明: 建议等级不强制要求，但强烈建议遵循以提高模块封装性和可维护性。
 */

/* 违规点: 该全局变量仅在本翻译单元使用，但未声明为 static，违反 Advisory 建议 */
int internal_counter = 0;

void misra_advisory_example(void) {
    internal_counter++;
}
"""
}


def main():
    print("🚀 开始生成 C 语言静态分析测试文件...")
    print("-" * 50)
    
    for filename, content in FILES_CONTENT.items():
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 已生成: {filename}")
        
    print("-" * 50)
    print("📁 文件生成完毕。共 6 个文件。")
    print("\n🔍 验证命令参考:")
    print("  # Cppcheck 验证 (默认版本需 >= 2.0)")
    print("  cppcheck cppcheck_error.c")
    print("  cppcheck cppcheck_warning.c")
    print("  cppcheck --enable=information cppcheck_info.c")
    print("\n  # MISRA C:2012 验证 (需配合官方 misra.py 插件)")
    print("  cppcheck --addon=misra.py misra_mandatory.c")
    print("  cppcheck --addon=misra.py misra_required.c")
    print("  cppcheck --addon=misra.py misra_advisory.c")
    print("\n💡 提示: MISRA 检测依赖工具链配置，商业工具(PCLint, QAC等)可直接导入 .c 文件扫描。")


if __name__ == "__main__":
    main()
