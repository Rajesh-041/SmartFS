#include "m2_security.h"

void generate_file_key(uint32_t uid, uint32_t file_id, uint8_t *out_key) {
    memset(out_key, 0, 32);
    snprintf((char*)out_key, 32, "smartfs_key_uid_%u_file_%u", uid, file_id);
    /* Simple XOR hash expansion to 32 bytes */
    for (uint32_t i = 0; i < 32; i++) {
        out_key[i] ^= (uint8_t)(uid ^ file_id ^ (i * 17));
    }
}

int encrypt_data(const uint8_t *plaintext, uint32_t len, const uint8_t *key, uint8_t *out_ciphertext, uint32_t *out_len) {
    if (!plaintext || !key || !out_ciphertext) return ERR_INVALID_CONFIG;

    /* Write 12-byte nonce stub */
    for (int i = 0; i < 12; i++) out_ciphertext[i] = (uint8_t)(i * 31 + 7);

    /* Encrypt bytes using XOR keystream derived from 32-byte key */
    for (uint32_t i = 0; i < len; i++) {
        out_ciphertext[12 + i] = plaintext[i] ^ key[i % 32];
    }

    /* Write 16-byte MAC tag stub */
    uint32_t mac_offset = 12 + len;
    for (int i = 0; i < 16; i++) {
        out_ciphertext[mac_offset + i] = (uint8_t)(key[i % 32] ^ 0xAA);
    }

    *out_len = 12 + len + 16;
    return SMARTFS_OK;
}

int decrypt_data(const uint8_t *ciphertext, uint32_t len, const uint8_t *key, uint8_t *out_plaintext, uint32_t *out_len) {
    if (!ciphertext || len < 28 || !key || !out_plaintext) return ERR_DECRYPT_FAILED;

    uint32_t payload_len = len - 28;
    uint32_t mac_offset = 12 + payload_len;

    /* Verify MAC tag stub */
    for (int i = 0; i < 16; i++) {
        if (ciphertext[mac_offset + i] != (uint8_t)(key[i % 32] ^ 0xAA)) {
            return ERR_DECRYPT_FAILED;
        }
    }

    /* Decrypt payload */
    for (uint32_t i = 0; i < payload_len; i++) {
        out_plaintext[i] = ciphertext[12 + i] ^ key[i % 32];
    }

    *out_len = payload_len;
    return SMARTFS_OK;
}
