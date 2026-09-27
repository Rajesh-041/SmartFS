#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "common.h"
#include "m1_storage.h"
#include "m2_security.h"
#include "m3_reliability.h"
#include "m4_integration.h"

static char g_token[64] = {0};
static char g_username[32] = "guest";
static char g_role[16] = "guest";

static void print_banner(void) {
    printf("=================================================================\n");
    printf("   SmartFS C — Secure & Intelligent File System Simulator (C99)\n");
    printf("=================================================================\n");
    printf(" Type 'help' for commands. Try 'login admin admin123'\n");
    printf("=================================================================\n\n");
}

int main(int argc, char *argv[]) {
    (void)argc; (void)argv;
    printf("[BOOT] Mounting Virtual Disk and running WAL Crash Recovery...\n");
    handle_boot("disk.img");
    printf("[OK] System clean and ready.\n\n");

    print_banner();

    char line[512];
    while (1) {
        printf("SmartFS-C (%s)> ", g_username);
        fflush(stdout);

        if (!fgets(line, sizeof(line), stdin)) break;
        line[strcspn(line, "\r\n")] = 0;
        if (strlen(line) == 0) continue;

        if (strcmp(line, "exit") == 0 || strcmp(line, "quit") == 0) {
            printf("Exiting SmartFS C Simulator. Goodbye!\n");
            break;
        }

        char cmd[32] = {0}, arg1[256] = {0}, arg2[256] = {0};
        int parsed = sscanf(line, "%31s %255s %255s", cmd, arg1, arg2);

        if (strcmp(cmd, "help") == 0) {
            printf("Available Commands:\n");
            printf("  login <user> <pass>      Log in (admin/admin123, alice/alice123)\n");
            printf("  logout                   End current session\n");
            printf("  mkdir <path>             Create directory\n");
            printf("  rmdir <path>             Remove empty directory\n");
            printf("  ls [path]                List directory contents\n");
            printf("  write <path> <content>   Write & encrypt file\n");
            printf("  read <path>              Read & decrypt file\n");
            printf("  delete <path>            Delete file\n");
            printf("  defrag [path]            Defragment file/disk\n");
            printf("  benchmark                Run FAT vs INODE benchmark\n");
            printf("  simulate-crash <stage>   Simulate crash during stage\n");
            printf("  restart / boot           Replay WAL crash recovery\n");
            printf("  status                   Display system status\n");
            printf("  exit                     Quit simulator\n\n");
        } else if (strcmp(cmd, "login") == 0) {
            if (parsed < 3) { printf("Usage: login <user> <pass>\n"); continue; }
            Session s;
            int res = authenticate(arg1, arg2, &s);
            if (res == SMARTFS_OK) {
                strncpy(g_token, s.token, 64);
                strncpy(g_username, arg1, 32);
                User *u = get_user_by_id(s.uid);
                if (u) strncpy(g_role, u->role, 16);
                printf("[OK] Logged in as '%s' (role=%s, token=%s...)\n", g_username, g_role, g_token);
            } else {
                printf("[ERROR] Authentication failed.\n");
            }
        } else if (strcmp(cmd, "logout") == 0) {
            revoke_session(g_token);
            memset(g_token, 0, sizeof(g_token));
            strcpy(g_username, "guest");
            strcpy(g_role, "guest");
            printf("[OK] Logged out.\n");
        } else if (strcmp(cmd, "mkdir") == 0) {
            int res = handle_mkdir_request(arg1, g_token);
            if (res == SMARTFS_OK) printf("[OK] Directory created: %s\n", arg1);
            else printf("[ERROR] mkdir failed: %d\n", res);
        } else if (strcmp(cmd, "rmdir") == 0) {
            int res = storage_rmdir(arg1);
            if (res == SMARTFS_OK) printf("[OK] Directory removed: %s\n", arg1);
            else printf("[ERROR] rmdir failed: %d\n", res);
        } else if (strcmp(cmd, "ls") == 0) {
            const char *p = (parsed >= 2) ? arg1 : "/";
            DirEntry entries[MAX_DIR_ENTRIES];
            uint32_t count = 0;
            int res = handle_list_request(p, entries, &count, g_token);
            if (res == SMARTFS_OK) {
                printf("Contents of %s (%u entries):\n", p, count);
                for (uint32_t i = 0; i < count; i++) {
                    printf("  %-6s %-20s %u bytes (perm: %o)\n",
                           entries[i].entry_type, entries[i].name, entries[i].size_bytes, entries[i].perm_bits);
                }
            } else {
                printf("[ERROR] ls failed: %d\n", res);
            }
        } else if (strcmp(cmd, "write") == 0) {
            if (parsed < 3) { printf("Usage: write <path> <content>\n"); continue; }
            int res = handle_write_request(arg1, (const uint8_t*)arg2, strlen(arg2), g_token, NULL);
            if (res >= 0) {
                printf("[JOURNAL] WRITE PENDING -> COMMITTED\n");
                printf("[OK] %d bytes written to '%s'.\n", res, arg1);
            } else {
                printf("[ERROR] Write failed with code %d\n", res);
            }
        } else if (strcmp(cmd, "read") == 0) {
            uint8_t out[65536];
            uint32_t out_size = 0;
            int res = handle_read_request(arg1, out, &out_size, g_token);
            if (res == SMARTFS_OK) {
                out[out_size] = 0;
                printf("%s\n", (char*)out);
            } else {
                printf("[ERROR] Read failed with code %d\n", res);
            }
        } else if (strcmp(cmd, "delete") == 0) {
            int res = handle_delete_request(arg1, g_token);
            if (res == SMARTFS_OK) printf("[OK] Deleted '%s'\n", arg1);
            else printf("[ERROR] Delete failed: %d\n", res);
        } else if (strcmp(cmd, "defrag") == 0) {
            const char *p = (parsed >= 2) ? arg1 : NULL;
            defragment(p);
            printf("[OK] Defragmentation completed for %s.\n", p ? p : "disk-wide");
        } else if (strcmp(cmd, "benchmark") == 0) {
            char report[2048];
            run_benchmark("mixed", 25, report, sizeof(report));
            printf("\n%s\n", report);
        } else if (strcmp(cmd, "simulate-crash") == 0) {
            printf("[SIMULATION] Injecting crash during stage '%s'...\n", arg1);
            uint8_t dummy[64] = "crash payload";
            int res = handle_write_request("/crash.txt", dummy, 13, g_token, arg1);
            if (res == ERR_SIMULATED_CRASH) {
                printf("[SIMULATED CRASH SUCCESSFUL] Process interrupted as expected.\n");
                printf("Run 'restart' or 'boot' to trigger WAL crash recovery replay.\n");
            }
        } else if (strcmp(cmd, "restart") == 0 || strcmp(cmd, "boot") == 0) {
            uint32_t rolled_back = 0, committed = 0, orphaned = 0;
            replay_journal(&rolled_back, &committed, &orphaned);
            printf("[RECOVERY] Rolled back: %u, Committed: %u, Reclaimed orphaned: %u.\n", rolled_back, committed, orphaned);
            printf("[OK] System clean, resuming normal operations.\n");
        } else if (strcmp(cmd, "status") == 0) {
            printf("System Status (C Engine):\n");
            printf("  Mode: %s\n", g_superblock.allocation_mode);
            printf("  Used Blocks: %u / %u\n", g_superblock.total_blocks - g_superblock.free_blocks, g_superblock.total_blocks);
            printf("  Cache Hit Ratio: %.1f%%\n", cache_get_hit_ratio() * 100.0);
            printf("  Fragmentation: %.2f%%\n", calculate_fragmentation(NULL));
            printf("  Active User: %s (%s)\n", g_username, g_role);
        } else {
            printf("[ERROR] Unknown command '%s'. Type 'help' for available commands.\n", cmd);
        }
    }
    return 0;
}
