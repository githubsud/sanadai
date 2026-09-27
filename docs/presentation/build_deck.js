// Builds docs/presentation/SanadAI_Presentation.pptx (10 slides, Arabic RTL).
//   NODE_PATH=<dir with pptxgenjs> node docs/presentation/build_deck.js
// All figures and examples come from the app's real results (docs/EVALUATION.md, live runs).
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..", "..");
const P = (...p) => path.join(ROOT, ...p);
const C = { deep: "0B3B3A", teal: "14655F", gold: "C9A227", mint: "E6F2EF", ink: "16302F", muted: "5B706E",
            white: "FFFFFF", green: "1E8E5A", greenBg: "E3F5EC", amber: "B7791F", amberBg: "FDF3DF",
            red: "C0392B", redBg: "FBE7E4", line: "CFE2DD" };
const FONT = "Arial";            // ships with Office, full Arabic support
const W = 13.333, H = 7.5, M = 0.6;

function pngSize(file) {           // width/height from the PNG header
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
// No presentation-wide rtlMode: it would force RTL onto Latin/number boxes. Arabic boxes set rtlMode themselves.
pres.title = "سند AI — تحقّق قبل أن تنشر";
pres.author = "Ahmed Abayazid Mussaad";

// ---------- helpers ----------
// Arabic boxes: rtlMode + lang ar-SA. LTR boxes (rtlMode:false: URLs, numbers, tech names) must be tagged en-US,
// otherwise PowerPoint lays an ar-SA paragraph out right-to-left and reverses "98%", "3 / 10", "BGE-M3".
const T = (opts) => {
  const o = Object.assign({ fontFace: FONT, rtlMode: true, align: "right", isTextBox: true, lang: "ar-SA",
                            valign: "top", margin: 0 }, opts);
  if (o.rtlMode === false) o.lang = "en-US";
  return o;
};

function title(slide, text, color = C.deep, sub) {
  slide.addText(text, T({ x: M, y: 0.45, w: W - 2 * M, h: 0.8, fontSize: 32, bold: true, color, valign: "middle" }));
  if (sub) slide.addText(sub, T({ x: M, y: 1.2, w: W - 2 * M, h: 0.5, fontSize: 16, color: C.muted }));
}

function badge(slide, x, y, label, fill = C.gold, color = C.deep, d = 0.55) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
  slide.addText(label, T({ x, y, w: d, h: d, fontSize: 16, bold: true, color, align: "center", valign: "middle" }));
}

function card(slide, x, y, w, h, fill = C.white, border = C.line) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill },
    line: { color: border, width: 1 }, shadow: { type: "outer", color: "000000", opacity: 0.08, blur: 6, offset: 2, angle: 90 } });
}

// Images are pre-cropped to their box ratio (Chrome); `contain` fits an image inside a box keeping its ratio.
function image(slide, file, x, y, w, h) {
  slide.addImage({ path: file, x, y, w, h });
}

function imageContain(slide, file, x, y, w, h) {
  const s = pngSize(file), r = s.w / s.h;
  let iw = w, ih = w / r;
  if (ih > h) { ih = h; iw = h * r; }
  slide.addImage({ path: file, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih });
}

function footer(slide, n, dark = false) {
  slide.addText(`${n} / 10`, T({ x: M, y: H - 0.45, w: 1.5, h: 0.3, fontSize: 10,
    color: dark ? "9FC9C2" : C.muted, align: "left", rtlMode: false }));
}

