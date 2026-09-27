#include "m1_storage.h"
#include "event_bus.h"

Superblock g_superblock;
FreeBitmap g_bitmap = {0, NULL};
FatTable g_fat_table = {0, NULL};
DirEntry g_directories[MAX_DIR_ENTRIES];
uint32_t g_dir_count = 0;
bool g_disk_mounted = false;

static Inode g_inodes[128];
static uint32_t g_inode_count = 0;

static void save_metadata(void) {
    if (!g_disk_mounted) return;

    uint8_t block_buf[BLOCK_SIZE];

    /* Block 0: Superblock */
    memset(block_buf, 0, BLOCK_SIZE);
    memcpy(block_buf, &g_superblock, sizeof(Superblock));
    disk_write_block(0, block_buf);

    /* Block 1: Bitmap */
    memset(block_buf, 0, BLOCK_SIZE);
    uint32_t bm_bytes = (g_superblock.total_blocks + 7) / 8;
    if (bm_bytes > BLOCK_SIZE) bm_bytes = BLOCK_SIZE;
    memcpy(block_buf, g_bitmap.bits, bm_bytes);
    disk_write_block(1, block_buf);

    /* Block 2: FAT Table */
    memset(block_buf, 0, BLOCK_SIZE);
    uint32_t fat_bytes = g_superblock.total_blocks * sizeof(int32_t);
    if (fat_bytes > BLOCK_SIZE) fat_bytes = BLOCK_SIZE;
    memcpy(block_buf, g_fat_table.entries, fat_bytes);
    disk_write_block(2, block_buf);

    /* Block 3: Inodes */
    memset(block_buf, 0, BLOCK_SIZE);
    uint32_t inode_bytes = sizeof(g_inodes);
    if (inode_bytes > BLOCK_SIZE) inode_bytes = BLOCK_SIZE;
    memcpy(block_buf, g_inodes, inode_bytes);
    disk_write_block(3, block_buf);

    /* Block 4: Directory Table */
    memset(block_buf, 0, BLOCK_SIZE);
    uint32_t dir_bytes = sizeof(g_directories);
    if (dir_bytes > BLOCK_SIZE) dir_bytes = BLOCK_SIZE;
    memcpy(block_buf, g_directories, dir_bytes);
    disk_write_block(4, block_buf);
}

static int load_metadata(void) {
    uint8_t block_buf[BLOCK_SIZE];

    /* Block 0 */
    disk_read_block(0, block_buf);
    Superblock sb;
    memcpy(&sb, block_buf, sizeof(Superblock));

    if (memcmp(sb.magic, MAGIC_BYTES, 4) != 0 || sb.total_blocks == 0 || sb.total_blocks > 1000000) {
        return ERR_CORRUPT_DISK;
    }

    g_superblock = sb;

    /* Block 1 */
    disk_read_block(1, block_buf);
    uint32_t bm_bytes = (g_superblock.total_blocks + 7) / 8;
    if (!g_bitmap.bits) g_bitmap.bits = (uint8_t*)malloc(bm_bytes);
    g_bitmap.total_blocks = g_superblock.total_blocks;
    memcpy(g_bitmap.bits, block_buf, bm_bytes);

    /* Block 2 */
    disk_read_block(2, block_buf);
    if (!g_fat_table.entries) g_fat_table.entries = (int32_t*)malloc(g_superblock.total_blocks * sizeof(int32_t));
    g_fat_table.total_blocks = g_superblock.total_blocks;
    memcpy(g_fat_table.entries, block_buf, g_superblock.total_blocks * sizeof(int32_t));

    /* Block 3 */
    disk_read_block(3, block_buf);
    memcpy(g_inodes, block_buf, sizeof(g_inodes));

    /* Block 4 */
    disk_read_block(4, block_buf);
    memcpy(g_directories, block_buf, sizeof(g_directories));

    g_dir_count = 0;
    for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
        if (g_directories[i].active) g_dir_count++;
    }
    return SMARTFS_OK;
}

