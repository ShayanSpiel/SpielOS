---
name: translation-fa
description: Translate SpielOS product, UX, website, onboarding, support, and marketing copy into living modern Persian. Use when translating any user-facing text from English to Persian/Farsi.
---

# SpielOS Persian Translation System

## Mission

Translate SpielOS into natural, modern Persian that sounds written by a smart Iranian founder and experienced UX writer.

Do not translate sentence structure. Rebuild the message for Persian-speaking users while preserving its exact meaning, product behavior, and intent.

The result must never sound like:

- A government website
- A bank advertisement
- A corporate presentation
- An academic translation
- Generic AI marketing
- Word-for-word English rendered in Persian

## Reference files

Before translating, read:

- `persian-glossary.md` — the single source of truth for all terminology
- `../../../company/strategy/icp.md` — the single source of truth for the customer profile (shared with copywriting skills)
- `../../copywriting/SKILL.md` — when the task involves creating content from work sessions, not translating existing copy

---

## Translation inputs

Before translating, identify:

1. **Surface**: hero, button, label, tooltip, onboarding, empty state, error, warning, documentation, marketing, or legal
2. **User**: founder, operator, technical builder, or general user
3. **Intent**: explain, guide, persuade, confirm, warn, or request action
4. **Action**: what the user can do or what just happened
5. **Constraint**: character limit, UI size, terminology, placeholders, and variables

Do not translate until these are clear from the source or surrounding context.

---

## Core translation method

### 1. Recover the real context

English often removes context that Persian naturally needs.

Bad:

> ۱۰ سال سیستم ساختم.

This is grammatically correct but meaningless in Persian. What kind of systems? For whom?

Good:

> ۱۰ سال برای استارتاپ‌ها سیستم ساختم.

Add context only when it is clearly supported by the source, product, or provided background. Never invent facts.

### 2. Translate the intention, not the grammar

Source: "Connect the tools your agent needs."

Bad:

> ابزارهای موردنیاز عامل خود را متصل نمایید.

Good:

> ابزارهایی رو وصل کن که ایجنت برای انجام کارش نیاز داره.

### 3. Make the actor and action clear

Prefer:

> ایجنت فایل‌ها رو می‌خونه و گزارش رو می‌سازه.

Avoid:

> گزارش با استفاده از اطلاعات فایل‌ها تولید می‌شود.

### 4. Prefer concrete verbs

Use: بساز، وصل کن، انتخاب کن، اجرا کن، متوقف کن، ادامه بده، بررسی کن، تأیید کن، بسپار، به خاطر بسپار، پاک کن

Avoid hiding actions behind nouns: مدیریت، انجام فرآیند، ایجاد امکان، بهره‌گیری، یکپارچه‌سازی، بهینه‌سازی

### 5. Explain outcomes before architecture

Good:

> اگر اجرا قطع بشه، از همون‌جایی که مونده ادامه پیدا می‌کنه.

Bad:

> زیرساخت اجرای پایدار و resumable.

Use technical architecture terms only when the user is configuring or learning the architecture.

### 6. Preserve substance

Do not simplify away important meaning merely to make the sentence casual.

Every translation must preserve:

- Who acts
- What happens
- Why it matters
- Important limits
- Risk or permanence
- Product capability
- Cause and effect

Natural Persian is not vague Persian.

### 7. Close sentences meaningfully in Persian

English copy often ends in fragments that Persian cannot carry. Every Persian sentence must be complete and natural on its own — it must not depend on the English source to make sense.

Bad:

> فایل‌ها لایه‌ی مواد خام SpielOS هستن. اسناد از کتابخانه، فضای ابری یا Google Drive رو وصل کن.

Good:

> فایل‌ها منابع SpielOS هستن. می‌تونی از طریق کتابخونه فایل‌ها، گوگل درایو یا کلاد وصلشون کنی و ازشون استفاده کنی.

If a Persian reader has to reverse-translate the sentence to understand it, rewrite it.

### 8. Problem sections must read as problems

