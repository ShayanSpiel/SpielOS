# SpielOS Persian Glossary

Single source of truth for all Persian terminology in SpielOS. Every translation — UI strings, notes, marketing copy, documentation, founder story — must use exactly these terms. When in doubt, fix the glossary first, then translate.

## Reference

- `../../../company/strategy/icp.md` — the single source of truth for the customer profile (shared with copywriting skills). The ICP determines what the reader already knows and which terms need explanation.

---

## A. Locked product labels

These are official product names or UI concepts. They must appear identically across every page, every time. Do not paraphrase, alternate, or "improve" them in context.

| English | Persian | Never use | Why |
|---|---|---|---|
| Agent | ایجنت | عامل هوشمند، عامل خودمختار | عامل is a literal dictionary translation that no Iranian founder uses for software agents. |
| Agentic | ایجنتیک | ایجنت (as adjective), ایجنتی‌وار | ایجنتیک is the established adjective form. Using ایجنت as an adjective creates ambiguity. |
| Role | نقش | | |
| Skill | مهارت | | |
| Workflow | ورک‌فلو | | |
| Eval / Evaluation | ارزیابی | | |
| Memory | حافظه | | |
| Tool | ابزار | | |
| Instruction | دستور | | |
| Task | کار | | |
| Approval | تأیید | | |
| Run | اجرا | | |
| Session | جلسه / جلسه کاری | سشن ❌ | سشن is a transliteration that sounds unnatural in Persian prose. |
| Department | دپارتمان | بخش ❌ | بخش is too generic and loses the organizational meaning. |
| AI employee | کارمند AI | | |
| AI department | دپارتمان AI | | |
| Director (Company Director role) | مدیرعامل | ایجنت کارگردان ❌, کارگردان ❌ | |
| Growth Marketing Lead | رهبر بازاریابی رشد | | |
| Market Research Lead | رهبر تحقیق بازار | | |
| Business Intelligence Analyst | تحلیلگر هوش تجاری | | |
| Employee (plural) | کارمندها | کارمندا ❌, کارمندان ❌ | کارمندا is not a word. کارمندان is a mixed plural — pick کارمندها everywhere. |
| Worker | کارمند | کارگر ❌ | کارگر means manual laborer. |
| Building block | اجزای سازنده / بلوک سازنده | بلوک ساختن ❌ | بلوک ساختن is a verb phrase, not a noun. |
| Credentials | اعتبارنامه / کلید | مدارک ❌ | مدارک means documents. |
| Source material | منبع / منابع | لایه‌ی مواد خام ❌, مواد خام ❌ | In product copy, use منبع/منابع. |
| Access | دسترسی | | |
| Pause | توقف | | |
| Resume | ادامه | | |
| Retry | دوباره اجرا کن | | |
| Permanent delete | برای همیشه پاک کن | | |
| Spiel | اشپیل | اسپیل ❌ | Correct Persian spelling. |
| Quality gate | دروازه کیفیت | | |
| Strategy | استراتژی | | |
| Knowledge | دانش | | |
| Approval (UI label) | تأیید | | |

### Agentic systems (compound forms)

| English | Persian | Never use | Why |
|---|---|---|---|
| Agent systems | سیستم‌های ایجنتیک | سیستم‌های ایجنت ❌ | ایجنت is a noun, not an adjective. |
| Agent architecture | معماری ایجنتیک | معماری ایجنت ❌ | Same rule. |
| Agent-based systems | سیستم‌های ایجنتیک | | |

### Never use (general)

These words are banned in all SpielOS Persian copy unless the glossary explicitly permits them:

| Word | Why |
|---|---|
| عامل هوشمند | Literal dictionary translation. No one says this. |
| عامل خودمختار | Same. |
| چارچوب مهار عامل | Unnecessarily complex calque. |
| سازوکار عامل‌محور | Same. |
| کارمندا | Not a Persian word. |
| کارگر (for software worker) | Means manual laborer. |
| سشن (for session) | Transliteration that sounds unnatural. |
| بلوک ساختن (for building block) | Verb phrase, not a noun. |
| مدارک (for credentials) | Means documents. |
| اسپیل (for Spiel) | Misspelling. |

---

## B. Technical terms allowed only with context

These terms are natural for technical readers but must not appear automatically in general marketing copy. For each, the glossary defines when it is appropriate, which ICP understands it, and what simpler Persian to use for non-technical readers.

### هارنس (harness)

