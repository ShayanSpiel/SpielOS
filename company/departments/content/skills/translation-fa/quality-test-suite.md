# SpielOS Quality Test Suite

Shared bilingual test cases for translation-fa, copywriting-fa, and copywriting-en skills. At least 45 examples across all required categories.

Each example includes: source material, ICP and awareness level, weak output, why it fails, correct output (English and/or Persian), and which rule corrected it.

---

# PART 1: PERSIAN TRANSLATION TESTS

---

## P1. Homepage hero

**English source:**

> I spent 10 years building systems. SpielOS is where they became one product.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad Persian:**

> ۱۰ سال سیستم ساختم. SpielOS جاییه که همه‌شون یه محصول شدن.

**Why it fails:** "۱۰ سال سیستم ساختم" is grammatically correct but meaningless — what kind of systems? For whom? "همه‌شون" has no clear referent. The sentence only makes sense if you already know the English source.

**Correct Persian:**

> ۱۰ سال برای استارتاپ‌ها سیستم ساختم. SpielOS جاییه که همه‌ی اون تجربه‌ها و سیستم‌ها توش به یک محصول ایجنتیک تبدیل شدن.

**Rule:** Zero-context reader test + context recovery (translation skill §1).

---

## P2. Button

**English source:**

> Join the waitlist

**ICP:** Any awareness level. **Surface:** button.

**Bad Persian:**

> به لیست انتظار ملحق شوید

**Why it fails:** Uses شوید (formal "you") instead of بپیوند (imperative, conversational). The tone does not match SpielOS default voice.

**Correct Persian:**

> به لیست انتظار بپیوند

**Rule:** Default voice — `تو` form, direct commands (persian-glossary.md §F).

---

## P3. Empty state

**English source:**

> No roles created yet. Create your first role and define what it does.

**ICP:** Product-aware. **Surface:** empty state.

**Bad Persian:**

> هنوز نقشی وجود ندارد.

**Why it fails:** Incomplete. Does not tell the user what to do next. Persian requires a complete thought with action.

**Correct Persian:**

> هنوز نقشی نساختی. اولین نقش رو بساز و مشخص کن چه کاری انجام بده.

**Rule:** Sentence completeness, empty state rules (translation skill §Rules by UX surface).

---

## P4. Error

**English source:**

> Model did not respond and the run stopped. Nothing was lost — retry.

**ICP:** Product-aware. **Surface:** error.

**Bad Persian:**

> مدل پاسخ نداد.

**Why it fails:** Does not tell the user whether work is safe or what to do next. Incomplete error message.

**Correct Persian:**

> مدل پاسخ نداد و اجرا متوقف شد. چیزی از دست نرفته؛ دوباره اجراش کن.

**Rule:** Error surface rules — say what failed, whether work is safe, next action (translation skill §Rules by UX surface).

---

## P5. Destructive warning

**English source:**

> This memory will be permanently deleted and cannot be recovered.

**ICP:** Product-aware. **Surface:** destructive warning.

**Bad Persian:**

> این حافظه پاک می‌شه و دیگه برنمی‌گرده.

**Why it fails:** Too casual for an irreversible action. Destructive warnings need slightly more formal Persian to convey severity.

**Correct Persian:**

> این حافظه برای همیشه پاک می‌شود و قابل بازیابی نیست.

**Rule:** Destructive warning surface — clear, slightly more formal (translation skill §Rules by UX surface).

---

## P6. Feature description — subject/verb agreement

**English source:**

> Roles define AI employees with personalities, rules, and contracts.

**ICP:** Solution-aware. **Surface:** feature description.

**Bad Persian:**

> نقش‌ها کارمندAI رو با شخصیت، قوانین و قرارداد تعریف می‌کنه.

**Why it fails:** Subject-verb number disagreement. "نقش‌ها" is plural, so the verb must be "تعریف می‌کنن" not "تعریف می‌کنه."

**Correct Persian:**

> نقش‌ها کارمندهای AI رو با شخصیت، قوانین و قرارداد تعریف می‌کنن.

**Rule:** Subject-verb number agreement (translation skill §9).

---

## P7. Technical documentation

**English source:**

> Orchestration coordinates multiple agents to execute a workflow.

**ICP:** Solution-aware, technical. **Surface:** documentation.

**Bad Persian:**

