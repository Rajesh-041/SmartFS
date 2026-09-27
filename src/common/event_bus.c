#include "event_bus.h"
#include <stdio.h>
#include <time.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <sys/time.h>
#endif

double get_current_time_sec(void) {
#ifdef _WIN32
    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    ULARGE_INTEGER uli;
    uli.LowPart = ft.dwLowDateTime;
    uli.HighPart = ft.dwHighDateTime;
    return (double)(uli.QuadPart - 116444736000000000ULL) / 10000000.0;
#else
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec + (tv.tv_usec / 1000000.0);
#endif
}

#define MAX_HANDLERS 32

typedef struct {
    char event_type[64];
    EventHandlerFn handler;
} EventSubscription;

static EventSubscription g_subscribers[MAX_HANDLERS];
static uint32_t g_subscriber_count = 0;

void event_bus_subscribe(const char *event_type, EventHandlerFn handler) {
    if (g_subscriber_count < MAX_HANDLERS && handler) {
        strncpy(g_subscribers[g_subscriber_count].event_type, event_type, 64);
        g_subscribers[g_subscriber_count].handler = handler;
        g_subscriber_count++;
    }
}

void emit_metric(const char *event_type, const char *payload_json) {
    for (uint32_t i = 0; i < g_subscriber_count; i++) {
        if (strcmp(g_subscribers[i].event_type, "*") == 0 ||
            strcmp(g_subscribers[i].event_type, event_type) == 0) {
            if (g_subscribers[i].handler) {
                g_subscribers[i].handler(event_type, payload_json);
            }
        }
    }
}
