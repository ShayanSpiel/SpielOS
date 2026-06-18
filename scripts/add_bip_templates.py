#!/usr/bin/env python3
"""add_bip_templates.py — Add BiP core templates to the registry.

Reads templates/registry/viral-templates.yaml, adds 90 new templates
across 3 new categories (ship_log, product, milestone) × 3 platforms
(x, linkedin, blog) × 10 templates each. Writes back in place.

Idempotent: if a category already exists for a platform, it merges.
"""

from pathlib import Path
import sys
import yaml

import engine_state


NEW_TEMPLATES = {
    "ship_log": {
        "x": [
            ("x-ship_log-01", "Day N of building X — what shipped",
             "Day {n} of building the engine.\n\nShipped: {what_1}, {what_2}, {what_3}.\n\nBroke: {what_broke}.\n\nBack to work.",
             "Follow for daily build logs"),
            ("x-ship_log-02", "Shipped at 3am — here's what broke",
             "Shipped at 3am.\n\n{what_i_thought_was_done} was not done.\n\nHere's what actually broke and how I caught it:",
             "RT if you've shipped at 3am"),
            ("x-ship_log-03", "Bug that ate Tuesday",
             "A bug ate my Tuesday.\n\nNot a {big_problem}. A {small_typo}.\n\n{lesson}.",
             "Follow for build logs"),
            ("x-ship_log-04", "Refactor week — N PRs merged",
             "Refactor week: {n} PRs merged.\n\n{line_count} lines changed.\n\n{before_after}.",
             "Diff in the replies"),
            ("x-ship_log-05", "5 things I shipped this week",
             "5 things I shipped this week:\n\n1. {thing_1}\n2. {thing_2}\n3. {thing_3}\n4. {thing_4}\n5. {thing_5}\n\n{favorite} was the win.",
             "Reply with yours"),
            ("x-ship_log-06", "The commit that almost didn't ship",
             "Almost didn't ship this commit.\n\n{reason}.\n\n{why_i_pushed_anyway}.",
             "Follow for daily commits"),
            ("x-ship_log-07", "I rewrote it. Twice. Here's why.",
             "I rewrote {feature}.\n\nOnce because it was slow.\n\nOnce because it was unclear.\n\n{v1_metric} → {v2_metric}.",
             "RT if you've done this"),
            ("x-ship_log-08", "Velocity is a vanity metric. Throughput isn't.",
             "Velocity is a vanity metric.\n\nThroughput isn't.\n\nThis week: {lines_written} vs {lines_shipping}.",
             "Follow for honest metrics"),
            ("x-ship_log-09", "The boring commit that fixed everything",
             "The boring commit that fixed everything:\n\n+{n} lines, -{m} lines.\n\nNo framework. No architecture diagram. Just {what_it_did}.",
             "RT the boring commits"),
            ("x-ship_log-10", "Why I deleted that feature",
             "Deleted {feature} today.\n\n{users_using_it} users used it.\n\n{why_i_deleted_it_anyway}.",
             "Follow for less-is-more builds"),
        ],
        "linkedin": [
            ("li-ship_log-01", "Week N of building the engine",
             "Week {n} of building the engine.\n\nThis week: shipped {feature}, broke {thing}, learned {lesson}.\n\nThe build is the marketing. The marketing is the build.\n\nHere is the actual log — what shipped, what broke, what I would do differently:",
             "Comment with your week"),
            ("li-ship_log-02", "I shipped at 3am and learned something",
             "I shipped at 3am last Tuesday.\n\nThe feature worked. The blog post did not. The Slack notifications did not. The cron job did not.\n\nI caught three of the four at 4am. The fourth I caught the next morning when a user DM'd me.\n\nHere is the postmortem — what I learned about shipping when the rest of the world is asleep:",
             "Save for your next 3am ship"),
            ("li-ship_log-03", "The bug that ate my Tuesday",
             "A bug ate my Tuesday. Not a {big_problem}. A {small_typo} in a regex that ran for 8 hours before anyone noticed.\n\nThe lesson is not about regex. The lesson is about observability. We do not see what we do not measure, and what we do not see will eat us.\n\nHere is what we changed:",
             "Comment if you have been bitten"),
            ("li-ship_log-04", "Refactor week — what changed and why",
             "Refactor week: {n} PRs merged, {line_count} lines changed.\n\nThis is the post I wish I had read six months ago. Here is the before/after, the tradeoffs, the things I would not do again, and the one thing I would change in every refactor I do for the rest of my career:",
             "Save for your next refactor"),
            ("li-ship_log-05", "Five things I shipped this week",
             "Five things I shipped this week:\n\n1. {thing_1} — {why_it_matters}\n2. {thing_2} — {why_it_matters}\n3. {thing_3} — {why_it_matters}\n4. {thing_4} — {why_it_matters}\n5. {thing_5} — {why_it_matters}\n\nThe favorite is at the bottom. Here is why and what it cost:",
             "Comment with your favorite ship"),
            ("li-ship_log-06", "The commit that almost didn't ship",
             "Almost didn't ship this commit.\n\n{reason}.\n\n{why_i_pushed_anyway}.\n\nThe lesson is not about persistence. The lesson is about what changes when you stop letting perfect block good. Here is the full story and the framework I now use:",
             "Save for when you almost quit"),
            ("li-ship_log-07", "I rewrote it. Twice. Here's what I learned.",
             "I rewrote {feature}. Once because it was slow. Once because it was unclear.\n\nThe first rewrite was a performance optimization. The second was a clarity optimization. The second one mattered more.\n\nHere is what I learned about when to rewrite for speed and when to rewrite for clarity:",
             "Comment with your rewrite story"),
            ("li-ship_log-08", "Velocity is a vanity metric. Throughput isn't.",
             "Velocity is a vanity metric. Throughput is not.\n\nThis week: {lines_written} written, {lines_shipping} shipped.\n\nThe ratio is what matters. Here is how I track it, what it tells me, and why most engineering teams measure the wrong thing:",
             "Save for your next retro"),
            ("li-ship_log-09", "The boring commit that fixed everything",
             "The boring commit that fixed everything: +{n} lines, -{m} lines.\n\nNo framework. No architecture diagram. No LinkedIn thought leadership. Just {what_it_did}.\n\nThe post I want to write is about the boring middle of engineering. The one where the work is unheroic and the outcomes are huge. Here it is:",
             "RT the boring commits"),
            ("li-ship_log-10", "Why I deleted a feature users liked",
             "I deleted {feature} today.\n\n{users_using_it} users used it. {percentage}% of them used it weekly.\n\n{why_i_deleted_it_anyway}.\n\nHere is the framework I now use to decide what to keep. The cost of maintenance is invisible. The benefit of focus is not. Here is how to choose:",
             "Comment with what you deleted"),
        ],
        "blog": [
            ("blog-ship_log-01", "Week in the build — what shipped, what broke, what I learned",
             "Week {n} of building the engine. This is the build log.\n\nHere is what shipped, what broke, and what I would do differently. The format is: shipped → broke → learned. Every week. No skipping.",
             "Subscribe for weekly build logs"),
            ("blog-ship_log-02", "Postmortem: the 3am ship that almost took down the system",
             "Postmortem: the 3am ship that almost took down the system.\n\nThis is the long version. The postmortem, the timeline, the decision tree, the recovery, and the system I built so it does not happen again.",
             "Read the full postmortem"),
            ("blog-ship_log-03", "The bug that ate my Tuesday — observability for solo builders",
             "A bug ate my Tuesday. Here is the full story, the postmortem, and the observability changes I made so it does not happen again. Specifically for solo builders and small teams who do not have a SRE department.",
             "Subscribe for build logs"),
            ("blog-ship_log-04", "Refactor week — the long version",
             "Refactor week: {n} PRs, {line_count} lines. This is the long version — the why, the what, the order, the things I would do differently. Refactors are how systems stay alive. Here is how I do mine.",
             "Read the full refactor log"),
            ("blog-ship_log-05", "The weekly build report — five ships, one favorite, one lesson",
             "Five things I shipped this week. One favorite. One lesson.\n\nThis is the format I will use every Friday. The short version is on X. The long version is here. The build log is the marketing. The marketing is the build log.",
             "Subscribe for weekly reports"),
            ("blog-ship_log-06", "The commit that almost didn't ship",
             "Almost did not ship this commit. Here is the full story of why, what I almost gave up on, and what changed when I pushed anyway. The lesson is bigger than this commit.",
             "Read the full story"),
            ("blog-ship_log-07", "I rewrote it twice — performance vs clarity",
             "I rewrote {feature} twice. Once for performance. Once for clarity. The second one mattered more. Here is the full story, the metrics, the tradeoffs, and when to optimize which.",
             "Read the full rewrite story"),
            ("blog-ship_log-08", "Velocity vs throughput — the metric that actually matters",
             "Velocity is lines per day. Throughput is lines in production. They are not the same. Here is the metric I track, why, and what it tells me about my engineering.",
             "Read the full breakdown"),
            ("blog-ship_log-09", "The boring commit — the work that does not make the highlight reel",
             "The boring commit: +{n}, -{m}. No framework. No architecture diagram. Just {what_it_did}.\n\nThis post is about the boring middle of building — the work that does not make the highlight reel but is the only thing that ships the product.",
             "Read the full essay"),
            ("blog-ship_log-10", "Why I deleted a feature — the cost of maintenance",
             "I deleted {feature} today. Here is the cost analysis, the user impact, the framework I now use, and the maintenance math every solo builder should know. The cost of maintenance is invisible. The benefit of focus is not.",
             "Read the full deletion story"),
        ],
    },
    "product": {
        "x": [
            ("x-product-01", "We just shipped X. Here's why it took 4 months.",
             "We just shipped {feature}.\n\nTook 4 months. Here's why:\n\n- {reason_1}\n- {reason_2}\n- {reason_3}\n\nThe lesson is not about shipping fast. The lesson is about shipping right.",
             "RT if you've waited"),
            ("x-product-02", "v2 is live. 3 things that changed.",
             "v2 is live.\n\n3 things changed:\n\n1. {change_1}\n2. {change_2}\n3. {change_3}\n\nThe architecture is the same. The story is not.",
             "Try v2 → link in bio"),
            ("x-product-03", "What's new in the engine",
             "What's new in the engine this month:\n\n- {feature_1}\n- {feature_2}\n- {feature_3}\n\nThe killer is at the bottom.",
             "Try it → link in reply"),
            ("x-product-04", "Built for builders, not marketers",
             "Built for builders, not marketers.\n\nIf you've ever opened a tool and felt like it was designed for someone else, this is for you.\n\nIf you have never opened a tool, this is also for you.",
             "RT if this resonates"),
            ("x-product-05", "We killed 2 features. Here's what we kept.",
             "We killed 2 features this month.\n\n{feature_a} and {feature_b}.\n\n{users_using_each} users used each.\n\nHere's what we kept instead, and why:",
             "Reply with what you killed"),
            ("x-product-06", "Open source is the launch",
             "Open source is the launch.\n\nWe made {project} public today.\n\n{lines_of_code} lines. {contributors} contributors. {license} license.\n\nHere's the link in the reply.",
             "Star it → link in reply"),
            ("x-product-07", "X is now in public beta",
             "{product} is now in public beta.\n\nWhat's in: {feature_1}, {feature_2}, {feature_3}.\nWhat's next: {feature_4}, {feature_5}.\n\n{cta} → link in reply",
             "Try the beta → link in reply"),
            ("x-product-08", "Why we built this",
             "Why we built {product}:\n\n{problem} was killing us.\n\nEvery existing tool solved it wrong — {wrong_solutions}.\n\nSo we built our own. Here's the story:",
             "Read the full story"),
            ("x-product-09", "Pricing is the product",
             "Pricing is the product.\n\nWe just changed ours. Here's why:\n\n{old_pricing} → {new_pricing}.\n\nThe math is in the reply.",
             "Reply if you agree"),
            ("x-product-10", "The feature post I wish I'd seen before building",
             "The feature post I wish I'd seen before building {feature}:\n\n{what_it_does}, {why_it_matters}, {who_its_for}.\n\nIf you are building something similar, this is the post I want you to read.",
             "Reply if you're building"),
        ],
        "linkedin": [
            ("li-product-01", "We just shipped X. Here's why it took 4 months.",
             "We just shipped {feature}. It took 4 months. Here is the honest version of why — the engineering tradeoffs, the user research, the three rewrites, the one thing I would do differently, and the post I wish I had read before I started.",
             "Save for your next ship"),
            ("li-product-02", "v2 is live — the story behind the rewrite",
             "v2 is live. The architecture is the same. The story is not.\n\nHere is the full version: what changed, what stayed, why we made the calls we made, and the one decision that took four months to make.",
             "Comment if you've done v2"),
            ("li-product-03", "What's new in the engine — monthly update",
             "What's new in the engine this month. The full version — not the highlight reel, the actual changes, the reasoning, the user feedback, and what we are killing next.",
             "Subscribe for monthly updates"),
            ("li-product-04", "Built for builders, not marketers",
             "Built for builders, not marketers. This is the product post I wish I had seen when I started building tools — the one that explains why the audience matters more than the feature list, and what it means to actually design for the people who will use it.",
             "Save if you build tools"),
            ("li-product-05", "We killed 2 features. Here's what we kept.",
             "We killed 2 features this month. {feature_a} and {feature_b}. {users_using_each} users used each. {paying_users_using_each} were paying. We killed them anyway. Here is the framework I now use to decide what to keep, and the math every founder should know.",
             "Comment with what you killed"),
            ("li-product-06", "Open source is the launch",
             "Open source is the launch. We made {project} public today — {lines_of_code} lines, {contributors} contributors, {license} license. Here is why, what it means, what we are keeping closed, and the post I wish I had read before I open-sourced anything.",
             "Save for your launch"),
            ("li-product-07", "X is now in public beta",
             "{product} is now in public beta. Here is the full version — what is in, what is out, what is next, how to get access, and the one question I want you to ask me in the first 30 days.",
             "Comment for access"),
            ("li-product-08", "Why we built this",
             "Why we built {product}. The full version — the problem, the wrong solutions we tried, the moment we knew we had to build it ourselves, and the framework I now use to decide what to build next.",
             "Save if you're building"),
            ("li-product-09", "Pricing is the product",
             "Pricing is the product. We just changed ours. Here is the full version — the math, the tradeoffs, the alternatives we considered, and the one principle I now use to set every price.",
             "Comment with your pricing"),
            ("li-product-10", "The feature post I wish I'd seen",
             "The feature post I wish I had seen before building {feature}. Here is the long version — the design rationale, the engineering tradeoffs, the user research, the things that surprised us, and the one thing I would change if I started today.",
             "Save for your next feature"),
        ],
        "blog": [
            ("blog-product-01", "We just shipped X. Here's the full story.",
             "We just shipped {feature}. Took 4 months. Here is the full story — the engineering tradeoffs, the user research, the three rewrites, the things I would do differently, and the post I wish I had read before I started.",
             "Read the full story"),
            ("blog-product-02", "v2 is live — what we changed and why",
             "v2 is live. The architecture is the same. The story is not. Here is the full post — what changed, what stayed, why we made the calls we made, the user feedback, the metrics, and the one decision that took four months.",
             "Read the v2 post"),
            ("blog-product-03", "Monthly update — what's new, what we killed, what we learned",
             "What's new in the engine this month. The full update — the changes, the reasoning, the user feedback, what we killed, what we are killing next, and the lessons that turned out to be wrong.",
             "Read the monthly update"),
            ("blog-product-04", "Built for builders, not marketers — the design philosophy",
             "Built for builders, not marketers. This is the long version of the design philosophy — why the audience matters more than the feature list, what it means to design for builders, and the framework I use for every product decision.",
             "Read the philosophy"),
            ("blog-product-05", "We killed 2 features — the math of maintenance",
             "We killed 2 features this month. Here is the full post — the math, the user impact, the framework for deciding what to keep, the cost of maintenance, and the alternative we shipped instead.",
             "Read the deletion post"),
            ("blog-product-06", "Open source is the launch — the playbook",
             "Open source is the launch. We made {project} public today. Here is the full playbook — why, what to open, what to keep closed, how to manage the launch, and the post I wish I had read before I open-sourced anything.",
             "Read the launch playbook"),
            ("blog-product-07", "Public beta — what we shipped and what's next",
             "{product} is now in public beta. Here is the full post — what is in, what is out, what is next, how to get access, the user feedback so far, and the one question I want you to ask in the first 30 days.",
             "Read the beta post"),
            ("blog-product-08", "Why we built this — the origin story",
             "Why we built {product}. The full origin story — the problem, the wrong solutions, the moment we knew we had to build our own, the early prototypes, the lessons that turned out to be wrong, and the framework I now use.",
             "Read the origin story"),
            ("blog-product-09", "Pricing is the product — the math",
             "Pricing is the product. We just changed ours. Here is the full post — the math, the tradeoffs, the alternatives, the test we ran, the result, and the principle I now use to set every price.",
             "Read the pricing post"),
            ("blog-product-10", "The feature post I wish I'd seen — the full breakdown",
             "The feature post I wish I had seen before building {feature}. Here is the full breakdown — the design rationale, the engineering tradeoffs, the user research, the things that surprised us, and what I would change if I started today.",
             "Read the breakdown"),
        ],
    },
    "milestone": {
        "x": [
            ("x-milestone-01", "1k users. Here's the weird one.",
             "1k users. Here's the weird one:\n\n{weird_user_1} signed up because {weird_reason}.\n\nIt has changed how I think about who this is for.",
             "RT if you've hit 1k"),
            ("x-milestone-02", "From 0 to $X MRR in N days",
             "0 → ${mrr} MRR in {days} days.\n\n{users} paying customers. {avg_revenue} ARPU.\n\nHere's the math nobody showed me:",
             "Reply with your MRR"),
            ("x-milestone-03", "We hit 100 paying customers",
             "100 paying customers.\n\n{n} of them are {persona_1}. {m} are {persona_2}.\n\n{one_thing_i_learned} was the unlock.",
             "Save for your 100"),
            ("x-milestone-04", "The 1% who showed up at week 1",
             "1% of users show up at week 1. The other 99% are noise.\n\nAt {user_count} users, here's what the 1% look like:",
             "Follow for retention data"),
            ("x-milestone-05", "First $1k. Here's the math.",
             "First $1k MRR.\n\n{how_long_it_took}. {what_i_was_wrong_about}. {one_thing_that_worked}.\n\nThe math is in the reply.",
             "Reply with your $1k"),
            ("x-milestone-06", "100 posts. What the data says.",
             "100 posts published.\n\nTop 3 by engagement:\n1. {post_1} — {eng_1}\n2. {post_2} — {eng_2}\n3. {post_3} — {eng_3}\n\nThe pattern: {what_worked}.",
             "Follow for the data"),
            ("x-milestone-07", "The number nobody asked me about",
             "The number nobody asks me about: {weird_metric}.\n\n{what_it_means} and {why_it_matters}.",
             "Reply with your weird metric"),
            ("x-milestone-08", "Year 1 in numbers",
             "Year 1 in numbers:\n\n- {metric_1}\n- {metric_2}\n- {metric_3}\n- {metric_4}\n- {metric_5}\n\nThe number I'm proud of: {quiet_win}.",
             "Save for your year 1"),
            ("x-milestone-09", "The day I stopped counting",
             "I stopped counting {metric} on {date}.\n\n{what_changed} and {what_i_realized}.",
             "RT if you've stopped counting"),
            ("x-milestone-10", "Three zeros",
             "Three zeros on the dashboard today.\n\n{users}. {revenue}. {posts}.\n\nNot the actual numbers. The number of digits.",
             "Reply with your three zeros"),
        ],
        "linkedin": [
            ("li-milestone-01", "1,000 users. Here's the weird one.",
             "1,000 users. Here's the weird one — the one that made me rethink who this is for.\n\n{weird_user_1} signed up because {weird_reason}. The reason has changed how I think about the entire product. Here is the full story and what I am doing about it.",
             "Save for your 1k"),
            ("li-milestone-02", "From 0 to $X MRR — the math nobody showed me",
             "0 → ${mrr} MRR in {days} days. {users} paying customers. {avg_revenue} ARPU.\n\nThe math nobody showed me — the actual cost of acquisition, the actual churn, the actual lifetime value. Here is the full breakdown, what surprised me, and the one thing I would do differently.",
             "Save for your 0→$X"),
            ("li-milestone-03", "100 paying customers — what I learned",
             "100 paying customers. {n} of them are {persona_1}. {m} are {persona_2}. {one_thing_i_learned} was the unlock.\n\nThe full post — who they are, what they bought, why they stayed, why they almost left, and the framework I now use to think about every customer.",
             "Comment with your 100"),
            ("li-milestone-04", "The 1% who show up — retention for solo builders",
             "1% of users show up at week 1. The other 99% are noise. At {user_count} users, here is what the 1% look like — and the framework I now use to find them, serve them, and grow from them. Retention is the only metric that matters for solo builders.",
             "Save for retention"),
            ("li-milestone-05", "First $1k MRR — the math",
             "First $1k MRR. {how_long_it_took}. {what_i_was_wrong_about}. {one_thing_that_worked}.\n\nThe full post — the math, the mistakes, the unlock, and the one principle I now use to set every milestone.",
             "Save for your $1k"),
            ("li-milestone-06", "100 posts published — what the data says",
             "100 posts published. The full data — engagement by post, by topic, by day, by hook type. The top 3, the bottom 3, the one pattern that emerged, and the framework I now use to write every post.",
             "Comment with your data"),
            ("li-milestone-07", "The number nobody asked me about",
             "The number nobody asks me about: {weird_metric}. {what_it_means} and {why_it_matters}.\n\nThe full post — the metric, the story behind it, what it predicts, and why it is more important than the metrics I usually report.",
             "Comment with your weird metric"),
            ("li-milestone-08", "Year 1 in numbers — the full report",
             "Year 1 in numbers. {metric_1}, {metric_2}, {metric_3}, {metric_4}, {metric_5}.\n\nThe full annual report — the wins, the losses, the lessons, and the one number I am proudest of that nobody else knows.",
             "Save for your year 1"),
            ("li-milestone-09", "The day I stopped counting",
             "I stopped counting {metric} on {date}. {what_changed} and {what_i_realized}.\n\nThe full post — the metric, the moment, what came after, and the framework I now use to know when a metric is no longer the right one to watch.",
             "Save for when to stop"),
            ("li-milestone-10", "Three zeros on the dashboard",
             "Three zeros on the dashboard today. {users}. {revenue}. {posts}.\n\nNot the actual numbers. The number of digits. The full post — what each zero means, what comes next, and the one thing about milestones nobody told me.",
             "Comment with your three zeros"),
        ],
        "blog": [
            ("blog-milestone-01", "1,000 users — the full story",
             "1,000 users. The full story — how we got here, who the weird one is, what changed, what stayed the same. The metrics, the qualitative feedback, the user research, the lessons, and the one thing I would tell myself on day 1.",
             "Read the 1k story"),
            ("blog-milestone-02", "From 0 to $X MRR — the full report",
             "0 → ${mrr} MRR in {days} days. The full report — the math, the costs, the churn, the LTV, the channel mix, the pricing experiments, and the one decision that unlocked everything.",
             "Read the MRR report"),
            ("blog-milestone-03", "100 paying customers — the full breakdown",
             "100 paying customers. The full breakdown — who they are, what they bought, why they stayed, why they almost left, the support load, the renewal pattern, and the framework I now use to think about every customer.",
             "Read the customer breakdown"),
            ("blog-milestone-04", "The 1% retention rule",
             "1% of users show up at week 1. The full post on retention for solo builders — what the 1% look like, how to find them, how to serve them, and the framework I now use to grow from them. Retention is the only metric that matters.",
             "Read the retention post"),
            ("blog-milestone-05", "First $1k MRR — the math and the lessons",
             "First $1k MRR. The math, the mistakes, the unlock, and the principle I now use to set every milestone. The full post — the funnel, the conversion, the price points, the offer structure, and what I would do differently.",
             "Read the $1k post"),
            ("blog-milestone-06", "100 posts — the full data analysis",
             "100 posts published. The full data analysis — engagement by post, topic, day, hook type, length, and structure. The top 3, the bottom 3, the patterns, and the framework I now use to write every post.",
             "Read the data analysis"),
            ("blog-milestone-07", "The number nobody asked me about",
             "The number nobody asks me about: {weird_metric}. The full post — the metric, the story behind it, what it predicts, and why it is more important than the metrics I usually report. Sometimes the weird number is the right number.",
             "Read the weird metric post"),
            ("blog-milestone-08", "Year 1 in numbers — the full annual report",
             "Year 1 in numbers. The full annual report — the wins, the losses, the lessons, and the one number I am proudest of that nobody else knows. The metrics, the qualitative data, the user stories, and the framework I now use to set year 2.",
             "Read the year 1 report"),
            ("blog-milestone-09", "The day I stopped counting",
             "I stopped counting {metric} on {date}. The full post — the metric, the moment, what came after, and the framework I now use to know when a metric is no longer the right one to watch. The lesson is bigger than the metric.",
             "Read the stopping post"),
            ("blog-milestone-10", "Three zeros on the dashboard — the full milestone essay",
             "Three zeros on the dashboard today. {users}. {revenue}. {posts}. The full essay — what each zero means, what comes next, the milestones I am chasing now, and the one thing about milestones nobody told me before I started.",
             "Read the milestone essay"),
        ],
    },
}