> ارکستریشن هماهنگ‌سازی چند ایجنت برای اجرای ورک‌فلو است.

**Why it fails:** Uses "هماهنگ‌سازی" (noun form) instead of a concrete verb structure. Sounds translated and stiff.

**Correct Persian:**

> ارکستریشن یعنی چند ایجنت رو طوری هماهنگ کنی که با هم یه ورک‌فلو رو اجرا کنن.

**Rule:** Explanation before terminology (translation skill §Explanation before terminology).

---

## P8. Founder story

**English source:**

> I packed those lessons into SpielOS: a platform for building and directing AI employees and departments.

**ICP:** Problem-aware. **Surface:** founder story.

**Bad Persian:**

> اون درس‌ها رو ریختم تو SpielOS: یه سکوی که تیم‌ها و بخش‌های AI رو بسازی و هدایت کنی.

**Why it fails:** "سکوی" sounds like a government translation. "بخش‌های AI" violates the glossary — must be "دپارتمان‌های AI." The sentence also loses the causality of "packed those lessons into."

**Correct Persian:**

> SpielOS جاییه که همه‌ی اون سیستم‌ها و تجربه‌ها در قالب یک محصول ایجنتیک جمع شدن: محصولی برای ساختن و هدایت کارمندها و دپارتمان‌های AI.

**Rule:** Glossary compliance (persian-glossary.md §A: دپارتمان not بخش), founder story surface.

---

## P9. Problem section

**English source:**

> Agents work without context. They do not know the company, the product, or the team.

**ICP:** Problem-aware. **Surface:** problem section.

**Bad Persian:**

> ایجنت‌ها بدون کانتکست کار می‌کنن.

**Why it fails:** Does not name the concrete actor or state what goes wrong. Too vague to read as a problem.

**Correct Persian:**

> ایجنت‌های معمولی بدون کانتکست و دانش از موضوع کار می‌کنن. نه شرکتت رو می‌شناسن، نه محصولت رو، نه تیمت رو.

**Rule:** Problem sections must read as problems — name the actor and state what goes wrong (translation skill §8).

---

## P10. Context recovery

**English source:**

> The system continues from where it stopped.

**ICP:** Solution-aware. **Surface:** feature description.

**Bad Persian:**

> سیستم ادامه می‌ده.

**Why it fails:** "سیستم ادامه می‌ده" is incomplete — continues what? From where? The sentence only makes sense with the English source.

**Correct Persian:**

> اگه اجرا قطع بشه، از همون‌جایی که مونده ادامه پیدا می‌کنه.

**Rule:** Context recovery, sentence completeness (translation skill §1, §7).

---

## P11. Banned word — راهکار

**English source:**

> An intelligent solution for optimizing business processes.

**ICP:** Problem-aware. **Surface:** marketing copy.

**Bad Persian:**

> راهکار هوشمند برای بهینه‌سازی فرآیندهای کسب‌وکار.

**Why it fails:** "راهکار" is banned corporate filler. "بهینه‌سازی فرآیندهای کسب‌وکار" is empty jargon.

**Correct Persian:**

> کارهای تکراری تیمت رو به ایجنت‌ها بسپار.

**Rule:** Banned words (persian-glossary.md §D), concrete verbs (translation skill §4).

---

## P12. Register mixing

**English source:**

> If the taxonomy is not aligned, you are paying a content debt forever.

**ICP:** Solution-aware. **Surface:** article.

**Bad Persian:**

> تاکسونومی‌ای که همراستا نباشه، بدهی محتوایی‌ست که تا ابد می‌پردازی.

**Why it fails:** Mixes conversational grammar ("نباشه", "می‌پردازی") with formal/legal vocabulary ("بدهی محتوایی‌ست", "تا ابد"). The registers clash.

**Correct Persian:**

> اگر ساختار محتوای سایت با خود محصول هماهنگ نباشه، مدت‌ها باید هزینه‌ی اصلاح و نگهداریش رو بدی.

**Rule:** Register control — do not mix registers in the same sentence (translation skill §Register control).

---

## P13. Feature page — calque + dangling phrase

**English source:**

> Files are the raw material layer of SpielOS. Connect documents from libraries, cloud storage, or Google Drive.

**ICP:** Product-aware. **Surface:** feature page.

**Bad Persian:**

> فایل‌ها لایه‌ی مواد خام SpielOS هستن. اسناد از کتابخانه، فضای ابری یا Google Drive رو وصل کن.

