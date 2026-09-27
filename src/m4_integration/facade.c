#include "m4_integration.h"
#include "m1_storage.h"
#include "m2_security.h"
#include "m3_reliability.h"
#include "event_bus.h"

int handle_boot(const char *disk_path) {
    auth_init();
    cache_init(CACHE_CAPACITY);
    quota_init(DEFAULT_QUOTA_BYTES);
    metrics_init();
    journal_init("journal.log");

    int res = mount_disk(disk_path);
    if (res != SMARTFS_OK) {
        res = format_disk(disk_path, DEFAULT_DISK_SIZE, BLOCK_SIZE, "FAT");
        if (res != SMARTFS_OK) return res;
    }

    uint32_t rolled_back = 0, committed = 0, orphaned = 0;
    replay_journal(&rolled_back, &committed, &orphaned);
    return SMARTFS_OK;
}

int handle_write_request(const char *path, const uint8_t *data, uint32_t size, const char *token, const char *fail_after) {
    Session session;
    int res = validate_session(token, &session);
    if (res != SMARTFS_OK) return res;

    User *user = get_user_by_id(session.uid);
    if (!user) return ERR_PERMISSION_DENIED;

    if (!check_rbac(user->role, "write", user->uid)) {
        log_access_attempt(user->uid, "write", path, "DENIED_RBAC");
        return ERR_PERMISSION_DENIED;
    }

    DirEntry *entry = resolve_path(path);
    if (entry) {
        if (!check_permission_bits(entry->perm_bits, entry->owner_uid, user->uid, 'w')) {
            log_access_attempt(user->uid, "write", path, "DENIED_PERM_BITS");
            return ERR_PERMISSION_DENIED;
        }
    } else {
        res = storage_create_file(path, user->uid, 0644);
        if (res != SMARTFS_OK) return res;
        entry = resolve_path(path);
    }

    if (!quota_check(user->uid, size)) {
        log_access_attempt(user->uid, "write", path, "DENIED_QUOTA");
        return ERR_QUOTA_EXCEEDED;
    }

    uint32_t txn_id = journal_write_intent("WRITE", path);

    if (fail_after && strcmp(fail_after, "journal") == 0) {
        return ERR_SIMULATED_CRASH;
    }

    uint8_t compressed[65536];
    uint32_t comp_len = 0;
    compress_block(data, size, compressed, &comp_len);

    uint8_t file_key[32];
    uint32_t key_id = (uint32_t)(entry - g_directories) + 1;
    generate_file_key(user->uid, key_id, file_key);

    uint8_t encrypted[65536];
    uint32_t enc_len = 0;
    encrypt_data(compressed, comp_len, file_key, encrypted, &enc_len);

    res = storage_write_file_blocks(path, encrypted, enc_len);

    if (fail_after && (strcmp(fail_after, "allocate") == 0 || strcmp(fail_after, "physical_write") == 0)) {
        return ERR_SIMULATED_CRASH;
    }

    uint32_t blocks[256];
    uint32_t b_count = 0;
    storage_get_file_blocks(path, blocks, &b_count);
    for (uint32_t i = 0; i < b_count; i++) {
        uint8_t buf[BLOCK_SIZE];
        disk_read_block(blocks[i], buf);
        cache_put(blocks[i], buf);
    }

    create_version(path, blocks, b_count, NULL);

    journal_commit(txn_id);

    if (fail_after && strcmp(fail_after, "commit") == 0) {
        return ERR_SIMULATED_CRASH;
    }

    quota_update(user->uid, (int32_t)size);
    log_access_attempt(user->uid, "write", path, "SUCCESS");

    char json[256];
    snprintf(json, sizeof(json), "{\"path\":\"%s\", \"bytes\":%u, \"uid\":%u}", path, size, user->uid);
    emit_metric("file_written", json);
    return (int)size;
}

int handle_read_request(const char *path, uint8_t *out_data, uint32_t *out_size, const char *token) {
    Session session;
    int res = validate_session(token, &session);
    if (res != SMARTFS_OK) return res;

    User *user = get_user_by_id(session.uid);
    if (!user) return ERR_PERMISSION_DENIED;

    if (!check_rbac(user->role, "read", user->uid)) {
        log_access_attempt(user->uid, "read", path, "DENIED_RBAC");
        return ERR_PERMISSION_DENIED;
    }

    DirEntry *entry = resolve_path(path);
    if (!entry) {
        log_access_attempt(user->uid, "read", path, "ENOENT");
        return ERR_ENOENT;
    }

    if (!check_permission_bits(entry->perm_bits, entry->owner_uid, user->uid, 'r')) {
        log_access_attempt(user->uid, "read", path, "DENIED_PERM_BITS");
        return ERR_PERMISSION_DENIED;
    }

    uint8_t encrypted[65536];
    uint32_t enc_len = 0;
    res = storage_read_file_blocks(path, encrypted, &enc_len);
    if (res != SMARTFS_OK) return res;

    uint8_t file_key[32];
    uint32_t key_id = (uint32_t)(entry - g_directories) + 1;
    generate_file_key(user->uid, key_id, file_key);

    uint8_t compressed[65536];
    uint32_t comp_len = 0;
    res = decrypt_data(encrypted, enc_len, file_key, compressed, &comp_len);
    if (res != SMARTFS_OK) return res;

    uint32_t plain_len = 0;
    decompress_block(compressed, comp_len, out_data, &plain_len);
    *out_size = plain_len;

    log_access_attempt(user->uid, "read", path, "SUCCESS");
    return SMARTFS_OK;
}

int handle_mkdir_request(const char *path, const char *token) {
    Session session;
    int res = validate_session(token, &session);
    if (res != SMARTFS_OK) return res;

    User *user = get_user_by_id(session.uid);
    if (!user || !check_rbac(user->role, "mkdir", user->uid)) return ERR_PERMISSION_DENIED;

    uint32_t txn_id = journal_write_intent("MKDIR", path);
    res = storage_mkdir(path, user->uid, 0755);
    journal_commit(txn_id);

    log_access_attempt(user->uid, "mkdir", path, "SUCCESS");
    return res;
}

int handle_delete_request(const char *path, const char *token) {
    Session session;
    int res = validate_session(token, &session);
    if (res != SMARTFS_OK) return res;

    User *user = get_user_by_id(session.uid);
    if (!user || !check_rbac(user->role, "delete", user->uid)) return ERR_PERMISSION_DENIED;

    DirEntry *entry = resolve_path(path);
    if (!entry) return ERR_ENOENT;

    uint32_t txn_id = journal_write_intent("DELETE", path);
    uint32_t deleted_size = entry->size_bytes;
    res = storage_delete_file(path);
    journal_commit(txn_id);

    quota_update(user->uid, -(int32_t)deleted_size);
    log_access_attempt(user->uid, "delete", path, "SUCCESS");
    return res;
}

int handle_list_request(const char *path, DirEntry *out_entries, uint32_t *out_count, const char *token) {
    Session session;
    int res = validate_session(token, &session);
    if (res != SMARTFS_OK) return res;

    User *user = get_user_by_id(session.uid);
    if (!user || !check_rbac(user->role, "read", user->uid)) return ERR_PERMISSION_DENIED;

    return storage_list_dir(path, out_entries, out_count);
}
