# SOUP Agency — AI & Automation Intern Interview Prep

**Interview:** Monday 16 November 2026, 11:30am. Sydney CBD (hybrid) — confirm whether it's at 4/60 Clarence Street or a video link.
**Who you'll likely meet:** Katya Vakulenko, Founder & Managing Director (she started SOUP in Sydney in 2019, no investors, still independent), possibly with a technical mentor.
**Format:** probably a conversation about what you've built, how you think, and whether you can ship small tools. Be ready to show something and explain it.

---

## 1. The company (grounded in public info, not GBrain — GBrain has no SOUP record)

- Independent, senior-led digital marketing agency, founded 2019 in Sydney by Katya Vakulenko. General Manager: Jess White.
- HQ: 4/60 Clarence Street, Sydney CBD; also Melbourne and Brisbane. ~17 specialists in one team, 200+ brands grown, 4.9★ on Clutch.
- Services: digital strategy, SEO and AI search (GEO), Google Ads, paid and organic social, content, email & CRM (Klaviyo, HubSpot), analytics and measurement.
- Google Partner, Meta Business Partner, HubSpot Partner.
- **Relevant to this role:** SOUP sells AI automation to clients — "working AI automations deployed to production in 4-8 weeks", priced on outcomes (cost savings, time reduction, error elimination). So this internship is likely a mix of **internal tools** and **client-facing automation builds**, working directly with the founder.
- Role: permanent part-time, 2–3 days per week, with a path to full-time based on performance.

---

## 2. The role, translated

| JD asks for | What it means in the interview |
|---|---|
| Build internal tools, workflows, automations | You can take a repetitive manual process and turn it into a script or small app |
| Develop small applications and prototypes | Scope small, ship working code, iterate |
| Connect platforms through APIs | You've read API docs, handled auth, parsed JSON, dealt with rate limits/errors |
| Use Claude and AI coding assistants | You use AI to write and test code, and you verify its output instead of trusting it |
| Show something you've built | Bring a demo: Nirite, Agent-Reach, or work from Waddle AI / LiveHaus |
| Work independently, research unfamiliar problems, ask for guidance | Give examples of both: solving it yourself and escalating early |

**Eligibility:** The JD requires Australian PR or a relevant working visa. You lodged your 485 visa around 10 November 2026 — that's a relevant working visa. State it plainly if asked; don't over-explain.

**Availability:** 2–3 days a week, hybrid. Confirm your Mondays (or whichever days) work around your graduation (30 Nov – 5 Dec) and family visit (28 Nov – 12 Dec) if those dates still stand.

---

## 3. Your evidence, mapped to the JD

| JD requirement | Your story |
|---|---|
| CS degree or equivalent self-taught | UNSW Computer Science, completed August 2026 |
| Python or JavaScript | Nirite is a Python CLI (uv, pytest, ruff, mypy); backend work at Waddle AI internship |
| APIs to connect applications | Nirite routes between NVIDIA nemotron, Gemini, and Ministral providers with fallback logic; GBrain MCP integration |
| Structured data and databases | Nirite data models and dedup-store design (SQLite chosen — single file, zero cost, WAL mode) |
| Data and business analytics | LiveHaus growth internship: ran prospecting outreach, read campaign metrics (e.g., 303 impressions, 68% in-network / 32% out-of-network, 115 members reached) and decided what the numbers meant |
| Git, testing, docs | Nirite repo: git, pytest test suite, ruff linting, mypy type checks, README/docs |
| AI assistants + checking output | Build with nemotron/Claude; chose smaller models where they fit better; fallback chains when the primary provider fails |
| Something to show and explain | Nirite demo (local CLI, end-to-end), plus Agent-Reach and your internship work |

---

## 4. Project stories to tell (what you built / contributed / learned)

The application asked for exactly this structure. Use it in the interview too.

**Nirite — AI prospect qualification tool**
- What: a CLI that qualifies prospects using LLMs, with provider fallbacks (nemotron → Gemini → Ministral), structured outputs, evals, and a dedup store.
- You: sole architect and builder. Chose zero-cost models only. Wrote tests, linting, type checks.
- Learned: model routing is more expensive than it looks; smaller models beat bigger ones on many tasks; don't add a database until you need atomic check-then-act (SQLite was the right call; JSON/Postgres were wrong for this scale).

**LiveHaus — growth/digital marketing internship + Heyreach outreach automation**
- What: ran prospecting outreach, connected platforms, tracked whether activity turned into conversations.
- You: set up and ran campaigns, read the metrics, adjusted targeting.
- Learned: data quality beats volume; 303 impressions means nothing if the right 115 people didn't see it; automation that sends bad messages faster is just bad at scale.

**Waddle AI — software engineering internship (backend)**
- What: backend development on a real product.
- You: shipped features, code review, worked in a team.
- Learned: how a professional codebase moves, how to ask for help without blocking, how to document so someone else can pick it up.

**Agent-Reach (optional supporting example)**
- External research channels for Nirite and career exploration — shows you research unfamiliar problems on your own time.

If they ask about confidentiality at Waddle AI or LiveHaus, talk about what you built and learned without naming clients or sharing data.

---

## 5. Likely questions and how to answer

**Style notes for your answers (your voice):** middle formality, personal story first then nuance, medium technical depth. No em dashes, no rule-of-three lists, no "not just X but Y", no staccato short sentences, no motivational fluff.

