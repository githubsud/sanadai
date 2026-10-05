# ruff: noqa: E501, E702  -- shot steps are written one-per-line like a screenplay
"""Record the ≤2-minute demo video of SanadAI automatically (docs/DEMO_SCRIPT.md).

    python docs/video/make_demo_video.py [--url http://127.0.0.1:8010] [--no-voice]

1. Arabic narration per shot with edge-tts (Microsoft neural voice ar-SA-HamedNeural; only the narration text is
   sent to the speech service).
2. Drives the real app in headless Chrome (Playwright) and records 1280x720 video; each shot lasts at least as long
   as its narration; Arabic captions and a click-highlight ring are injected so the video reads without sound.
3. ffmpeg (imageio-ffmpeg): narration clips placed at each shot's start, encoded to MP4 (H.264 + AAC).
Dev tools: pip install playwright edge-tts imageio-ffmpeg. The app must be running (scripts/run.ps1 --port 8010).
"""

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "video" / "SanadAI_Demo.mp4"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VOICE = "ar-SA-HamedNeural"

MIXED_POST = ("فوائد اليوم:\nقال رسول الله ﷺ: «اطلبوا العلم ولو بالصين»\n"
              "وقال النبي ﷺ: «من كان يؤمن بالله واليوم الآخر فليكرم ضيفه»\nقال تعالى: ﴿قل هو الله أحد الله الصمد﴾")

SHOTS = [
    ("intro", "كم مرة وصلك منشور يبدأ بـ«قال رسول الله ﷺ»، ولم تعرف: هل هو صحيح؟ سند AI يتحقق قبل أن تنشر."),
    ("fabricated", "منشور بالإنجليزية: «اطلبوا العلم ولو بالصين». يستخرج سند الادعاء، ويجد نصه العربي في الدرر "
                   "السنية، وينقل حكم العلماء كما هو: باطل لا أصل له."),
    ("evidence", "ويقترح بديلًا صحيحًا بالمعنى نفسه، بمصدره وحكمه. ومخطط الأدلة يوضح كل خطوة، من الادعاء إلى "
                 "الصياغة النهائية."),
    ("weak", "حديث متداول آخر: «كما تكونوا يولى عليكم»: يحتاج مراجعة، مع أحكام أربعة من العلماء بكتبهم وأرقامها."),
    ("authentic", "وحين يكون النص صحيحًا، نجده في صحيح البخاري برقم ستة آلاف ومئة وثمانية وثلاثين، بنصه الأصلي "
                  "وإسناده الكامل."),
    ("quran", "والآيات تُطابَق حرفيًا مع نص المصحف من مشروع تنزيل، بالرسم العثماني دون أي تعديل. والواجهة بالعربية "
              "والإنجليزية."),
    ("prepare", "ثم: جهّز للنشر. يُستبدل كل نص بأصله حرفيًا مع التوثيق، وما لا أصل له ببديل صحيح، ويُتحقق آليًا "
                "من حرفية كل نص."),
    ("image", "ويقرأ لقطات الشاشة أيضًا: يستخرج النصوص من الصورة، ويتحقق منها بالطريقة نفسها."),
    ("outro", "سند AI: لا حكم من عند النظام، ولا نص شرعي من توليد الذكاء الاصطناعي، وكل نتيجة معها دليلها."),
]

OVERLAY_JS = r"""
(() => {
  if (document.getElementById('demo-cap')) return;
  const st = document.createElement('style');
  st.textContent = `
   #demo-cap{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:9999;max-width:1100px;width:88%;
     background:rgba(11,59,58,.92);color:#fff;border-radius:14px;padding:12px 22px;font:600 21px/1.6 'IBM Plex Sans Arabic',
     Tahoma,sans-serif;direction:rtl;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.25);transition:opacity .3s}
   #demo-cap:empty{opacity:0}
   .demo-ring{position:fixed;z-index:9998;width:46px;height:46px;margin:-23px 0 0 -23px;border:4px solid #C9A227;
     border-radius:50%;pointer-events:none;animation:demoRing .7s ease-out forwards}
   @keyframes demoRing{from{transform:scale(.4);opacity:1}to{transform:scale(1.6);opacity:0}}
   #demo-card{position:fixed;inset:0;z-index:10000;background:linear-gradient(160deg,#0B3B3A,#14655F);color:#fff;
     display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;direction:rtl;
     font-family:'IBM Plex Sans Arabic',Tahoma,sans-serif;transition:opacity .6s}
   #demo-card h1{font-size:76px;margin:0} #demo-card h2{font-size:34px;margin:0;color:#C9A227}
   #demo-card p{font-size:22px;margin:4px 0;color:#E6F2EF} #demo-card .links{direction:ltr;font-size:20px;color:#9FC9C2}
   #demo-card img{width:110px;height:110px}`;
  document.head.appendChild(st);
  const cap = document.createElement('div'); cap.id = 'demo-cap'; document.body.appendChild(cap);
})();
"""


