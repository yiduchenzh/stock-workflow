# -*- coding: utf-8 -*-
"""Download douyin videos and transcribe with faster-whisper (Chinese).

Usage:
  python scripts/douyin_asr.py <outdir> [--model <name_or_path>] [--only-missing]
Reads  <outdir>/video_details.json  (needs "src")
Writes <outdir>/transcripts.json    (incrementally, atomic)
       <outdir>/media/<aweme_id>.mp4
"""
import json
import os
import re
import sys
import time
import urllib.request

OUT = None
MEDIA = None
MODEL_DIR = None

PROMPT = ("以下是A股股票技术分析讲解。涉及趋势、结构、K线、均线、MACD、回调、主升浪、"
          "小苹果模型、分型、支撑压力、止损止盈等术语。")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")


def aweme_id(url):
    m = re.search(r"/video/(\d+)", url or "")
    return m.group(1) if m else None


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def mp4_to_wav(mp4, wav):
    """16k mono PCM wav via bundled ffmpeg (avoids PyAV version issues)."""
    import subprocess
    exe = ffmpeg_exe()
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", mp4,
           "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", wav]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0 or not os.path.exists(wav) or os.path.getsize(wav) < 1000:
        raise RuntimeError("ffmpeg failed: " + p.stderr.decode("utf-8", "ignore")[-200:])
    return wav


def wav_to_float32(wav):
    import wave
    import numpy as np
    with wave.open(wav, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
        sw = w.getsampwidth()
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype("float32") / 2147483648.0
    else:
        raise RuntimeError("unsupported sample width %d" % sw)
    return a


def has_audio(mp4):
    import subprocess
    try:
        p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", mp4],
                           capture_output=True, timeout=60)
    except Exception:
        return False
    return "Audio:" in p.stderr.decode("utf-8", "ignore")


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        return True
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    })
    tmp = path + ".part"
    with urllib.request.urlopen(req, timeout=90) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
    os.replace(tmp, path)
    return os.path.getsize(path) > 20000


def main():
    global OUT, MEDIA
    outdir = sys.argv[1]
    OUT = os.path.join(outdir, "transcripts.json")
    MEDIA = os.path.join(outdir, "media")
    os.makedirs(MEDIA, exist_ok=True)
    model_name = "large-v3-turbo"
    if "--model" in sys.argv:
        model_name = sys.argv[sys.argv.index("--model") + 1]
    only_missing = "--only-missing" in sys.argv

    details = json.load(open(os.path.join(outdir, "video_details.json"), encoding="utf-8"))
    out = {}
    if os.path.exists(OUT):
        try:
            out = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            out = {}

    todo = []
    for href, v in details.items():
        aid = aweme_id(href)
        if not aid:
            continue
        if only_missing and aid in out and (out[aid].get("text") or "").strip():
            continue
        if not v.get("src"):
            print("no src for", href, flush=True)
            continue
        todo.append((aid, href, v))
    print("todo=%d cached=%d" % (len(todo), len(out)), flush=True)
    if not todo:
        return 0

    from faster_whisper import WhisperModel
    print("loading model %s ..." % model_name, flush=True)
    t0 = time.time()
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=8)
    print("model ready in %.1fs" % (time.time() - t0), flush=True)

    for n, (aid, href, v) in enumerate(todo, 1):
        mp4 = os.path.join(MEDIA, aid + ".mp4")
        cs = [c for c in (v.get("cands") or []) if c.get("url")]
        seen_u = set()
        cs = [c for c in cs if not (c["url"] in seen_u or seen_u.add(c["url"]))]
        # audio-bearing H.264 mp4 variants first (smallest first), then others
        pref = [c for c in cs if c.get("h265") == 0 and c.get("fmt") == "mp4"]
        pref.sort(key=lambda c: c.get("size") or 0)
        rest = [c for c in cs if c not in pref]
        urls = [c["url"] for c in pref] + [c["url"] for c in rest]
        if v.get("src") and v["src"] not in urls:
            urls.append(v["src"])
        if not urls:
            print("[%d/%d] %s no candidate urls" % (n, len(todo), aid), flush=True)
            continue

        got = os.path.exists(mp4) and has_audio(mp4)
        if not got:
            for ci, u in enumerate(urls):
                try:
                    if os.path.exists(mp4):
                        os.remove(mp4)
                    if not download(u, mp4):
                        print("   cand%d too small" % ci, flush=True)
                        continue
                    if has_audio(mp4):
                        got = True
                        print("   cand%d has audio (size=%d)" % (ci, os.path.getsize(mp4)), flush=True)
                        break
                    print("   cand%d no audio stream, next" % ci, flush=True)
                except Exception as e:
                    print("   cand%d dl FAIL %s" % (ci, str(e)[:70]), flush=True)
        if not got:
            print("[%d/%d] %s NO AUDIO in any candidate" % (n, len(todo), aid), flush=True)
            continue
        wav = os.path.join(MEDIA, aid + ".wav")
        try:
            if not os.path.exists(wav) or os.path.getsize(wav) < 1000:
                mp4_to_wav(mp4, wav)
            audio = wav_to_float32(wav)
        except Exception as e:
            print("[%d/%d] %s decode FAIL %s" % (n, len(todo), aid, str(e)[:90]), flush=True)
            continue
        try:
            t1 = time.time()
            segs, info = model.transcribe(audio, language="zh", beam_size=5,
                                          vad_filter=True, initial_prompt=PROMPT,
                                          condition_on_previous_text=False,
                                          without_timestamps=False)
            parts = []
            seglist = []
            for s in segs:
                parts.append(s.text.strip())
                seglist.append([round(s.start, 1), round(s.end, 1), s.text.strip()])
            text = "".join(parts)
            out[aid] = {"href": href, "title": (v.get("title") or "")[:200],
                        "dur": v.get("dur"), "asr": text, "segments": seglist,
                        "text": "", "src": v.get("src")}
            tmp = OUT + ".tmp"
            json.dump(out, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            os.replace(tmp, OUT)
            print("[%d/%d] %s OK %.1fs chars=%d" % (n, len(todo), aid, time.time() - t1, len(text)),
                  flush=True)
        except Exception as e:
            print("[%d/%d] %s ASR FAIL %s" % (n, len(todo), aid, str(e)[:90]), flush=True)
    print("done ->", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
