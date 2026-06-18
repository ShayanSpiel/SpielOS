#!/usr/bin/env python3
"""add_expanded_templates.py — Add the 3 expanded BiP template categories.

Adds 90 templates across:
  - feature       (added Y, here's why)              10 × 3 platforms
  - behind        (what's in my stack)               10 × 3 platforms
  - case_study    (client X went from Y to Z)        10 × 3 platforms

Idempotent: skips templates that already exist.
"""

from pathlib import Path
import sys
import yaml

import engine_state


NEW_TEMPLATES = {
    "feature": {
        "x": [
            ("x-feature-01", "Added Y. Here's the one metric that moved.",
             "Added {feature} last week.\n\n{number} users used it. {metric} moved {percentage}%.\n\nThe thing I did not expect: {surprise}.",
             "RT if you ship features"),
            ("x-feature-02", "The small change that mattered most",
             "The small change that mattered most this month: {feature}.\n\n{n} lines. {m} days. {result}.",
             "Follow for build logs"),
            ("x-feature-03", "I added a feature nobody asked for",
             "I added {feature}. Nobody asked for it.\n\n{users_using_it} users tried it in the first {timeframe}. {feedback}.",
             "RT if you build unprompted"),
            ("x-feature-04", "The feature I almost killed",
             "Almost killed {feature}. {users_using_it} users used it. {percentage}% of them were power users.\n\nI kept it. Here's the framework I used:",
             "Save for feature decisions"),
            ("x-feature-05", "Why I added a feature you won't see",
             "Added {feature} today. You will not see it.\n\n{why_invisible} and {why_it_matters}.",
             "Follow for invisible work"),
            ("x-feature-06", "Added Y, removed Z. Net: same lines, more value.",
             "Added {feature_a}, removed {feature_b}.\n\nNet: same lines of code. {metric} moved {percentage}%.",
             "Reply with your swaps"),
            ("x-feature-07", "The feature that 3 users asked for",
             "3 users asked for {feature}.\n\nI built it in a weekend. {result}.",
             "RT if you listen to 3"),
            ("x-feature-08", "The 1% feature I built for me",
             "Built {feature} for me. {users_using_it} other people use it too.\n\n{why_i_built_it_for_me}.",
             "Follow for selfish features"),
            ("x-feature-09", "The feature I added on a Tuesday",
             "Added {feature} on a Tuesday.\n\n{why_tuesday} and {what_happened}.",
             "Reply with your Tuesday ships"),
            ("x-feature-10", "What 'small' features look like at scale",
             "At {user_count} users, the small features add up.\n\n{feature_a} +{metric_a}. {feature_b} +{metric_b}. {feature_c} +{metric_c}.",
             "Save for your scale-up"),
        ],
        "linkedin": [
            ("li-feature-01", "Added Y, here's the one metric that moved",
             "Added {feature} last week. {number} users used it. {metric} moved {percentage}%. The thing I did not expect: {surprise}.\n\nThe full post — why we built it, what surprised us, what we would do differently, and the one metric that proved the feature was worth shipping.",
             "Save for feature launches"),
            ("li-feature-02", "The small change that mattered most",
             "The small change that mattered most this month: {feature}. {n} lines. {m} days. {result}.\n\nThe full post — the small changes, the big outcomes, the ones we missed, and the framework I now use to decide which small changes are worth shipping.",
             "Comment with your small wins"),
            ("li-feature-03", "I added a feature nobody asked for",
             "I added {feature}. Nobody asked for it. {users_using_it} users tried it in the first {timeframe}. {feedback}.\n\nThe full post — the case for building unprompted, the risk of building unprompted, and the framework I use to decide when to ship a feature nobody asked for.",
             "Save for unprompted features"),
            ("li-feature-04", "The feature I almost killed",
             "Almost killed {feature}. {users_using_it} users used it. {percentage}% of them were power users. I kept it.\n\nThe full post — the framework for keeping vs killing features, the math of maintenance, the user research, and the one question I ask before killing anything.",
             "Comment if you've killed a feature"),
            ("li-feature-05", "Why I added a feature you won't see",
             "Added {feature} today. You will not see it. {why_invisible} and {why_it_matters}.\n\nThe full post — the invisible work of building software, what stays in the codebase and what gets surfaced, and the framework I use to decide.",
             "Save for invisible work"),
            ("li-feature-06", "Added Y, removed Z — the net-zero change",
             "Added {feature_a}, removed {feature_b}. Net: same lines of code. {metric} moved {percentage}%.\n\nThe full post — the case for net-zero code changes, the feature swap framework, and the user research behind every swap we make.",
             "Comment with your swaps"),
            ("li-feature-07", "The feature that 3 users asked for",
             "3 users asked for {feature}. I built it in a weekend. {result}.\n\nThe full post — the case for listening to 3 users, the math of small user requests, and the framework I use to decide which to build and which to ignore.",
             "Save for small requests"),
            ("li-feature-08", "The 1% feature I built for me",
             "Built {feature} for me. {users_using_it} other people use it too. {why_i_built_it_for_me}.\n\nThe full post — the case for building selfish features, the user research that emerged, and the framework I use to decide when to build for me vs for them.",
             "Save for selfish features"),
            ("li-feature-09", "The feature I added on a Tuesday",
             "Added {feature} on a Tuesday. {why_tuesday} and {what_happened}.\n\nThe full post — the case for shipping on Tuesdays, the rhythm of building, the features that ship on random days, and the framework I use to time my releases.",
             "Comment with your Tuesday ships"),
            ("li-feature-10", "What 'small' features look like at scale",
             "At {user_count} users, the small features add up. {feature_a} +{metric_a}. {feature_b} +{metric_b}. {feature_c} +{metric_c}.\n\nThe full post — the math of small features at scale, the long tail of impact, and the framework I use to decide which small features to ship at scale.",
             "Save for your scale-up"),
        ],
        "blog": [
            ("blog-feature-01", "Added Y — the full feature post",
             "Added {feature}. The full feature post — the why, the design, the engineering, the user research, the launch, the metrics, the surprises, and the things I would do differently. The post I wish I had read before I built it.",
             "Read the feature post"),
            ("blog-feature-02", "The small change that mattered most — long form",
             "The small change that mattered most this month. The long version — the math, the user feedback, the post-mortem, the framework for deciding which small changes are worth shipping, and the one I will remember.",
             "Read the small change post"),
            ("blog-feature-03", "I added a feature nobody asked for",
             "I added {feature}. Nobody asked for it. The full post — the case for building unprompted, the risk, the user research, the launch, the metrics, and the framework I use to decide when to ship a feature nobody asked for.",
             "Read the unprompted post"),
            ("blog-feature-04", "The feature I almost killed",
             "Almost killed {feature}. The full post — the framework for keeping vs killing, the math of maintenance, the user research, the post-mortem, and the one question I ask before killing anything. The post every PM should read before sunsetting anything.",
             "Read the killing post"),
            ("blog-feature-05", "Why I added a feature you won't see",
             "Added a feature you will not see. The full post — the invisible work of building software, what stays in the codebase and what gets surfaced, the framework I use to decide, and the post I wish I had read about invisible features.",
             "Read the invisible post"),
            ("blog-feature-06", "Added Y, removed Z — the net-zero playbook",
             "Added {feature_a}, removed {feature_b}. Net: same lines of code. The full playbook — the case for net-zero code changes, the feature swap framework, the user research, and the math every engineering team should know.",
             "Read the swap playbook"),
            ("blog-feature-07", "The feature that 3 users asked for",
             "3 users asked for {feature}. The full post — the case for listening to 3 users, the math of small user requests, the framework I use to decide which to build, and the one I will remember forever.",
             "Read the small request post"),
            ("blog-feature-08", "The 1% feature I built for me",
             "Built {feature} for me. The full post — the case for building selfish features, the user research that emerged, the framework I use to decide when to build for me vs for them, and the one feature I will never delete.",
             "Read the selfish post"),
            ("blog-feature-09", "The feature I added on a Tuesday",
             "Added a feature on a Tuesday. The full post — the case for shipping on Tuesdays, the rhythm of building, the features that ship on random days, and the framework I use to time my releases. The post every indie hacker should read.",
             "Read the Tuesday post"),
            ("blog-feature-10", "What 'small' features look like at scale",
             "At {user_count} users, the small features add up. The full post — the math, the long tail, the framework I use to decide which small features to ship at scale, and the ones that surprised me the most.",
             "Read the scale post"),
        ],
    },
    "behind": {
        "x": [
            ("x-behind-01", "What's in my stack",
             "What's in my stack:\n\n- {tool_1} for {purpose_1}\n- {tool_2} for {purpose_2}\n- {tool_3} for {purpose_3}\n- {tool_4} for {purpose_4}\n\nTotal: ${cost}/mo. Worth every cent.",
             "Reply with your stack"),
            ("x-behind-02", "The tool that changed how I work",
             "The tool that changed how I work: {tool}.\n\n{before_state} → {after_state}.\n\nI would pay {amount} for this. The actual cost: {actual_cost}.",
             "RT if you agree"),
            ("x-behind-03", "The tool I dropped this year",
             "Dropped {tool} this year.\n\n{why}. {what_i_use_instead}. {what_i_miss}.",
             "Reply with your drops"),
            ("x-behind-04", "My notion setup — 4 years of iteration",
             "My Notion setup — 4 years of iteration.\n\n{databases}, {pages}, {templates}.\n\nThe one thing I would do differently: {lesson}.",
             "Save if you use Notion"),
            ("x-behind-05", "The boring tool that does the heavy lifting",
             "The boring tool that does the heavy lifting: {tool}.\n\nNo marketing. No Twitter hype. Just {what_it_does}.",
             "Follow for boring tools"),
            ("x-behind-06", "I replaced 5 tools with 1",
             "Replaced 5 tools with 1.\n\nBefore: {tool_a}, {tool_b}, {tool_c}, {tool_d}, {tool_e}.\nAfter: {tool_z}.\n\nSaved {hours}/week.",
             "RT if you consolidate"),
            ("x-behind-07", "The 3 tools I use every day",
             "The 3 tools I use every day:\n\n1. {tool_1} — {what_for}\n2. {tool_2} — {what_for}\n3. {tool_3} — {what_for}\n\n{note_about_choosing}.",
             "Save if you like tools"),
            ("x-behind-08", "My build environment in 4 commands",
             "My build environment in 4 commands:\n\n- {cmd_1}\n- {cmd_2}\n- {cmd_3}\n- {cmd_4}\n\n{note_about_reproducibility}.",
             "Reply with yours"),
            ("x-behind-09", "The free tool I can't live without",
             "The free tool I can't live without: {tool}.\n\n{why_free} and {what_it_replaces}.",
             "RT free tools"),
            ("x-behind-10", "What my editor looks like",
             "What my editor looks like: {screenshot_or_desc}.\n\n{font}, {theme}, {plugins}.\n\n{one_thing_about_flow}.",
             "Reply with your setup"),
        ],
        "linkedin": [
            ("li-behind-01", "What's in my stack — the full post",
             "What's in my stack. The full post — every tool, the cost, the reason, the alternatives I tried, the ones I dropped, and the one tool I would pay 10x more for. The post I wish I had read when I started.",
             "Save for your stack"),
            ("li-behind-02", "The tool that changed how I work",
             "The tool that changed how I work: {tool}. {before_state} → {after_state}.\n\nThe full post — the before/after, the cost, the alternatives, the things I miss from the old tool, and the framework I use to decide which tool is worth the price.",
             "Comment with your tool"),
            ("li-behind-03", "The tool I dropped this year",
             "Dropped {tool} this year. {why}. {what_i_use_instead}. {what_i_miss}.\n\nThe full post — the case for dropping tools, the math of switching costs, the migration plan, and the framework I use to decide when to drop a tool.",
             "Save for tool swaps"),
            ("li-behind-04", "My Notion setup — 4 years of iteration",
             "My Notion setup — 4 years of iteration. {databases}, {pages}, {templates}.\n\nThe full post — the setup, the lessons, the things I would do differently, the templates, and the one habit that made the biggest difference.",
             "Save for your Notion"),
            ("li-behind-05", "The boring tool that does the heavy lifting",
             "The boring tool that does the heavy lifting: {tool}. No marketing. No Twitter hype. Just {what_it_does}.\n\nThe full post — the case for boring tools, the boring tools I use, the ones I would never replace, and the framework I use to evaluate tools.",
             "Save for boring tools"),
            ("li-behind-06", "I replaced 5 tools with 1",
             "Replaced 5 tools with 1. The full post — the case for consolidation, the migration plan, the things I lost, the things I gained, and the framework I use to decide which tools to keep.",
             "Comment with your stack"),
            ("li-behind-07", "The 3 tools I use every day",
             "The 3 tools I use every day. The full post — the tools, what I use them for, the alternatives, the cost, and the framework I use to choose tools. The post I wish I had read when I started building.",
             "Save for tool choices"),
            ("li-behind-08", "My build environment in 4 commands",
             "My build environment in 4 commands. The full post — the commands, the reproducibility, the alternatives, the time savings, and the framework I use to set up dev environments.",
             "Save for your env"),
            ("li-behind-09", "The free tool I can't live without",
             "The free tool I can't live without: {tool}. The full post — the free tools I use, the cost they would charge, the alternatives, and the framework I use to decide when to pay for a tool vs use the free version.",
             "Save for free tools"),
            ("li-behind-10", "What my editor looks like",
             "What my editor looks like. The full post — the setup, the font, the theme, the plugins, the keyboard shortcuts, and the framework I use to set up an editor for flow.",
             "Comment with your setup"),
        ],
        "blog": [
            ("blog-behind-01", "What's in my stack — the full breakdown",
             "What's in my stack. The full breakdown — every tool, the cost, the reason, the alternatives I tried, the ones I dropped, and the framework I use to decide which tools to keep. The post I wish I had read when I started building.",
             "Read the stack breakdown"),
            ("blog-behind-02", "The tool that changed how I work — the long form",
             "The tool that changed how I work. The long form — the before/after, the cost, the alternatives, the things I miss from the old tool, and the framework I use to evaluate which tool is worth the price.",
             "Read the tool essay"),
            ("blog-behind-03", "The tool I dropped this year",
             "Dropped {tool} this year. The full post — the case for dropping tools, the math of switching costs, the migration plan, the things I lost, the things I gained, and the framework I use to decide when to drop a tool.",
             "Read the dropping post"),
            ("blog-behind-04", "My Notion setup — the full template",
             "My Notion setup — 4 years of iteration. The full template — the databases, the pages, the templates, the views, the formulas, and the framework I use to keep it useful. The post I wish I had read when I started.",
             "Read the Notion template"),
            ("blog-behind-05", "The boring tools that do the heavy lifting",
             "The boring tools that do the heavy lifting. The full post — the case for boring tools, the boring tools I use every day, the ones I would never replace, and the framework I use to evaluate tools.",
             "Read the boring tools post"),
            ("blog-behind-06", "I replaced 5 tools with 1 — the migration playbook",
             "I replaced 5 tools with 1. The full migration playbook — the case for consolidation, the migration plan, the things I lost, the things I gained, and the framework I use to decide which tools to keep.",
             "Read the migration playbook"),
            ("blog-behind-07", "The 3 tools I use every day — the long form",
             "The 3 tools I use every day. The long form — the tools, what I use them for, the alternatives, the cost, the switching costs, and the framework I use to choose tools. The post I wish I had read when I started.",
             "Read the tools essay"),
            ("blog-behind-08", "My build environment in 4 commands",
             "My build environment in 4 commands. The full post — the commands, the reproducibility, the alternatives, the time savings, and the framework I use to set up dev environments for new projects.",
             "Read the env post"),
            ("blog-behind-09", "The free tools I can't live without",
             "The free tools I can't live without. The full post — the free tools I use, the cost they would charge, the alternatives, and the framework I use to decide when to pay for a tool vs use the free version.",
             "Read the free tools post"),
            ("blog-behind-10", "What my editor looks like — the long form",
             "What my editor looks like. The long form — the setup, the font, the theme, the plugins, the keyboard shortcuts, the macros, and the framework I use to set up an editor for flow.",
             "Read the editor setup"),
        ],
    },
    "case_study": {
        "x": [
            ("x-case-01", "Client X went from Y to Z",
             "Client {client} went from {before_metric} to {after_metric} in {timeframe}.\n\n{one_change} → {result}.",
             "Reply with your case"),
            ("x-case-02", "Before/after — the math",
             "Before: {before_state}\nAfter: {after_state}\n\n{one_thing_that_changed} → {result_metric}.",
             "Save for your case studies"),
            ("x-case-03", "3 clients, 1 pattern",
             "3 clients, 1 pattern.\n\nAll of them had {common_problem}.\n\nAll of them fixed it with {common_solution}.",
             "Reply if you see the pattern"),
            ("x-case-04", "The case I can't talk about (but here are the numbers)",
             "The case I can't talk about.\n\n{industry}, {n} months, {result_metric}.\n\nAnonymized because {reason}.",
             "RT if you've anonymized"),
            ("x-case-05", "What 'success' actually looked like",
             "What 'success' actually looked like for {client}:\n\n{before_state} → {after_state}.\n\n{thing_i_expected} vs {thing_that_actually_happened}.",
             "Save if you're scaling"),
            ("x-case-06", "The cheapest client work I did",
             "The cheapest client work I did: {hours} hours, ${amount}.\n\n{result}.\n\nThe most valuable lesson: {lesson}.",
             "Reply with your cheapest"),
            ("x-case-07", "I lost the client. Here's what I learned.",
             "I lost the client.\n\n{why}. {what_i_learned}. {what_i_would_do_differently}.",
             "Save for the L's"),
            ("x-case-08", "The 6-month case study",
             "6 months ago: {client} asked for {request}.\n\nToday: {result}.\n\n{number} of {outcome}.",
             "Follow for case studies"),
            ("x-case-09", "What worked for one client (but not the next)",
             "What worked for one client: {solution}.\n\nWhat did not work for the next: {why_it_failed}.\n\n{what_i_learned_about_generalization}.",
             "Save for generalization"),
            ("x-case-10", "The client who changed my product",
             "The client who changed my product: {client}.\n\n{request} → {feature_added}.\n\n{users_using_it} now use it.",
             "Reply with your changing client"),
        ],
        "linkedin": [
            ("li-case-01", "Client X went from Y to Z — the full case study",
             "Client {client} went from {before_metric} to {after_metric} in {timeframe}. {one_change} → {result}.\n\nThe full case study — the context, the diagnosis, the intervention, the result, the lessons, and what I would do differently. The post I wish I had read before I started working with clients.",
             "Save for the case study"),
            ("li-case-02", "Before/after — the math",
             "Before: {before_state}. After: {after_state}. {one_thing_that_changed} → {result_metric}.\n\nThe full post — the math of the transformation, the timeline, the interventions, the user research, and the framework I use to measure client outcomes.",
             "Save for the transformation"),
            ("li-case-03", "3 clients, 1 pattern",
             "3 clients, 1 pattern. All of them had {common_problem}. All of them fixed it with {common_solution}.\n\nThe full post — the pattern, the data, the cases, the math, and the framework I use to spot patterns across client work.",
             "Comment with your pattern"),
            ("li-case-04", "The case I can't talk about",
             "The case I can't talk about. {industry}, {n} months, {result_metric}. Anonymized because {reason}.\n\nThe full post — the lessons, the math, the things I learned, and the framework I use to extract learning from confidential work.",
             "Save for the L's"),
            ("li-case-05", "What 'success' actually looked like",
             "What 'success' actually looked like for {client}: {before_state} → {after_state}. {thing_i_expected} vs {thing_that_actually_happened}.\n\nThe full post — the real outcome, the unexpected wins, the unexpected losses, and the framework I use to set expectations with clients.",
             "Save for the wins"),
            ("li-case-06", "The cheapest client work I did",
             "The cheapest client work I did: {hours} hours, ${amount}. {result}. The most valuable lesson: {lesson}.\n\nThe full post — the math of cheap client work, the lessons, the things I would not do again, and the framework I use to price short engagements.",
             "Comment with your cheap work"),
            ("li-case-07", "I lost the client. Here's what I learned.",
             "I lost the client. {why}. {what_i_learned}. {what_i_would_do_differently}.\n\nThe full post — the loss, the post-mortem, the lessons, the things I would not change, and the framework I use to learn from losing clients.",
             "Save for the L's"),
            ("li-case-08", "The 6-month case study",
             "6 months ago: {client} asked for {request}. Today: {result}. {number} of {outcome}.\n\nThe full post — the timeline, the interventions, the metrics, the surprises, and the framework I use to track 6-month client outcomes.",
             "Save for long case studies"),
            ("li-case-09", "What worked for one client (but not the next)",
             "What worked for one client: {solution}. What did not work for the next: {why_it_failed}. {what_i_learned_about_generalization}.\n\nThe full post — the case for generalization, the cases, the lessons, and the framework I use to know when to generalize.",
             "Save for the lesson"),
            ("li-case-10", "The client who changed my product",
             "The client who changed my product: {client}. {request} → {feature_added}. {users_using_it} now use it.\n\nThe full post — the case for listening to clients, the math, the user research, and the framework I use to decide which client requests become product features.",
             "Save for product feedback"),
        ],
        "blog": [
            ("blog-case-01", "Client X went from Y to Z — the full case study",
             "Client {client} went from {before_metric} to {after_metric} in {timeframe}. The full case study — the context, the diagnosis, the intervention, the result, the lessons, the data, and the framework I use to do this work.",
             "Read the case study"),
            ("blog-case-02", "Before/after — the math of transformation",
             "Before: {before_state}. After: {after_state}. The math of transformation — the timeline, the interventions, the user research, the surprises, and the framework I use to measure outcomes.",
             "Read the math post"),
            ("blog-case-03", "3 clients, 1 pattern — the full post",
             "3 clients, 1 pattern. The full post — the pattern, the data, the cases, the math, the lessons, and the framework I use to spot patterns across client work.",
             "Read the pattern post"),
            ("blog-case-04", "The case I can't talk about — anonymized essay",
             "The case I can't talk about. Anonymized. The full essay — the lessons, the math, the things I learned, the things I would not change, and the framework I use to extract learning from confidential work.",
             "Read the anonymized essay"),
            ("blog-case-05", "What 'success' actually looked like",
             "What 'success' actually looked like. The full essay — the real outcome, the unexpected wins, the unexpected losses, and the framework I use to set expectations with clients.",
             "Read the success essay"),
            ("blog-case-06", "The cheapest client work I did",
             "The cheapest client work I did. The full essay — the math, the lessons, the things I would not do again, the things I would do again, and the framework I use to price short engagements.",
             "Read the cheap work essay"),
            ("blog-case-07", "I lost the client — the full post-mortem",
             "I lost the client. The full post-mortem — the loss, the analysis, the lessons, the things I would not change, and the framework I use to learn from losing clients.",
             "Read the loss post-mortem"),
            ("blog-case-08", "The 6-month case study",
             "6 months ago: {client} asked for {request}. Today: {result}. The full 6-month case study — the timeline, the interventions, the metrics, the surprises, and the framework I use to track long client outcomes.",
             "Read the 6-month study"),
            ("blog-case-09", "What worked for one client (but not the next)",
             "What worked for one client: {solution}. What did not work for the next: {why_it_failed}. The full essay — the case for generalization, the cases, the lessons, and the framework I use to know when to generalize.",
             "Read the generalization essay"),
            ("blog-case-10", "The client who changed my product",
             "The client who changed my product. The full essay — the case for listening to clients, the math, the user research, the feature, the launch, the metrics, and the framework I use to decide which client requests become product features.",
             "Read the product feedback essay"),
        ],
    },
}