// ---------- 1. cover ----------
{
  const s = pres.addSlide(); s.background = { color: C.deep };
  s.addImage({ path: P("docs", "presentation", "logo.png"), x: W - M - 1.1, y: 0.7, w: 1.1, h: 1.1 });
  s.addText("سند AI", T({ x: M, y: 1.9, w: W - 2 * M, h: 1.2, fontSize: 60, bold: true, color: C.white }));
  s.addText("تحقّق قبل أن تنشر", T({ x: M, y: 3.05, w: W - 2 * M, h: 0.7, fontSize: 30, bold: true, color: C.gold }));
  s.addText("أداة ذكية للتحقق من الآيات والأحاديث والأقوال المتداولة قبل نشرها: تجد النص الأصلي في المصادر الموثوقة، "
    + "وتنقل أحكام العلماء كما هي، وتقترح البديل الصحيح — دون أن يُصدر النظام حكمًا من عنده.",
    T({ x: W - M - 8.6, y: 3.9, w: 8.6, h: 1.1, fontSize: 17, color: C.mint, lineSpacingMultiple: 1.2 }));
  s.addText([
    { text: "المسار: ", options: { bold: true, color: C.gold } },
    { text: "أدوات المعرفة والتحقق لتمكين المعرّفين بالإسلام", options: { color: C.white, breakLine: true } },
    { text: "مقدّم الفكرة: ", options: { bold: true, color: C.gold } },
    { text: "أحمد أبايزيد مساعد — مشاركة فردية", options: { color: C.white } },
  ], T({ x: M, y: 5.3, w: W - 2 * M, h: 0.9, fontSize: 15, paraSpaceAfter: 4 }));
  s.addText("sanadai-zl6q.onrender.com   ·   github.com/githubsud/sanadai",
    T({ x: M, y: 6.45, w: W - 2 * M, h: 0.4, fontSize: 13, color: "9FC9C2", align: "right", rtlMode: false }));
  s.addNotes("سند AI: أداة تحقق للدعاة وصنّاع المحتوى. المسار: أدوات المعرفة والتحقق لتمكين المعرّفين بالإسلام.");
}

// ---------- 2. problem ----------
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "المشكلة: نصوص تُنسب إلى النبي ﷺ دون تثبّت");
  const items = [
    ["١", "أحاديث موضوعة وضعيفة", "منشورات تبدأ بـ«قال رسول الله ﷺ» ولا أصل لها، تُتداول على نطاق واسع."],
    ["٢", "ألفاظ آيات مُحرّفة", "تُنقل آيات بكلمة مغيَّرة أو ناقصة، ويصعب اكتشاف ذلك بالعين."],
    ["٣", "التحقق اليدوي مرهق", "يحتاج البحث في كتب متعددة ومعرفة أحكام العلماء، فيُعاد النشر بحسن نية."],
  ];
  const cw = 3.85, gap = 0.3, y = 1.65, ch = 2.55;
  items.forEach(([n, h, b], i) => {
    const x = W - M - cw - i * (cw + gap);
    card(s, x, y, cw, ch);
    badge(s, x + cw - 0.8, y + 0.3, n);
    s.addText(h, T({ x: x + 0.3, y: y + 0.35, w: cw - 1.25, h: 0.5, fontSize: 19, bold: true, color: C.deep }));
    s.addText(b, T({ x: x + 0.3, y: y + 1.05, w: cw - 0.6, h: 1.3, fontSize: 14, color: C.ink, lineSpacingMultiple: 1.15 }));
  });
  card(s, M, 4.55, W - 2 * M, 2.05, C.redBg, C.redBg);
  s.addText("مثال حقيقي متداول", T({ x: M + 0.35, y: 4.75, w: W - 2 * M - 0.7, h: 0.4, fontSize: 14, bold: true, color: C.red }));
  s.addText("«اطلبوا العلم ولو بالصين»", T({ x: M + 0.35, y: 5.15, w: W - 2 * M - 0.7, h: 0.6, fontSize: 24, bold: true, color: C.ink }));
  s.addText("قال فيه ابن حبان: «باطل لا أصل له» (المجروحين 1/489)، وحكم عليه الألباني بأنه «باطل» — ومع ذلك يُنسب إلى النبي ﷺ في آلاف المنشورات.",
    T({ x: M + 0.35, y: 5.75, w: W - 2 * M - 0.7, h: 0.7, fontSize: 14, color: C.ink }));
  footer(s, 2);
}