static bool is_block_free(uint32_t b) {
    if (b >= g_superblock.total_blocks) return false;
    uint32_t byte_idx = b / 8;
    uint32_t bit_idx = b % 8;
    return (g_bitmap.bits[byte_idx] & (1 << bit_idx)) == 0;
}

static void mark_block(uint32_t b, bool allocated) {
    if (b >= g_superblock.total_blocks) return;
    uint32_t byte_idx = b / 8;
    uint32_t bit_idx = b % 8;
    if (allocated) {
        g_bitmap.bits[byte_idx] |= (1 << bit_idx);
    } else {
        g_bitmap.bits[byte_idx] &= ~(1 << bit_idx);
    }
}

int format_disk(const char *path, uint32_t size_bytes, uint32_t block_size, const char *mode) {
    if (size_bytes == 0 || size_bytes % block_size != 0) return ERR_INVALID_CONFIG;

    uint32_t total_b = size_bytes / block_size;
    memset(&g_superblock, 0, sizeof(Superblock));
    memcpy(g_superblock.magic, MAGIC_BYTES, 4);
    g_superblock.disk_size = size_bytes;
    g_superblock.block_size = block_size;
    g_superblock.total_blocks = total_b;
    g_superblock.free_blocks = total_b - RESERVED_METADATA_BLOCKS;
    strncpy(g_superblock.allocation_mode, mode, 8);
    g_superblock.fs_version = 1;

    uint32_t bm_bytes = (total_b + 7) / 8;
    if (g_bitmap.bits) free(g_bitmap.bits);
    g_bitmap.bits = (uint8_t*)calloc(1, bm_bytes);
    g_bitmap.total_blocks = total_b;

    /* Reserve metadata blocks 0..15 */
    for (uint32_t i = 0; i < RESERVED_METADATA_BLOCKS; i++) {
        mark_block(i, true);
    }

    if (g_fat_table.entries) free(g_fat_table.entries);
    g_fat_table.entries = (int32_t*)malloc(total_b * sizeof(int32_t));
    g_fat_table.total_blocks = total_b;
    for (uint32_t i = 0; i < total_b; i++) {
        g_fat_table.entries[i] = (i < RESERVED_METADATA_BLOCKS) ? FAT_EOF : FAT_FREE;
    }

    memset(g_inodes, 0, sizeof(g_inodes));
    memset(g_directories, 0, sizeof(g_directories));

    /* Root directory */
    g_directories[0].active = true;
    strncpy(g_directories[0].name, "/", MAX_NAME_LEN);
    strncpy(g_directories[0].path, "/", MAX_PATH_LEN);
    strncpy(g_directories[0].entry_type, "dir", 8);
    g_directories[0].perm_bits = 0755;
    g_directories[0].owner_uid = 0;
    g_dir_count = 1;

    int res = disk_open(path, true, size_bytes);
    if (res != SMARTFS_OK) return res;

    g_disk_mounted = true;
    save_metadata();
    return SMARTFS_OK;
}

int mount_disk(const char *path) {
    int res = disk_open(path, false, 0);
    if (res != SMARTFS_OK) return res;

    g_disk_mounted = true;
    res = load_metadata();
    if (res != SMARTFS_OK) {
        disk_close();
        g_disk_mounted = false;
        return res;
    }
    return SMARTFS_OK;
}

int allocate_block(uint32_t *block_id) {
    if (!g_disk_mounted) return ERR_CORRUPT_DISK;
    for (uint32_t i = RESERVED_METADATA_BLOCKS; i < g_superblock.total_blocks; i++) {
        if (is_block_free(i)) {
            mark_block(i, true);
            g_superblock.free_blocks--;
            save_metadata();
            *block_id = i;
            
            char metric[128];
            snprintf(metric, sizeof(metric), "{\"used_blocks\":%u, \"free_blocks\":%u}",
                     g_superblock.total_blocks - g_superblock.free_blocks, g_superblock.free_blocks);
            emit_metric("disk_usage_changed", metric);
            return SMARTFS_OK;
        }
    }
    return ERR_DISK_FULL;
}