Name the concrete actor and state what goes wrong. A bare, context-free statement is not a problem.

Bad:

> ایجنت‌ها بدون کانتکست کار می‌کنن.

Good:

> ایجنت‌های معمولی بدون کانتکست و دانش از موضوع کار می‌کنن.

### 9. Match subject and verb number

Plural Persian subjects take plural verbs — even when English uses a product name as a singular subject.

Bad:

> ایجنت‌ها چی فراهم می‌کنه.

Good:

> ایجنت‌ها چی فراهم می‌کنن.

Applies to every string: مهارت‌ها... می‌کنن، ارزیابی‌ها... می‌کنن، اتصالات... می‌کنن.

---

## Zero-context reader test

Before translating any article, note, landing page, or long-form section, assume the reader has not seen:

- The work session
- The prompt given to the agent
- Previous website drafts
- Internal product discussions
- The English source
- Earlier paragraphs from another page

Every opening must establish enough context to answer:

1. What happened?
2. Where did it happen?
3. Who was involved?
4. Why should the reader care?
5. What will this section explain?

Reject openings that begin with a conclusion before describing the situation.

Bad:

> اگه خروجی AI یکدست نیست، اولین واکنش اینه که تقصیر رو بندازی گردن مدل.

Better:

> وقتی ترجمه‌های فارسی سایت رو بررسی کردم، دیدم اصطلاحات اصلی محصول در هر صفحه متفاوت نوشته شدن. اولین حدس این بود که مدل ترجمه‌ی ضعیفی داره، اما مشکل اصلی جای دیگه بود: هنوز زبان مشخصی برای محصول تعریف نکرده بودیم.

---

## Full-document translation

Never translate long-form copy sentence by sentence in isolation.

Before writing Persian:

1. Read the complete source.
2. Summarize its central argument in one sentence.
3. Identify the intended reader.
4. Identify what the reader already knows.
5. Extract the event, evidence, decision, lesson, and CTA.
6. Identify English metaphors or slogans that cannot survive literally.
7. Create a Persian paragraph outline.
8. Write the Persian version from that outline.

The Persian article may use different sentence boundaries, paragraph lengths, and transitions from the English source. Preserve meaning and facts, not English syntax.

---

## Persian sentence completeness

Every sentence must contain a complete and useful thought.

Reject:

- Bare warnings
- Unfinished contrasts
- Lists disguised as sentences
- Nouns without a verb where Persian requires one
- References with no clear antecedent
- Sentences whose meaning depends on reverse-translating them into English

Bad:

> هیچ‌وقت سشن برای جلسه.

This is a fragment, not an instruction. It does not tell the reader what to do.

Good:

> برای session همیشه از «جلسه» یا «جلسه کاری» استفاده کن؛ «سشن» ننویس.

Bad:

> واژه‌های نقش و مهارت باید قفل می‌شدن.

Good:

> ترجمه‌ی واژه‌هایی مثل نقش و مهارت باید قبل از شروع کار تعریف و یکدست می‌شد.

Bad:

> واژه‌نامه یه سیاهه‌ی تصمیمه.

Good:

> واژه‌نامه فهرست تصمیم‌های زبانی محصوله.

Bad:

> ردیه‌های صریح.

Good:

> واژه‌های ممنوع و دلیل ممنوع بودنشان.

Bad:

> وسوسه‌ی بزرگ یه داستان موازیه.

Good:

> خطر اینجاست که سایت شروع کنه نسخه‌ای خیالی از محصول رو توصیف کنه.

---

## Natural Persian collocations

Evaluate phrases, not only individual words. A sentence can use correct glossary terms and still be unnatural.

Reject literal combinations such as:

- حقیقت محصول بهره‌ی مرکب می‌ده
- برق بازاریابی
- داستان موازی
- معماری جواب است
- جستجو چیزی است که محصول است
- صفحه جای خودش را به دست می‌آورد
- ساختار آینه‌ی هارنس است
- بدهی محتوایی
- وسوسه‌ی بزرگ

