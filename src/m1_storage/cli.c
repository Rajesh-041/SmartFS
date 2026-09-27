#include "m1_storage.h"

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Usage: m1_cli format [size_mb] [block_size] [fat|inode]\n");
        return 1;
    }

    if (strcmp(argv[1], "format") == 0) {
        uint32_t size_mb = (argc >= 3) ? atoi(argv[2]) : 64;
        uint32_t block_size = (argc >= 4) ? atoi(argv[3]) : 4096;
        const char *mode = (argc >= 5) ? argv[4] : "FAT";

        uint32_t size_bytes = size_mb * 1024 * 1024;
        int res = format_disk("disk.img", size_bytes, block_size, mode);
        if (res == SMARTFS_OK) {
            printf("[OK] Formatted disk.img (%u MB, %uB blocks, mode=%s)\n", size_mb, block_size, mode);
        } else {
            printf("[ERROR] Format failed with code %d\n", res);
        }
    }
    return 0;
}
