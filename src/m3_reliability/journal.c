#include "m3_reliability.h"
#include "event_bus.h"

#ifdef _WIN32
#include <io.h>
#define fsync _commit
#else
#include <unistd.h>
#endif

static char g_journal_path[MAX_PATH_LEN] = "journal.log";
static uint32_t g_next_txn_id = 1;

void journal_init(const char *path) {
    if (path) strncpy(g_journal_path, path, MAX_PATH_LEN);

    JournalRecord records[1024];
    uint32_t count = 0;
    scan_journal(records, &count);
    if (count > 0) {
        g_next_txn_id = records[count - 1].txn_id + 1;
    } else {
        g_next_txn_id = 1;
    }
}

static void append_record(const JournalRecord *r) {
    FILE *fp = fopen(g_journal_path, "ab");
    if (!fp) return;

    fwrite(r, sizeof(JournalRecord), 1, fp);
    fflush(fp);
    fsync(fileno(fp)); /* Synchronous durable flush! */
    fclose(fp);
}

uint32_t journal_write_intent(const char *op_type, const char *target) {
    uint32_t txn_id = g_next_txn_id++;

    JournalRecord r;
    memset(&r, 0, sizeof(JournalRecord));
    r.txn_id = txn_id;
    strncpy(r.op_type, op_type, 16);
    strncpy(r.target, target, MAX_PATH_LEN);
    r.status = JOURNAL_PENDING;
    r.timestamp = get_current_time_sec();

    append_record(&r);

    char json[256];
    snprintf(json, sizeof(json),
             "{\"txn_id\":%u, \"op_type\":\"%s\", \"target\":\"%s\", \"status\":\"PENDING\"}",
             txn_id, op_type, target);
    emit_metric("journal_event", json);
    return txn_id;
}

void journal_commit(uint32_t txn_id) {
    JournalRecord r;
    memset(&r, 0, sizeof(JournalRecord));
    r.txn_id = txn_id;
    strncpy(r.op_type, "COMMIT", 16);
    snprintf(r.target, MAX_PATH_LEN, "txn_%u", txn_id);
    r.status = JOURNAL_COMMITTED;
    r.timestamp = get_current_time_sec();

    append_record(&r);

    char json[256];
    snprintf(json, sizeof(json),
             "{\"txn_id\":%u, \"op_type\":\"COMMIT\", \"target\":\"txn_%u\", \"status\":\"COMMITTED\"}",
             txn_id, txn_id);
    emit_metric("journal_event", json);
}

void journal_rollback(uint32_t txn_id) {
    JournalRecord r;
    memset(&r, 0, sizeof(JournalRecord));
    r.txn_id = txn_id;
    strncpy(r.op_type, "ROLLBACK", 16);
    snprintf(r.target, MAX_PATH_LEN, "txn_%u", txn_id);
    r.status = JOURNAL_ROLLED_BACK;
    r.timestamp = get_current_time_sec();

    append_record(&r);

    char json[256];
    snprintf(json, sizeof(json),
             "{\"txn_id\":%u, \"op_type\":\"ROLLBACK\", \"target\":\"txn_%u\", \"status\":\"ROLLED_BACK\"}",
             txn_id, txn_id);
    emit_metric("journal_event", json);
}

int scan_journal(JournalRecord *out_records, uint32_t *out_count) {
    FILE *fp = fopen(g_journal_path, "rb");
    if (!fp) {
        *out_count = 0;
        return SMARTFS_OK;
    }

    uint32_t count = 0;
    while (fread(&out_records[count], sizeof(JournalRecord), 1, fp) == 1) {
        count++;
    }
    fclose(fp);
    *out_count = count;
    return SMARTFS_OK;
}
