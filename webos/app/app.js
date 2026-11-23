/* SPDX-License-Identifier: AGPL-3.0-or-later */
(function () {
    "use strict";
    var status = document.getElementById("status");
    var subtitle = document.getElementById("subtitle");
    var hint = document.getElementById("hint");
    var receiverUI = window.PlayCaptionReceiverUI ? new window.PlayCaptionReceiverUI(document) : null;
    var inputPanel = document.getElementById("inputs");
    var inputBridge = null;
    var inputButtons = [];
    var inputIndex = 0;
    var bridge = null;
    var activityBridge = null;
    var activityWarning = "";
    var protocolWarning = "";
    var statusText = "";
    var lastActivity = 0;
    var timer = null;
    var lastSeen = 0;
    var lastId = null;
    var source = null;
    var subtitleUntil = 0;
    var hintUntil = 0;
    var controls = document.getElementById("controls");
    var output = document.getElementById("output");
    var testSubtitle = document.getElementById("test-subtitle");
    var controlButtons = [];
    var controlIndex = 0;
    var hiddenByUser = false;
    var testUntil = 0;
    var lastDataAt = 0;
    var lastCaptionAt = 0;
    var otherSender = false;
    var receiverReady = false;
    var receiverNetworkReady = true;
    var receiverStartedAt = 0;
    var receiverFailure = false;
    var receiverLabel = "LG PlayCaption";
    var receiverVersion = "neznámá";
    var lastReplyAt = 0, retryAt = 0;
    var serviceSeen = false, lastError = "", lastPacket = "", discoveryWarning = "";
    var lifecycle = "spuštění";
    var startupDiagnostics = document.getElementById("startup-diagnostics");
    var startupTest = document.getElementById("startup-test");
    if (startupTest) startupTest.onclick = function () { localTest(true); };

    function updateInfo(now) {
        var diagnostics = "Služba: " + (serviceSeen ? "odpověděla" : "čekám na odpověď") +
            " · UDP 41989: " + (receiverReady ? "naslouchá" : "nepotvrzeno") +
            " · UI: " + lifecycle +
            "\nPoslední paket: " + (lastPacket || "žádný") +
            (lastError ? "\nPoslední chyba: " + lastError : "") +
            (discoveryWarning ? "\n" + discoveryWarning : "");
        if (startupDiagnostics && !inputPanel.hidden) startupDiagnostics.textContent = diagnostics;
        if (!controls || controls.hidden) return;
        var state = activityWarning || protocolWarning || (!receiverReady || !receiverNetworkReady || receiverFailure ? statusText : lastDataAt ?
            (now - lastDataAt <= 5000 ? "Zařízení posílá platná data." : "Komunikace byla přerušena.") : "Přijímač je připraven, čeká na zařízení.");
        var saved = "nezvolen";
        try { saved = localStorage.getItem("playcaption-input") || saved; } catch (error) {}
        var port = /hdmi([1-9][0-9]*)$/.exec(saved);
        document.getElementById("connection-info").textContent = receiverLabel + " · verze " + receiverVersion + "\n" + state + "\n" + diagnostics +
            "\nPoslední data: " + (lastDataAt ? Math.max(0, Math.floor((now - lastDataAt) / 1000)) + " s" : "žádná") +
            " · poslední titulek: " + (lastCaptionAt ? Math.max(0, Math.floor((now - lastCaptionAt) / 1000)) + " s" : "žádný") +
            "\nNaposledy vybraný vstup: " + (port ? "HDMI " + port[1] : "nezvolen") +
            (otherSender ? "\nPříjem z dalšího zařízení byl odmítnut, původní zdroj je stále aktivní." : "") +
            (hiddenByUser ? "\nTitulky jsou dočasně skryté; Příběhový režim čeká na zobrazení." : "");
    }

    function storyMasked(now) {
        return hiddenByUser || now < testUntil || (controls && !controls.hidden) || (inputPanel && !inputPanel.hidden);
    }

    function pauseMaskedStory(now) {
        if (receiverUI && receiverUI.storyActive() && storyMasked(now)) receiverUI.pauseStory(now);
    }

    function showControls(visible) {
        if (!controls) return;
        controls.hidden = !visible;
        pauseMaskedStory(Date.now());
        if (visible) { controlIndex = 0; controlButtons[0].focus(); updateInfo(Date.now()); }
    }

    function localTest(fromInput) {
        showControls(false);
        var launchState = lifecycle;
        if (fromInput) inputPanel.hidden = true;
        testSubtitle.textContent = "Lokální test zobrazení · Příliš žluťoučký kůň.\nTento text neověřuje spojení ani překlad.";
        testSubtitle.hidden = false;
        testUntil = Date.now() + 5000;
        output.hidden = true;
        pauseMaskedStory(Date.now());
        setTimeout(function () {
            if (Date.now() < testUntil) return;
            testSubtitle.hidden = true;
            output.hidden = hiddenByUser;
            if (fromInput && lifecycle === launchState) { inputPanel.hidden = false; startupTest.focus(); }
        }, 5000);
    }

    if (controls) {
        controlButtons = ["change-input", "local-test", "toggle-output", "return-game", "close-app"].map(function (id) { return document.getElementById(id); });
        controlButtons[0].onclick = function () { showControls(false); configureLaunch({}); };
        controlButtons[1].onclick = function () { localTest(false); };
        controlButtons[2].onclick = function () {
            hiddenByUser = !hiddenByUser;
            output.hidden = hiddenByUser || testUntil > Date.now();
            pauseMaskedStory(Date.now());
            this.textContent = hiddenByUser ? "Znovu zobrazit titulky" : "Dočasně skrýt titulky";
            updateInfo(Date.now());
        };
        controlButtons[3].onclick = function () { showControls(false); };
        controlButtons[4].onclick = function () { stop(); window.close(); };
        if (typeof XMLHttpRequest !== "undefined") {
            var metadata = new XMLHttpRequest();
            metadata.open("GET", "appinfo.json", true);
            metadata.onload = function () {
                try {
                    var info = JSON.parse(metadata.responseText);
                    if (/^\d+\.\d+\.\d+$/.test(info.version)) receiverVersion = info.version;
                } catch (error) {}
                updateInfo(Date.now());
            };
            metadata.send();
        }
    }

    function configureLaunch(params) {
        if (!inputPanel) return;
        var detail = params;
        if (!detail) {
            try { detail = JSON.parse(window.PalmSystem && window.PalmSystem.launchParams || "{}"); }
            catch (error) { detail = {}; }
        }
        inputPanel.hidden = detail && detail.resumeOverlay === true;
        if (inputPanel.hidden) return;
        var options = document.getElementById("input-options");
        var inputStatus = document.getElementById("input-status");
        var current = document.getElementById("input-current");
        options.textContent = "";
        inputButtons = [];
        inputStatus.textContent = "Načítám HDMI vstupy…";
        current.disabled = false;
        current.onclick = function () { inputPanel.hidden = true; };
        if (inputBridge) inputBridge.cancel();
        inputButtons = startupTest ? [startupTest, current] : [current];
        current.focus();
        if (typeof PalmServiceBridge === "undefined") {
            inputStatus.textContent = "Rozhraní HDMI není dostupné.";
            return;
        }
        var request = new PalmServiceBridge();
        inputBridge = request;
        request.onservicecallback = function (raw) {
            if (inputBridge !== request) return;
            var result;
            try { result = JSON.parse(raw); } catch (error) { result = {}; }
            if (!result || typeof result !== "object") result = {};
            inputBridge = null;
            var devices = Array.isArray(result.devices) ? result.devices.filter(function (device) {
                return device && /^com\.webos\.app\.hdmi[1-9][0-9]*$/.test(device.appId || "");
            }) : [];
            inputButtons = [];
            if (!result.returnValue || !Array.isArray(result.devices)) {
                inputStatus.textContent = "LG neposkytla seznam vstupů. Pokud už vidíš obraz hry, zvol Pokračovat nad aktuálním obrazem. Jinak aplikaci zavři, vyber HDMI a znovu ji otevři.";
            } else {
                inputStatus.textContent = "";
                devices.forEach(function (device) {
                        var button = document.createElement("button");
                        button.textContent = "HDMI " + device.appId.match(/hdmi([1-9][0-9]*)$/)[1] +
                            (device.label ? " · " + String(device.label).slice(0, 100) : "");
                        button.onclick = function () {
                            inputStatus.textContent = "Přepínám vstup a spouštím titulky…";
                            inputButtons.forEach(function (item) { item.disabled = true; });
                            try { localStorage.setItem("playcaption-input", device.appId); } catch (error) {}
                            var switcher = new PalmServiceBridge();
                            inputBridge = switcher;
                            switcher.onservicecallback = function (answer) {
                                if (inputBridge !== switcher) return;
                                inputBridge = null;
                                var response;
                                try { response = JSON.parse(answer); } catch (error) { response = {}; }
                                if (!response || typeof response !== "object") response = {};
                                if (response.returnValue) inputPanel.hidden = true;
                                else {
                                    inputStatus.textContent = response.errorText || "Přepnutí se nepodařilo.";
                                    inputButtons.forEach(function (item) { item.disabled = false; });
                                }
                            };
                            switcher.call("luna://cz.playcaption.overlaytest.receiver/switchInput", JSON.stringify({ id: device.appId }));
                        };
                        options.appendChild(button);
                        inputButtons.push(button);
                    });
            }
            if (startupTest) inputButtons.push(startupTest);
            inputButtons.push(current);
            var saved;
            try { saved = localStorage.getItem("playcaption-input"); } catch (error) {}
            inputIndex = 0;
            devices.some(function (device, index) {
                if (device.appId !== saved) return false;
                inputIndex = index;
                return true;
            });
            inputButtons[inputIndex].focus();
        };
        try { request.call("luna://com.webos.service.eim/getAllInputStatus", "{}"); }
        catch (error) { inputStatus.textContent = "Volání seznamu HDMI selhalo: " + error.message; }
    }

    function showStatus(text) {
        statusText = text;
        status.textContent = receiverFailure ? text : activityWarning || protocolWarning || text;
        status.hidden = false;
    }

    function clearText(preserveStory) {
        if (receiverUI) {
            if (preserveStory && receiverUI.storyActive()) receiverUI.pauseStory(Date.now()); else receiverUI.clear();
        }
        subtitle.hidden = true;
        hint.hidden = true;
        hint.textContent = "";
        lastId = null;
        source = null;
        lastSeen = 0;
        otherSender = false;
    }

    function stop() {
        showControls(false);
        hiddenByUser = false; testUntil = 0; lastDataAt = 0; lastCaptionAt = 0;
        receiverReady = false; otherSender = false;
        if (output) output.hidden = false;
        if (testSubtitle) testSubtitle.hidden = true;
        if (controls) controlButtons[2].textContent = "Dočasně skrýt titulky";
        if (inputBridge) {
            inputBridge.onservicecallback = function () {};
            inputBridge.cancel();
            inputBridge = null;
        }
        if (timer !== null) clearInterval(timer);
        timer = null;
        if (activityBridge) {
            activityBridge.onservicecallback = function () {};
            activityBridge.cancel();
            activityBridge = null;
        }
        cancelReceiver();
        clearText();
        activityWarning = "";
        protocolWarning = "";
    }

    function keepOverlayOpen() {
        lastActivity = Date.now();
        if (activityBridge) {
            activityBridge.onservicecallback = function () {};
            activityBridge.cancel();
        }
        var request = new PalmServiceBridge();
        activityBridge = request;
        request.onservicecallback = function (raw) {
            if (activityBridge !== request) return;
            var result;
            try { result = JSON.parse(raw); } catch (error) { result = {}; }
            activityWarning = result && result.returnValue === true ? "" :
                "PlayCaption · LG odmítá prodloužení překryvu, může se po 2 minutách zavřít.";
            status.textContent = activityWarning || protocolWarning || statusText;
            status.hidden = !activityWarning && !protocolWarning && Boolean(lastSeen);
            activityBridge = null;
        };
        // LG zavírá nečinný overlay po 120 s, i když se jeho text průběžně mění.
        try { request.call("luna://com.webos.surfacemanager.screenSaver/restartUserActivityTimer", "{}"); }
        catch (error) { activityWarning = "LG odmítá prodloužení překryvu: " + error.message; }
    }

    var ackBridge = null;
    function storyAck(id, state) {
        if (ackBridge) return;
        var request = new PalmServiceBridge(); ackBridge = request;
        var timeout = setTimeout(function () { if (ackBridge === request) { ackBridge = null; request.cancel(); } }, 2000);
        request.onservicecallback = function () { clearTimeout(timeout); if (ackBridge === request) ackBridge = null; };
        request.call("luna://cz.playcaption.overlaytest.receiver/storyAck", JSON.stringify({id:id,state:state}));
    }
    function cancelReceiver() {
        if (!bridge) return;
        var old = bridge;
        bridge = null;
        old.onservicecallback = function () {};
        old.cancel();
    }

    function receiverError(text) {
        receiverReady = false;
        receiverFailure = true;
        lastError = text;
        protocolWarning = "";
        retryAt = Date.now() + 3000;
        showStatus("PlayCaption LG · " + text + " · opakuji spojení");
        updateInfo(Date.now());
    }

    function receive(raw) {
        var result;
        try {
            result = JSON.parse(raw);
            if (!result || typeof result !== "object") throw new Error("Neplatná odpověď");
        } catch (error) {
            receiverError("neplatná odpověď přijímače");
            clearText();
            return;
        }
        if (!result.returnValue) {
            if (result.udpPort) serviceSeen = true;
            receiverError(result.errorText || "přijímač není dostupný");
            clearText();
            return;
        }
        serviceSeen = true;
        lastReplyAt = Date.now();
        if (result.probe) {
            lastPacket = result.probe + " od " + result.source;
            updateInfo(lastReplyAt);
            return;
        }
        if (result.unsupportedStory) {
            protocolWarning = "PlayCaption LG · Tento přijímač nepodporuje Story. Na zařízení přepni na Standardní režim.";
            showStatus(statusText); updateInfo(Date.now()); return;
        }
        if (result.otherSender) { otherSender = true; updateInfo(Date.now()); return; }
        var packet = result.packet;
        if (!packet) {
            var name = typeof result.name === "string" ? result.name.slice(0, 64) : "LG PlayCaption";
            receiverLabel = name; receiverReady = Boolean(result.ready);
            receiverNetworkReady = result.networkReady !== false;
            discoveryWarning = result.discoveryWarning || "";
            if (receiverReady) { receiverFailure = false; retryAt = 0; }
            if (lastSeen && receiverReady && receiverNetworkReady) return;
            showStatus(result.ready && !receiverNetworkReady ? "PlayCaption LG · Čekám na síť TV. Zkontroluj Wi-Fi nebo síťový kabel · OK / Zpět = nabídka" : result.ready ? "PlayCaption LG · Čekám na zařízení. Vyber „" + name + "“ · OK / Zpět = nabídka" : receiverFailure ? statusText : "PlayCaption LG · Spouštím příjem…");
            return;
        }
        var now = Date.now();
        if (packet.kind === "subtitle" || packet.kind === "story") protocolWarning = "";
        receiverReady = true; receiverFailure = false;
        lastDataAt = now;
        lastPacket = packet.kind + (packet.id ? " " + packet.id : "") + " od " + result.source +
            (packet.text ? " · " + packet.text.slice(0, 100).replace(/\s+/g, " ") : "");
        statusText = "Zařízení posílá platná data. OK / Zpět = nabídka";
        var connectionChanged = source !== result.source || (lastSeen && now - lastSeen > 5000);
        if (connectionChanged) clearText(packet.kind === "story" && (!source || source === result.source));
        if (receiverUI && receiverUI.handle(packet, now)) {
            lastSeen = now;
            source = result.source;
            status.hidden = !activityWarning && !protocolWarning;
            return;
        }
        if (packet.kind !== "story" && receiverUI && receiverUI.storyActive()) return;
        if (packet.kind === "story" && receiverUI && receiverUI.oldStory(packet.id)) return;
        // Opakované pakety jsou heartbeat; nesmějí znovu zobrazit již prošlý titulek.
        var changed = packet.id !== lastId || connectionChanged;
        lastSeen = now;
        status.hidden = !activityWarning && !protocolWarning;
        if (!changed && packet.kind !== "story") return;
        lastId = packet.id;
        if (packet.text) lastCaptionAt = now;
        source = result.source;
        if (!receiverUI) subtitle.textContent = packet.text;
        subtitle.hidden = !packet.text;
        subtitleUntil = now + packet.duration;
        var layout = packet.layout;
        var width = layout ? layout[2] : 0.8;
        var left = layout ? Math.max(width / 2, Math.min(1 - width / 2, layout[0])) : 0.5;
        subtitle.style.left = (left * 100) + "%";
        subtitle.style.bottom = ((1 - (layout ? layout[1] : 0.91)) * 100) + "%";
        subtitle.style.width = (width * 100) + "%";
        var viewport = document.documentElement ? document.documentElement.clientHeight : 1080;
        subtitle.style.fontSize = Math.min(38 * (layout ? layout[3] : 1), (viewport * 0.18 - 32) / 2.7) + "px";
        if (receiverUI && packet.kind === "story") {
            subtitleUntil = Infinity;
            packet.paused = packet.paused || Boolean(storyMasked(now));
            var state = receiverUI.story(packet, now);
            if (state) storyAck(packet.id, state);
        } else if (receiverUI) receiverUI.caption(packet, now);
        if (packet.hint !== hint.textContent) {
            hint.textContent = packet.hint;
            hint.hidden = !packet.hint;
            hintUntil = now + 20000;
        }
    }

    function connectReceiver() {
        cancelReceiver();
        receiverStartedAt = Date.now();
        lastReplyAt = 0;
        retryAt = 0;
        if (!receiverFailure) showStatus("PlayCaption · Spouštím příjem…");
        if (typeof PalmServiceBridge === "undefined") {
            receiverError("PalmServiceBridge není dostupný");
            return;
        }
        try {
            var request = new PalmServiceBridge();
            bridge = request;
            request.onservicecallback = function (raw) { if (bridge === request) receive(raw); };
            request.call("luna://cz.playcaption.overlaytest.receiver/listen", JSON.stringify({ subscribe: true }));
        } catch (error) { receiverError("Volání služby selhalo: " + error.message); }
    }

    function start() {
        stop();
        receiverFailure = false;
        connectReceiver();
        if (typeof PalmServiceBridge !== "undefined") keepOverlayOpen();
        timer = setInterval(function () {
            var now = Date.now();
            if (retryAt && now >= retryAt) connectReceiver();
            else if (!retryAt && !receiverReady && now - receiverStartedAt >= 10000) {
                receiverError("Služba nepotvrdila spuštění příjmu do 10 s.");
            }
            if (!retryAt && receiverReady && lastReplyAt && now - lastReplyAt > 10000) {
                receiverError("Odběr služby přestal odpovídat.");
            }
            if (receiverUI) {
                if (lastSeen && now - lastSeen > 5000) receiverUI.pauseStory(now);
                pauseMaskedStory(now);
                receiverUI.tick(now);
            }
            if (typeof PalmServiceBridge !== "undefined" && now - lastActivity >= 45000) keepOverlayOpen();
            if (now >= subtitleUntil) subtitle.hidden = true;
            if (now >= hintUntil) hint.hidden = true;
            if (testSubtitle && now >= testUntil) testSubtitle.hidden = true;
            if (output) output.hidden = hiddenByUser || now < testUntil;
            if (lastSeen && now - lastSeen > 5000) {
                clearText(true);
                hint.textContent = "";
                showStatus("PlayCaption LG · Spojení přerušeno, čekám na zařízení · OK / Zpět = nabídka");
            }
            updateInfo(now);
        }, 250);
    }

    // shortcut: overlay není veřejný kontrakt LG, ověřit na každém cílovém firmwaru.
    document.addEventListener("webOSRelaunch", function (event) {
        lifecycle = "obnovení aplikace";
        if (timer === null) start();
        else if (!receiverReady) connectReceiver();
        configureLaunch(event && event.detail);
    });
    document.addEventListener("visibilitychange", function () {
        lifecycle = document.hidden ? "na pozadí" : "v popředí";
        if (!document.hidden && (timer === null || !receiverReady ||
                (lastReplyAt && Date.now() - lastReplyAt > 10000))) {
            if (timer === null) start();
            else connectReceiver();
        }
        updateInfo(Date.now());
    });
    document.addEventListener("keydown", function (event) {
        var back = event.keyCode === 461 || event.key === "Escape";
        if (controls && !controls.hidden) {
            if (back) { event.preventDefault(); showControls(false); return; }
            if (event.keyCode >= 37 && event.keyCode <= 40) {
                event.preventDefault();
                controlIndex = (controlIndex + (event.keyCode === 37 || event.keyCode === 38 ? -1 : 1) + controlButtons.length) % controlButtons.length;
                controlButtons[controlIndex].focus(); return;
            }
            if (event.keyCode === 13) { event.preventDefault(); controlButtons[controlIndex].onclick(); return; }
        }
        if (inputPanel && !inputPanel.hidden && inputButtons.length) {
            if (event.keyCode >= 37 && event.keyCode <= 40) {
                event.preventDefault();
                inputIndex = (inputIndex + (event.keyCode === 37 || event.keyCode === 38 ? -1 : 1) + inputButtons.length) % inputButtons.length;
                inputButtons[inputIndex].focus();
                return;
            }
        }
        if (controls && (!inputPanel || inputPanel.hidden) && (back || event.keyCode === 13)) {
            event.preventDefault(); showControls(true); return;
        }
        if (back) {
            event.preventDefault();
            stop();
            window.close();
        }
    });
    window.addEventListener("pagehide", stop);
    window.addEventListener("pageshow", function () { if (timer === null) start(); });
    start();
    configureLaunch();
}());
