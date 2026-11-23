/* SPDX-License-Identifier: AGPL-3.0-or-later */
// Runs on Node.js 0.12.2, with real UDP and only the TV's Luna bus mocked.
"use strict";
var assert = require("assert");
var fs = require("fs");
var vm = require("vm");
var dgram = require("dgram");
var handlers = {};
var sender = dgram.createSocket("udp4");
var port;
var stage = 0;
var token = "legacy-test";
var watchdog = setTimeout(function () { throw new Error("UDP test timed out at stage " + stage); }, 5000);
var nonce = Array(33).join("d");
var id = Array(33).join("a") + ".1.1.0";

function send(value) {
    var bytes = new Buffer(value, "utf8");
    sender.send(bytes, 0, bytes.length, port, "127.0.0.1", function (error) { assert.ifError(error); });
}

function Service(name) {
    assert.strictEqual(name, "cz.playcaption.overlaytest.receiver");
    this.register = function (method, request, cancel) { handlers[method] = {request:request, cancel:cancel}; };
}

vm.runInNewContext(fs.readFileSync(__dirname + "/service/service.js", "utf8"), {
    require: function (name) {
        if (name === "webos-service") return Service;
        if (name === "os") return {hostname:function () { return "legacy"; }, networkInterfaces:function () {
            return {eth0:[{family:"IPv4", address:"127.0.0.1", mac:"00:11:22:33:44:55"}]};
        }};
        if (name === "dgram") return {createSocket:function () {
            var socket = dgram.createSocket("udp4");
            var bind = socket.bind;
            socket.bind = function (wanted, host, callback) {
                assert.strictEqual(wanted, 41989);
                bind.call(socket, 0, "127.0.0.1", function () { port = socket.address().port; callback(); });
            };
            return socket;
        }};
        return require(name.charAt(0) === "." ? "./service/" + name.slice(2) : name);
    },
    Buffer:Buffer, console:console, setInterval:setInterval, clearInterval:clearInterval
});

sender.on("message", function (message) {
    var value = message.toString("utf8");
    if (stage === 1) {
        assert.strictEqual(value.split("\t")[4], nonce);
        stage = 2;
        send("PCQ1\t" + id);
    } else {
        assert.strictEqual(stage, 2);
        assert.strictEqual(value, "PCA1\t" + id + "\tready");
        stage = 3;
        send("PCT1\t42\t6000\tPříliš žluťoučký kůň\\nDruhý řádek\t\t0.5\t0.9\t0.8\t1\tB:-1");
    }
});
sender.bind(0, "127.0.0.1", function () {
    handlers.listen.request({isSubscription:true, uniqueToken:token, respond:function (event) {
        assert.strictEqual(event.returnValue, true, event.errorText);
        if (stage === 0 && event.ready) {
            stage = 1;
            send("PLAYCAPTION_FIND\t" + nonce);
        }
        if (stage === 3 && event.packet) {
            assert.strictEqual(event.packet.text, "Příliš žluťoučký kůň\nDruhý řádek");
            assert.strictEqual(event.packet.colors[0], -1);
            handlers.listen.cancel({uniqueToken:token});
            sender.close();
            clearTimeout(watchdog);
            console.log("OK: " + process.version + " discovery, PCQ1/PCA1 a víceřádkový PCT1 přes UDP.");
        }
    }});
});