def add_defaults(category: str) -> dict:
    """Return the defaults block for a new category."""
    if category == "ship_log":
        return {
            "psych_triggers": [pride for pride in ("pride", "fear", "curiosity", "belonging")][0:4],
            "anti_patterns": ["generic_advice", "no_emotion"],
            "body": "narrative",
            "best_for": {
                "archetypes": ["S2", "S8", "S10"],
                "meaning_axes": ["behavioral", "leverage", "human"],
                "funnel_stages": ["TOFU", "MOFU"],
                "icp_layers": ["L1", "L2", "L3"],
            },
        }
    if category == "product":
        return {
            "psych_triggers": ["pride", "curiosity", "trust", "greed"],
            "anti_patterns": ["generic_advice", "no_emotion"],
            "body": "narrative",
            "best_for": {
                "archetypes": ["S2", "S8", "S1"],
                "meaning_axes": ["leverage", "systemic", "behavioral"],
                "funnel_stages": ["MOFU", "TOFU"],
                "icp_layers": ["L2", "L3"],
            },
        }
    if category == "milestone":
        return {
            "psych_triggers": ["pride", "fomo", "trust", "curiosity"],
            "anti_patterns": ["no_emotion", "buried_value"],
            "body": "narrative",
            "best_for": {
                "archetypes": ["S1", "S6", "S10"],
                "meaning_axes": ["human", "leverage", "systemic"],
                "funnel_stages": ["MOFU", "TOFU", "BOFU"],
                "icp_layers": ["L1", "L2", "L3"],
            },
        }
    return {}


