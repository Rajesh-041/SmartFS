#include "m3_reliability.h"

int compress_block(const uint8_t *src, uint32_t src_len, uint8_t *dst, uint32_t *dst_len) {
    if (!src || !dst) return ERR_INVALID_CONFIG;
    if (src_len == 0) {
        *dst_len = 0;
        return SMARTFS_OK;
    }

    uint32_t out_idx = 0;
    for (uint32_t i = 0; i < src_len; i++) {
        uint8_t count = 1;
        while (i + 1 < src_len && src[i] == src[i + 1] && count < 255) {
            count++;
            i++;
        }
        dst[out_idx++] = count;
        dst[out_idx++] = src[i];
    }
    *dst_len = out_idx;
    return SMARTFS_OK;
}

int decompress_block(const uint8_t *src, uint32_t src_len, uint8_t *dst, uint32_t *dst_len) {
    if (!src || !dst) return ERR_INVALID_CONFIG;
    if (src_len == 0) {
        *dst_len = 0;
        return SMARTFS_OK;
    }

    uint32_t out_idx = 0;
    uint32_t max_cap = 65535;

    for (uint32_t i = 0; i + 1 < src_len; i += 2) {
        uint8_t count = src[i];
        uint8_t val = src[i + 1];
        for (uint8_t c = 0; c < count; c++) {
            if (out_idx >= max_cap) break;
            dst[out_idx++] = val;
        }
    }
    *dst_len = out_idx;
    return SMARTFS_OK;
}
