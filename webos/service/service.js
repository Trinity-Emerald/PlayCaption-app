/* SPDX-License-Identifier: AGPL-3.0-or-later */
"use strict";
var Service = require("webos-service");
var dgram = require("dgram");
var os = require("os");
var crypto = require("crypto");
var protocol = require("./protocol");
var service = new Service(require("./package.json").name);
require("./switch-input").register(service);
var subscriptions = Object.create(null);
var socket = null;
var announceTimer = null;
var ready = false;
var storyPeer = null;
var receiverName = "LG PlayCaption";
var networkReady = false;
var announcement = null;
var sender = null;
var senderSeen = 0;
var rejectedAt = 0;

function notify(payload) {
    Object.keys(subscriptions).forEach(function (key) { subscriptions[key].respond(payload); });
}

function send(receiver, bytes, port, address, callback) {
    receiver.send(bytes, 0, bytes.length, port, address, callback);
}

function state() {
    return {returnValue:true, ready:ready, networkReady:networkReady, name:receiverName,
        udpPort:41989, discoveryWarning:discoveryWarning};
}

var discoveryWarning = "";

function stop() {
    clearInterval(announceTimer);
    announceTimer = null;
    ready = false;
    networkReady = false;
    announcement = null;
    discoveryWarning = "";
    storyPeer = null;
    sender = null;
    senderSeen = 0;
    rejectedAt = 0;
    if (socket) { try { socket.close(); } catch (error) {} }
    socket = null;
}

function start() {
    if (socket) return;
    var receiver = dgram.createSocket("udp4");
    socket = receiver;
    function announce() {
        if (socket !== receiver) return;
        // Po obnovení Wi-Fi/LAN se IP i broadcast mohou změnit bez restartu služby.
        var addresses = [];
        var hasIPv4 = false;
        var identity = os.hostname();
        var interfaces = os.networkInterfaces();
        Object.keys(interfaces).forEach(function (name) {
            interfaces[name].forEach(function (iface) {
                if (iface.internal || (iface.family !== "IPv4" && iface.family !== 4)) return;
                hasIPv4 = true;
                identity += iface.mac;
                if (!iface.netmask) return;
                var ip = iface.address.split(".");
                var mask = iface.netmask.split(".");
                addresses.push(ip.map(function (part, i) { return Number(part) | (255 ^ Number(mask[i])); }).join("."));
            });
        });
        var id = crypto.createHash("sha256").update(identity).digest("hex").slice(0, 12);
        var name = "LG PlayCaption · " + id.toUpperCase();
        receiverName = name;
        networkReady = hasIPv4;
        announcement = protocol.encode("PLAYCAPTION_TV\tlg-" + id + "\t" + receiverName + "\t0");
        notify(state());
        if (discoveryWarning) return;
        addresses.forEach(function (address) {
            send(receiver, announcement, 41988, address, function (error) {
                if (error) console.error("PlayCaption discovery:", error.code);
            });
        });
    }
    receiver.on("error", function (error) {
        if (socket !== receiver) return;
        stop();
        notify({ returnValue: false, udpPort: 41989, errorText: "Příjem UDP selhal: " + (error.code || error.message) });
    });
    receiver.on("message", function (buffer, remote) {
        if (socket !== receiver) return;
        var query = buffer.length === 49 && /^PLAYCAPTION_FIND\t([a-f0-9]{32})$/.exec(buffer.toString("utf8"));
        if (query && ready && announcement) {
            send(receiver, Buffer.concat([announcement, protocol.encode("\t" + query[1])]), remote.port, remote.address, function () {});
            notify({returnValue:true, probe:"PLAYCAPTION_FIND", source:remote.address});
            return;
        }
        var packet = protocol.parse(buffer);
        var now = Date.now();
        if (!packet) return;
        // Starý Android mění UDP porty: do budoucího párování držíme zdroj podle IP.
        if (sender && sender !== remote.address && now - senderSeen < 5000) {
            if (!rejectedAt || now - rejectedAt >= 5000) {
                rejectedAt = now;
                notify({ returnValue: true, otherSender: true });
            }
            return;
        }
        if (packet.kind === "storyQuery") {
            send(receiver, protocol.encode("PCA1\t" + packet.id + "\tready"), remote.port, remote.address, function () {});
            notify({returnValue:true, probe:"PCQ1", source:remote.address});
            return;
        }
        if (sender !== remote.address) storyPeer = null;
        sender = remote.address;
        senderSeen = now;
        if (packet.kind === "story") storyPeer = {id:packet.id,address:remote.address,port:remote.port};
        notify({ returnValue: true, packet: packet, source: remote.address });
    });
    receiver.bind(41989, "0.0.0.0", function () {
        if (socket !== receiver) return;
        try { receiver.setBroadcast(true); }
        catch (error) { discoveryWarning = "UDP broadcast: " + (error.code || error.message); }
        ready = true;
        announce();
        announceTimer = setInterval(announce, 2000);
    });
}

service.register("listen", function (message) {
    if (!message.isSubscription) {
        message.respond({ returnValue: false, errorText: "Vyžadováno subscribe: true." });
        return;
    }
    subscriptions[message.uniqueToken] = message;
    start();
    message.respond(state());
}, function (message) {
    delete subscriptions[message.uniqueToken];
    // Keep UDP alive while webOS retains this service process: switching HDMI can
    // briefly detach the overlay subscription without stopping the receiver.
    // The OS still owns the service lifecycle.
});

service.register("storyAck", function (message) {
    var p = message.payload || {};
    if (!socket || !storyPeer || p.id !== storyPeer.id || ["reading", "done"].indexOf(p.state) < 0) {
        message.respond({returnValue:false}); return;
    }
    send(socket, protocol.encode("PCA1\t" + p.id + "\t" + p.state), storyPeer.port, storyPeer.address, function (error) {
        message.respond({returnValue:!error});
    });
});

// Start listening as soon as the service is launched, independently of UI subscriptions.
// This also makes direct PCQ1 probes possible while the overlay is being resumed.
start();
