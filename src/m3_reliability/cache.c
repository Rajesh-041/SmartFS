#include "m3_reliability.h"
#include "event_bus.h"

typedef struct CacheNode {
    uint32_t block_id;
    uint8_t data[BLOCK_SIZE];
    struct CacheNode *prev;
    struct CacheNode *next;
} CacheNode;

static CacheNode *g_cache_head = NULL;
static CacheNode *g_cache_tail = NULL;
static CacheNode *g_hash_map[1024]; /* Block ID % 1024 -> node */
static uint32_t g_cache_capacity = CACHE_CAPACITY;
static uint32_t g_cache_size = 0;

static uint32_t g_hits = 0;
static uint32_t g_misses = 0;

static void add_to_head(CacheNode *node) {
    node->next = g_cache_head->next;
    node->prev = g_cache_head;
    g_cache_head->next->prev = node;
    g_cache_head->next = node;
}

static void remove_node(CacheNode *node) {
    node->prev->next = node->next;
    node->next->prev = node->prev;
}

static void move_to_head(CacheNode *node) {
    remove_node(node);
    add_to_head(node);
}

void cache_init(uint32_t capacity) {
    g_cache_capacity = capacity;
    g_cache_size = 0;
    g_hits = 0;
    g_misses = 0;

    memset(g_hash_map, 0, sizeof(g_hash_map));

    g_cache_head = (CacheNode*)malloc(sizeof(CacheNode));
    g_cache_tail = (CacheNode*)malloc(sizeof(CacheNode));
    g_cache_head->next = g_cache_tail;
    g_cache_head->prev = NULL;
    g_cache_tail->prev = g_cache_head;
    g_cache_tail->next = NULL;
}

bool cache_get(uint32_t block_id, uint8_t *out_buffer) {
    uint32_t idx = block_id % 1024;
    CacheNode *curr = g_hash_map[idx];
    while (curr) {
        if (curr->block_id == block_id) {
            move_to_head(curr);
            memcpy(out_buffer, curr->data, BLOCK_SIZE);
            g_hits++;
            char json[128];
            snprintf(json, sizeof(json), "{\"block_id\":%u, \"hit_ratio\":%.4f}", block_id, cache_get_hit_ratio());
            emit_metric("cache_hit", json);
            return true;
        }
        curr = curr->next;
    }

    g_misses++;
    char json[128];
    snprintf(json, sizeof(json), "{\"block_id\":%u, \"hit_ratio\":%.4f}", block_id, cache_get_hit_ratio());
    emit_metric("cache_miss", json);
    return false;
}

void cache_put(uint32_t block_id, const uint8_t *buffer) {
    uint32_t idx = block_id % 1024;
    CacheNode *curr = g_hash_map[idx];
    while (curr) {
        if (curr->block_id == block_id) {
            memcpy(curr->data, buffer, BLOCK_SIZE);
            move_to_head(curr);
            return;
        }
        curr = curr->next;
    }

    if (g_cache_size >= g_cache_capacity) {
        /* Evict tail */
        CacheNode *tail_node = g_cache_tail->prev;
        if (tail_node && tail_node != g_cache_head) {
            remove_node(tail_node);
            uint32_t t_idx = tail_node->block_id % 1024;
            if (g_hash_map[t_idx] == tail_node) g_hash_map[t_idx] = tail_node->next;
            free(tail_node);
            g_cache_size--;
        }
    }

    CacheNode *new_node = (CacheNode*)malloc(sizeof(CacheNode));
    new_node->block_id = block_id;
    memcpy(new_node->data, buffer, BLOCK_SIZE);
    add_to_head(new_node);

    g_hash_map[idx] = new_node;
    g_cache_size++;
}

void cache_invalidate(uint32_t block_id) {
    uint32_t idx = block_id % 1024;
    CacheNode *curr = g_hash_map[idx];
    while (curr) {
        if (curr->block_id == block_id) {
            remove_node(curr);
            g_hash_map[idx] = curr->next;
            free(curr);
            g_cache_size--;
            return;
        }
        curr = curr->next;
    }
}

double cache_get_hit_ratio(void) {
    uint32_t total = g_hits + g_misses;
    if (total == 0) return 0.0;
    return (double)g_hits / total;
}
