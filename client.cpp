#include <iostream>
#include <string>
#ifdef _WIN32
#  include <winsock2.h>
#  include <ws2tcpip.h>
#  include <windows.h>
#  pragma comment(lib, "ws2_32.lib")
#else
#  include <sys/socket.h>
#  include <netdb.h>
#  include <unistd.h>
#endif

int main(int argc, char* argv[]) {
    std::string host = "localhost";
    std::string port = "8000";
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

    SOCKET sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock == INVALID_SOCKET) {
        #ifdef _WIN32
        std::cerr << "socket failed: " << WSAGetLastError() << std::endl;
        #else
        perror("socket");
        #endif
        freeaddrinfo(res);
        #ifdef _WIN32
        WSACleanup();
        #endif
        return 1;
    }

    if (connect(sock, res->ai_addr, (int)res->ai_addrlen) == SOCKET_ERROR) {
        #ifdef _WIN32
        std::cerr << "connect failed: " << WSAGetLastError() << std::endl;
        closesocket(sock);
        WSACleanup();
        #else
        perror("connect");
        close(sock);
        #endif
        freeaddrinfo(res);
        return 1;
    }

    std::string body = "{\"client_id\":\"" + client_id + "\"}";
    std::string request;
    request += "POST /register HTTP/1.1\r\n";
    request += "Host: " + host + "\r\n";
    request += "Content-Type: application/json\r\n";
    request += "Content-Length: " + std::to_string(body.size()) + "\r\n";
    request += "\r\n";
    request += body;

    if (send(sock, request.c_str(), (int)request.size(), 0) == SOCKET_ERROR) {
        #ifdef _WIN32
        std::cerr << "send failed: " << WSAGetLastError() << std::endl;
        #else
        perror("send");
        #endif
    }

    char buf[1024];
#ifdef _WIN32
    int n = recv(sock, buf, sizeof(buf) - 1, 0);
#else
    ssize_t n = recv(sock, buf, sizeof(buf) - 1, 0);
#endif
    if (n > 0) {
        buf[n] = '\0';
        std::cout << buf << std::endl;
    }

#ifdef _WIN32
    closesocket(sock);
    WSACleanup();
#else
    close(sock);
#endif
    freeaddrinfo(res);
    return 0;
}
