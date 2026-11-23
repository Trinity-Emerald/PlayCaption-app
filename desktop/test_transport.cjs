/* SPDX-License-Identifier: AGPL-3.0-or-later */
const assert = require("node:assert/strict");
const { execFile } = require("node:child_process");
const fs = require("node:fs");
const { createRequire } = require("node:module");
const path = require("node:path");
const { promisify } = require("node:util");
const vm = require("node:vm");

const servicePath = path.resolve(__dirname, "../webos/service/service.js");
const serviceRequire = createRequire(servicePath);
const handlers = {};
function Service() {
    this.register = (name, request, cancel) => { handlers[name] = { request, cancel }; };
}

vm.runInNewContext(fs.readFileSync(servicePath, "utf8"), {
    require(name) {
        if (name === "webos-service") return Service;
        if (name === "os") return { hostname: () => "LG-test", networkInterfaces: () => ({}) };
        return serviceRequire(name);
    },
    Buffer, console, setInterval, clearInterval,
}, { filename: servicePath });

async function main() {
    let received;
    let resolveReady;
    const ready = new Promise(resolve => { resolveReady = resolve; });
    handlers.listen.request({
        isSubscription: true,
        uniqueToken: "desktop-test",
        respond(message) {
            assert.equal(message.returnValue, true, message.errorText);
            if (message.ready) resolveReady();
            if (message.packet) received = message;
        },
    });
    const watchdog = setTimeout(() => { throw new Error("UDP test timeout"); }, 8000);
    try {
        await ready;
        const { stdout } = await promisify(execFile)(process.env.PYTHON || "python3", ["-c", [
            "from transport import make_packet, probe_receiver, send_subtitle",
            "assert len({make_packet('a').split(b'\\t')[1] for _ in range(50)}) == 50",
            "print(probe_receiver('127.0.0.1'))",
            "send_subtitle('127.0.0.1', 'Příliš žluťoučký kůň\\r\\nC:\\\\hra\\tdruhý řádek', 3200)",
        ].join("\n")], { cwd: __dirname, timeout: 5000, env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
        assert.match(stdout.trim(), /^LG PlayCaption · [0-9A-F]{12}$/);
        assert.equal(received.source, "127.0.0.1");
        assert.equal(received.packet.text, "Příliš žluťoučký kůň\nC:\\hra druhý řádek");
        assert.equal(received.packet.duration, 3200);
        console.log("OK: desktop discovery and UTF-8 subtitle through production webOS UDP service.");
    } finally {
        clearTimeout(watchdog);
        handlers.listen.cancel({ uniqueToken: "desktop-test" });
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
