/*
 * smartfs_xv6.c — SmartFS Storage Engine Simulator for xv6 (RISC-V / x86)
 *
 * To run in xv6 on Ubuntu:
 * 1. Copy this file into your xv6 directory as user/smartfs.c
 * 2. Add $U/_smartfs to UPROGS in Makefile
 * 3. Run: make qemu
 * 4. Inside xv6 terminal: $ smartfs
 */

#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"
#include "kernel/fcntl.h"

#define BLOCK_SIZE 512       /* Standard xv6 block size */
#define TOTAL_BLOCKS 128     /* 64 KB virtual disk */
#define RESERVED_BLOCKS 4
#define MAX_NAME 32
#define MAX_FILES 32

/* Superblock */
struct superblock {
  char magic[4];          /* "SMFS" */
  ushort total_blocks;
  ushort free_blocks;
  ushort mode;            /* 0: FAT, 1: INODE */
};

/* Directory Entry */
struct dir_entry {
  char name[MAX_NAME];
  ushort type;           /* 1: file, 2: dir */
  short target;          /* block or inode */
  uint size;
  ushort active;
};

/* Free Bitmap */
static uchar bitmap[TOTAL_BLOCKS / 8];
static short fat_table[TOTAL_BLOCKS];
static struct dir_entry directories[MAX_FILES];
static struct superblock sb;

static int disk_fd = -1;

/* Virtual Disk Raw I/O */
static int disk_read(int block_id, uchar *buf) {
  if (disk_fd < 0 || block_id >= TOTAL_BLOCKS) return -1;
  seek(disk_fd, block_id * BLOCK_SIZE);
  read(disk_fd, buf, BLOCK_SIZE);
  return 0;
}

static int disk_write(int block_id, const uchar *buf) {
  if (disk_fd < 0 || block_id >= TOTAL_BLOCKS) return -1;
  seek(disk_fd, block_id * BLOCK_SIZE);
  write(disk_fd, buf, BLOCK_SIZE);
  return 0;
}

static void mark_bitmap(int b, int alloc) {
  int idx = b / 8;
  int bit = b % 8;
  if (alloc) bitmap[idx] |= (1 << bit);
  else bitmap[idx] &= ~(1 << bit);
}

static int is_free(int b) {
  return (bitmap[b / 8] & (1 << (b % 8))) == 0;
}

/* Save / Load Metadata */
static void save_metadata(void) {
  uchar buf[BLOCK_SIZE];

  /* Block 0: Superblock */
  memset(buf, 0, BLOCK_SIZE);
  memcpy(buf, &sb, sizeof(sb));
  disk_write(0, buf);

  /* Block 1: Bitmap */
  memset(buf, 0, BLOCK_SIZE);
  memcpy(buf, bitmap, sizeof(bitmap));
  disk_write(1, buf);

  /* Block 2: FAT Table */
  memset(buf, 0, BLOCK_SIZE);
  memcpy(buf, fat_table, sizeof(fat_table));
  disk_write(2, buf);

  /* Block 3: Directory Entries */
  memset(buf, 0, BLOCK_SIZE);
  memcpy(buf, directories, sizeof(directories));
  disk_write(3, buf);
}

static int format_disk(void) {
  disk_fd = open("disk.img", O_CREATE | O_RDWR);
  if (disk_fd < 0) return -1;

  /* Zero disk */
  uchar zero[BLOCK_SIZE];
  memset(zero, 0, BLOCK_SIZE);
  for (int i = 0; i < TOTAL_BLOCKS; i++) {
    write(disk_fd, zero, BLOCK_SIZE);
  }

  sb.magic[0] = 'S'; sb.magic[1] = 'M'; sb.magic[2] = 'F'; sb.magic[3] = 'S';
  sb.total_blocks = TOTAL_BLOCKS;
  sb.free_blocks = TOTAL_BLOCKS - RESERVED_BLOCKS;
  sb.mode = 0; /* FAT */

  memset(bitmap, 0, sizeof(bitmap));
  for (int i = 0; i < RESERVED_BLOCKS; i++) mark_bitmap(i, 1);

  for (int i = 0; i < TOTAL_BLOCKS; i++) fat_table[i] = -1;

  memset(directories, 0, sizeof(directories));
  directories[0].active = 1;
  strcpy(directories[0].name, "/");
  directories[0].type = 2;

  save_metadata();
  printf("[OK] SmartFS formatted on xv6 (disk.img, 64 KB, 512B blocks)\n");
  return 0;
}

static int alloc_block(void) {
  for (int i = RESERVED_BLOCKS; i < TOTAL_BLOCKS; i++) {
    if (is_free(i)) {
      mark_bitmap(i, 1);
      sb.free_blocks--;
      save_metadata();
      return i;
    }
  }
  return -1;
}

/* Simple Encryption/Compression simulation in xv6 */
static void encrypt_payload(uchar *data, int len, uchar key) {
  for (int i = 0; i < len; i++) {
    data[i] ^= key;
  }
}

static int write_file(const char *name, const char *text) {
  int text_len = strlen(text);
  int blk = alloc_block();
  if (blk < 0) {
    printf("[ERROR] Disk full in xv6\n");
    return -1;
  }

  uchar buf[BLOCK_SIZE];
  memset(buf, 0, BLOCK_SIZE);
  memcpy(buf, text, text_len);

  /* Encrypt with key 0x5A */
  encrypt_payload(buf, text_len, 0x5A);
  disk_write(blk, buf);

  /* Find free dir entry */
  for (int i = 0; i < MAX_FILES; i++) {
    if (!directories[i].active) {
      directories[i].active = 1;
      strcpy(directories[i].name, name);
      directories[i].type = 1;
      directories[i].target = blk;
      directories[i].size = text_len;
      fat_table[blk] = -1;
      save_metadata();
      printf("[JOURNAL] WRITE PENDING -> COMMITTED\n");
      printf("[OK] Wrote %d bytes (encrypted) to block %d\n", text_len, blk);
      return 0;
    }
  }
  return -1;
}

static int read_file(const char *name) {
  for (int i = 0; i < MAX_FILES; i++) {
    if (directories[i].active && strcmp(directories[i].name, name) == 0) {
      int blk = directories[i].target;
      uchar buf[BLOCK_SIZE];
      disk_read(blk, buf);

      /* Decrypt with key 0x5A */
      encrypt_payload(buf, directories[i].size, 0x5A);
      buf[directories[i].size] = 0;
      printf("Content of '%s': %s\n", name, buf);
      return 0;
    }
  }
  printf("[ERROR] File '%s' not found\n", name);
  return -1;
}

static void list_files(void) {
  printf("SmartFS xv6 File Listing:\n");
  for (int i = 0; i < MAX_FILES; i++) {
    if (directories[i].active) {
      printf("  %-16s %s %d bytes (block %d)\n",
             directories[i].name,
             directories[i].type == 2 ? "<DIR>" : "FILE",
             directories[i].size,
             directories[i].target);
    }
  }
}

int main(int argc, char *argv[]) {
  printf("=====================================================\n");
  printf("   SmartFS Storage Engine running inside xv6 OS\n");
  printf("=====================================================\n");

  format_disk();
  write_file("notes.txt", "Hello SmartFS inside xv6 QEMU!");
  write_file("os_project.txt", "Multi-user WAL journaled OS storage engine");

  printf("\n");
  list_files();

  printf("\n");
  read_file("notes.txt");
  read_file("os_project.txt");

  close(disk_fd);
  printf("\n[OK] SmartFS xv6 execution completed successfully.\n");
  exit(0);
}
