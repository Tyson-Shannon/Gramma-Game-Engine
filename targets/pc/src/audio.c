#include <SDL2/SDL.h>
#include <gramma/gramma.h>
#include "pc_internal.h"
#include <string.h>

/*
 * Four-channel synth. Music is an event stream (not a WAV): the same note
 * arrays can be re-compiled for any target's sound chip by the pipeline.
 * SFX either synthesize a wave or play pipeline-converted PCM.
 */

#define PC_AUDIO_RATE 44100u

typedef struct {
    bool          active;
    gr_wave       wave;
    double        phase;
    double        freq;
    double        slope;
    uint32_t      remaining;
    uint32_t      total;
    uint8_t       volume;
    const gr_pcm *pcm;
    uint32_t      pcm_index;
} Channel;

static Channel g_channels[GR_AUDIO_CHANNELS];
static SDL_AudioDeviceID g_device;
static const gr_config *g_cfg;
static const gr_song *g_song;
static uint16_t g_note_index;
static uint32_t g_note_elapsed;
static uint32_t g_noise = 0x12345678u;

static int16_t wave_sample(Channel *ch)
{
    double value;

    if (ch->wave == GR_WAVE_PCM) {
        if (ch->pcm == NULL || ch->pcm->data == NULL ||
            ch->pcm_index >= ch->pcm->length) {
            ch->active = false;
            return 0;
        }
        ++ch->pcm_index;
        return (int16_t)((int32_t)(uint8_t)ch->pcm->data[ch->pcm_index - 1] * 256);
    }

    ch->phase += ch->freq / (double)PC_AUDIO_RATE;
    while (ch->phase >= 1.0) {
        ch->phase -= 1.0;
        if (ch->wave == GR_WAVE_NOISE) {
            g_noise = g_noise * 1103515245u + 12345u;
        }
    }
    switch (ch->wave) {
    case GR_WAVE_TRIANGLE:
        value = 1.0 - 4.0 * ((ch->phase > 0.5) ? (1.0 - ch->phase) : ch->phase);
        break;
    case GR_WAVE_SAW:
        value = 2.0 * ch->phase - 1.0;
        break;
    case GR_WAVE_NOISE:
        value = ((g_noise >> 16) & 1u) ? 1.0 : -1.0;
        break;
    case GR_WAVE_SQUARE:
    default:
        value = ch->phase < 0.5 ? 1.0 : -1.0;
        break;
    }
    return (int16_t)(value * 12000.0);
}

static void audio_callback(void *userdata, int16_t *stream, int samples)
{
    int i, c;

    (void)userdata;
    memset(stream, 0, (size_t)samples * sizeof(int16_t));
    for (i = 0; i < samples; ++i) {
        int32_t mix = 0;
        for (c = 0; c < GR_AUDIO_CHANNELS; ++c) {
            Channel *ch = &g_channels[c];
            int32_t sample;
            int32_t envelope = 256;

            if (!ch->active) {
                continue;
            }
            if (ch->remaining < ch->total / 4 && ch->total != 0) {
                envelope = (int32_t)(ch->remaining * 1024u / ch->total);
            }
            sample = (int32_t)wave_sample(ch) * (int32_t)ch->volume / 15;
            sample = sample * envelope / 256;
            mix += sample;
            if (ch->wave != GR_WAVE_PCM) {
                if (ch->remaining > 0) {
                    --ch->remaining;
                }
                ch->freq += ch->slope / (double)PC_AUDIO_RATE;
                if (ch->freq < 0.0) {
                    ch->freq = 0.0;
                }
                if (ch->remaining == 0) {
                    ch->active = false;
                }
            }
        }
        mix /= GR_AUDIO_CHANNELS;
        if (mix > 32767) {
            mix = 32767;
        } else if (mix < -32768) {
            mix = -32768;
        }
        stream[i] = (int16_t)mix;
    }
}