- **When appropriate:** Technical architecture copy, developer documentation, product deep-dives.
- **ICP:** Not the primary buyer — business owners and operators are non-technical. Technical documentation only; always explain before use.
- **Needs explanation:** Yes, for general founders. Explain as «سیستمی که ایجنت‌ها رو مدیریت و اجرا می‌کنه».
- **Simpler alternative for non-technical readers:** سیستم مدیریت ایجنت، or simply describe what it does.

### ارکستریشن (orchestration)

- **When appropriate:** Technical architecture copy describing multi-agent coordination.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Yes, for general founders.
- **Simpler alternative:** هماهنگ‌کردن چند ایجنت برای انجام یک کار.

Technical copy:

> ارکستریشن اجرای چند ایجنت در کنار هم برای رسیدن به یک نتیجه.

General founder copy:

> چند ایجنت رو طوری به هم وصل کن که هرکدوم بخشی از کار رو انجام بدن.

### کانتکست (context)

- **When appropriate:** Technical copy, product documentation, developer-facing material.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** For general readers, clarify what context means in this product.
- **Simpler alternative:** اطلاعات و دانشی که ایجنت برای انجام کارش نیاز داره.

### پایپ‌لاین (pipeline)

- **When appropriate:** Technical copy, workflow documentation.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Yes, for non-technical readers.
- **Simpler alternative:** مسیر اجرای کار، زنجیره‌ای از مراحل.

### هند‌آف / Handoff

- **When appropriate:** Technical copy, workflow documentation.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Yes, for non-technical readers.
- **Simpler alternative:** انتقال کار بین ایجنت‌ها یا بین ایجنت و انسان.

### پrovایدر / Provider

- **When appropriate:** Technical copy, settings, configuration pages.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Not usually — the word is familiar enough in tech contexts.
- **Simpler alternative:** ارائه‌دهنده مدل (when needed).

### روتینگ / Routing

- **When appropriate:** Technical architecture copy.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Yes, for general readers.
- **Simpler alternative:** انتخاب مسیر مناسب برای هر درخواست.

### ویزر / Wrapper

- **When appropriate:** Technical documentation, API docs.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Yes, for general readers.
- **Simpler alternative:** لایه‌ی اتصال، ابزار اتصال.

### لوکال / Locale

- **When appropriate:** Technical copy about i18n, developer documentation.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Not usually — familiar in tech.
- **Simpler alternative:** زبان و منطقه.

### تاکسونومی / Taxonomy

- **When appropriate:** Technical architecture copy, information architecture discussions.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Yes, for general readers.
- **Simpler alternative:** ساختار دسته‌بندی.

### رول / Role (technical compound)

- **When appropriate:** Only in deeply technical copy where distinguishing the concept from the product label «نقش» would confuse readers.
- **ICP:** Technical documentation only — never for the primary buyer.
- **Needs explanation:** Rarely needed — prefer نقش.
- **Simpler alternative:** نقش.

### General rule for category B terms

Before using any term from this category, ask: **Does the reader need the term, or do they need the meaning?**

For the primary buyer (non-technical owners and operators), explain first. Only introduce the term where it adds precision:

> چند ایجنت رو طوری به هم وصل کن که هرکدوم بخشی از کار رو انجام بدن. این همون ارکستریشن ورک‌فلوئه.

Do not use technical terms to avoid explaining the product.

---

## C. Contextual terms — not fixed translations

Some English words cannot have one mandatory Persian equivalent in every context. The glossary provides several valid renderings by context. Choose the one that fits the sentence.

### founder

| Context | Valid renderings |
|---|---|
| In product copy, generic | فاندر |
| In founder story, personal | فاندر، بنیان‌گذار |
| As a job title in metadata | فاندر |

### building

| Context | Valid renderings |
|---|---|
| Building a product | ساختن محصول |
| Building in public | محصول رو جلوی چشم بقیه ساختن / مسیر ساخت محصول رو عمومی منتشر کردن |
| Building systems | طراحی و ساخت سیستم‌ها |
| Building blocks | اجزای سازنده |

### system

| Context | Valid renderings |
|---|---|
| Software system | سیستم |
| Growth system | سیستم رشد |
| System of systems | مجموعه‌ای از سیستم‌ها |
| Operating system | سیستم‌عامل |

### source

| Context | Valid renderings |
|---|---|
| Source code | سورس‌کد |
| Source material | منبع / منابع |
| Source of truth | منبع اصلی / مرجع |

### structure

| Context | Valid renderings |
|---|---|
| Information structure | ساختار اطلاعات |
| Company structure | ساختار شرکت |
| Structure of a page | ساختار صفحه |
| Structural problem | مشکل ساختاری |

### operation

| Context | Valid renderings |
|---|---|
| Business operations | عملیات شرکت |
| Daily operations | کارهای روزمره |
| Operational | عملیاتی |

