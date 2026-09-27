#include "m3_reliability.h"
#include "m1_storage.h"
#include "event_bus.h"

int replay_journal(uint32_t *out_rolled_back, uint32_t *out_committed, uint32_t *out_orphaned) {
    JournalRecord records[1024];
    uint32_t record_count = 0;
    scan_journal(records, &record_count);

    uint8_t status_map[1024] = {0}; /* 0=None, 1=PENDING, 2=COMMITTED, 3=ROLLED_BACK */
    char targets[1024][MAX_PATH_LEN];
    memset(targets, 0, sizeof(targets));

    for (uint32_t i = 0; i < record_count; i++) {
        uint32_t tid = records[i].txn_id;
        if (tid < 1024) {
            if (records[i].status == JOURNAL_COMMITTED) {
                status_map[tid] = 2;
            } else if (records[i].status == JOURNAL_ROLLED_BACK) {
                status_map[tid] = 3;
            } else if (status_map[tid] == 0) {
                status_map[tid] = 1;
                strncpy(targets[tid], records[i].target, MAX_PATH_LEN);
            }
        }
    }

    uint32_t rolled_back = 0;
    uint32_t committed = 0;

    for (uint32_t tid = 1; tid < 1024; tid++) {
        if (status_map[tid] == 2) {
            committed++;
        } else if (status_map[tid] == 1) {
            /* Unwound pending transaction */
            if (strlen(targets[tid]) > 0) {
                DirEntry *e = resolve_path(targets[tid]);
                if (e && strcmp(e->entry_type, "file") == 0) {
                    if (e->size_bytes == 0) {
                        storage_delete_file(targets[tid]);
                    }
                }
            }
            journal_rollback(tid);
            rolled_back++;
        }
    }

    /* Orphan scan & reclamation */
    bool ref_map[16384] = {false};
    for (uint32_t i = 0; i < RESERVED_METADATA_BLOCKS; i++) ref_map[i] = true;

    for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
        if (g_directories[i].active && strcmp(g_directories[i].entry_type, "file") == 0) {
            uint32_t blocks[256];
            uint32_t count = 0;
            storage_get_file_blocks(g_directories[i].path, blocks, &count);
            for (uint32_t b = 0; b < count; b++) {
                if (blocks[b] < g_superblock.total_blocks) ref_map[blocks[b]] = true;
            }
        }
    }

    uint32_t orphaned = 0;
    for (uint32_t b = RESERVED_METADATA_BLOCKS; b < g_superblock.total_blocks; b++) {
        uint32_t byte_idx = b / 8;
        uint32_t bit_idx = b % 8;
        bool is_alloc = (g_bitmap.bits[byte_idx] & (1 << bit_idx)) != 0;
        if (is_alloc && !ref_map[b]) {
            free_block(b);
            orphaned++;
        }
    }

    if (out_rolled_back) *out_rolled_back = rolled_back;
    if (out_committed) *out_committed = committed;
    if (out_orphaned) *out_orphaned = orphaned;

    char json[256];
    snprintf(json, sizeof(json),
             "{\"rolled_back\":%u, \"committed\":%u, \"orphaned_reclaimed\":%u, \"status\":\"CLEAN\"}",
             rolled_back, committed, orphaned);
    emit_metric("recovery_completed", json);

    return SMARTFS_OK;
}
