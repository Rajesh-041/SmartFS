#ifndef SMARTFS_M4_INTEGRATION_H
#define SMARTFS_M4_INTEGRATION_H

#include "common.h"

void quota_init(uint32_t default_limit);
bool quota_check(uint32_t uid, uint32_t incoming_bytes);
void quota_update(uint32_t uid, int32_t delta_bytes);
QuotaRecord* quota_get(uint32_t uid);

void metrics_init(void);
void metrics_get_json(char *out_json, uint32_t max_len);

int handle_boot(const char *disk_path);
int handle_write_request(const char *path, const uint8_t *data, uint32_t size, const char *token, const char *fail_after);
int handle_read_request(const char *path, uint8_t *out_data, uint32_t *out_size, const char *token);
int handle_mkdir_request(const char *path, const char *token);
int handle_delete_request(const char *path, const char *token);
int handle_list_request(const char *path, DirEntry *out_entries, uint32_t *out_count, const char *token);

int run_benchmark(const char *workload, uint32_t num_ops, char *out_report, uint32_t max_report_len);

#endif /* SMARTFS_M4_INTEGRATION_H */
