#!/usr/bin/env python3
"""
Outbound Department — email templates and signatures.

Templates are keyed by language ("English" or "Persian"); each language has
VARIANT_ROTATE-based A/B variants. Use {placeholders} for personalization.

Available placeholders:
  {contact_name}, {first_name}, {company}, {title}, {domain},
  {personalization_hook}, {suggested_cta}, {website}, {country}, {segment},
  {SIGNATURE_HTML}, {SIGNATURE_TEXT}
"""

from .config import (
    FROM_NAME,
    SIGNATURE_TITLE,
    SIGNATURE_AVATAR_URL,
    SIGNATURE_LINKEDIN,
    SIGNATURE_X,
    SIGNATURE_SERVICES,
    SIGNATURE_APPLY,
)

SIGNATURE_HTML = f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:24px;border-top:1px solid #e5e5e5;padding-top:16px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.5;color:#333333;">
  <tr>
    <td style="padding-right:12px;vertical-align:middle;">
      <img src="{SIGNATURE_AVATAR_URL}" alt="{FROM_NAME}" width="48" height="48" style="border-radius:50%;display:block;" />
    </td>
    <td style="vertical-align:middle;">
      <div style="font-size:14px;font-weight:bold;color:#111111;">{FROM_NAME}</div>
      <div style="color:#555555;">{SIGNATURE_TITLE}</div>
      <div style="margin-top:4px;">
        <a href="{SIGNATURE_LINKEDIN}" style="color:#0a66c2;text-decoration:none;">LinkedIn</a>
        &nbsp;&middot;&nbsp;
        <a href="{SIGNATURE_X}" style="color:#111111;text-decoration:none;">X</a>
        &nbsp;&middot;&nbsp;
        <a href="{SIGNATURE_SERVICES}" style="color:#333333;text-decoration:none;">spielos.xyz/services</a>
      </div>
      <div style="margin-top:8px;">
        <a href="{SIGNATURE_APPLY}" style="color:#2f81f7;text-decoration:none;font-weight:bold;">Apply for a Free Review</a>
      </div>
    </td>
  </tr>
</table>"""

SIGNATURE_TEXT = f"""\
{FROM_NAME}
{SIGNATURE_TITLE}
LinkedIn: {SIGNATURE_LINKEDIN}
X: {SIGNATURE_X}
{SIGNATURE_SERVICES}
Apply for a Free Review (no call needed): {SIGNATURE_APPLY}"""

TEMPLATES = {
    "English": [
        {
            "label": "recruitment-workflow",
            "subject": "One staffing workflow",
            "body_html": """\
<p>Hi {company} team,</p>
<p>{company} staffs {segment} roles for {country} clients, and the coordination runs through a specific loop: candidate shortlists, interview summaries, onboarding follow-ups.</p>
<p>I build supervised AI employees that carry that loop, one workflow at a time, with a person approving each step.</p>
<p>Is the shortlist stage still done by hand, or have you systemized it? If it is still manual, I'd be happy to map it with you.</p>
<p>Best,<br>Shayan</p>
{SIGNATURE_HTML}""",
            "body_text": """\
Hi {company} team,

{company} staffs {country} roles for clients, and the coordination overhead lives in one chain: candidate shortlists, interview summaries, feedback follow-ups.

I build supervised AI employees that carry that loop, one workflow at a time, with a person approving each step.

Is the shortlist stage still done by hand, or have you systemized it? If it is still manual, I'd be happy to map it with you.

Best,
Shayan

{SIGNATURE_TEXT}""",
        },
        {
            "label": "agency-delivery",
            "subject": "Delivery loop cost",
            "body_html": """\
<p>Hi {company} team,</p>
<p>{company} runs a client-delivery flow around {segment} work in {country}, and the classic cost is in the handoffs: brief to research to drafts to QA to reporting.</p>
<p>I build supervised AI employees that carry that flow, with a person approving each step.</p>
<p>Which stage is still manual: first drafts, or the client reporting? If either is, I'd be happy to map that one stage with you.</p>
<p>Best,<br>Shayan</p>
{SIGNATURE_HTML}""",
            "body_text": """\
Hi {company},

{company} is a client-delivery business in {country}, and the classic cost sits in the handoffs: brief to research to drafts to QA to reporting.

I build supervised AI employees that carry that flow, with a person approving each step.

Which stage is still manual: first drafts, or the client reporting? If either is, I'd gladly map that one stage with you.

Best,
Shayan

{SIGNATURE_TEXT}""",
        },
        {
            "label": "saas-ops",
            "subject": "Support ops at {company}",
            "body_html": """\
<p>Hi {company} team,</p>
<p>{company} is a SaaS business, and most of them share the same bottleneck: incoming customer feedback and support requests triaged by hand and routed between people.</p>
<p>I build supervised AI employees for that loop: classify the request, draft the response, escalate the exceptions.</p>
<p>Is triage still manual for {company}, or do you already run it through a system? If it is manual, I'd be happy to map it.</p>
<p>Best,<br>Shayan</p>
{SIGNATURE_HTML}""",
            "body_text": """\
Hi {company},

{company} is a SaaS business, and most SaaS teams share the same bottleneck: support and product feedback triaged by hand and routed between people.

I build supervised AI employees for that loop: classify, draft, escalate.

If triage is still manual at {company}, I'd be happy to map it with you — what do you think?

Best,
Shayan

{SIGNATURE_TEXT}""",
        },
        {
            "label": "generic-workflow",
            "subject": "One workflow at {company}",
            "body_html": """\