**Why it fails:** "لایه‌ی مواد خام" is a literal calque. "اسناد از کتابخانه..." is a dangling phrase that does not close meaningfully in Persian.

**Correct Persian:**

> فایل‌ها منابع SpielOS هستن. می‌تونی از طریق کتابخونه فایل‌ها، گوگل درایو یا کلاد وصلشون کنی و ازشون استفاده کنی.

**Rule:** Sentence completeness, concrete vocabulary (translation skill §7, persian-glossary.md §A: منبع/منابع not لایه‌ی مواد خام).

---

## P14. CTA — academic calque

**English source:**

> Explore SpielOS

**ICP:** Any awareness level. **Surface:** CTA.

**Bad Persian:**

> SpielOS رو کاوش کن

**Why it fails:** "کاوش کن" is an academic calque. No one says this in conversational Persian.

**Correct Persian:**

> SpielOS رو ببین

**Rule:** Default voice, concrete verbs (translation skill §4, persian-glossary.md §F).

---

## P15. Terminology — wrong adjective form

**English source:**

> Agent systems require orchestration, context, memory, and evaluation.

**ICP:** Solution-aware. **Surface:** feature description.

**Bad Persian:**

> سیستم‌های ایجنت به ارکستریشن، کانتکست، حافظه و ارزیابی نیاز دارن.

**Why it fails:** "سیستم‌های ایجنت" violates the glossary — must be "سیستم‌های ایجنتیک" (adjective form).

**Correct Persian:**

> سیستم‌های ایجنتیک به ارکستریشن، کانتکست، حافظه و ارزیابی نیاز دارن.

**Rule:** Locked product labels — ایجنتیک not ایجنت as adjective (persian-glossary.md §A).

---

## P16. Social post — fragment only meaningful in English

**English source:**

> Just shipped: the glossary that fixed our translation. Turns out the problem was not the model — it was the missing contract between product and language.

**ICP:** Problem-aware, technical. **Surface:** X post.

**Bad Persian:**

> تازه منتشر کردیم: واژه‌نامه‌ای که ترجمه رو درست کرد. معلوم شد مشکل مدل نبود — قراردادی که بین محصول و زبان وجود نداشت.

**Why it fails:** "تازه منتشر کردیم" is stiff. "قراردادی که بین محصول و زبان وجود نداشت" is a fragment that only makes sense if you already know the context.

**Correct Persian:**

> واژه‌نامه‌ای ساختیم که ترجمه رو درست کرد. مشکل مدل نبود — محصول هنوز زبان خودش رو نداشت.

**Rule:** Sentence completeness, zero-context reader test (copywriting skill §Quality gates).

---

## P17. SEO paragraph — literal translation

**English source:**

> SpielOS is an AI employee platform that lets you build and manage AI departments with roles, skills, and workflows.

**ICP:** Problem-aware. **Surface:** SEO paragraph.

**Bad Persian:**

> SpielOS یک پلتفرم کارمند AI است که به شما امکان می‌دهد دپارتمان‌های AI با نقش‌ها، مهارت‌ها و ورک‌فلوها بسازید و مدیریت کنید.

**Why it fails:** Uses شما (formal). "پلتفرم کارمند AI" is awkward. Sounds translated.

**Correct Persian:**

> SpielOS محصولیه که باهاش تیم‌ها و دپارتمان‌های AI می‌سازی. نقش‌ها، مهارت‌ها و ورک‌فلوها رو تعریف می‌کنی و کارمندهای AI مثل یه تیم واقعی کار می‌کنن.

**Rule:** Default voice (تو form), register control, natural collocations.

---

## P18. Localization — literal calque for "building"

**English source:**

> Building in public

**ICP:** Problem-aware, founder. **Surface:** article title/concept.

**Bad Persian:**

> ساختن در عام

**Why it fails:** "در عام" is a literal calque that no Persian speaker uses. "Building in public" is an English concept that needs a Persian explanation.

**Correct Persian:**

> ساختن جلوی چشم همه

Or:

> مسیر ساخت محصول رو عمومی منتشر کردن

**Rule:** Translate intention not grammar, contextual terms (persian-glossary.md §C: building).

---

## P19. Slogan overuse

**English source:**

> One architecture, two languages, zero fiction.

