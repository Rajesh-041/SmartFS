#ifndef SMARTFS_COMMON_H
#define SMARTFS_COMMON_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>

#define MAGIC_BYTES "SMFS"
#define BLOCK_SIZE 4096
#define DEFAULT_DISK_SIZE 67108864  /* 64 MB */
#define TOTAL_BLOCKS (DEFAULT_DISK_SIZE / BLOCK_SIZE) /* 16384 */
#define RESERVED_METADATA_BLOCKS 16
#define FAT_EOF -1
#define FAT_FREE 0
#define DIRECT_LIMIT 12
#define MAX_PATH_LEN 256
#define MAX_NAME_LEN 64
#define MAX_DIR_ENTRIES 256
#define DEFAULT_QUOTA_BYTES 10485760 /* 10 MB */
#define SESSION_TIMEOUT_SEC 1800
#define CACHE_CAPACITY 64

/* Error Codes */
#define SMARTFS_OK 0
#define ERR_INVALID_CONFIG -1
#define ERR_CORRUPT_DISK -2
#define ERR_DISK_FULL -3
#define ERR_ENOENT -4
#define ERR_EEXIST -5
#define ERR_ENOTEMPTY -6
#define ERR_EUSEREXISTS -7
#define ERR_EAUTHFAILED -8
#define ERR_ESESSIONEXPIRED -9
#define ERR_ESESSIONINVALID -10
#define ERR_PERMISSION_DENIED -11
#define ERR_QUOTA_EXCEEDED -12
#define ERR_DECRYPT_FAILED -13
#define ERR_SIMULATED_CRASH -14

/* Superblock */
typedef struct {
    char magic[4];
    uint32_t disk_size;
    uint32_t block_size;
    uint32_t total_blocks;
    uint32_t free_blocks;
    char allocation_mode[8]; /* "FAT" or "INODE" */
    uint32_t root_dir_ptr;
    uint32_t fs_version;
} Superblock;

/* Free-Block Bitmap */
typedef struct {
    uint32_t total_blocks;
    uint8_t *bits;
} FreeBitmap;

/* FAT Table */
typedef struct {
    uint32_t total_blocks;
    int32_t *entries;
} FatTable;

/* Inode */
typedef struct {
    uint32_t inode_id;
    uint32_t owner_uid;
    uint32_t group_gid;
    uint32_t perm_bits;
    uint32_t size_bytes;
    double ctime;
    double mtime;
    uint32_t direct_blocks[DIRECT_LIMIT];
    int32_t indirect_block;
    int32_t double_indirect;
} Inode;

/* Directory Entry */
typedef struct {
    char name[MAX_NAME_LEN];
    char path[MAX_PATH_LEN];
    char entry_type[8]; /* "file" or "dir" */
    uint32_t target;
    uint32_t parent;
    uint32_t size_bytes;
    double mtime;
    uint32_t perm_bits;
    uint32_t owner_uid;
    bool active;
} DirEntry;

/* Journal Record */
typedef enum {
    JOURNAL_PENDING = 0,
    JOURNAL_COMMITTED = 1,
    JOURNAL_ROLLED_BACK = 2
} JournalStatus;

typedef struct {
    uint32_t txn_id;
    char op_type[16];
    char target[MAX_PATH_LEN];
    JournalStatus status;
    double timestamp;
} JournalRecord;

/* Version Entry */
typedef struct {
    uint32_t version_id;
    char file_path[MAX_PATH_LEN];
    double timestamp;
    uint32_t block_map[128];
    uint32_t block_count;
} VersionEntry;

/* User */
typedef struct {
    uint32_t uid;
    char username[32];
    uint8_t password_hash[32];
    uint8_t salt[16];
    char role[16]; /* "admin", "standard", "guest" */
    bool active;
} User;

/* Session */
typedef struct {
    char token[64];
    uint32_t uid;
    double created_at;
    double expires_at;
    bool active;
} Session;

/* Quota Record */
typedef struct {
    uint32_t uid;
    uint32_t limit_bytes;
    uint32_t used_bytes;
} QuotaRecord;

/* Helper Time */
double get_current_time_sec(void);

#endif /* SMARTFS_COMMON_H */
