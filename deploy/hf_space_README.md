---
title: SanadAI سند
emoji: 📜
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Verify circulating hadith & Quran quotes with sources
---

<div dir="rtl">

# سند AI — تحقّق قبل أن تنشر

الصق منشورًا متداولًا (أو صورة له) بالعربية أو الإنجليزية: يستخرج سند AI الآيات والأحاديث والأقوال المنسوبة،
ويجد النص الأصلي في مصادر موثوقة، وينقل أحكام العلماء كما هي، ويقترح بديلًا صحيحًا، ويجهّز المنشور للنشر بالنصوص
الأصلية حرفيًا مع التوثيق. **لا حكم من عند النظام.**

</div>

**SanadAI** verifies circulating Quran verses, hadith and attributed sayings against Tanzil, 50,703 hadith from
17 collections and Dorar.net — quoting sources and scholars' gradings verbatim, never generating sacred text.

- Source code, documentation and evaluation: https://github.com/githubsud/sanadai
- This public demo runs on a free CPU: the first request after the Space wakes up can take a minute.
  AI claim extraction / screenshot reading are rate-limited per visitor; beyond the limit the rule-based extractor
  is used.
