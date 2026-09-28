#include "App.h"
#include <openssl/ssl.h>
#include <cstdlib>
#include <iostream>
#include <string>

template <bool TLS> int serve(uWS::TemplatedApp<TLS> &app) {
    if constexpr (TLS) {
        auto *context = static_cast<SSL_CTX *>(app.getNativeHandle());
        if (!context || !SSL_CTX_set_min_proto_version(context, TLS1_3_VERSION)
            || !SSL_CTX_set_max_proto_version(context, TLS1_3_VERSION)
            || !SSL_CTX_set_ciphersuites(context, "TLS_AES_128_GCM_SHA256")) return 1;
    }
    app.post("/echo", [](auto *res, auto *) {
        res->onAborted([] {});
        res->onData([res, body = std::string{}](std::string_view data, bool last) mutable {
            if (body.size() + data.size() > 65536) { res->close(); return; }
            if (last && body.empty()) {
                res->writeHeader("Content-Type", "application/octet-stream")->end(data);
            } else {
                body.append(data);
                if (last) {
                    // end() can destroy the onData capture. Keep response bytes
                    // in a local owner until end() has copied any backpressure.
                    std::string complete = std::move(body);
                    res->writeHeader("Content-Type", "application/octet-stream")->end(complete);
                }
            }
        });
    });
    bool listening = false;
    app.listen("127.0.0.1", 18080, [&listening](auto *socket) { listening = socket != nullptr; });
    if (!listening) return 1;
    std::cout << "uWS echo ready on 127.0.0.1:18080" << std::endl;
    app.run();
    return 0;
}
int main() {
    if (std::getenv("BENCH_TLS")) {
        uWS::SSLApp app({.key_file_name = "build/key.pem", .cert_file_name = "build/cert.pem"});
        return serve(app);
    }
    uWS::App app;
    return serve(app);
}