// ---------- 3. solution ----------
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "الحل: الصق المنشور… واحصل على الأصل وحكم العلماء");
  const steps = [
    ["١", "الصق النص أو الصورة", "بالعربية أو الإنجليزية، من أي منصة."],
    ["٢", "استخراج الادعاءات", "كل آية وحديث وقول منسوب، بنصه الحرفي من المنشور."],
    ["٣", "المطابقة ونقل الأحكام", "النص الأصلي ورقمه، ومقارنة الألفاظ كلمة بكلمة، وأحكام العلماء كما هي."],
    ["٤", "البديل وجهّز للنشر", "بديل صحيح للضعيف والموضوع، ومنشور جاهز بالنصوص الأصلية والتوثيق."],
  ];
  const cw = 2.85, gap = 0.2, y = 1.55, ch = 2.35;
  steps.forEach(([n, h, b], i) => {
    const x = W - M - cw - i * (cw + gap);
    card(s, x, y, cw, ch, C.mint, C.mint);
    badge(s, x + cw - 0.8, y + 0.25, n, C.teal, C.white);
    s.addText(h, T({ x: x + 0.25, y: y + 0.95, w: cw - 0.5, h: 0.45, fontSize: 16, bold: true, color: C.deep }));
    s.addText(b, T({ x: x + 0.25, y: y + 1.4, w: cw - 0.5, h: 0.9, fontSize: 12.5, color: C.ink, lineSpacingMultiple: 1.1 }));
    if (i < steps.length - 1)
      s.addText("◀", T({ x: x - gap - 0.02, y: y + ch / 2 - 0.2, w: 0.22, h: 0.4, fontSize: 14, color: C.gold, align: "center" }));
  });
  image(s, P("docs", "presentation", "crop-results.png"), M, 4.15, W - 2 * M, 2.65);
  footer(s, 3);
}

// ---------- 4. live demo ----------
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "من التطبيق: منشور بالإنجليزية… وحكم العلماء بالعربية");
  image(s, P("docs", "presentation", "crop-fabricated.png"), W - M - 7.9, 1.45, 7.9, 5.4);
  const notes = [
    ["١", "يربط النص الإنجليزي بأصله العربي في الدرر السنية."],
    ["٢", "ينقل الأحكام كما هي: ابن حبان «باطل لا أصل له»، والألباني «باطل»، وغيرهما."],
    ["٣", "إشارة حمراء: منسوب خطأً أو لا أصل له."],
    ["٤", "يقترح بديلًا صحيحًا بالمعنى نفسه مع حكمه ومصدره."],
  ];
  notes.forEach(([n, t], i) => {
    const y = 1.6 + i * 1.3;
    badge(s, M + 3.55, y, n);
    s.addText(t, T({ x: M, y: y - 0.05, w: 3.4, h: 1.1, fontSize: 14.5, color: C.ink, lineSpacingMultiple: 1.1 }));
  });
  footer(s, 4);
}

// ---------- 5. traffic light ----------
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "إشارة واضحة ودرجة سند لكل ادعاء", C.deep, "الدرجة تقيس ثقة المطابقة والأدلة — وليست حكمًا شرعيًا");
  const cols = [
    ["موثّق", C.green, C.greenBg, "آية مطابقة لنص المصحف، أو حديث صحيح/حسن.",
      [["«قل هو الله أحد»", "سورة الإخلاص 112:1", "100"], ["«من كان يؤمن بالله واليوم الآخر فليكرم ضيفه»", "صحيح البخاري 6138", "90"]]],
    ["يحتاج مراجعة", C.amber, C.amberBg, "حديث ضعيف، أو ألفاظ مغيَّرة، أو تطابق بالمعنى فقط.",
      [["«كما تكونوا يولى عليكم»", "أربعة أحكام: «ضعيف»", "75"]]],
    ["منسوب خطأً أو لا أصل له", C.red, C.redBg, "حكم عليه العلماء بالوضع، أو لم يُعثر عليه في المصادر المعتمدة.",
      [["«اطلبوا العلم ولو بالصين»", "«باطل لا أصل له»", "30"]]],
  ];
  const cw = 3.85, gap = 0.3, y = 1.95, ch = 4.75;
  cols.forEach(([name, color, bg, desc, ex], i) => {
    const x = W - M - cw - i * (cw + gap);
    card(s, x, y, cw, ch, bg, bg);
    s.addShape(pres.shapes.OVAL, { x: x + cw - 0.75, y: y + 0.3, w: 0.45, h: 0.45, fill: { color }, line: { color } });
    s.addText(name, T({ x: x + 0.25, y: y + 0.27, w: cw - 1.1, h: 0.5, fontSize: 18, bold: true, color }));
    s.addText(desc, T({ x: x + 0.25, y: y + 0.95, w: cw - 0.5, h: 0.95, fontSize: 13, color: C.ink, lineSpacingMultiple: 1.1 }));
    ex.forEach(([q, src, score], j) => {
      const ey = y + 2.0 + j * 1.3;
      card(s, x + 0.2, ey, cw - 0.4, 1.15, C.white, C.white);
      s.addText(score, T({ x: x + 0.3, y: ey + 0.12, w: 0.9, h: 0.9, fontSize: 26, bold: true, color, align: "center", valign: "middle" }));
      s.addText(q, T({ x: x + 1.2, y: ey + 0.1, w: cw - 1.55, h: 0.6, fontSize: 12.5, bold: true, color: C.ink }));
      s.addText(src, T({ x: x + 1.2, y: ey + 0.7, w: cw - 1.55, h: 0.35, fontSize: 11, color: C.muted }));
    });
  });
  footer(s, 5);
}