**ICP:** Solution-aware. **Surface:** article closing.

**Bad Persian:**

> یه معماری، دو زبان، صفر داستان خیالی.

**Why it fails:** Slogan construction that sounds dramatic but communicates little. If repeated in the same article as other slogan lines, the writing sounds generated.

**Correct Persian:**

> SpielOS یه ساختار داره که هم فارسی و هم انگلیسی باهاش کار می‌کنن — بدون نسخه‌ی خیالی از محصول.

**Rule:** Evidence over slogans — keep a line only when it adds meaning (copywriting skill §Evidence over slogans).

---

## P20. Contextual term — contextual terms not fixed translations

**English source:**

> Building systems for startups

**ICP:** Problem-aware. **Surface:** founder story.

**Bad Persian:**

> بنا کردن سیستم‌ها برای استارتاپ‌ها

**Why it fails:** "بنا کردن" is a literal calque for "building." In the context of systems, Persian uses "ساختن" or "طراحی و ساختن."

**Correct Persian:**

> طراحی و ساخت سیستم‌ها برای استارتاپ‌ها

**Rule:** Contextual terms — building (persian-glossary.md §C).

---

# PART 2: ENGLISH COPYWRITING TESTS

---

## E1. Context-free opening

**Work-session input:**

> When I asked an AI agent to design SpielOS's SEO structure, it created dozens of team pages, solutions, and templates — pages for features that did not exist in the product yet.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad English:**

> Everyone wants a marketing taxonomy.

**Why it fails:** Starts with an abstract thesis. Assumes the reader already knows why taxonomy matters. No context, no evidence, no situation.

**Correct English:**

> When I asked an AI agent to plan SpielOS's SEO structure, it proposed dozens of pages for teams, templates, and solutions that did not exist in the product.

**Rule:** Reader-context rule (copywriting-en §Reader-context rule).

---

## E2. Session log versus reader-centered story

**Work-session input:**

> Reviewed FA translations. Found inconsistent terminology. Built glossary. Tested again. Output improved.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad English:**

> We reviewed the translations. Found inconsistent terminology. Built a glossary. Tested again. Output improved.

**Why it fails:** Chronological session log. Does not address the reader's problem. No evidence, no tension, no lesson.

**Correct English:**

> Bad translation does not always come from a bad model. Sometimes the product has not decided how to describe itself. I discovered this when three SpielOS pages had three different translations for the same concept.

**Rule:** Work sessions are evidence, not structure (copywriting-en §Work sessions are evidence).

---

## E3. Feature inventory versus outcome

**Work-session input:**

> SpielOS has roles, skills, workflows, memory, tool connections, approvals, evals, Direct Mode, Director Mode.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad English:**

> SpielOS has roles, skills, workflows, memory, tool connections, approvals, evaluations, and execution modes.

**Why it fails:** Feature inventory dumped into positioning. The reader does not know why any of these matter.

**Correct English:**

> Your AI employees need clear roles, instructions, company knowledge, and a way to hand work between them. SpielOS gives you all of that in one system.

**Rule:** Product truth versus customer language (copywriting-en §Product truth versus customer language).

---

## E4. Internal jargon versus customer language

**Work-session input:**

> Added persistent context layer to the harness. Orchestrates multi-agent workflows with evaluation gates.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad English:**

> Added persistent context infrastructure to the harness. Orchestrates multi-agent workflows with evaluation gates.

**Why it fails:** Internal architecture labels. The reader may not know what a harness, orchestration, or evaluation gate is.

**Correct English:**

> Your agents now remember company context between sessions. When one agent finishes its part, the next one picks up where it left off — and you can review the work before it moves forward.

**Rule:** Customer language over internal labels (copywriting-en §Product truth versus customer language).

---

## E5. Problem-aware versus solution-aware copy

**Work-session input:**

> Direct Mode runs workflows step by step. Director Mode lets a long-running agent manage an entire pipeline.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad English (for problem-aware):**

> Direct Mode executes workflows. Director Mode manages pipelines.

**Why it fails:** Uses product-specific terms (Direct Mode, Director Mode, pipelines) without first establishing the problem.

**Correct English (for problem-aware):**

> Some work needs a single clear sequence. Other work needs an agent to manage a longer process with multiple steps. SpielOS handles both.

**Correct English (for solution-aware):**