def tts(text: str, path: Path) -> None:
    import edge_tts

    asyncio.run(edge_tts.Communicate(text, VOICE, rate="+12%").save(str(path)))


def duration(path: Path) -> float:
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010/")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--skip", nargs="*", default=[], help="shot names to leave out, e.g. image")
    a = ap.parse_args()
    global SHOTS
    SHOTS = [sh for sh in SHOTS if sh[0] not in a.skip]
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="sanad_video_"))

    # 1) narration
    clips = {}
    for name, text in SHOTS:
        mp3 = tmp / f"{name}.mp3"
        if not a.no_voice:
            tts(text, mp3)
            clips[name] = (mp3, duration(mp3))
        else:
            clips[name] = (None, max(4.0, len(text) / 14))
    print("narration:", {k: round(v[1], 1) for k, v in clips.items()}, "total", round(sum(v[1] for v in clips.values()), 1))

    # 2) recording
    starts: dict[str, float] = {}
    logo = (ROOT / "web" / "assets" / "logo.svg").read_text(encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(tmp),
                            record_video_size={"width": 1280, "height": 720})
        t_video0 = time.monotonic()
        pg = ctx.new_page()
        pg.goto(a.url)
        pg.wait_for_function("document.querySelector('#health')?.classList.contains('ok')", timeout=120000)
        pg.evaluate(OVERLAY_JS)
        t_ready = time.monotonic()

        def cap(text):
            pg.evaluate("t => { document.getElementById('demo-cap').textContent = t; }", text)

        def click(sel):
            box = pg.locator(sel).first.bounding_box()
            if box:
                pg.evaluate("""([x,y]) => { const r=document.createElement('div'); r.className='demo-ring';
                    r.style.left=x+'px'; r.style.top=y+'px'; document.body.appendChild(r); setTimeout(()=>r.remove(),800); }""",
                            [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
                pg.wait_for_timeout(350)
            pg.locator(sel).first.click()

        def scroll_to(sel, block="center"):
            pg.evaluate("([s,b]) => document.querySelector(s)?.scrollIntoView({behavior:'smooth', block:b})", [sel, block])
            pg.wait_for_timeout(900)

        def wait_results():
            try:
                pg.wait_for_function("!document.getElementById('loading').hidden", timeout=4000)
            except Exception:  # noqa: BLE001 - may finish before we look
                pass
            pg.wait_for_function("document.getElementById('loading').hidden && !document.getElementById('results').hidden",
                                 timeout=180000)
            pg.wait_for_timeout(700)

        def shot(name, actions):
            if name in a.skip:
                return
            starts[name] = time.monotonic() - t_video0
            text = dict(SHOTS)[name]
            cap(text)
            actions()
            remaining = clips[name][1] + 0.3 - (time.monotonic() - t_video0 - starts[name])
            if remaining > 0:
                pg.wait_for_timeout(int(remaining * 1000))

        def card(html):
            pg.evaluate("h => { const c=document.createElement('div'); c.id='demo-card'; c.innerHTML=h; document.body.appendChild(c); }", html)

        def uncard():
            pg.evaluate("() => { const c=document.getElementById('demo-card'); if(c){c.style.opacity=0; setTimeout(()=>c.remove(),700);} }")

        # --- shots ---
        card(f"{logo}<h1>سند AI</h1><h2>تحقّق قبل أن تنشر</h2><p>التحقق من الآيات والأحاديث والأقوال المتداولة — بالمصدر وحكم العلماء كما هو</p>")
        pg.evaluate("() => { const s=document.querySelector('#demo-card svg'); if(s){s.setAttribute('width',110);s.setAttribute('height',110);} }")
        shot("intro", lambda: (pg.wait_for_timeout(clips['intro'][1] * 1000 - 700), uncard()))

        def fabricated():
            click('[data-example="fabricated"]'); wait_results(); scroll_to("#claims .card .grades", "center")
        shot("fabricated", fabricated)

        def evidence():
            scroll_to("#claims .card .alt", "center"); pg.wait_for_timeout(900)
            scroll_to("#claims .card .graph-wrap", "center"); pg.wait_for_timeout(600)
            click("#claims .card .gnode >> nth=1"); pg.wait_for_timeout(1300)
            click("#claims .card .gnode >> nth=3")
        shot("evidence", evidence)

        def weak():
            pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})"); pg.wait_for_timeout(700)
            click('[data-example="weak"]'); wait_results(); scroll_to("#claims .card .grades", "center")
        shot("weak", weak)

        def authentic():
            pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})"); pg.wait_for_timeout(700)
            click('[data-example="authentic"]'); wait_results(); scroll_to("#claims .card .sacred", "center")
            pg.wait_for_timeout(1200); click("#claims .card details summary"); pg.wait_for_timeout(600)
            scroll_to("#claims .card details", "center")
        shot("authentic", authentic)

        def quran():
            pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})"); pg.wait_for_timeout(700)
            click('[data-example="quran"]'); wait_results(); scroll_to("#claims .card .sacred", "center")
            pg.wait_for_timeout(1000); click("#langToggle"); pg.wait_for_timeout(2200); click("#langToggle")
        shot("quran", quran)

        def prepare():
            pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})"); pg.wait_for_timeout(700)
            pg.fill("#postText", MIXED_POST); click("#verifyBtn"); wait_results()
            pg.wait_for_timeout(600); click("#prepareBtn"); pg.wait_for_timeout(400)
            # the <dialog> is in the browser's top layer: move the caption inside it so it stays visible
            pg.evaluate("() => document.getElementById('prepareModal').appendChild(document.getElementById('demo-cap'))")
            pg.wait_for_timeout(2000)
        shot("prepare", prepare)

        def image():
            pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
            pg.evaluate("() => document.body.appendChild(document.getElementById('demo-cap'))")
            pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})"); pg.wait_for_timeout(600)
            pg.fill("#postText", "")
            pg.set_input_files("#fileInput", str(ROOT / "docs" / "demo" / "synthetic_post.png"))
            pg.wait_for_timeout(1200); click("#verifyBtn"); wait_results()
        shot("image", image)

        # close the prepare dialog if still open (the image shot normally does it) and bring the caption back
        pg.evaluate("""() => { const d=document.getElementById('prepareModal'); if (d.open) d.close();
                       document.body.appendChild(document.getElementById('demo-cap')); }""")
        card(f"{logo}<h1>سند AI</h1><p>لا حكم من عند النظام · لا نص شرعي من توليد الذكاء الاصطناعي · كل نتيجة معها دليلها</p>"
             "<p class='links'>sanadai-zl6q.onrender.com · github.com/githubsud/sanadai</p>")
        pg.evaluate("() => { const s=document.querySelector('#demo-card svg'); if(s){s.setAttribute('width',110);s.setAttribute('height',110);} }")
        cap("")
        shot("outro", lambda: None)
        video_path = pg.video.path()
        ctx.close()
        t_close = time.monotonic() - t_video0
        b.close()

    # 3) compose. Playwright starts recording a little after t_video0: derive the true start of the video
    # from its duration (it ends when the context closes) and express every event in video time.
    video_start = max(0.0, t_close - duration(Path(video_path)))
    starts = {k: v - video_start for k, v in starts.items()}
    trim = max(0.0, t_ready - t_video0 - video_start - 0.1)
    length = (t_close - video_start) - trim
    cmd = [FFMPEG, "-y", "-ss", f"{trim:.2f}", "-i", str(video_path)]
    filt, labels = [], []
    if not a.no_voice:
        for i, (name, _t) in enumerate(SHOTS, start=1):
            cmd += ["-i", str(clips[name][0])]
            delay = int(max(0.0, starts[name] - trim + 0.25) * 1000)
            filt.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
            labels.append(f"[a{i}]")
        filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad[aout]")
        cmd += ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-t", f"{length:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(OUT)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        return 1
    print(f"video: {OUT}  length {length:.1f}s  size {OUT.stat().st_size / 1e6:.1f} MB")
    print("shot starts:", {k: round(v - trim, 1) for k, v in starts.items()})
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
