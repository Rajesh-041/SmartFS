#include <stdio.h>
#include <assert.h>
#include "common.h"
#include "m1_storage.h"
#include "m2_security.h"
#include "m3_reliability.h"
#include "m4_integration.h"

int main(void) {
    printf("=================================================================\n");
    printf("        SmartFS C End-to-End Integration Test Suite\n");
    printf("=================================================================\n");
    fflush(stdout);

    remove("test_integ_disk.img");
    remove("journal.log");
    int res = handle_boot("test_integ_disk.img");
    printf("1. handle_boot res = %d\n", res); fflush(stdout);
    assert(res == SMARTFS_OK);

    Session s_alice;
    res = authenticate("alice", "alice123", &s_alice);
    printf("2. authenticate alice res = %d\n", res); fflush(stdout);
    assert(res == SMARTFS_OK);

    res = handle_mkdir_request("/home/alice", s_alice.token);
    printf("3. handle_mkdir_request res = %d\n", res); fflush(stdout);
    assert(res == SMARTFS_OK);

    uint8_t payload[] = "SmartFS C Integration Test Payload 123456789";
    int bytes_w = handle_write_request("/home/alice/notes.txt", payload, sizeof(payload), s_alice.token, NULL);
    printf("4. handle_write_request bytes_w = %d\n", bytes_w); fflush(stdout);
    assert(bytes_w == (int)sizeof(payload));

    uint8_t readback[512];
    uint32_t read_sz = 0;
    res = handle_read_request("/home/alice/notes.txt", readback, &read_sz, s_alice.token);
    printf("5. handle_read_request res = %d, read_sz = %u\n", res, read_sz); fflush(stdout);
    assert(res == SMARTFS_OK);
    assert(read_sz == sizeof(payload));
    assert(memcmp(payload, readback, read_sz) == 0);

    /* Test Quota Rejection */
    quota_init(50); /* Set small quota 50 bytes */
    uint8_t huge[500];
    memset(huge, 'X', sizeof(huge));
    res = handle_write_request("/home/alice/huge.txt", huge, sizeof(huge), s_alice.token, NULL);
    printf("6. handle_write_request huge res = %d\n", res); fflush(stdout);
    assert(res == ERR_QUOTA_EXCEEDED);

    /* Test Guest Write Denial */
    Session s_guest;
    authenticate("guest", "guest123", &s_guest);
    res = handle_write_request("/guest_file.txt", payload, sizeof(payload), s_guest.token, NULL);
    printf("7. handle_write_request guest res = %d\n", res); fflush(stdout);
    assert(res == ERR_PERMISSION_DENIED);

    printf("=================================================================\n");
    printf("[ALL INTEGRATION TESTS PASSED SUCCESSFULLY]\n");
    fflush(stdout);
    return 0;
}
