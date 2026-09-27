#ifndef SMARTFS_M2_SECURITY_H
#define SMARTFS_M2_SECURITY_H

#include "common.h"

void auth_init(void);
int register_user(const char *username, const char *password, const char *role, User *out_user);
void hash_password(const char *password, const uint8_t *salt, uint8_t *out_hash);
bool verify_password(const char *password, const uint8_t *stored_hash, const uint8_t *salt);
int authenticate(const char *username, const char *password, Session *out_session);
int validate_session(const char *token, Session *out_session);
void revoke_session(const char *token);

bool check_rbac(const char *role, const char *operation, uint32_t uid);
bool check_permission_bits(uint32_t perm_bits, uint32_t owner_uid, uint32_t requesting_uid, char mode);

void generate_file_key(uint32_t uid, uint32_t file_id, uint8_t *out_key);
int encrypt_data(const uint8_t *plaintext, uint32_t len, const uint8_t *key, uint8_t *out_ciphertext, uint32_t *out_len);
int decrypt_data(const uint8_t *ciphertext, uint32_t len, const uint8_t *key, uint8_t *out_plaintext, uint32_t *out_len);

void log_access_attempt(uint32_t uid, const char *op, const char *target, const char *result);
User* get_user_by_id(uint32_t uid);

#endif /* SMARTFS_M2_SECURITY_H */