> Direct Mode runs a workflow step by step. Director Mode lets a long-running agent manage an entire pipeline with checkpoints and approvals.

**Rule:** Awareness levels — do not write every page as if it addresses all levels (copywriting-en §Awareness levels).

---

## E6. Generic AI copy versus SpielOS-specific copy

**Work-session input:**

> SpielOS lets you define AI roles, give them instructions, connect tools, and run workflows with human approval.

**ICP:** Solution-aware founder. **Awareness:** medium.

**Bad English:**

> Unlock the power of AI employees. Transform your business with next-generation agentic workflows.

**Why it fails:** Generic AI language. Could belong to any AI startup. "Unlock the power" and "next-generation" are empty claims.

**Correct English:**

> Define an AI role, write its instructions, connect the tools it needs, and hand it real work. When something important comes up, you approve it before it goes out.

**Rule:** English voice — avoid generic SaaS language (copywriting-en §English voice, §Banned phrases).

---

## E7. Unsupported claims

**Work-session input:**

> Built a translation glossary. Terminology is now consistent across the site.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad English:**

> Our revolutionary glossary system ensures flawless multilingual content across all surfaces.

**Why it fails:** "Revolutionary" is unsupported. "Flawless" is false. "All surfaces" is unverifiable. Three empty claims in one sentence.

**Correct English:**

> I built a glossary that locks every product term to one Persian equivalent. Now the site uses the same language everywhere.

**Rule:** Evidence over slogans, banned phrases (copywriting-en §English voice, §Evidence over slogans).

---

## E8. Overwritten slogans

**Work-session input:**

> Translating sentence by sentence broke the article. Had to translate the full document first, then write Persian from a paragraph outline.

**ICP:** Problem-aware founder. **Awareness:** low.

**Bad English:**

> Sentence-by-sentence translation is death. Whole-document translation is life.

**Why it fails:** Dramatic contrast formula that sounds generated. Repeated constructions like this make writing feel AI-produced.

**Correct English:**

> Translating sentence by sentence broke the article. The Persian version only made sense if you already knew the English. I had to read the full piece, understand the argument, and rebuild it in Persian from a paragraph outline.

**Rule:** Avoid repeated contrast formulas (copywriting-en §English voice, §Evidence over slogans).

---

## E9. Product truth versus marketing claim

**Work-session input:**

> SpielOS supports marketing, research, support, analytics, HR, and documentation. But each requires setup and configuration.

**ICP:** Solution-aware founder. **Awareness:** medium.

**Bad English:**

> SpielOS handles your entire company's operations out of the box.

**Why it fails:** "Entire company's operations" overstates. "Out of the box" is false — setup is required.

**Correct English:**

> SpielOS can support work across marketing, research, support, analytics, HR, and documentation — but each area needs roles, instructions, and tool connections set up first.

**Rule:** Product truth (copywriting-en §Product truth versus customer language).

---

## E10. CTA — vague versus specific

**Work-session input:**

> User has read the founder story and understands the product.

**ICP:** Product-aware. **Surface:** CTA.

**Bad English:**

> Learn more.

**Why it fails:** Vague. Does not tell the reader what will happen next or why they should click.

**Correct English:**

> Join the waitlist

Or:

> See how SpielOS works

**Rule:** CTAs must be direct and specific (copywriting-en §CTAs).

---

# PART 3: BILINGUAL COMPARISON TESTS

These tests show the same evidence expressed naturally in both languages. Neither is a translation of the other.

---

## B1. Same evidence, different sentence structure

**Work-session input:**

> Three SpielOS pages had three different translations for "agent" — عامل, ایجنت, and missing entirely.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> Three SpielOS pages had three different translations for "agent." One used a dictionary calque, one used the product term, and one left it out entirely.

**Correct Persian:**

> سه صفحه‌ی SpielOS برای یک مفهوم واحد، سه ترجمه‌ی متفاوت داشتن. «ایجنت» یه جا عامل بود، یه جا ایجنت، یه جا اصلاً نبود.

**Why both work:** Each uses the sentence structure natural to its language. English uses a summary sentence then a list. Persian uses a setup sentence then a rhythmic three-part contrast. Neither copies the other's structure.

**Rule:** Shared bilingual content rule — sentence structure must not be forced to match.

---

## B2. Same problem, different opening style

**Work-session input:**