Rewrite the underlying meaning using Persian expressions that naturally occur together. If you cannot say it naturally in spoken Persian, it does not belong in written Persian either.

### Common translation failures

These are real mistakes from production, not theoretical examples:

**Do not translate compound concepts word-by-word:**

- "Create videos from HTML" → NOT "ویدیو از HTML بساز" (word-for-word)
- Right: "از HTML ویدیو بساز" (natural Persian word order)

**Do not use meaningless calques:**

- "pipeline" → NOT "خط لول" (literal pipe翻译, meaningless in Persian)
- Right: "پایپلاین" or "ابزار" or "سیستم" depending on context

**Do not use wrong verb number:**

- "I built" → NOT "ساختیم" (we built)
- Right: "ساختم" (I built) — match the actual actor

**Do not break natural phrase structure:**

- "Install it. 3 steps." → NOT "نصبش کن. ۳ مرحله." (choppy, unnatural)
- Right: "توی ۳ مرحله نصبش کن" (one natural sentence)

**Do not use translated terms where a borrowed term is standard:**

- "skill" → NOT "مهارت" (sounds like a government brochure)
- Right: "اسکیل" (the product term, used consistently)

**Do not mix "ما" (we) and "من" (I) inconsistently:**

- If the founder is speaking as an individual, use "من" and first-person singular verbs
- "We built this pipeline" in founder voice → "با همین ابزار ساختم" (I built with this tool)

---

## Register control

Default public SpielOS Persian should be:

- Conversational
- Educated
- Direct
- Precise
- Modern
- Not slangy
- Not bureaucratic
- Not academic
- Not overly literary

Do not mix highly conversational grammar with formal vocabulary in the same sentence.

Bad:

> تاکسونومی‌ای که همراستا نباشه، بدهی محتوایی‌ست که تا ابد می‌پردازی.

Better:

> اگر ساختار محتوای سایت با خود محصول هماهنگ نباشه، مدت‌ها باید هزینه‌ی اصلاح و نگهداریش رو بدی.

Use more formal Persian only for:

- Legal copy
- Privacy
- Billing
- Security
- Irreversible deletion
- Serious warnings

---

## Explanation before terminology

A technically correct word is not automatically good copy.

Before using terms such as هارنس، ارکستریشن، کانتکست or پایپ‌لاین, ask whether the reader needs the term or the meaning.

For non-technical owners and operators, first explain what happens:

> چند ایجنت رو طوری به هم وصل کن که هرکدوم بخشی از کار رو انجام بدن.

Only then, where useful:

> این همون ارکستریشن ورک‌فلوئه.

See `persian-glossary.md` section B for the full list of contextual technical terms and their simpler alternatives.

---

## Default voice

Use clean conversational Persian:

- `تو`, not `شما`
- `رو`, not `را`
- `می‌سازه`, not `می‌سازد`
- `می‌تونه`, not `می‌تواند`
- `بهت نشون می‌ده`, not `به شما نمایش می‌دهد`
- Direct commands: `بساز`, `وصل کن`, `اجرا کن`, `ادامه بده`

Keep spelling and نیم‌فاصله clean.

The tone should be: direct, intelligent, warm, confident, compact, conversational but not slangy.

---

## Rules by UX surface

### Homepage hero

State one clear outcome. Do not tell the founder story here.

Good:

> تیم AI خودت رو بساز و هدایت کن.

Bad:

> پلتفرم جامع نسل بعدی برای تحول ایجنتیک شرکت‌ها

### Supporting text

Explain how the promise works:

> نقش‌ها رو تعریف کن، ابزارها و حافظه رو وصل کن و به ایجنت‌ها کار واقعی بسپار.

### Buttons

Use short, direct actions:

- ایجنت بساز
- ابزار وصل کن
- اجرا کن
- ادامه بده
- نتیجه رو ببین
- تأیید کن
- به لیست انتظار بپیوند

### Labels

Use nouns, not sentences:

