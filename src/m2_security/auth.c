#include "m2_security.h"

static User g_users[32];
static uint32_t g_user_count = 0;

static Session g_sessions[64];
static uint32_t g_session_count = 0;
static uint32_t g_next_uid = 1000;

void hash_password(const char *password, const uint8_t *salt, uint8_t *out_hash) {
    memset(out_hash, 0, 32);
    uint32_t pass_len = strlen(password);
    for (uint32_t i = 0; i < 32; i++) {
        out_hash[i] = (uint8_t)(password[i % pass_len] ^ salt[i % 16] ^ (i * 31));
    }
}

bool verify_password(const char *password, const uint8_t *stored_hash, const uint8_t *salt) {
    uint8_t computed[32];
    hash_password(password, salt, computed);
    return memcmp(computed, stored_hash, 32) == 0;
}

void auth_init(void) {
    memset(g_users, 0, sizeof(g_users));
    memset(g_sessions, 0, sizeof(g_sessions));
    g_user_count = 0;

    register_user("admin", "admin123", "admin", NULL);
    register_user("alice", "alice123", "standard", NULL);
    register_user("bob", "bob123", "standard", NULL);
    register_user("guest", "guest123", "guest", NULL);
}

int register_user(const char *username, const char *password, const char *role, User *out_user) {
    for (uint32_t i = 0; i < g_user_count; i++) {
        if (g_users[i].active && strcmp(g_users[i].username, username) == 0) {
            return ERR_EUSEREXISTS;
        }
    }

    if (g_user_count >= 32) return ERR_DISK_FULL;

    User *u = &g_users[g_user_count++];
    u->active = true;
    u->uid = g_next_uid++;
    strncpy(u->username, username, 32);
    strncpy(u->role, role, 16);
    for (int i = 0; i < 16; i++) u->salt[i] = (uint8_t)(rand() % 256);
    hash_password(password, u->salt, u->password_hash);

    if (out_user) *out_user = *u;
    return SMARTFS_OK;
}

int authenticate(const char *username, const char *password, Session *out_session) {
    User *user = NULL;
    for (uint32_t i = 0; i < g_user_count; i++) {
        if (g_users[i].active && strcmp(g_users[i].username, username) == 0) {
            user = &g_users[i];
            break;
        }
    }

    if (!user || !verify_password(password, user->password_hash, user->salt)) {
        log_access_attempt(0, "login", username, "FAILED");
        return ERR_EAUTHFAILED;
    }

    /* Create Session */
    Session *s = NULL;
    for (uint32_t i = 0; i < 64; i++) {
        if (!g_sessions[i].active) {
            s = &g_sessions[i];
            break;
        }
    }
    if (!s) s = &g_sessions[0];

    s->active = true;
    s->uid = user->uid;
    s->created_at = get_current_time_sec();
    s->expires_at = s->created_at + SESSION_TIMEOUT_SEC;
    snprintf(s->token, 64, "tok_%u_%ld", user->uid, (long)s->created_at);

    log_access_attempt(user->uid, "login", username, "SUCCESS");
    if (out_session) *out_session = *s;
    return SMARTFS_OK;
}

int validate_session(const char *token, Session *out_session) {
    if (!token) return ERR_ESESSIONINVALID;

    for (uint32_t i = 0; i < 64; i++) {
        if (g_sessions[i].active && strcmp(g_sessions[i].token, token) == 0) {
            if (get_current_time_sec() > g_sessions[i].expires_at) {
                g_sessions[i].active = false;
                return ERR_ESESSIONEXPIRED;
            }
            if (out_session) *out_session = g_sessions[i];
            return SMARTFS_OK;
        }
    }
    return ERR_ESESSIONINVALID;
}

void revoke_session(const char *token) {
    if (!token) return;
    for (uint32_t i = 0; i < 64; i++) {
        if (g_sessions[i].active && strcmp(g_sessions[i].token, token) == 0) {
            g_sessions[i].active = false;
            break;
        }
    }
}

User* get_user_by_id(uint32_t uid) {
    for (uint32_t i = 0; i < g_user_count; i++) {
        if (g_users[i].active && g_users[i].uid == uid) {
            return &g_users[i];
        }
    }
    return NULL;
}