> Every agent starts from zero. The founder keeps repeating the same company context.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> Every new AI session starts from zero. I kept repeating the same company context — what the product does, who the customer is, what tone to use — in every conversation.

**Correct Persian:**

> هر جلسه‌ی AI از صفر شروع می‌شه. من مجبور بودم هر بار همون کانتکست شرکت رو تکرار کنم — محصول چیه، مشتری کیه، لحن چطوری باشه.

**Why both work:** English uses a declarative statement then first-person evidence. Persian uses the same structure but adds the specific examples (product, customer, tone) that Persian readers expect for completeness. The English version could stay more compact because English tolerates implication better.

**Rule:** Level of explicit context differs by language (shared bilingual content rule).

---

## B3. Same feature, different explanation depth

**Work-session input:**

> Roles define AI employees. Skills give them reusable abilities. Workflows connect them.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> Roles define your AI employees — who they are, what they do, and what rules they follow. Skills give them reusable abilities. Workflows connect them into a sequence.

**Correct Persian:**

> نقش‌ها کارمندهای AI رو تعریف می‌کنن — شخصیت، قوانین و محدودیت‌هاشون. مهارت‌ها بهشون قابلیت‌های تکراری می‌دن. ورک‌فلوها همه رو به هم وصل می‌کنن.

**Why both work:** English uses an em dash and a three-part list. Persian uses the same em dash pattern but adds "محدودیت‌هاشون" (their constraints) because Persian readers expect the boundary to be explicit. Neither is a translation of the other.

**Rule:** Explanation depth adapts to reader expectations per language.

---

## B4. Same opening, different register

**Work-session input:**

> Asked an agent to plan SEO. It invented features that don't exist.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> I asked an AI agent to plan SpielOS's SEO structure. It came back with pages for features the product does not have.

**Correct Persian:**

> از یک ایجنت خواستم ساختار سئوی SpielOS رو طراحی کنه. صفحه‌هایی پیشنهاد داد برای قابلیت‌هایی که هنوز در محصول وجود نداشتن.

**Why both work:** English is more compact — "came back with" is informal but efficient. Persian expands slightly because "هنوز در محصول وجود نداشتن" (did not yet exist in the product) needs the temporal marker "هنوز" for natural flow.

**Rule:** Register and explicitness adapt to language norms.

---

## B5. Same CTA, different wording

**Work-session input:**

> Reader has finished the founder story and wants to try the product.

**ICP:** Product-aware. **Surface:** CTA.

**Correct English:**

> Join the SpielOS waitlist

**Correct Persian:**

> به لیست انتظار SpielOS بپیوند

**Why both work:** English uses the imperative form directly. Persian adds the verb "بپیوند" because Persian CTAs need an explicit verb — a bare noun phrase feels incomplete.

**Rule:** CTA wording adapts to what feels natural in each language.

---

## B6. Same title concept, different phrasing

**Work-session input:**

> Deleted most of the pages an AI agent suggested because they described a product that doesn't exist.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> Why I deleted most of the pages an AI agent suggested for SpielOS

**Correct Persian:**

> چرا بیشتر صفحه‌های پیشنهادی AI رو از سایت حذف کردم

**Why both work:** English uses "most of the pages an AI agent suggested" — a relative clause. Persian uses "صفحه‌های پیشنهادی AI" — a compound noun phrase. Neither copies the other's syntax.

**Rule:** Headlines follow the natural word order of each language.

---

## B7. Same problem, different metaphor

**Work-session input:**

> Using AI without a system is like having employees with no instructions, no memory, and no manager.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> Using AI without a system is like hiring employees and giving them no instructions, no memory, and no manager.

**Correct Persian:**

> استفاده از AI بدون سیستم مثل اینه که کارمند بگیری ولی بهشون نه دستوری بدی، نه کانتکستی بدی، نه کسی مراقبشون باشه.

**Why both work:** English uses "hiring employees and giving them no..." — a compound verb structure. Persian uses "بگیری ولی بهشون نه... نه... نه..." — a rejection pattern that is natural in Persian for listing absences. The metaphor is the same; the expression is native to each language.

**Rule:** Metaphors and figures of speech must not be forced to match.

---

## B8. Same evidence, different paragraph break

**Work-session input:**

> The glossary locked every product term. The translation skill enforced sentence-level rules. The quality test caught remaining issues.

**ICP:** Solution-aware founder. **Awareness:** medium.