int allocate_blocks(uint32_t n, const char *strategy, uint32_t *out_blocks) {
    if (n == 0) return SMARTFS_OK;
    if (g_superblock.free_blocks < n) return ERR_DISK_FULL;

    for (uint32_t i = 0; i < n; i++) {
        int res = allocate_block(&out_blocks[i]);
        if (res != SMARTFS_OK) return res;
    }
    return SMARTFS_OK;
}

void free_block(uint32_t block_id) {
    if (block_id < RESERVED_METADATA_BLOCKS || block_id >= g_superblock.total_blocks) return;
    if (!is_block_free(block_id)) {
        mark_block(block_id, false);
        g_superblock.free_blocks++;
        save_metadata();
    }
}

int fat_alloc_chain(uint32_t n_blocks, int32_t *out_start) {
    if (n_blocks == 0) { *out_start = FAT_EOF; return SMARTFS_OK; }
    uint32_t chain[1024];
    int res = allocate_blocks(n_blocks, "linked", chain);
    if (res != SMARTFS_OK) return res;

    for (uint32_t i = 0; i < n_blocks - 1; i++) {
        g_fat_table.entries[chain[i]] = chain[i + 1];
    }
    g_fat_table.entries[chain[n_blocks - 1]] = FAT_EOF;
    save_metadata();
    *out_start = (int32_t)chain[0];
    return SMARTFS_OK;
}

int fat_free_chain(int32_t start, uint32_t *out_freed, uint32_t *out_count) {
    uint32_t count = 0;
    int32_t curr = start;
    while (curr != FAT_EOF && curr != FAT_FREE && curr >= (int32_t)RESERVED_METADATA_BLOCKS) {
        uint32_t next = g_fat_table.entries[curr];
        free_block((uint32_t)curr);
        g_fat_table.entries[curr] = FAT_FREE;
        if (out_freed) out_freed[count] = (uint32_t)curr;
        count++;
        curr = next;
    }
    if (out_count) *out_count = count;
    save_metadata();
    return SMARTFS_OK;
}

int fat_get_chain(int32_t start, uint32_t *out_chain, uint32_t *out_count) {
    uint32_t count = 0;
    int32_t curr = start;
    while (curr != FAT_EOF && curr != FAT_FREE && curr >= 0 && curr < (int32_t)g_superblock.total_blocks) {
        out_chain[count++] = (uint32_t)curr;
        curr = g_fat_table.entries[curr];
    }
    *out_count = count;
    return SMARTFS_OK;
}

int inode_allocate(uint32_t owner_uid, uint32_t perm_bits, Inode *out_inode) {
    for (uint32_t i = 1; i < 128; i++) {
        if (g_inodes[i].inode_id == 0) {
            g_inodes[i].inode_id = i;
            g_inodes[i].owner_uid = owner_uid;
            g_inodes[i].perm_bits = perm_bits;
            g_inodes[i].ctime = get_current_time_sec();
            g_inodes[i].mtime = get_current_time_sec();
            save_metadata();
            if (out_inode) *out_inode = g_inodes[i];
            return SMARTFS_OK;
        }
    }
    return ERR_DISK_FULL;
}

int inode_grow(uint32_t inode_id, uint32_t n_blocks) {
    if (inode_id == 0 || inode_id >= 128) return ERR_ENOENT;
    Inode *in = &g_inodes[inode_id];

    uint32_t new_blocks[64];
    int res = allocate_blocks(n_blocks, "indexed", new_blocks);
    if (res != SMARTFS_OK) return res;

    for (uint32_t i = 0; i < n_blocks; i++) {
        if (in->size_bytes / BLOCK_SIZE < DIRECT_LIMIT) {
            in->direct_blocks[in->size_bytes / BLOCK_SIZE] = new_blocks[i];
            in->size_bytes += BLOCK_SIZE;
        }
    }
    in->mtime = get_current_time_sec();
    save_metadata();
    return SMARTFS_OK;
}

