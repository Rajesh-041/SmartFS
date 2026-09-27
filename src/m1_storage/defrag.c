#include "m1_storage.h"
#include "event_bus.h"

double calculate_fragmentation(const char *path) {
    if (path) {
        DirEntry *e = resolve_path(path);
        if (!e || strcmp(e->entry_type, "file") != 0) return 0.0;
        uint32_t blocks[256];
        uint32_t count = 0;
        storage_get_file_blocks(path, blocks, &count);
        if (count <= 1) return 0.0;

        uint32_t non_contig = 0;
        for (uint32_t i = 0; i < count - 1; i++) {
            if (blocks[i + 1] != blocks[i] + 1) non_contig++;
        }
        return (double)non_contig / (count - 1) * 100.0;
    } else {
        uint32_t total_files = 0;
        double sum_frag = 0.0;
        for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
            if (g_directories[i].active && strcmp(g_directories[i].entry_type, "file") == 0) {
                sum_frag += calculate_fragmentation(g_directories[i].path);
                total_files++;
            }
        }
        double disk_frag = total_files > 0 ? (sum_frag / total_files) : 0.0;
        char json[128];
        snprintf(json, sizeof(json), "{\"fragmentation_pct\": %.2f}", disk_frag);
        emit_metric("fragmentation_reported", json);
        return disk_frag;
    }
}

int defragment(const char *path) {
    if (!path) return ERR_ENOENT;
    DirEntry *e = resolve_path(path);
    if (!e || strcmp(e->entry_type, "file") != 0) return ERR_ENOENT;

    uint8_t data[65536];
    uint32_t size = 0;
    int res = storage_read_file_blocks(path, data, &size);
    if (res != SMARTFS_OK) return res;

    res = storage_write_file_blocks(path, data, size);
    if (res != SMARTFS_OK) return res;

    double new_frag = calculate_fragmentation(path);
    char json[128];
    snprintf(json, sizeof(json), "{\"path\":\"%s\", \"new_fragmentation_pct\":%.2f}", path, new_frag);
    emit_metric("defrag_completed", json);
    return SMARTFS_OK;
}
