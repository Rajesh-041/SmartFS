#ifndef SMARTFS_M1_STORAGE_H
#define SMARTFS_M1_STORAGE_H

#include "common.h"

extern Superblock g_superblock;
extern FreeBitmap g_bitmap;
extern FatTable g_fat_table;
extern DirEntry g_directories[MAX_DIR_ENTRIES];
extern uint32_t g_dir_count;
extern bool g_disk_mounted;

int disk_open(const char *path, bool create, uint32_t size_bytes);
void disk_close(void);
int disk_read_block(uint32_t block_id, uint8_t *buffer);
int disk_write_block(uint32_t block_id, const uint8_t *buffer);

int format_disk(const char *path, uint32_t size_bytes, uint32_t block_size, const char *mode);
int mount_disk(const char *path);

int allocate_block(uint32_t *block_id);
int allocate_blocks(uint32_t n, const char *strategy, uint32_t *out_blocks);
void free_block(uint32_t block_id);

int fat_alloc_chain(uint32_t n_blocks, int32_t *out_start);
int fat_free_chain(int32_t start, uint32_t *out_freed, uint32_t *out_count);
int fat_get_chain(int32_t start, uint32_t *out_chain, uint32_t *out_count);

int inode_allocate(uint32_t owner_uid, uint32_t perm_bits, Inode *out_inode);
int inode_grow(uint32_t inode_id, uint32_t n_blocks);
int inode_free(uint32_t inode_id);

DirEntry* resolve_path(const char *path);
int storage_mkdir(const char *path, uint32_t owner_uid, uint32_t perm_bits);
int storage_rmdir(const char *path);
int storage_list_dir(const char *path, DirEntry *out_entries, uint32_t *out_count);

int storage_create_file(const char *path, uint32_t owner_uid, uint32_t perm_bits);
int storage_get_file_blocks(const char *path, uint32_t *out_blocks, uint32_t *out_count);
int storage_write_file_blocks(const char *path, const uint8_t *data, uint32_t size_bytes);
int storage_read_file_blocks(const char *path, uint8_t *out_data, uint32_t *out_size);
int storage_delete_file(const char *path);

double calculate_fragmentation(const char *path);
int defragment(const char *path);

#endif /* SMARTFS_M1_STORAGE_H */
