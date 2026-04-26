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
