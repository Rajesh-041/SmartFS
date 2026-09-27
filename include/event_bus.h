#ifndef SMARTFS_EVENT_BUS_H
#define SMARTFS_EVENT_BUS_H

#include "common.h"

typedef void (*EventHandlerFn)(const char *event_type, const char *payload_json);

void event_bus_subscribe(const char *event_type, EventHandlerFn handler);
void emit_metric(const char *event_type, const char *payload_json);

#endif /* SMARTFS_EVENT_BUS_H */
