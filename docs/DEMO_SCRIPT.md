# DEMO SCRIPT — سند AI (≤ 2 minutes)

**Setup before recording:** `.\scripts\run.ps1` (or `./scripts/run.sh`), open `http://127.0.0.1:8000`, wait for the
green «النظام جاهز» dot (models warmed up). Browser at 1280×800, zoom 110%. All example inputs are the built-in
chips, so every result shown is real output of the app. Record in Arabic UI; switch to English once (shot 6).

| # | Time | Shot (screen) | Narration (Arabic) |
|---|---|---|---|
| 1 | 0:00–0:12 | Landing page; slow zoom on the tagline and the input box. | «كم مرة وصلك منشور يبدأ بـ"قال رسول الله ﷺ"… ولم تعرف: هل هذا صحيح؟ سند AI يتحقق من الآيات والأحاديث والأقوال المتداولة قبل أن تنشرها.» |
| 2 | 0:12–0:32 | Click chip «حديث موضوع (بالإنجليزية)». Loading steps animate; card appears 🔴 with the Dorar verdicts. | «منشور بالإنجليزية: "اطلبوا العلم ولو بالصين". يستخرج النظام الادعاء، ويبحث في المصادر، ويجد النص العربي في الدرر السنية، وينقل حكم العلماء كما هو: "باطل لا أصل له". النظام لا يُصدر حكمًا؛ بل ينقله بمصدره.» |
| 3 | 0:32–0:47 | Scroll to «بديل صحيح بالمعنى نفسه» and the Evidence Graph; click the nodes الادعاء → المصدر → التحقق. | «ويقترح بديلًا صحيحًا بالمعنى نفسه، مع مصدره وحكمه. ومخطط الأدلة يُظهر كل خطوة: الادعاء، المصدر، النص الأصلي، التحقق، ثم الصياغة النهائية.» |
| 4 | 0:47–1:02 | Click chip «حديث ضعيف». Card 🟡; show the four quoted «ضعيف» verdicts with graders and books. | «حديث متداول آخر: "كما تكونوا يولى عليكم". النتيجة: يحتاج مراجعة، مع أحكام أربعة من العلماء، كل حكم بكتابه ورقمه.» |
| 5 | 1:02–1:20 | Click chip «حديث صحيح». Card 🟢 90: source Sahih al-Bukhari 6138, original text with tashkeel, «النص كاملًا بالإسناد» expanded briefly. | «وحين يكون النص صحيحًا: نجده في صحيح البخاري برقم ٦١٣٨، ونعرض النص الأصلي بتشكيله، والإسناد كاملًا لمن أراد.» |
| 6 | 1:20–1:32 | Click chip «آية قرآنية». Card 🟢 100 with Uthmani text from Tanzil; toggle UI to English for 3 seconds and back. | «والآيات تُطابَق حرفيًا مع نص المصحف من مشروع تنزيل، بالرسم العثماني، بلا أي تعديل. والواجهة بالعربية والإنجليزية.» |
| 7 | 1:32–1:50 | Paste a mixed post (fabricated + authentic + verse), verify, click «جهّز للنشر»; show AR text with [1][2][3] and the Sources block; press «نسخ». | «وأخيرًا: جهّز للنشر. يعيد النظام كتابة منشورك: كل نص يُستبدل بأصله حرفيًا مع التوثيق، وما لا أصل له يُستبدل ببديل صحيح أو يُحذف. ثم يتحقق آليًا أن كل نص مقدّس موجود حرفيًا في المصادر.» |
| 8 | 1:50–2:00 | Footer principles; logo. | «سند AI: لا حكم من عند النظام، ولا نص مقدّس من توليد الذكاء الاصطناعي، وكل نتيجة معها دليلها.» |

**Mixed post for shot 7** (copy exactly):

```
فوائد اليوم:
قال رسول الله ﷺ: «اطلبوا العلم ولو بالصين»
وقال النبي ﷺ: «من كان يؤمن بالله واليوم الآخر فليكرم ضيفه»
قال تعالى: ﴿قل هو الله أحد الله الصمد﴾
```

**Tips:** hide the bookmarks bar; keep the mouse still while reading narration; if Dorar is offline the cached
results are identical (the demo inputs are pre-seeded).
