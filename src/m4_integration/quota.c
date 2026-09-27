#include "m4_integration.h"
#include "event_bus.h"

static QuotaRecord g_quotas[32];
static uint32_t g_quota_count = 0;
static uint32_t g_default_limit = DEFAULT_QUOTA_BYTES;

void quota_init(uint32_t default_limit) {
    g_default_limit = default_limit;
    memset(g_quotas, 0, sizeof(g_quotas));
    g_quota_count = 0;
}

QuotaRecord* quota_get(uint32_t uid) {
    for (uint32_t i = 0; i < g_quota_count; i++) {
        if (g_quotas[i].uid == uid) return &g_quotas[i];
    }
    if (g_quota_count < 32) {
        QuotaRecord *q = &g_quotas[g_quota_count++];
        q->uid = uid;
        q->limit_bytes = g_default_limit;
        q->used_bytes = 0;
        return q;
    }
    return &g_quotas[0];
}

bool quota_check(uint32_t uid, uint32_t incoming_bytes) {
    QuotaRecord *q = quota_get(uid);
    return (q->used_bytes + incoming_bytes) <= q->limit_bytes;
}

void quota_update(uint32_t uid, int32_t delta_bytes) {
    QuotaRecord *q = quota_get(uid);
    if (delta_bytes < 0 && (uint32_t)(-delta_bytes) > q->used_bytes) {
        q->used_bytes = 0;
    } else {
        q->used_bytes += delta_bytes;
    }

    char json[128];
    snprintf(json, sizeof(json), "{\"uid\":%u, \"used_bytes\":%u, \"limit_bytes\":%u}",
             uid, q->used_bytes, q->limit_bytes);
    emit_metric("quota_updated", json);
}
