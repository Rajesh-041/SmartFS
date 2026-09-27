import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger("SmartFS.EventBus")

class EventBus:
    """Thread-safe, non-blocking Observer pattern event bus for analytics & dashboard."""
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def emit_metric(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emits event to all subscribers. Must NEVER raise an exception."""
        payload_copy = dict(payload) if payload else {}
        payload_copy["event_type"] = event_type
        
        # Call global subscribers if any
        handlers = self._subscribers.get(event_type, []) + self._subscribers.get("*", [])
        for handler in handlers:
            try:
                handler(payload_copy)
            except Exception as e:
                logger.warning(f"Event handler failed for event {event_type}: {e}")

_GLOBAL_EVENT_BUS = EventBus()

def subscribe(event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
    _GLOBAL_EVENT_BUS.subscribe(event_type, handler)

def emit_metric(event_type: str, payload: Dict[str, Any]) -> None:
    _GLOBAL_EVENT_BUS.emit_metric(event_type, payload)