def add_defaults(category: str) -> dict:
    if category == "feature":
        return {
            "psych_triggers": ["curiosity", "greed", "trust"],
            "anti_patterns": ["generic_advice", "no_emotion"],
            "body": "narrative",
            "best_for": {
                "archetypes": ["S2", "S8", "S1"],
                "meaning_axes": ["leverage", "behavioral", "systemic"],
                "funnel_stages": ["MOFU", "TOFU"],
                "icp_layers": ["L1", "L2", "L3"],
            },
        }
    if category == "behind":
        return {
            "psych_triggers": ["curiosity", "greed", "pride"],
            "anti_patterns": ["no_emotion", "buried_value"],
            "body": "narrative",
            "best_for": {
                "archetypes": ["S8", "S7", "S10"],
                "meaning_axes": ["behavioral", "leverage"],
                "funnel_stages": ["TOFU", "MOFU"],
                "icp_layers": ["L1", "L2", "L3"],
            },
        }
    if category == "case_study":
        return {
            "psych_triggers": ["trust", "greed", "fomo", "pride"],
            "anti_patterns": ["no_emotion", "buried_value"],
            "body": "narrative",
            "best_for": {
                "archetypes": ["S6", "S1", "S7"],
                "meaning_axes": ["leverage", "systemic", "human"],
                "funnel_stages": ["BOFU", "MOFU"],
                "icp_layers": ["L3", "L4"],
            },
        }
    return {}


def add_expanded_templates(registry_path: Path) -> dict:
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
                    "name": f"{category.replace('_', ' ').title()} — BiP Expanded",
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
    result = add_expanded_templates(registry_path)
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