def _emotion_list():
    return ["pride", "fear", "curiosity", "belonging", "hope", "guilt", "trust", "fomo", "greed", "anger"]


def add_bip_templates(registry_path: Path) -> dict:
    if not registry_path.exists():
        return {"ok": False, "reason": f"not found: {registry_path}"}
    data = yaml.safe_load(registry_path.read_text()) or {}
    if "platforms" not in data:
        data["platforms"] = {}
    added = 0
    skipped = 0
    by_platform_cat = {}
    for category, platforms in NEW_TEMPLATES.items():
        for plat_id, templates in platforms.items():
            if plat_id not in data["platforms"]:
                data["platforms"][plat_id] = {"categories": []}
            cats = data["platforms"][plat_id].setdefault("categories", [])
            existing_ids = {t["id"] for cat in cats for t in cat.get("templates", [])}
            cat_idx = None
            for i, cat in enumerate(cats):
                if cat.get("id") == category:
                    cat_idx = i
                    break
            if cat_idx is None:
                new_cat = {
                    "id": category,
                    "name": f"{category.replace('_', ' ').title()} — BiP Core",
                    "defaults": add_defaults(category),
                    "templates": [],
                }
                cats.append(new_cat)
                cat_idx = len(cats) - 1
            for tmpl_id, name, hook, cta in templates:
                if tmpl_id in existing_ids:
                    skipped += 1
                    continue
                cats[cat_idx]["templates"].append({
                    "id": tmpl_id,
                    "name": name,
                    "hook": hook,
                    "cta": cta,
                })
                added += 1
                by_platform_cat[(plat_id, category)] = by_platform_cat.get((plat_id, category), 0) + 1
    registry_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return {
        "ok": True,
        "added": added,
        "skipped": skipped,
        "by_platform_cat": {f"{p}/{c}": n for (p, c), n in by_platform_cat.items()},
    }


def main():
    registry_path = Path(engine_state.VAULT) / "templates" / "registry" / "viral-templates.yaml"
    result = add_bip_templates(registry_path)
    if not result.get("ok"):
        print(f"ERROR: {result.get('reason')}", file=sys.stderr)
        return 1
    print(f"  added:   {result['added']}")
    print(f"  skipped: {result['skipped']}")
    for k, v in sorted(result.get("by_platform_cat", {}).items()):
        print(f"  {k:30s} +{v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
