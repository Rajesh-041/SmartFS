#include "m3_reliability.h"
#include "m1_storage.h"

static VersionEntry g_versions[128];
static uint32_t g_version_count = 0;
static uint32_t g_next_v_id = 1;

int create_version(const char *file_path, const uint32_t *block_map, uint32_t block_count, VersionEntry *out_entry) {
    if (g_version_count >= 128) return ERR_DISK_FULL;

    VersionEntry *v = &g_versions[g_version_count++];
    v->version_id = g_next_v_id++;
    strncpy(v->file_path, file_path, MAX_PATH_LEN);
    v->timestamp = get_current_time_sec();
    v->block_count = block_count;
    for (uint32_t i = 0; i < block_count && i < 128; i++) {
        v->block_map[i] = block_map[i];
    }

    if (out_entry) *out_entry = *v;
    return SMARTFS_OK;
}

int list_versions(const char *file_path, VersionEntry *out_entries, uint32_t *out_count) {
    uint32_t count = 0;
    for (uint32_t i = 0; i < g_version_count; i++) {
        if (strcmp(g_versions[i].file_path, file_path) == 0) {
            out_entries[count++] = g_versions[i];
        }
    }
    *out_count = count;
    return SMARTFS_OK;
}

int restore_version(const char *file_path, uint32_t version_id) {
    for (uint32_t i = 0; i < g_version_count; i++) {
        if (g_versions[i].version_id == version_id && strcmp(g_versions[i].file_path, file_path) == 0) {
            uint8_t data[65536];
            uint32_t total_size = 0;
            for (uint32_t b = 0; b < g_versions[i].block_count; b++) {
                uint8_t buf[BLOCK_SIZE];
                disk_read_block(g_versions[i].block_map[b], buf);
                memcpy(data + total_size, buf, BLOCK_SIZE);
                total_size += BLOCK_SIZE;
            }
            return storage_write_file_blocks(file_path, data, total_size);
        }
    }
    return ERR_ENOENT;
}
