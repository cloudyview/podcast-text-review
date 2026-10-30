# Data contracts

Use the README for commands. This page documents the data needed when adapting the tool.

## Timed input

UTF-8 SRT, a JSON array, or JSON with `cues`, `segments` or `rows`. Each row needs `text` and `start/end` or `start_seconds/end_seconds` in source seconds. Optional fields such as `raw_text`, `speaker`, `speaker_source` and `word_spans` survive preparation. `word_spans` uses half-open Unicode-code-point `char_in/char_out` relative to the row, and source `start/end` seconds. A shared multi-character span is never split by character count.

Reading punctuation must preserve all lexical characters. `format_transcript.py` keeps raw text, appends reading hints and accepts a speaker-turn list of `{start,end,speaker}`. It does not translate, paraphrase, infer identity or deduplicate speech. Uncertain crossing turns remain flagged.

## Session and state

The baseline pins video and transcript identities and copies the UI assets. The media is referenced without copying; an optional playback proxy is separate. Startup checks original media stats and frozen-file hashes. A baseline mismatch requires a new session or an explicit migration, not an automatic override.

`data/删改状态.json`: baseline identity, revision, current cuts and annotations. Each confirmed word edit retains selected text, character positions, source time and candidate provenance. `annotations.speaker_overrides` maps cue IDs to user-supplied names. Speaker corrections do not change audio.

`data/删改过程.jsonl`: durable before/after events, including annotation snapshots. The state snapshot is atomically replaced. One writable server per session; stale revisions return 409. `export-decisions` merges overlapping cuts, preserves annotations and maps the retained clock. Only `export-video` renders media, refusing overwrite.

Character highlights require a matching text-baseline ID. When changing text, keep old selections as provenance and retain cuts by their source times; never reuse stale character positions.

## ASR and audio

Whisper models are downloaded from vendor metadata with SHA256 validation; external weights are not distributed here. The optional MLX Qwen path uses separate ASR and forced-alignment models. Model-level speech normalization can still happen: inspect representative original speech and do not claim a perfect verbatim transcript from model settings alone.

Whisper alignment windows are analysis assets, not cuts in the recording. A bounded short-silence tail repair can recover the known DTW short-segment assertion; true coverage time never expands. Unavailable candidates fall back to manual waveform boundaries.

The browser requests at most 180 seconds of mono 24k PCM WAV. Web Audio schedules retained spans. Its fallback slices the same samples and encodes a WAV for native HTML audio. Neither path fabricates speech or changes speed. Fallback activation does not certify every browser/OS combination.

## Verification and privacy

Use synthetic fixtures and temporary sessions for tests; never create test deletions in the user's live state. Commit source/tests and public synthetic examples only. Do not commit model weights, recorded media, user transcripts, review histories, local paths from diagnostic logs or screenshots containing private material.