### architecture

| Context | Valid renderings |
|---|---|
| Software architecture | معماری |
| Agent architecture | معماری ایجنتیک |
| Architecture of a system | ساختار یک سیستم |

### platform

| Context | Valid renderings |
|---|---|
| In product copy | محصول، پلتفرم |
| In technical copy | پلتفرم |
| In founder story | محصول |

### layer

| Context | Valid renderings |
|---|---|
| Technical layer | لایه |
| Context layer | لایه‌ی کانتکست |
| Layer of abstraction | لایه‌ی انتزاعی |

### execution

| Context | Valid renderings |
|---|---|
| Running a task | اجرا |
| Execution of a workflow | اجرای ورک‌فلو |
| Long-running execution | اجرای طولانی‌مدت |

---

## D. Banned words and phrases

These words are banned in all SpielOS Persian copy. Each ban includes the reason.

| Banned word/phrase | Why it is banned | Use instead |
|---|---|---|
| راهکار | Corporate filler. Sounds like a government brochure. | محصول، ابزار، یه روش ساده |
| سامانه | Bureaucratic. No Iranian founder talks like this. | سیستم |
| بستر | Generic. Hides what you actually mean. | پلتفرم (in technical copy) or describe what it does |
| پلتفرم جامع | Marketing filler. Says nothing specific. | Name the product or describe the capability |
| هوشمندسازی | Buzzword. Means nothing without context. | Describe the actual change |
| تحول دیجیتال | Same. | Describe what changed |
| توانمندسازی | Corporate jargon. | Describe what the user can now do |
| بهره‌گیری | Bureaucratic verb. | استفاده کن، استفاده کردن |
| زیست‌بوم | Academic. | اکوسیستم (in technical copy) or ecosystem |
| فرآیندهای سازمانی | Bureaucratic. | کارهای شرکت، فرآیندها |
| نوآورانه | Empty adjective. | Describe what makes it new |
| قدرتمند | Empty adjective. | Describe what it actually does |
| پیشرفته | Empty adjective. | Describe the specific capability |
| نسل بعدی | Marketing filler. | Name the actual improvement |
| سیاهه | Obscure literary word. | فهرست |
| ردیه | Obscure. No one says this in conversation. | لیست ممنوعه، دلیل ممنوعیت |
| مصداق | Legal/academic. | مثال |
| مبادرت | Bureaucratic. | اقدام |
| مضاف | Legal/academic. | و، علاوه بر |
| مستفاد | Legal/academic. | استفاده شده از |
| مطروحه | Bureaucratic. | مطرح‌شده |

---

## E. Language register rules

### Default public Persian

- Conversational
- Educated
- Direct
- Precise
- Modern
- Not slangy
- Not bureaucratic
- Not academic
- Not overly literary

### When to shift register

Use more formal Persian only for:

- Legal copy
- Privacy policies
- Billing
- Security warnings
- Irreversible deletion warnings
- Serious product warnings

### Avoid mixing registers

Do not mix highly conversational grammar with formal vocabulary in the same sentence.

Bad:

> تاکسونومی‌ای که همراستا نباشه، بدهی محتوایی‌ست که تا ابد می‌پردازی.

Better:

> اگر ساختار محتوای سایت با خود محصول هماهنگ نباشه، مدت‌ها باید هزینه‌ی اصلاح و نگهداریش رو بدی.

---

## F. Default voice

- `تو` form, not `شما`: می‌تونی، می‌سازه، بده، بساز
- `رو` not `را`
- `می‌سازه` not `می‌سازد`
- `می‌تونه` not `می‌تواند`
- `بهت نشون می‌ده` not `به شما نمایش می‌دهد`
- Direct commands: `بساز`، `وصل کن`، `اجرا کن`، `ادامه بده`

### Persian digits in prose

Use Persian digits in body copy: ۳ میلیون، ۲۰۲۴، ۵۰٪

### نیم‌فاصله

Keep نیم‌فاصله clean: می‌کنه، می‌شه، می‌تونن

### Technical terms that keep English

These keep English spelling in all contexts: API, CLI, URL, Markdown, GitHub, LangChain, LangGraph, RAG, model names, SpielOS, AI, Prompt, Token, Inference

---

## G. Quality test (every string)

1. Would an Iranian founder say this out loud?
2. Does it make sense WITHOUT seeing the English source?
3. Is the actor + action clear? (who does what)
4. Is the context Persian needs present?
5. Does terminology match this glossary?
6. Is the register appropriate for the surface?
7. Is the subject-verb number agreement correct?
