#include <iostream>
#include <string>
#include <sys/socket.h>
#include <netdb.h>
#include <unistd.h>

int main(int argc, char* argv[]) {
    std::string host = "localhost";
    std::string port = "8000";
    std::string client_id = "client_" + std::to_string(getpid());
    if (argc > 1) client_id = argv[1];

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo* res;
    if (getaddrinfo(host.c_str(), port.c_str(), &hints, &res) != 0) {
        perror("getaddrinfo");
        return 1;
    }

    int sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock < 0) {
        perror("socket");
        freeaddrinfo(res);
        return 1;
    }

    if (connect(sock, res->ai_addr, res->ai_addrlen) < 0) {
        perror("connect");
        close(sock);
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

    if (send(sock, request.c_str(), request.size(), 0) < 0) {
        perror("send");
    }

    char buf[1024];
    ssize_t n = recv(sock, buf, sizeof(buf) - 1, 0);
    if (n > 0) {
        buf[n] = '\0';
        std::cout << buf << std::endl;
    }

    close(sock);
    freeaddrinfo(res);
    return 0;
}
