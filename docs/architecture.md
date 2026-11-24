# Architecture

Parley is a single GTK 4 application. There is no web server and no browser
runtime: the interface, the audio pipeline and the model client all live in the
same Python process.

```
┌───────────────────────────────────────────────────────────────┐
│ Gtk.Application / Gtk.ApplicationWindow                       │
│  welcome → practice → scenarios → session                     │
│                     ├→ pronunciation                          │
│                     ├→ sentence                                │
│                     ├→ stories                                 │
│                     └→ level test                              │
│  settings, onboarding                                         │
└───────────────▲───────────────────────────────────────────────┘
                │ GLib.idle_add
┌───────────────┴───────────────────────────────────────────────┐
│ ConversationEngine (worker thread)                            │
│  Recorder → VAD → speech-to-text → prompt → stream_chat → TTS  │
│  AudioPlayer                                                  │
└───────────────▲───────────────────────────────────────────────┘
                │ HTTP on 127.0.0.1
┌───────────────┴───────────────────────────────────────────────┐
│ Ollama (/api/chat) or llama.cpp (/v1/chat/completions)        │
└───────────────────────────────────────────────────────────────┘
```

## Core modules

| Module | Responsibility |
| --- | --- |
| `core/config.py` | Languages, voices, model tiers, paths and `Settings`. |
| `core/backends.py` | Detect, start, preload and report an Ollama or llama.cpp service. |
| `core/llm.py` | Streaming chat and a small backend abstraction. |
| `core/prompts.py` | System prompt with the `<MAIN>`/`<NOTE>` response format. |
| `core/parser.py` | Splits a model reply into the in-character text and the note. |
| `core/scenarios.py` | The 19 role-play briefs and their CEFR bands. |
| `core/stt.py` | faster-whisper wrapper and transcription metrics. |
| `core/tts.py` | Piper wrapper, sentence splitting and cache. |
| `core/exercises.py` | Phrase generation, pronunciation comparison and cloze texts. |
| `core/text.py` | Shared text cleanup: hyphen runs, CJK punctuation and sentence limits. |
| `core/scoring.py` | Conversation-only scores, per-language history and level bands. |
| `core/i18n.py` | Interface translations for the eight UI languages. |
| `content/stories.py` | Story catalogue, download and removal. |

## Audio layer

- `audio/recorder.py` opens a 16 kHz mono `sounddevice` stream. In continuous
  mode an energy VAD (`audio/vad.py`) groups frames into utterances. In
  push-to-talk mode the page decides when to record.
- `audio/player.py` plays WAV/MP3 and supports seek, pause and speed changes
  between 0.5× and 1.5×.
- `audio/pipeline.py` owns the conversation state machine:

  ```
  idle → thinking → speaking → listening
  listening → thinking → speaking → listening
  ```

  The microphone is suppressed while the tutor speaks, so the app does not
  listen to its own voice. Events are plain dataclasses; the UI marshals them to
  the GTK main loop with `GLib.idle_add`.

## Threading rules

- GTK is only touched from the main thread.
- The conversation engine, speech recognition, TTS and downloads run on worker
  threads.
- Worker threads never call GTK directly. They emit an event or schedule a
  closure with `GLib.idle_add`.
- Navigating away from a page calls its `shutdown()` method, which stops the
  engine, the microphone and the player.

## Model backends

The runtime never assumes that a service is local-private without checking. It
probes `http://127.0.0.1:11434` (Ollama) and `http://127.0.0.1:8080/v1`
(llama.cpp) first:

1. An explicit user choice wins.
2. A running Ollama service is reused.
3. A running llama.cpp service is reused.
4. Otherwise the preferred backend is started.

The session page only creates a `ConversationEngine` after the runtime reports
`state == "running"`, which means the service answered and a model is loaded.

## Text normalisation

`core/text.py` keeps the visible text and the spoken text identical. It expands
runs of three or more hyphen-joined words (`I'm-ready-to-go` becomes
`I'm ready to go`), removes duplicated or mixed CJK punctuation such as `。、.`,
adds a terminal mark when the model omits one, and limits generated phrases to
the requested sentence count and word budget. Pronunciation asks for one short
sentence and passes `max_words=18`, so the reader gets a phrase instead of a
paragraph, while Complete the Sentence keeps its requested number of sentences.

## Keeping the conversation moving

`core/prompts.py` builds the system prompt with an explicit conversation-rules
block and, after the first reply, a list of questions already asked.
`audio/pipeline.py` extracts questions from each assistant reply, refreshes the
system prompt before the next request, and keeps more history by default
(`history_turns=10`). Together with the no-repeat rule, this prevents the
beginner role-plays from restarting the introduction or asking the same
question again after a few answers.

## Conversation scoring

`core/scoring.py` turns the metrics that `core/stt.py` already reports into a
personal 0-100 score. Only spoken turns are counted: speaking speed, pause
ratio, vocabulary variety, average turn length and recogniser confidence. The
history is stored in `scores.json` inside the data folder and keeps the last 500
records. Set `PARLEY_SCORES` to point at another file, which is useful for
tests.

The same module powers the guided level test page. The six level names are a
personal scale inspired by speaking tests; they are deliberately not labelled
with CEFR or IELTS/TOEFL scores, and the interface says they have no official
value.

## Data folder

`PARLEY_DATA_DIR` overrides the data root. The default is the project folder in
a source checkout and `~/.local/share/parley` (or `%APPDATA%\Parley`) in an
installed build. Models, voices, cache, stories and `config.json` live below it.
