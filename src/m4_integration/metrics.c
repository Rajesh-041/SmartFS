#include "m4_integration.h"
#include "event_bus.h"
#include "m1_storage.h"
#include "m3_reliability.h"

static char g_last_event_json[1024] = "{}";

static void on_metric_event(const char *event_type, const char *payload_json) {
    snprintf(g_last_event_json, sizeof(g_last_event_json),
             "{\"event\":\"%s\", \"data\":%s}", event_type, payload_json);
}

void metrics_init(void) {
    event_bus_subscribe("*", on_metric_event);
}

void metrics_get_json(char *out_json, uint32_t max_len) {
    uint32_t used_b = g_superblock.total_blocks - g_superblock.free_blocks;
    double hit_ratio = cache_get_hit_ratio();
    double frag = calculate_fragmentation(NULL);

    snprintf(out_json, max_len,
             "{\"disk_usage\":{\"used_blocks\":%u, \"free_blocks\":%u, \"total_blocks\":%u}, "
             "\"cache_hit_ratio\":%.4f, \"fragmentation_pct\":%.2f, \"last_event\":%s}",
             used_b, g_superblock.free_blocks, g_superblock.total_blocks,
             hit_ratio, frag, g_last_event_json);
}
