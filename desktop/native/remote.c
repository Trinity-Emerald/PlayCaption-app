// SPDX-License-Identifier: AGPL-3.0-or-later
// Additional permission under GNU AGPL section 7: you may link this file
// with OpenSSL and distribute the resulting work under the AGPL.
#include <chiaki/session.h>
#include <stdio.h>
#include <string.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static void registered(ChiakiRegistEvent *event, void *user)
{
    bool *success = user;
    if (event->type != CHIAKI_REGIST_EVENT_TYPE_FINISHED_SUCCESS)
        return;

    ChiakiRegisteredHost *host = event->registered_host;
    *success = fwrite(host->rp_regist_key, 1, sizeof(host->rp_regist_key), stdout)
                == sizeof(host->rp_regist_key)
            && fwrite(host->rp_key, 1, sizeof(host->rp_key), stdout) == sizeof(host->rp_key)
            && fflush(stdout) == 0;
}

static int pair(const char *host, ChiakiLog *log)
{
    ChiakiRegistInfo info = {0};
    ChiakiRegist registration;
    bool success = false;
    unsigned char pin[8];

    info.host = host;
    info.target = CHIAKI_TARGET_PS5_1;
    if (fread(info.psn_account_id, 1, sizeof(info.psn_account_id), stdin)
                != sizeof(info.psn_account_id) || fread(pin, 1, sizeof(pin), stdin) != sizeof(pin))
        return 2;

    for (size_t i = 0; i < sizeof(pin); i++) {
        if (pin[i] < '0' || pin[i] > '9')
            return 2;
        info.pin = info.pin * 10 + (pin[i] - '0');
    }

    ChiakiErrorCode error = chiaki_regist_start(&registration, log, &info, registered, &success);
    if (error != CHIAKI_ERR_SUCCESS) {
        fprintf(stderr, "pair: %s\n", chiaki_error_string(error));
        return 3;
    }
    chiaki_regist_fini(&registration);
    return success ? 0 : 4;
}

static bool video(uint8_t *buffer, size_t size, int32_t lost, bool recovered, void *user)
{
    (void)lost;
    (void)recovered;
    (void)user;
    return fwrite(buffer, 1, size, stdout) == size && fflush(stdout) == 0;
}

static void session_event(ChiakiEvent *event, void *user)
{
    (void)user;
    if (event->type == CHIAKI_EVENT_CONNECTED) {
        fputs("connected\n", stderr);
    } else if (event->type == CHIAKI_EVENT_LOGIN_PIN_REQUEST) {
        fputs("console-login-pin-required\n", stderr);
    } else if (event->type == CHIAKI_EVENT_QUIT) {
        fprintf(stderr, "quit: %s\n", chiaki_quit_reason_string(event->quit.reason));
    }
}

static int stream(const char *host, ChiakiLog *log)
{
    ChiakiSession session;
    ChiakiConnectInfo info = {0};
    info.ps5 = true;
    info.host = host;
    info.audio_video_disabled = CHIAKI_AUDIO_DISABLED;
    info.packet_loss_max = 0.05;
    info.enable_idr_on_fec_failure = true;
    chiaki_connect_video_profile_preset(&info.video_profile, CHIAKI_VIDEO_RESOLUTION_PRESET_720p,
                                       CHIAKI_VIDEO_FPS_PRESET_30);
    info.video_profile.codec = CHIAKI_CODEC_H264;
    if (fread(info.regist_key, 1, sizeof(info.regist_key), stdin) != sizeof(info.regist_key)
            || fread(info.morning, 1, sizeof(info.morning), stdin) != sizeof(info.morning))
        return 2;

    ChiakiErrorCode error = chiaki_session_init(&session, &info, log);
    if (error != CHIAKI_ERR_SUCCESS) {
        fprintf(stderr, "session-init: %s\n", chiaki_error_string(error));
        return 3;
    }

    chiaki_session_set_video_sample_cb(&session, video, NULL);
    chiaki_session_set_event_cb(&session, session_event, NULL);
    error = chiaki_session_start(&session);
    if (error == CHIAKI_ERR_SUCCESS)
        error = chiaki_session_join(&session);
    chiaki_session_fini(&session);
    if (error != CHIAKI_ERR_SUCCESS)
        fprintf(stderr, "session: %s\n", chiaki_error_string(error));
    return error == CHIAKI_ERR_SUCCESS ? 0 : 4;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        if (chiaki_lib_init() != CHIAKI_ERR_SUCCESS)
            return 3;
        puts("NEXCAP Remote 1");
        return 0;
    }
    if (argc != 3)
        return 2;

#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) < 0 || _setmode(_fileno(stdout), _O_BINARY) < 0)
        return 2;
#endif

    if (chiaki_lib_init() != CHIAKI_ERR_SUCCESS)
        return 3;
    ChiakiLog log;
    chiaki_log_init(&log, 0, NULL, NULL);
    if (strcmp(argv[1], "pair") == 0)
        return pair(argv[2], &log);
    if (strcmp(argv[1], "stream") == 0)
        return stream(argv[2], &log);
    return 2;
}
