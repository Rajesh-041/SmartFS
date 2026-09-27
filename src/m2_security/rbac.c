#include "m2_security.h"
#include "event_bus.h"

bool check_rbac(const char *role, const char *operation, uint32_t uid) {
    bool allowed = false;

    if (strcmp(role, "admin") == 0) {
        allowed = true;
    } else if (strcmp(role, "standard") == 0) {
        if (strcmp(operation, "admin") != 0) allowed = true;
    } else if (strcmp(role, "guest") == 0) {
        if (strcmp(operation, "read") == 0) allowed = true;
    }

    char json[128];
    snprintf(json, sizeof(json), "{\"uid\":%u, \"role\":\"%s\", \"op\":\"%s\", \"allowed\":%s}",
             uid, role, operation, allowed ? "true" : "false");
    emit_metric("rbac_checked", json);
    return allowed;
}
