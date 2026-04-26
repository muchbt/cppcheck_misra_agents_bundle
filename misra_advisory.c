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
