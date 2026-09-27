#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "common.h"
#include "m1_storage.h"
#include "m2_security.h"
#include "m3_reliability.h"
#include "m4_integration.h"

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
typedef int socklen_t;
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#define closesocket close
#endif

#define PORT 5000

static char g_index_html[65536] = {0};

static void load_index_html(void) {
    FILE *fp = fopen("dashboard/templates/index.html", "r");
    if (!fp) fp = fopen("index.html", "r");
    if (fp) {
        size_t r = fread(g_index_html, 1, sizeof(g_index_html) - 1, fp);
        g_index_html[r] = 0;
        fclose(fp);
    } else {
        strcpy(g_index_html, "<html><body><h1>SmartFS Dashboard Server (C)</h1></body></html>");
    }
}

int main(int argc, char *argv[]) {
    (void)argc; (void)argv;
#ifdef _WIN32
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
#endif

    handle_boot("disk.img");
    load_index_html();

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        printf("[ERROR] Failed to create socket\n");
        return 1;
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));

    struct sockaddr_in address;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(PORT);

    if (bind(server_fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        printf("[ERROR] Bind failed on port %d\n", PORT);
        return 1;
    }

    if (listen(server_fd, 10) < 0) {
        printf("[ERROR] Listen failed\n");
        return 1;
    }

    printf("=================================================================\n");
    printf(" SmartFS C Dashboard Server running at http://localhost:%d\n", PORT);
    printf("=================================================================\n");

    while (1) {
        struct sockaddr_in client_addr;
        socklen_t addrlen = sizeof(client_addr);
        int client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &addrlen);
        if (client_fd < 0) continue;

        char req_buf[2048] = {0};
        recv(client_fd, req_buf, sizeof(req_buf) - 1, 0);

        if (strstr(req_buf, "GET /api/metrics") != NULL) {
            char json_buf[4096];
            metrics_get_json(json_buf, sizeof(json_buf));

            char resp[8192];
            snprintf(resp, sizeof(resp),
                     "HTTP/1.1 200 OK\r\n"
                     "Content-Type: application/json\r\n"
                     "Access-Control-Allow-Origin: *\r\n"
                     "Content-Length: %u\r\n\r\n%s",
                     (unsigned int)strlen(json_buf), json_buf);
            send(client_fd, resp, (int)strlen(resp), 0);
        } else if (strstr(req_buf, "POST /api/defrag") != NULL) {
            defragment(NULL);
            const char *res_str = "{\"status\":\"success\",\"message\":\"Defragmentation completed\"}";
            char resp[1024];
            snprintf(resp, sizeof(resp),
                     "HTTP/1.1 200 OK\r\n"
                     "Content-Type: application/json\r\n"
                     "Content-Length: %u\r\n\r\n%s",
                     (unsigned int)strlen(res_str), res_str);
            send(client_fd, resp, (int)strlen(resp), 0);
        } else if (strstr(req_buf, "POST /api/benchmark") != NULL) {
            char report[2048];
            run_benchmark("mixed", 15, report, sizeof(report));
            char resp[4096];
            snprintf(resp, sizeof(resp),
                     "HTTP/1.1 200 OK\r\n"
                     "Content-Type: application/json\r\n"
                     "Content-Length: %u\r\n\r\n{\"results\":[], \"report\":\"%s\"}",
                     (unsigned int)(strlen(report) + 26), report);
            send(client_fd, resp, (int)strlen(resp), 0);
        } else {
            char resp[65536 + 512];
            snprintf(resp, sizeof(resp),
                     "HTTP/1.1 200 OK\r\n"
                     "Content-Type: text/html\r\n"
                     "Content-Length: %u\r\n\r\n%s",
                     (unsigned int)strlen(g_index_html), g_index_html);
            send(client_fd, resp, (int)strlen(resp), 0);
        }

        closesocket(client_fd);
    }

    closesocket(server_fd);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