// ---------- 6. integrity principles (dark) ----------
{
  const s = pres.addSlide(); s.background = { color: C.deep };
  title(s, "الأمانة العلمية: مبادئ لا يتجاوزها النظام", C.white);
  const items = [
    ["١", "لا حكم من عند النظام", "كل حكم منقول من مصدره باسم قائله وكتابه ورقمه. الدرجة مقياس لثقة المطابقة، لا حكم شرعي."],
    ["٢", "لا يولّد الذكاء الاصطناعي نصًا شرعيًا", "دوره مقصور على استخراج الادعاءات وقراءة الصور، ويُرفض آليًا أي نص ليس في منشور المستخدم حرفيًا."],
    ["٣", "كل نتيجة معها دليلها", "ما لم يُعثر عليه يُقال فيه: «لم يُعثر عليه في المصادر المعتمدة». ونص القرآن حرفيًا من مشروع تنزيل دون تعديل."],
  ];
  items.forEach(([n, h, b], i) => {
    const y = 1.65 + i * 1.7;
    card(s, M, y, W - 2 * M, 1.45, C.teal, C.teal);
    badge(s, W - M - 0.95, y + 0.45, n);
    s.addText(h, T({ x: M + 0.4, y: y + 0.2, w: W - 2 * M - 1.7, h: 0.5, fontSize: 21, bold: true, color: C.gold }));
    s.addText(b, T({ x: M + 0.4, y: y + 0.72, w: W - 2 * M - 1.7, h: 0.65, fontSize: 15, color: C.white }));
  });
  footer(s, 6, true);
}