**Correct English:**

> The glossary locked every product term. The translation skill enforced sentence-level rules. The quality test caught remaining issues.

**Correct Persian:**

> واژه‌نامه هر اصطلاح محصول رو قفل کرد. مهارت ترجمه قواعد جمله‌سازی رو اعمال کرد. آزمون کیفیت مشکلات باقی‌مانده رو گرفت.

**Why both work:** In this case, both languages use the same three-sentence structure because the sentences are short and parallel. But the Persian version uses past tense ("کرد") where English uses present ("locks") because Persian copy reads more naturally in past tense for completed decisions.

**Rule:** Tense and aspect may differ even when structure is similar.

---

## B9. Same lesson, different level of explicit context

**Work-session input:**

> Built a glossary because translations were inconsistent. Problem was not the model — it was the missing contract between product and language.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> Bad translation does not always come from a bad model. Sometimes the product has not decided how to describe itself.

**Correct Persian:**

> ترجمه‌ی بد همیشه از مدل بد نمیاد. گاهی محصول هنوز تصمیم نگرفته با چه زبانی خودش رو توضیح بده.

**Why both work:** English is more compact — "decided how to describe itself" carries the full meaning in fewer words. Persian adds "با چه زبانی" (with what language) because the prepositional phrase is needed for the sentence to feel complete in Persian. English can leave it implicit.

**Rule:** Level of explicit context differs by language (shared bilingual content rule).

---

## B10. Same product truth, different customer language

**Work-session input:**

> SpielOS provides roles, skills, workflows, context, memory, tool connections, approvals, and evaluations.

**ICP:** Problem-aware founder. **Awareness:** low.

**Correct English:**

> Your AI employees need clear roles, instructions, and company knowledge. They need tools, memory, and a way to hand work between them. SpielOS gives you all of that.

**Correct Persian:**

> کارمندهای AI به نقش واضح، دستورات و دانش شرکت نیاز دارن. به ابزار، حافظه و راهی برای انتقال کار بینشون نیاز دارن. SpielOS همه‌ی اینا رو یکجا داره.

**Why both work:** Neither lists the full feature inventory. Both start with what the reader needs, then connect to the product. English uses "hand work between them" (idiomatic). Persian uses "انتقال کار بینشون" (more explicit). Both are natural for their audience.

**Rule:** Customer language over feature inventory (copywriting skills §Product truth versus customer language).

---

# PART 4: COPYWRITING-FA SPECIFIC TESTS

---

## F1. Iranian founder voice

**Work-session input:**

> The product had no consistent terminology. Different pages used different words for the same thing.

**ICP:** Iranian founder, problem-aware. **Surface:** article opening.

**Bad Persian:**

> محصول فاقد اصطلاحات یکپارچه بود. صفحات مختلف برای یک مفهوم از کلمات متفاوت استفاده می‌کردند.

**Why it fails:** "فاقد" and "یکپارچه" are formal/bureaucratic. "استفاده می‌کردند" uses the formal verb ending. An Iranian founder would not say this aloud.

**Correct Persian:**

> محصول هنوز زبان مشخصی نداشت. هر صفحه برای یه چیز یه اسم جداگانه گذاشته بود.

**Rule:** ICP simulation — how would an Iranian founder describe this aloud? (copywriting-fa §Persian-specific simulation questions).

---

## F2. Terms that need explanation

**Work-session input:**

> Added orchestration to the harness. Multi-agent workflows now coordinate through the pipeline.

**ICP:** Iranian founder, problem-aware. **Surface:** feature description.

**Bad Persian:**

> ارکستریشن رو به هارنس اضافه کردیم. ورک‌فلوهای چند ایجنتی حالا از طریق پایپ‌لاین هماهنگ می‌شن.

**Why it fails:** Dumps four technical terms (ارکستریشن, هارنس, ورک‌فلو, پایپ‌لاین) in one sentence without explanation. Problem-aware readers will not understand this.

**Correct Persian:**

> چند ایجنت رو طوری به هم وصل کردیم که با هم کار کنن. هرکدوم بخشی از کار رو انجام می‌ده و بقیه ادامه می‌دن.

**Rule:** Explanation before terminology, awareness levels (copywriting-fa §Persian-specific simulation questions, §Awareness levels).

---

## F3. Artificially translated search phrases

**Work-session input:**