- نقش‌ها
- ابزارها
- حافظه
- اجراها
- دسترسی‌ها

### Empty states

Say what is missing and what to do:

> هنوز نقشی نساختی. اولین نقش رو بساز و مشخص کن چه کاری انجام بده.

### Errors

Say what failed, whether work is safe, and the next action:

> مدل پاسخ نداد و اجرا متوقف شد. چیزی از دست نرفته؛ دوباره اجراش کن.

### Destructive warnings

Be clear and slightly more formal:

> این حافظه برای همیشه پاک می‌شود و قابل بازیابی نیست.

### Founder story

Keep context, causality, and lived experience:

> ۱۰ سال برای استارتاپ‌ها سیستم ساختم. SpielOS جاییه که همه‌ی اون تجربه‌ها در قالب یک محصول ایجنتیک جمع شدن.

Do not turn founder copy into motivational slogans.

---

## Showcase mockups and RTL

The feature pages render fake product UI ("showcases") so visitors can picture SpielOS. These mockups follow extra rules.

### Real product content only

Mockups must reflect the REAL SpielOS product. Never invent product names, workflows, models, or metrics.

Real references to use:

- Roles: Director, Growth Marketing Lead, Market Research Lead, Business Intelligence Analyst, Customer Support Lead, Product Operations Manager, HR Operations Partner
- Skills: `knowledge.search`, `memory.propose`, `file.read`, `generate.business-document`, `harness.create-draft`, `ask.user`
- Workflows: Marketing — Evidence-Backed Campaign Brief (nodes: Collect Evidence → Write Brief), Analytics Weekly Review, Competitor Research Brief
- Evals: Customer Safe Communication, Evidence Integrity, Operational Readiness
- Knowledge files: `company-profile.md`, `operating-principles.md`, `output-standard.md`, `department-marketing.md`, `template-campaign-brief.md`
- Memories: `evidence-policy.md`, `approval-policy.md`
- Providers: OpenAI-compatible, Anthropic, Mistral (no Google/Gemini)
- Models: Claude Sonnet 5, Claude Opus 5, Claude Haiku 4.5, Mistral Small, Mistral Medium 3.5, gpt-5.6
- Integrations: Gmail (search/read/draft/send email), Google Calendar, MCP catalog

File names, model names, and metric values stay as real proper nouns/data. Do not translate them.

### Routing through translations

Every user-facing string in a showcase goes through `t(locale, key)`. Never hardcode English in `.astro` markup. Use `t(locale, key, { param })` for `{count}`, `{value}`, `{time}`, `{stages}`, `{passed}/{total}`.

Persian mockup labels use the standard glossary terms.

### RTL

`[dir="rtl"]` pages mirror the layout. Directional icons must flip:

- `bx-chevron-right`, `bx-right-arrow`, `bx-arrow-right` → add `rtl-flip`
- `bx-chevron-left`, `bx-left-arrow` → do NOT add `rtl-flip`

This is handled by the `.rtl-flip` class in `base.css`. Any new directional icon must be verified for RTL.

### Aria labels

No hardcoded aria-labels. Use `t(locale, ...)` keys.

---

## Translation validation

After producing Persian, hide the English source and review only the Persian.

Ask:

- Is the subject clear?
- Is there a real verb?
- Does each pronoun have a clear referent?
- Does the first paragraph establish context?
- Does each paragraph logically follow the previous one?
- Could an Iranian reader understand it without translating it back into English?
- Would an Iranian founder actually say this aloud?
- Is any word technically valid but unnecessary?
- Is any sentence merely trying to sound intelligent?
- Is the register appropriate for this surface?

Rewrite until all answers are satisfactory.

---

## Output rules

Return only the final Persian copy unless notes or alternatives are requested.

Preserve exactly:

- Variables
- Placeholders
- Commands
- URLs
- IDs
- Code
- File paths
- Markdown structure when required

When context is insufficient, mark the uncertain phrase instead of inventing product meaning.

Specific, natural, and context-aware beats literal translation.
