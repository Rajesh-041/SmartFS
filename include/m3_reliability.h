#ifndef SMARTFS_M3_RELIABILITY_H
#define SMARTFS_M3_RELIABILITY_H

#include "common.h"

void journal_init(const char *path);
uint32_t journal_write_intent(const char *op_type, const char *target);
void journal_commit(uint32_t txn_id);
void journal_rollback(uint32_t txn_id);
int scan_journal(JournalRecord *out_records, uint32_t *out_count);

int replay_journal(uint32_t *out_rolled_back, uint32_t *out_committed, uint32_t *out_orphaned);

void cache_init(uint32_t capacity);
bool cache_get(uint32_t block_id, uint8_t *out_buffer);
void cache_put(uint32_t block_id, const uint8_t *buffer);
void cache_invalidate(uint32_t block_id);
double cache_get_hit_ratio(void);

int compress_block(const uint8_t *src, uint32_t src_len, uint8_t *dst, uint32_t *dst_len);
int decompress_block(const uint8_t *src, uint32_t src_len, uint8_t *dst, uint32_t *dst_len);

int create_version(const char *file_path, const uint32_t *block_map, uint32_t block_count, VersionEntry *out_entry);
int list_versions(const char *file_path, VersionEntry *out_entries, uint32_t *out_count);
int restore_version(const char *file_path, uint32_t version_id);

#endif /* SMARTFS_M3_RELIABILITY_H */
