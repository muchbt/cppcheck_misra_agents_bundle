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
