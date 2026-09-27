#include "m2_security.h"
#include "event_bus.h"

void log_access_attempt(uint32_t uid, const char *op, const char *target, const char *result) {
    char json[256];
    snprintf(json, sizeof(json),
             "{\"uid\":%u, \"op\":\"%s\", \"target\":\"%s\", \"result\":\"%s\", \"timestamp\":%.2f}",
             uid, op, target, result, get_current_time_sec());
    emit_metric("access_logged", json);
}