<p>Hi {company} team,</p>
<p>Every scaling business has one repetitive workflow that eats the week: the follow-ups, the handoffs, the reporting between tools.</p>
<p>I build supervised AI employees that carry one such workflow end to end, with a person approving each step.</p>
<p>Which workflow at {company} is the most manual right now? If it is still manual, I'd be happy to map it with you.</p>
<p>Best,<br>Shayan</p>
{SIGNATURE_HTML}""",
            "body_text": """\
Hi {company},

Every scaling business has one repetitive workflow that eats the week: the follow-ups, the handoffs, the reporting between tools.

I build supervised AI employees that carry one such workflow end to end, with a person approving each step.

Which workflow at {company} is the most manual right now? If it is still manual, I'd be happy to map it with you.

Best,
Shayan

{SIGNATURE_TEXT}""",
        },
    ],
    "Persian": [
        {
            "label": "scarcity-handpicked",
            "subject": "یک بریف رایگان برای {company} رزرو کردم",
            "body_html": """\
<p>سلام {first_name}،</p>
<p>این هفته ۳ بریف آزمایشی رایگان می‌دهم، و {company} را برای یکی از آن‌ها انتخاب کرده‌ام.</p>
<p>به‌عنوان {title} در کسب‌وکار {segment}، هر روز می‌بینید: کارهای تکراری بین ابزارها ساعت‌های زیادی را می‌گیرد که باید صرف درآمد شود.</p>
<p>هر بریف یک <a href="https://spielos.xyz/services/agent-brief/" style="color:#2f81f7;">Agent Brief</a> یک‌صفحه‌ای است: نقشه کامل یک ورک‌فلو، شکل اتوماسیون و ROI مورد انتظار. چه با هم کار کنیم چه نه، بریف مال شماست.</p>
<p>اگر می‌خواهید، کافی است «map» را پاسخ بدهید.</p>
<p>با احترام،<br>شایان</p>
{SIGNATURE_HTML}""",
            "body_text": """\
سلام {first_name}،

این هفته ۳ بریف آزمایشی رایگان می‌دهم، و {company} را برای یکی از آن‌ها انتخاب کرده‌ام.

به‌عنوان {title} در کسب‌وکار {segment}، هر روز می‌بینید: کارهای تکراری بین ابزارها ساعت‌ها می‌برد.

هر بریف یک Agent Brief یک‌صفحه‌ای است: نقشه کامل یک ورک‌فلو، شکل اتوماسیون و ROI. چه با هم کار کنیم چه نکنیم، بریف مال شماست.

قالب بریف: https://spielos.xyz/services/agent-brief/

اگر خواستید، «map» پاسخ دهید.

با احترام،
شایان

{SIGNATURE_TEXT}""",
        },
        {
            "label": "curiosity-gap",
            "subject": "سوالی از یک روز کاری در {company}",
            "body_html": """\
<p>سلام {first_name}،</p>
<p>این هفته ۳ بریف آزمایشی رایگان می‌دهم و {company} را برای یکی از آن‌ها انتخاب کرده‌ام.</p>
<p>به‌عنوان {title} در کسب‌وکار {segment}، اگر می‌خواستید یک ورک‌فلو را به ابزارها بسپارید، کدام بود؟ معمولاً کارهای تکراری بین ابزارها: جستجو، پیگیری، گزارش‌ها.</p>
<p>یک بریف یک‌صفحه‌ای است: <a href="https://spielos.xyz/services/agent-brief/" style="color:#2f81f7;">قالب Agent Brief</a> برای همان ورک‌فلو، بدون هیچ تعهدی. اگر خواستید، «map» را بگویید.</p>
<p>با احترام،<br>شایان</p>
{SIGNATURE_HTML}""",
            "body_text": """\
سلام {first_name}،

این هفته ۳ بریف آزمایشی رایگان می‌دهم و {company} را انتخاب کرده‌ام.

به‌عنوان {title} در کسب‌وکار {segment}، اگر می‌خواستید یک ورک‌فلو را بسپارید، کدام بود؟ معمولاً: کارهای تکراری بین ابزارها.

یک بریف یک‌صفحه‌ای بدون هیچ تعهدی. اگر خواستید «map» بگویید.

{SIGNATURE_TEXT}""",
        },
        {
            "label": "pilot-window",
            "subject": "این هفته ۳ اسلات؛ یکی برای {company}",
            "body_html": """\
<p>سلام {first_name}،</p>
<p>این هفته ۳ بریف آزمایشی رایگان می‌دهم و یک اسلات را برای {company} نگه داشته‌ام.</p>
<p>به‌عنوان {title}، ترجیح می‌دهم کار را نشان بدهم تا درباره‌اش حرف بزنم.</p>
<p>هر بریف یک صفحه است: <a href="https://spielos.xyz/services/agent-brief/" style="color:#2f81f7;">قالب Agent Brief</a> برای یک ورک‌فلو. نتیجه کامل مال شماست.</p>
<p>اگر خواستید، «map» بگویید تا اسلات را قطعی کنم.</p>
<p>با احترام،<br>شایان</p>
{SIGNATURE_HTML}""",
            "body_text": """سلام {first_name}،

این هفته ۳ بریف آزمایشی رایگان می‌دهم و یک اسلات را برای {company} نگه داشته‌ام.

اگر خواستید، «map» بگویید.

با احترام،
شایان

{SIGNATURE_TEXT}""",
        },
    ],
}
