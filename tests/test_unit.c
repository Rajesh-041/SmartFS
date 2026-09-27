#include <stdio.h>
#include <assert.h>
#include "common.h"
#include "m1_storage.h"
#include "m2_security.h"
#include "m3_reliability.h"
#include "m4_integration.h"

void test_m1_disk_and_allocator(void) {
    printf("[TEST] M1: Disk Format, Allocation and Directory Management...\n");
    int res = format_disk("test_unit_disk.img", 16777216, 4096, "FAT");
    assert(res == SMARTFS_OK);
    assert(g_superblock.total_blocks == 4096);

    uint32_t b_id = 0;
    res = allocate_block(&b_id);
    assert(res == SMARTFS_OK);
    assert(b_id >= RESERVED_METADATA_BLOCKS);

    res = storage_mkdir("/home", 1000, 0755);
    assert(res == SMARTFS_OK);

    DirEntry *e = resolve_path("/home");
    assert(e != NULL);
    assert(strcmp(e->name, "home") == 0);

    res = storage_create_file("/home/file.txt", 1000, 0644);
    assert(res == SMARTFS_OK);

    uint8_t payload[] = "Hello C SmartFS";
    res = storage_write_file_blocks("/home/file.txt", payload, sizeof(payload));
    assert(res == SMARTFS_OK);

    uint8_t readback[128];
    uint32_t read_sz = 0;
    res = storage_read_file_blocks("/home/file.txt", readback, &read_sz);
    assert(res == SMARTFS_OK);
    assert(read_sz == sizeof(payload));
    assert(memcmp(payload, readback, read_sz) == 0);

    printf("  -> M1 Storage Engine Unit Tests PASSED.\n");
}

void test_m2_security(void) {
    printf("[TEST] M2: Auth, RBAC, Permissions and Encryption...\n");
    auth_init();

    User u;
    int res = register_user("charlie", "pass123", "standard", &u);
    assert(res == SMARTFS_OK);

    Session s;
    res = authenticate("charlie", "pass123", &s);
    assert(res == SMARTFS_OK);

    res = authenticate("charlie", "wrongpass", &s);
    assert(res == ERR_EAUTHFAILED);

    assert(check_rbac("admin", "admin", 1000) == true);
    assert(check_rbac("standard", "admin", 1001) == false);

    uint8_t key[32];
    generate_file_key(1001, 5, key);

    uint8_t plain[] = "Encrypted Secret C Payload";
    uint8_t cipher[256];
    uint32_t cipher_len = 0;
    res = encrypt_data(plain, sizeof(plain), key, cipher, &cipher_len);
    assert(res == SMARTFS_OK);

    uint8_t decrypted[256];
    uint32_t dec_len = 0;
    res = decrypt_data(cipher, cipher_len, key, decrypted, &dec_len);
    assert(res == SMARTFS_OK);
    assert(memcmp(plain, decrypted, dec_len) == 0);

    printf("  -> M2 Security & Access Control Unit Tests PASSED.\n");
}

void test_m3_reliability(void) {
    printf("[TEST] M3: WAL Journal, Cache and Compression...\n");
    cache_init(4);

    uint8_t b_data[BLOCK_SIZE] = "Cached Block Data";
    cache_put(10, b_data);

    uint8_t out_b[BLOCK_SIZE];
    bool hit = cache_get(10, out_b);
    assert(hit == true);
    assert(memcmp(b_data, out_b, BLOCK_SIZE) == 0);

    uint8_t src[] = "AAAAABBBBBCCCCCDDDDD";
    uint8_t comp[128];
    uint32_t comp_len = 0;
    compress_block(src, sizeof(src), comp, &comp_len);
    assert(comp_len < sizeof(src));

    uint8_t decomp[128];
    uint32_t decomp_len = 0;
    decompress_block(comp, comp_len, decomp, &decomp_len);
    assert(memcmp(src, decomp, sizeof(src)) == 0);

    printf("  -> M3 Reliability Unit Tests PASSED.\n");
}

int main(void) {
    printf("=================================================================\n");
    printf("        SmartFS C Unit Test Suite\n");
    printf("=================================================================\n");
    test_m1_disk_and_allocator();
    test_m2_security();
    test_m3_reliability();
    printf("=================================================================\n");
    printf("[ALL UNIT TESTS PASSED SUCCESSFULLY]\n");
    return 0;
}
