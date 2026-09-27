CC = gcc
CFLAGS = -Wall -Wextra -std=c99 -Iinclude
LIBS = -lws2_32

COMMON_SRCS = src/common/event_bus.c \
              src/m1_storage/disk.c src/m1_storage/allocator.c src/m1_storage/defrag.c \
              src/m2_security/auth.c src/m2_security/rbac.c src/m2_security/permissions.c src/m2_security/crypto.c src/m2_security/audit.c \
              src/m3_reliability/journal.c src/m3_reliability/cache.c src/m3_reliability/compression.c src/m3_reliability/versioning.c src/m3_reliability/recovery.c \
              src/m4_integration/quota.c src/m4_integration/metrics.c src/m4_integration/facade.c src/m4_integration/benchmark.c

COMMON_OBJS = $(COMMON_SRCS:.c=.o)

TARGETS = smartfs.exe m1_cli.exe dashboard_server.exe test_unit.exe test_integration.exe test_crash.exe

all: $(TARGETS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

smartfs.exe: src/main.o $(COMMON_OBJS)
	$(CC) $(CFLAGS) $^ -o $@ $(LIBS)

m1_cli.exe: src/m1_storage/cli.o $(COMMON_OBJS)
	$(CC) $(CFLAGS) $^ -o $@ $(LIBS)

dashboard_server.exe: dashboard/server.o $(COMMON_OBJS)
	$(CC) $(CFLAGS) $^ -o $@ $(LIBS)

test_unit.exe: tests/test_unit.o $(COMMON_OBJS)
	$(CC) $(CFLAGS) $^ -o $@ $(LIBS)

test_integration.exe: tests/test_integration.o $(COMMON_OBJS)
	$(CC) $(CFLAGS) $^ -o $@ $(LIBS)

test_crash.exe: tests/test_crash_injection.o $(COMMON_OBJS)
	$(CC) $(CFLAGS) $^ -o $@ $(LIBS)

test: all
	./test_unit.exe
	./test_integration.exe
	./test_crash.exe

clean:
	rm -f src/*.o src/*/*.o dashboard/*.o tests/*.o $(TARGETS) *.img *.log

.PHONY: all test clean