> Target keyword: AI employee management platform

**ICP:** Problem-aware founder. **Surface:** SEO paragraph.

**Bad Persian:**

> پلتفرم مدیریت کارمند هوش مصنوعی

**Why it fails:** "پلتفرم مدیریت کارمند هوش مصنوعی" is an artificial compound that no one searches for. "کارمند هوش مصنوعی" is also a glossary violation — must be "کارمند AI."

**Correct Persian:**

> ابزاری برای ساختن و اداره کردن تیم AI

Or:

> سیستم کارمند و دپارتمان AI

**Rule:** Persian SEO localization — prefer phrases people naturally type (copywriting-fa §Persian SEO localization).

---

## F4. Sentences that only work with English source

**Work-session input:**

> The page explains what SpielOS does.

**ICP:** Problem-aware founder. **Surface:** article.

**Bad Persian:**

> صفحه توضیح می‌ده SpielOS چیه.

**Why it fails:** "توضیح می‌ده SpielOS چیه" is a calque of "explains what SpielOS is." In Persian, this should be structured differently.

**Correct Persian:**

> صفحه دقیقاً همون چیزی رو توضیح می‌ده که SpielOS واقعاً انجام می‌ده.

**Rule:** Each sentence must work without its English source (copywriting-fa §Persian-specific simulation questions).

---

# SUMMARY OF FAILURE MODES COVERED

| # | Category | Failure mode | Rule |
|---|---|---|---|
| P1 | Translation | Context-free opening | Zero-context reader test |
| P2 | Translation | Formal register in button | Default voice (تو form) |
| P3 | Translation | Incomplete empty state | Sentence completeness |
| P4 | Translation | Missing error action | Error surface rules |
| P5 | Translation | Wrong register for destructive warning | Destructive warning rules |
| P6 | Translation | Subject-verb disagreement | Number agreement |
| P7 | Translation | Stiff technical translation | Explanation before terminology |
| P8 | Translation | Glossary violation + bad calque | Glossary §A |
| P9 | Translation | Vague problem statement | Translation §8 |
| P10 | Translation | Meaningless without English | Context recovery |
| P11 | Translation | Corporate filler word | Glossary §D |
| P12 | Translation | Register mixing | Register control |
| P13 | Translation | Calque + dangling phrase | Sentence completeness + glossary |
| P14 | Translation | Academic calque for CTA | Concrete verbs |
| P15 | Translation | Wrong adjective form | Glossary §A |
| P16 | Translation | Fragment only meaningful in English | Sentence completeness |
| P17 | Translation | Literal SEO translation | Voice + register |
| P18 | Translation | Literal calque for "building" | Intention not grammar |
| P19 | Translation | Slogan overuse | Evidence over slogans |
| P20 | Translation | Literal calque for contextual term | Glossary §C |
| E1 | English | Context-free opening | Reader-context rule |
| E2 | English | Session log | Work sessions are evidence |
| E3 | English | Feature inventory | Customer language |
| E4 | English | Internal jargon | Customer language |
| E5 | English | Wrong awareness level | Awareness levels |
| E6 | English | Generic AI language | English voice, banned phrases |
| E7 | English | Unsupported claims | Evidence over slogans |
| E8 | English | Overwritten slogans | Contrast formulas |
| E9 | English | False product claim | Product truth |
| E10 | English | Vague CTA | CTAs must be specific |
| B1 | Bilingual | Structural copying | Sentence structure differs |
| B2 | Bilingual | Different opening style | Explicit context differs |
| B3 | Bilingual | Different explanation depth | Reader expectations differ |
| B4 | Bilingual | Different register | Register adapts per language |
| B5 | Bilingual | Different CTA wording | CTA verbs differ |
| B6 | Bilingual | Different title syntax | Word order differs |
| B7 | Bilingual | Different metaphor expression | Figures of speech differ |
| B8 | Bilingual | Different tense/aspect | Tense may differ |
| B9 | Bilingual | Different explicit context | Explicitness differs |
| B10 | Bilingual | Different customer language | Language-native phrasing |
| F1 | Persian copy | Bureaucratic register | Iranian founder voice |
| F2 | Persian copy | Technical term dumping | Explanation before terminology |
| F3 | Persian copy | Artificial search phrases | Natural Persian SEO |
| F4 | Persian copy | Calque dependent on English | Sentence independence |
