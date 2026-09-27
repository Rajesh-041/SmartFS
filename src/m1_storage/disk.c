#include "m1_storage.h"

static FILE *g_disk_fp = NULL;
static char g_disk_path[MAX_PATH_LEN] = {0};

int disk_open(const char *path, bool create, uint32_t size_bytes) {
    if (g_disk_fp) {
        fclose(g_disk_fp);
        g_disk_fp = NULL;
    }

    strncpy(g_disk_path, path, MAX_PATH_LEN);

    if (create) {
        g_disk_fp = fopen(path, "wb+");
        if (!g_disk_fp) return ERR_CORRUPT_DISK;

        /* Create file of size_bytes by seeking to size-1 and writing a byte */
        if (fseek(g_disk_fp, size_bytes - 1, SEEK_SET) != 0) {
            fclose(g_disk_fp);
            g_disk_fp = NULL;
            return ERR_INVALID_CONFIG;
        }
        fputc(0, g_disk_fp);
        fflush(g_disk_fp);
    } else {
        g_disk_fp = fopen(path, "rb+");
        if (!g_disk_fp) return ERR_CORRUPT_DISK;
    }

    return SMARTFS_OK;
}

void disk_close(void) {
    if (g_disk_fp) {
        fflush(g_disk_fp);
        fclose(g_disk_fp);
        g_disk_fp = NULL;
    }
}

int disk_read_block(uint32_t block_id, uint8_t *buffer) {
    if (!g_disk_fp || block_id >= TOTAL_BLOCKS) return ERR_CORRUPT_DISK;
    long offset = (long)block_id * BLOCK_SIZE;
    if (fseek(g_disk_fp, offset, SEEK_SET) != 0) return ERR_CORRUPT_DISK;

    memset(buffer, 0, BLOCK_SIZE);
    size_t read_bytes = fread(buffer, 1, BLOCK_SIZE, g_disk_fp);
    (void)read_bytes;
    return SMARTFS_OK;
}

int disk_write_block(uint32_t block_id, const uint8_t *buffer) {
    if (!g_disk_fp || block_id >= TOTAL_BLOCKS) return ERR_CORRUPT_DISK;
    long offset = (long)block_id * BLOCK_SIZE;
    if (fseek(g_disk_fp, offset, SEEK_SET) != 0) return ERR_CORRUPT_DISK;

    if (fwrite(buffer, 1, BLOCK_SIZE, g_disk_fp) != BLOCK_SIZE) return ERR_CORRUPT_DISK;
    fflush(g_disk_fp);
    return SMARTFS_OK;
}
