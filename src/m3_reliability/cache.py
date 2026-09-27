import threading
from typing import Optional, Dict
from src.common.event_bus import emit_metric

class Node:
    def __init__(self, block_id: int, data: bytes):
        self.block_id = block_id
        self.data = data
        self.prev: Optional["Node"] = None
        self.next: Optional["Node"] = None

class LRUCache:
    """O(1) LRU block cache implemented with a hash map and doubly-linked list."""
    def __init__(self, capacity: int = 64):
        self.capacity = capacity
        self.map: Dict[int, Node] = {}
        # Dummy sentinel nodes
        self.head = Node(0, b"")
        self.tail = Node(0, b"")
        self.head.next = self.tail
        self.tail.prev = self.head
        self.hits = 0
        self.misses = 0
        self._lock = threading.Lock()

    def _add_node_to_head(self, node: Node) -> None:
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node

    def _remove_node(self, node: Node) -> None:
        p = node.prev
        n = node.next
        if p:
            p.next = n
        if n:
            n.prev = p

    def _move_to_head(self, node: Node) -> None:
        self._remove_node(node)
        self._add_node_to_head(node)

    def _pop_tail(self) -> Optional[Node]:
        res = self.tail.prev
        if res and res != self.head:
            self._remove_node(res)
            return res
        return None

    def get(self, block_id: int) -> Optional[bytes]:
        with self._lock:
            if block_id in self.map:
                node = self.map[block_id]
                self._move_to_head(node)
                self.hits += 1
                emit_metric("cache_hit", {"block_id": block_id, "hit_ratio": self.hit_ratio})
                return node.data
            else:
                self.misses += 1
                emit_metric("cache_miss", {"block_id": block_id, "hit_ratio": self.hit_ratio})
                return None

    def put(self, block_id: int, data: bytes) -> None:
        with self._lock:
            if block_id in self.map:
                node = self.map[block_id]
                node.data = data
                self._move_to_head(node)
            else:
                new_node = Node(block_id, data)
                self.map[block_id] = new_node
                self._add_node_to_head(new_node)
                if len(self.map) > self.capacity:
                    tail_node = self._pop_tail()
                    if tail_node:
                        del self.map[tail_node.block_id]

    def invalidate(self, block_id: int) -> None:
        with self._lock:
            if block_id in self.map:
                node = self.map.pop(block_id)
                self._remove_node(node)

    def clear(self) -> None:
        with self._lock:
            self.map.clear()
            self.head.next = self.tail
            self.tail.prev = self.head
            self.hits = 0
            self.misses = 0

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return round(self.hits / total, 4)

GLOBAL_CACHE = LRUCache(capacity=64)