int inode_free(uint32_t inode_id) {
    if (inode_id == 0 || inode_id >= 128) return ERR_ENOENT;
    Inode *in = &g_inodes[inode_id];
    uint32_t num_b = in->size_bytes / BLOCK_SIZE;
    for (uint32_t i = 0; i < num_b && i < DIRECT_LIMIT; i++) {
        free_block(in->direct_blocks[i]);
    }
    memset(in, 0, sizeof(Inode));
    save_metadata();
    return SMARTFS_OK;
}

DirEntry* resolve_path(const char *path) {
    if (!path) return NULL;
    for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
        if (g_directories[i].active && strcmp(g_directories[i].path, path) == 0) {
            return &g_directories[i];
        }
    }
    return NULL;
}

int storage_mkdir(const char *path, uint32_t owner_uid, uint32_t perm_bits) {
    if (resolve_path(path) != NULL) return ERR_EEXIST;

    for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
        if (!g_directories[i].active) {
            g_directories[i].active = true;
            strncpy(g_directories[i].path, path, MAX_PATH_LEN);
            /* Extract base name */
            const char *slash = strrchr(path, '/');
            strncpy(g_directories[i].name, slash ? slash + 1 : path, MAX_NAME_LEN);
            strncpy(g_directories[i].entry_type, "dir", 8);
            g_directories[i].perm_bits = perm_bits;
            g_directories[i].owner_uid = owner_uid;
            g_directories[i].mtime = get_current_time_sec();
            g_dir_count++;
            save_metadata();
            return SMARTFS_OK;
        }
    }
    return ERR_DISK_FULL;
}

int storage_rmdir(const char *path) {
    DirEntry *entry = resolve_path(path);
    if (!entry) return ERR_ENOENT;
    if (strcmp(entry->entry_type, "dir") != 0) return ERR_ENOENT;

    /* Check empty */
    uint32_t prefix_len = strlen(path);
    for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
        if (g_directories[i].active && strcmp(g_directories[i].path, path) != 0) {
            if (strncmp(g_directories[i].path, path, prefix_len) == 0) {
                return ERR_ENOTEMPTY;
            }
        }
    }

    entry->active = false;
    g_dir_count--;
    save_metadata();
    return SMARTFS_OK;
}

int storage_list_dir(const char *path, DirEntry *out_entries, uint32_t *out_count) {
    uint32_t count = 0;
    uint32_t prefix_len = strlen(path);
    for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
        if (g_directories[i].active && strcmp(g_directories[i].path, path) != 0) {
            if (strncmp(g_directories[i].path, path, prefix_len) == 0) {
                out_entries[count++] = g_directories[i];
            }
        }
    }
    *out_count = count;
    return SMARTFS_OK;
}

int storage_create_file(const char *path, uint32_t owner_uid, uint32_t perm_bits) {
    if (resolve_path(path) != NULL) return ERR_EEXIST;

    for (uint32_t i = 0; i < MAX_DIR_ENTRIES; i++) {
        if (!g_directories[i].active) {
            g_directories[i].active = true;
            strncpy(g_directories[i].path, path, MAX_PATH_LEN);
            const char *slash = strrchr(path, '/');
            strncpy(g_directories[i].name, slash ? slash + 1 : path, MAX_NAME_LEN);
            strncpy(g_directories[i].entry_type, "file", 8);
            g_directories[i].perm_bits = perm_bits;
            g_directories[i].owner_uid = owner_uid;
            g_directories[i].size_bytes = 0;
            g_directories[i].target = FAT_EOF;
            g_directories[i].mtime = get_current_time_sec();
            g_dir_count++;
            save_metadata();
            return SMARTFS_OK;
        }
    }
    return ERR_DISK_FULL;
}