static void audio_callback_thunk(void *userdata, Uint8 *stream, int len)
{
    audio_callback(userdata, (int16_t *)stream, len / (int)sizeof(int16_t));
}

static void start_voice(uint8_t channel, gr_wave wave, uint16_t freq,
                        uint16_t duration_ms, uint8_t volume,
                        int16_t slope, const gr_pcm *pcm)
{
    Channel *ch;

    if (channel >= GR_AUDIO_CHANNELS) {
        return;
    }
    ch = &g_channels[channel];
    memset(ch, 0, sizeof(*ch));
    ch->active = true;
    ch->wave = wave;
    ch->freq = (double)freq;
    ch->slope = (double)slope;
    ch->volume = volume > 15 ? 15 : volume;
    ch->pcm = pcm;
    ch->total = (uint32_t)duration_ms * PC_AUDIO_RATE / 1000u;
    if (ch->total == 0) {
        ch->total = 1;
    }
    ch->remaining = ch->total;
}

static void start_note(const gr_note *note)
{
    uint32_t ms;

    if (g_song == NULL || note == NULL || g_song->bpm == 0) {
        return;
    }
    ms = (uint32_t)note->ticks * 60000u / g_song->bpm / 4u;
    start_voice(note->channel, note->wave, note->freq_hz, (uint16_t)ms,
                note->volume, 0, NULL);
}

bool pc_audio_init(const gr_config *cfg)
{
    SDL_AudioSpec spec;

    g_cfg = cfg;
    memset(g_channels, 0, sizeof(g_channels));
    memset(&spec, 0, sizeof(spec));
    spec.freq = (int)PC_AUDIO_RATE;
    spec.format = AUDIO_S16SYS;
    spec.channels = 1;
    spec.samples = 1024;
    spec.callback = audio_callback_thunk;

    g_device = SDL_OpenAudioDevice(NULL, 0, &spec, NULL, 0);
    if (g_device == 0) {
        return false; /* the game still runs, just silently */
    }
    SDL_PauseAudioDevice(g_device, 0);
    return true;
}

void pc_audio_quit(void)
{
    if (g_device != 0) {
        SDL_CloseAudioDevice(g_device);
        g_device = 0;
    }
    g_song = NULL;
    g_cfg = NULL;
}

void pc_audio_tick(uint32_t dt_ms)
{
    if (g_song == NULL || g_song->note_count == 0 || g_song->bpm == 0) {
        return;
    }
    g_note_elapsed += dt_ms;
    while (g_song != NULL) {
        const gr_note *note = &g_song->notes[g_note_index];
        uint32_t duration = (uint32_t)note->ticks * 60000u /
                            g_song->bpm / 4u;
        if (duration == 0) {
            duration = 1;
        }
        if (g_note_elapsed < duration) {
            break;
        }
        g_note_elapsed -= duration;
        ++g_note_index;
        if (g_note_index >= g_song->note_count) {
            if (!g_song->loop) {
                g_song = NULL;
                return;
            }
            g_note_index = 0;
        }
        start_note(&g_song->notes[g_note_index]);
    }
}

gr_result pc_backend_music_play(const gr_song *song)
{
    g_song = song;
    g_note_index = 0;
    g_note_elapsed = 0;
    if (song != NULL && song->note_count > 0) {
        start_note(&song->notes[0]);
    }
    return GR_OK;
}

void pc_backend_music_stop(void)
{
    g_song = NULL;
    memset(g_channels, 0, sizeof(g_channels));
}

void pc_backend_sfx_play(uint16_t id, uint8_t channel)
{
    const gr_sfx_def *def;

    if (g_cfg == NULL || id >= g_cfg->sfx_count) {
        return;
    }
    def = g_cfg->sfx[id];
    start_voice(channel, def->wave, def->freq_hz, def->duration_ms,
                def->volume, def->freq_slope_hz, def->pcm);
}
