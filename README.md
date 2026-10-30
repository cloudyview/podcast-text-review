# Podcast Text Review

Local-first, human-in-the-loop video editing through timed text. Includes a reusable **Codex skill**, a browser review workbench and Python command-line tools. **MIT licensed.**

Choose spoken words, inspect their source audio, adjust boundaries on a waveform, audition the join and confirm a non-destructive deletion. Keep the original recording and a complete history of review decisions.

**人工文字审校**：连续原文选字词 → 原声定位 → 波形微调 → 试听删除后的衔接 → 确认。支持自动保存、恢复、撤销/重做、说话人分段和阅读标点。不会用总结稿或翻译稿替代逐字原话。

## What runs where?

| Component | Job |
|---|---|
| Python 3.10+ standard library | Local HTTP server, immutable session baseline, revision checks and operation log |
| Browser JavaScript | Text selection, waveform and review controls |
| Web Audio | Source-PCM playback and scheduled join audition |
| HTML audio fallback | Play a locally assembled PCM WAV if Web Audio is unavailable or fails; manual play controls appear if autoplay is blocked |
| FFmpeg / ffprobe | Probe media, extract short source WAVs, optional browser-compatible video proxy and **explicit** video export |
| Local ASR | Produce a working transcript when no matching transcript exists |

**No Node.js, npm, cloud transcription account or API key is required to run the core tool.** Node is optional for JavaScript tests. Clicking Delete saves ranges and history; it does not invoke a full video render. Local audio extraction may invoke FFmpeg; the audition then plays locally in the browser. Only `export-video` renders an edited file.

## Quick start

```sh
git clone https://github.com/cloudyview/podcast-text-review.git
cd podcast-text-review
python3 review.py doctor
```

Install missing FFmpeg explicitly:

```sh
python3 review.py doctor --install ffmpeg --dry-run
python3 review.py doctor --install ffmpeg
```

The installer supports existing Homebrew on macOS, apt/dnf/pacman on Linux, and winget on Windows. It does not install a package manager, hide administrator prompts, or claim success if the binaries remain unavailable. On Windows use `py -3` if `python3` is not available; restart the terminal after PATH changes. Python must already be installed.

### Existing timed transcript

```sh
python3 review.py new --media /path/to/video.mp4 \
  --transcript /path/to/same-version.srt --session /path/to/review-session \
  --title 'My podcast review' --no-align
python3 review.py serve --session /path/to/review-session --open
```

This reuses the supplied text and starts in manual waveform-boundary mode. SRT or timed JSON is accepted. Untimed TXT cannot establish audio boundaries. A subtitle translated or paraphrased from speech is **not** a suitable word-deletion transcript.

To prepare machine timing candidates from the actual source audio:

```sh
python3 review.py doctor --install whisper       # Homebrew install; other platforms: see below
python3 review.py download-model base
python3 review.py align --session /path/to/review-session \
  --model /path/to/ggml-base.bin --language en
```

### No subtitles: local speech recognition

```sh
python3 review.py new --media /path/to/video.mp4 \
  --session /path/to/new-review --title 'My podcast' --language en
python3 review.py serve --session /path/to/new-review --open
```

The default Whisper path requires `whisper-cli` and downloads the selected model from its official model repository on first use, validating its SHA256 from vendor metadata. `--model /path/to/model.bin` reuses a local model; `--model-name small` chooses another supported download. There is no upload of the recording. Existing same-clock text is reused; it is not automatically rewritten.

**Verbatim matters.** ASR is fallible, and some engines normalize dialect speech into a different written form even in transcription mode. The tool retains raw recognition output and never runs a summarizer, translator or prose rewrite over the review text. Test a representative sample before trusting dialect word deletions; unsupported or mismatched words must use manual audio-boundary review. Reading punctuation is appended without changing lexical characters, and raw text remains available.

### Speakers and paragraphs

Supply known speaker turns rather than guessing names from the video layout:

```sh
python3 review.py new --media /path/to/video.mp4 --transcript /path/to/verbatim.srt \
  --speaker-turns examples/speaker-turns.json --session /path/to/speaker-review --no-align
```