### "Tell me about yourself."
Hook: I recently finished my Computer Science degree at UNSW, and since graduating I've been building Nirite, an AI-powered tool for qualifying prospects.
Nuance/evidence: Before that I interned at Waddle AI doing backend development, and at LiveHaus doing growth and digital marketing where I ran outreach automation with Heyreach. I'm comfortable in Python and JavaScript, I connect platforms through APIs, and I use AI coding assistants daily — but I treat their output as a draft, not an answer.
Close: I'm looking for a role where I build tools people actually use, which is why this caught my eye.

### "Why SOUP? Why this role?"
Hook: SOUP is independent and senior-led, and this role reports to the founder. That appeals to me because I want direct feedback and work that ships.
Nuance: I also like that SOUP sells automation to clients, not just uses it internally. I've seen both sides — running marketing campaigns at LiveHaus and building the tooling at Nirite — so I understand the client problem and the build problem.
Close: Part-time hybrid fits where I am right now, and I'd be glad if it turned into something full-time.

### "Tell me about something you've built."
Use the Nirite story (section 4). Structure: what it does → what you contributed → what you learned. Be ready to demo it live or share your screen. If they ask for code, walk them through one function — how it calls an API, parses the response, handles the error case.

### "How do you use AI coding assistants, and how do you check their output?"
Hook: I use them to write boilerplate, generate test cases, and explore unfamiliar APIs.
Nuance: I never paste their output straight into the repo. I read it, run it, and test the failure paths — timeouts, bad JSON, rate limits. For Nirite I chose nemotron as the primary model because it's free and capable, with Gemini and Ministral as fallbacks. I made that call after comparing them, not because a bigger model sounds better.
Close: The assistant writes the code; I'm still responsible for whether it works.

### "Describe a time you got stuck or had to debug something hard."
Pick a real Nirite debugging story: a provider returning malformed structured output, or a fallback chain that didn't trigger. Explain: what you expected, what happened, how you isolated it (logs, reproducing with a minimal input), and the fix. End with what you changed so it doesn't recur (e.g., added a validation step, added a test).

### "How do you decide when to ask for help versus figuring it out yourself?"
Hook: I research first, then time-box it.
Nuance: If I've been stuck for a couple of hours on something unfamiliar, I ask — with what I've tried and what I think the problem is. At LiveHaus I learned that asking early saves everyone time; at Nirite I learned that some problems only yield to sitting with them. Both are true, depending on the situation.

### "Can you connect two platforms through an API? Give an example."
Hook: Yes. In Nirite I connect to LLM providers through their APIs: auth headers, request bodies, streaming vs non-streaming responses, error handling.
Nuance: The hard part is rarely the happy path. It's retries with backoff, parsing partial responses, and not hammering a rate-limited endpoint. I'd bring the same approach to connecting, say, a CRM to an email platform or ad data to a reporting sheet.
Close: I read the docs, build a small script, test it with real data, then wrap it properly.

### "Do you have Australian permanent residency or a relevant working visa?"
Hook: Yes. I hold a 485 visa, which I lodged around 10 November 2026.
Close: That gives me full working rights in Australia.

### "Are you available 2–3 days a week, hybrid?"
Hook: Yes. I can commit to that schedule and come into the Clarence Street office.
Nuance: Check your graduation dates (30 Nov – 5 Dec) and family visit (28 Nov – 12 Dec) before naming specific days.

### "Where do you see this going?"
Hook: I'd like to start by shipping useful internal tools and client automations, learn how an agency runs, and grow into a full-time role if the fit works for both of us.

---

## 6. One idea to pitch (shows initiative)

SOUP pitches client automations with a 4–8 week build and outcome-based pricing. Come with one small, concrete idea, scoped to a week or two of an intern's time:

**Option A — New-business lead intake and enrichment.** A form or inbox trigger that captures a new lead, enriches it (LinkedIn/company look-up), drafts a personalised first message, and logs it so SOUP's team can review before sending. Manual today; automated tomorrow.

**Option B — Client performance snapshot.** A weekly script that pulls headline numbers from the platforms SOUP uses (Google Ads, Meta Ads, GA4, email) into one summary so the team spends less time copying numbers and more time interpreting them.

Present it as: "Here's one thing I'd build in my first month. I'd scope it with you first so it actually fits how you work." Don't oversell it — one small automation that saves a few hours a week is plenty.

---

## 7. Questions to ask them

- What would my first automation or internal tool be?
- How is the work split between internal tools and client-facing automations?
- How do you and the technical mentor split guidance?
- What does "good" look like after three months?
- What's your stack for automations today (scripts, n8n, Make, Zapier, custom code)?
- What's one manual process in the agency that annoys people every week?

---

## 8. Monday checklist

- [ ] Confirm time, location (office or link), and who you're meeting.
- [ ] Have Nirite running locally and ready to demo; prepare screenshots in case the demo environment fails.
- [ ] Bring/be ready to discuss your CV and one or two project examples (what you built, contributed, learned).
- [ ] Have your 485 visa detail ready if eligibility comes up.
- [ ] Name your preferred days for 2–3 days/week hybrid.
- [ ] Write your top 3–4 questions from section 7 in a notebook.

Good luck. You've built real things, you can explain them, and you understand the business side too — that's a strong combination for this role.