int storage_get_file_blocks(const char *path, uint32_t *out_blocks, uint32_t *out_count) {
    DirEntry *entry = resolve_path(path);
    if (!entry) return ERR_ENOENT;

    if (strcmp(g_superblock.allocation_mode, "FAT") == 0) {
        return fat_get_chain(entry->target, out_blocks, out_count);
    } else {
        Inode *in = &g_inodes[entry->target];
        uint32_t count = in->size_bytes / BLOCK_SIZE;
        for (uint32_t i = 0; i < count; i++) out_blocks[i] = in->direct_blocks[i];
        *out_count = count;
        return SMARTFS_OK;
    }
}

int storage_write_file_blocks(const char *path, const uint8_t *data, uint32_t size_bytes) {
    DirEntry *entry = resolve_path(path);
    if (!entry) return ERR_ENOENT;

    uint32_t n_blocks = (size_bytes + BLOCK_SIZE - 1) / BLOCK_SIZE;
    if (n_blocks == 0) n_blocks = 1;

    uint32_t alloc_blocks[256];
    int res = allocate_blocks(n_blocks, "linked", alloc_blocks);
    if (res != SMARTFS_OK) return res;

    for (uint32_t i = 0; i < n_blocks; i++) {
        uint8_t buf[BLOCK_SIZE];
        memset(buf, 0, BLOCK_SIZE);
        uint32_t offset = i * BLOCK_SIZE;
        uint32_t len = (offset + BLOCK_SIZE <= size_bytes) ? BLOCK_SIZE : (size_bytes - offset);
        memcpy(buf, data + offset, len);
        disk_write_block(alloc_blocks[i], buf);
    }

    if (strcmp(g_superblock.allocation_mode, "FAT") == 0) {
        if (entry->target != FAT_EOF && entry->target != FAT_FREE) {
            fat_free_chain(entry->target, NULL, NULL);
        }
        for (uint32_t i = 0; i < n_blocks - 1; i++) {
            g_fat_table.entries[alloc_blocks[i]] = alloc_blocks[i + 1];
        }
        g_fat_table.entries[alloc_blocks[n_blocks - 1]] = FAT_EOF;
        entry->target = alloc_blocks[0];
    }

    entry->size_bytes = size_bytes;
    entry->mtime = get_current_time_sec();
    save_metadata();
    return SMARTFS_OK;
}

int storage_read_file_blocks(const char *path, uint8_t *out_data, uint32_t *out_size) {
    DirEntry *entry = resolve_path(path);
    if (!entry) return ERR_ENOENT;

    uint32_t blocks[256];
    uint32_t count = 0;
    storage_get_file_blocks(path, blocks, &count);

    uint8_t buf[BLOCK_SIZE];
    uint32_t offset = 0;
    for (uint32_t i = 0; i < count; i++) {
        disk_read_block(blocks[i], buf);
        uint32_t len = (offset + BLOCK_SIZE <= entry->size_bytes) ? BLOCK_SIZE : (entry->size_bytes - offset);
        memcpy(out_data + offset, buf, len);
        offset += len;
    }
    *out_size = entry->size_bytes;
    return SMARTFS_OK;
}

int storage_delete_file(const char *path) {
    DirEntry *entry = resolve_path(path);
    if (!entry) return ERR_ENOENT;

    if (strcmp(g_superblock.allocation_mode, "FAT") == 0) {
        if (entry->target != FAT_EOF && entry->target != FAT_FREE) {
            fat_free_chain(entry->target, NULL, NULL);
        }
    } else {
        inode_free(entry->target);
    }

    entry->active = false;
    g_dir_count--;
    save_metadata();
    return SMARTFS_OK;
}