// ---------- 7. how it works ----------
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "كيف يعمل: بحث هجين ومطابقة كلمة بكلمة");
  const flow = [["المنشور", "نص أو صورة"], ["الاستخراج", "Gemini / Claude + قواعد"], ["البحث", "نصي + دلالي + إعادة ترتيب"],
                ["المقارنة", "كلمة بكلمة وإبراز الفروق"], ["الأحكام", "منقولة من المصادر"], ["النتيجة", "إشارة ودرجة وبديل"]];
  const fw = 1.78, fg = 0.22, fy = 1.5;
  flow.forEach(([h, b], i) => {
    const x = W - M - fw - i * (fw + fg);
    card(s, x, fy, fw, 1.25, i === flow.length - 1 ? C.teal : C.mint, i === flow.length - 1 ? C.teal : C.mint);
    const dark = i === flow.length - 1;
    s.addText(h, T({ x: x + 0.1, y: fy + 0.15, w: fw - 0.2, h: 0.4, fontSize: 15, bold: true, color: dark ? C.white : C.deep, align: "center" }));
    s.addText(b, T({ x: x + 0.1, y: fy + 0.6, w: fw - 0.2, h: 0.55, fontSize: 11, color: dark ? C.mint : C.ink, align: "center" }));
    if (i < flow.length - 1)
      s.addText("◀", T({ x: x - fg, y: fy + 0.42, w: fg, h: 0.4, fontSize: 12, color: C.gold, align: "center" }));
  });
  const src = [["6,236", "آية", "نص المصحف بالرسم العثماني — مشروع تنزيل"],
               ["50,703", "حديثًا", "من 17 كتابًا بالعربية والإنجليزية، و82 ألف حكم بأسماء المحدّثين"],
               ["الدرر السنية", "", "أحكام الأحاديث المتداولة و«الصحيح البديل»"]];
  const sw = 3.85, sg = 0.3, sy = 3.1;
  src.forEach(([big, unit, d], i) => {
    const x = W - M - sw - i * (sw + sg);
    card(s, x, sy, sw, 1.75);
    s.addText([{ text: big, options: { fontSize: 30, bold: true, color: C.teal } },
               { text: unit ? "  " + unit : "", options: { fontSize: 16, color: C.teal } }],
      T({ x: x + 0.3, y: sy + 0.2, w: sw - 0.6, h: 0.65 }));
    s.addText(d, T({ x: x + 0.3, y: sy + 0.95, w: sw - 0.6, h: 0.7, fontSize: 12.5, color: C.ink }));
  });
  s.addText("التقنيات:", T({ x: W - M - 1.3, y: 5.2, w: 1.3, h: 0.45, fontSize: 13.5, bold: true, color: C.deep }));
  s.addText("Python · FastAPI · SQLite FTS5 · BGE-M3 · bge-reranker-v2-m3 · ChromaDB · Gemini / Claude · HTML/CSS/JS",
    T({ x: M, y: 5.2, w: W - 2 * M - 1.45, h: 0.45, fontSize: 13.5, color: C.ink, rtlMode: false, align: "right" }));
  s.addText("البحث الحرفي أولًا: النص المنقول كما هو يُحسم في أقل من ثانية، والنماذج الدلالية للمطابقة بالمعنى وعبر اللغتين.",
    T({ x: M, y: 5.7, w: W - 2 * M, h: 0.45, fontSize: 13.5, color: C.muted }));
  footer(s, 7);
}

// ---------- 8. results ----------
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "النتائج: تقييم على 120 حالة اختبار", C.deep,
    "أحاديث صحيحة بصيغ مختلفة، وأحاديث ضعيفة وموضوعة متداولة، وآيات بعضها مُغيَّر عمدًا، وأمثال منسوبة خطأً");
  const stats = [["98%", "الوصول إلى المصدر الصحيح ضمن أفضل 5 نتائج", "المستهدف ≥ 90%"],
                 ["99.2%", "دقة الإشارة الضوئية", "موثّق / مراجعة / لا أصل له"],
                 ["100%", "استخراج الادعاءات", "من نص المنشور"],
                 ["0", "نص ضعيف أو موضوع عُرض على أنه موثّق", "أمان قبل كل شيء"]];
  const cw = 2.85, gap = 0.2, y = 2.0, ch = 3.35;
  stats.forEach(([n, l, sub], i) => {
    const x = W - M - cw - i * (cw + gap);
    card(s, x, y, cw, ch, i === 3 ? C.deep : C.mint, i === 3 ? C.deep : C.mint);
    s.addText(n, T({ x: x + 0.2, y: y + 0.35, w: cw - 0.4, h: 1.2, fontSize: 54, bold: true, color: i === 3 ? C.gold : C.teal,
      align: "center", rtlMode: false }));
    s.addText(l, T({ x: x + 0.25, y: y + 1.65, w: cw - 0.5, h: 0.95, fontSize: 14.5, bold: true, color: i === 3 ? C.white : C.deep, align: "center" }));
    s.addText(sub, T({ x: x + 0.25, y: y + 2.65, w: cw - 0.5, h: 0.5, fontSize: 11.5, color: i === 3 ? C.mint : C.muted, align: "center" }));
  });
  s.addText("التقرير الكامل وطريقة القياس منشوران في المستودع: docs/EVALUATION.md",
    T({ x: M, y: 5.75, w: W - 2 * M, h: 0.4, fontSize: 12.5, color: C.muted }));
  footer(s, 8);
}

