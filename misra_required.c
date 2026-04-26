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