Turns are `{start, end, speaker}` in source seconds. The UI starts a new paragraph on speaker changes, sentence endings, pauses, and long reading blocks. Cross-speaker uncertainty is marked for review. Without speaker metadata, the UI says **speaker unassigned**, rather than pretending to perform speaker diarization. Speaker names are not inferred automatically by the core package.

### Browser compatibility

Open the printed **localhost** URL in a modern browser. Web Audio is preferred, with `webkitAudioContext` support and ordinary HTML audio fallback. Add `?audio=native` to exercise the fallback. These paths are capability-tested; not every browser/OS combination has been manually certified.

If a source codec/container cannot play in your browser, pass `--proxy` to `new`. This creates a separate H.264/AAC MP4 for playback, retaining source identity and original media. Proxy generation is optional because it can be expensive. HTTPS deployment, shared hosting and multiple-user editing are outside the scope of this loopback-only prototype.

## Review, save and export

1. Drag-select a word or phrase in continuous text; locate the candidate source range.
2. Listen to the selected audio and, when needed, adjust waveform/time boundaries in 20 ms steps.
3. Audition the join, then confirm. Partial/missing token matches require manual boundary adjustment; character-count timing is never fabricated.
4. Restore, undo or redo as needed. Wait for the saved indicator before closing the page.

Sessions keep `data/删改状态.json` (current marks), `data/删改过程.jsonl` (before/after history), and frozen transcript/assets. Restart the same session to resume. One writable server per session is enforced. A second tab with a stale revision cannot silently overwrite newer marks.

```sh
python3 review.py export-decisions --session /path/to/review-session --output /path/to/decisions.json
# Only this command renders video; it refuses to overwrite the output:
python3 review.py export-video --session /path/to/review-session --output /path/to/edited.mp4
```

Decision export merges overlapping cuts and maps retained source ranges onto a new clock. Video export re-encodes retained ranges; it is not a guarantee of editorial continuity or perfect phoneme boundaries. Listen to the actual export before delivery.

## Use as a skill

The repository root is a discoverable skill (`SKILL.md`, `agents/`, `scripts/`, `assets/`). Clone into a new directory under your agent's skills directory, or copy the repository there. Do not overwrite an existing skill/session to install an update. Invoke **`$podcast-text-review`** or ask to open a video for human text review. The skill calls these local tools; no MCP server registration is needed.

## Dependencies and models

- [FFmpeg downloads](https://ffmpeg.org/download.html): external runtime, not bundled.
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp): local ASR and experimental attention-DTW token candidates. On Linux/Windows, use upstream's CMake build instructions if a packaged `whisper-cli` is unavailable. The dependency doctor does not silently build a compiler toolchain.
- Model weights have their own licenses and are downloaded separately, never committed here.
- macOS's existing `swiftc` is optionally used for a small Foundation character-normalization helper **for matching only**. Displayed raw words are not normalized or rewritten.

## Development and limits

```sh
python3 -m unittest discover -s tests -v
node tests/test_audio.js    # optional Node 18+ test runner; not an application dependency
```

Tests use synthetic color/tone media and temporary sessions. They cover source identity, save/restart, committed-event recovery, revision conflicts, source ranges, speaker/punctuation lexical preservation, native-audio fallback and FFmpeg export. Local ASR also has a synthetic-speech smoke test; CI does not download large models.

This is an early tool for **human** review. Machine wording, speaker-turn metadata and timing candidates may be wrong; the UI requires listening and boundary confirmation. Keep session data outside this source checkout. Sessions, media, model weights, transcripts and logs are ignored by Git. No analytics or user recordings are included in this repository.

### Optional Apple Silicon Qwen backend

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-mlx.txt
.venv/bin/python review.py new --media /path/to/video.mp4 \
  --session /path/to/qwen-review --asr-engine mlx-qwen --language yue
```

This downloads separately licensed Qwen ASR and forced-aligner weights on first use, or accepts local model directories through `--mlx-model` and `--mlx-aligner`. It preserves raw model wording and outputs character/word timing candidates. Cantonese uses the aligner's CJK tokenizer; that choice does not translate the transcript. Automatic speaker identity is not part of this backend; pass known turns or correct the paragraph labels manually. `raw-*.json` audit files remain inside the local session cache.
