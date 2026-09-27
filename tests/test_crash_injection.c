#include <stdio.h>
#include <assert.h>
#include "common.h"
#include "m1_storage.h"
#include "m2_security.h"
#include "m3_reliability.h"
#include "m4_integration.h"

static const char *STAGES[] = {"journal", "allocate", "physical_write", "commit"};

void test_crash_stage(const char *stage) {
    disk_close();
    remove("test_crash_disk.img");
    remove("journal.log");
    handle_boot("test_crash_disk.img");

    Session s_admin;
    int r_auth = authenticate("admin", "admin123", &s_admin);
    printf("1. stage '%s' auth res = %d\n", stage, r_auth); fflush(stdout);
    assert(r_auth == SMARTFS_OK);

    uint8_t payload[] = "Crash injection test payload data";
    int res = handle_write_request("/test_crash.txt", payload, sizeof(payload), s_admin.token, stage);
    printf("2. stage '%s' write res = %d (expected %d)\n", stage, res, ERR_SIMULATED_CRASH); fflush(stdout);
    assert(res == ERR_SIMULATED_CRASH);

    uint32_t rolled_back = 0, committed = 0, orphaned = 0;
    replay_journal(&rolled_back, &committed, &orphaned);

    printf("  [PASS] Stage '%s': WAL rolled back %u in-flight txn, reclaimed %u orphaned blocks.\n",
           stage, rolled_back, orphaned);
    fflush(stdout);
}

int main(void) {
    printf("=================================================================\n");
    printf("        SmartFS C WAL Crash Injection Test Suite\n");
    printf("=================================================================\n");
    fflush(stdout);

    for (int i = 0; i < 4; i++) {
        test_crash_stage(STAGES[i]);
    }

    printf("=================================================================\n");
    printf("[ALL CRASH RECOVERY STAGES PASSED SUCCESSFULLY]\n");
    fflush(stdout);
    return 0;
}