// ---------- 9. prepare + image ----------
{
  const s = pres.addSlide(); s.background = { color: C.white };
  title(s, "«جهّز للنشر» وقراءة الصور");
  image(s, P("docs", "presentation", "crop-prepare.png"), W - M - 5.5, 1.45, 5.5, 5.25);
  s.addText("يعيد كتابة المنشور: كل نص متداول يُستبدل بأصله حرفيًا مع التوثيق، وما لا أصل له يُستبدل ببديل صحيح أو يُحذف — ثم يتحقق آليًا أن كل نص شرعي موجود حرفيًا في المصادر.",
    T({ x: M, y: 1.5, w: 6.4, h: 1.5, fontSize: 15, color: C.ink, lineSpacingMultiple: 1.15 }));
  card(s, M, 3.2, 6.4, 2.55, C.mint, C.mint);
  imageContain(s, P("docs", "demo", "synthetic_post.png"), M + 0.2, 3.35, 6.0, 1.95);
  s.addText("لقطة شاشة لمنشور (مثال مصنوع للاختبار): يقرأ النظام النص ويتحقق من الادعاءين.",
    T({ x: M + 0.2, y: 5.35, w: 6.0, h: 0.35, fontSize: 11.5, color: C.muted }));
  s.addText("مشاركة مباشرة عبر واتساب · إخراج بالعربية أو الإنجليزية مع ترجمة المعاني",
    T({ x: M, y: 6.0, w: 6.4, h: 0.5, fontSize: 13, bold: true, color: C.teal }));
  footer(s, 9);
}

// ---------- 10. impact + roadmap (dark) ----------
{
  const s = pres.addSlide(); s.background = { color: C.deep };
  title(s, "الأثر المتوقع والخطوة القادمة", C.white);
  const impact = [["الدعاة والمعرّفون بالإسلام", "محتوى موثّق بالنص الأصلي ومصدره."],
                  ["صنّاع المحتوى", "تحقق في ثوانٍ بدل البحث اليدوي."],
                  ["عامة المستخدمين", "ثقافة التثبت قبل المشاركة."]];
  impact.forEach(([h, b], i) => {
    const y = 1.55 + i * 1.02;
    badge(s, W - M - 0.55, y + 0.05, String.fromCharCode(0x0661 + i));
    s.addText(h, T({ x: W - M - 6.3, y: y, w: 5.6, h: 0.42, fontSize: 17, bold: true, color: C.gold }));
    s.addText(b, T({ x: W - M - 6.3, y: y + 0.42, w: 5.6, h: 0.45, fontSize: 14, color: C.white }));
  });
  card(s, M, 1.5, 5.6, 3.1, C.teal, C.teal);
  s.addText("خطة التطوير", T({ x: M + 0.3, y: 1.7, w: 5.0, h: 0.45, fontSize: 17, bold: true, color: C.gold }));
  const plan = ["مراجعة علمية من متخصصين لقوائم الاختبار والأحاديث المتداولة",
                "توسيع قاعدة الأحاديث الضعيفة والموضوعة المتداولة",
                "لغات إضافية: الأردية، الإندونيسية، الفرنسية",
                "بوت واتساب وإضافة للمتصفح للتحقق من داخل المحادثة"];
  plan.forEach((t, i) => {
    const y = 2.3 + i * 0.55;
    s.addShape(pres.shapes.OVAL, { x: M + 5.05, y: y + 0.13, w: 0.14, h: 0.14, fill: { color: C.gold }, line: { color: C.gold } });
    s.addText(t, T({ x: M + 0.3, y, w: 4.6, h: 0.45, fontSize: 13.5, color: C.white, valign: "middle" }));
  });
  card(s, M, 4.95, W - 2 * M, 1.55, C.white, C.white);
  s.addText("جرّبه الآن", T({ x: M + 0.35, y: 5.1, w: 6.5, h: 0.45, fontSize: 18, bold: true, color: C.deep, align: "left" }));
  s.addText([{ text: "sanadai-zl6q.onrender.com", options: { breakLine: true } }, { text: "github.com/githubsud/sanadai" }],
    T({ x: M + 0.35, y: 5.55, w: 6.5, h: 0.85, fontSize: 16, bold: true, color: C.teal, align: "left", rtlMode: false }));
  s.addText("سند AI — تحقّق قبل أن تنشر", T({ x: W - M - 5.5, y: 5.55, w: 5.2, h: 0.6, fontSize: 20, bold: true, color: C.deep }));
  footer(s, 10, true);
}

const out = P("docs", "presentation", "SanadAI_Presentation.pptx");
pres.writeFile({ fileName: out }).then((f) => console.log("written", f));
