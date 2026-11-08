# Cover Letter Voice Guide (Safwan)

Distilled from diffing 27 sent cover letters against their raw Resumate drafts (Oct-Nov 2026).
The letters used as voice sources: Quora Full-Stack, Affirm, Citco, Revvity, SOTI, PRI, 1Password,
Agility PR, DataVisor, BDO, plus small edits in Vaughan, Allstate, Compass, Geotab, ATS.

Resumate's current `VOICE` block (`COVER_LETTER_CALL.py`, `_SHARED_RULES`) is two lines:
"Confident, specific, professional... Mirror the job posting's key requirements". Most of what gets
rewritten by hand comes from that block producing polished, metric-heavy, company-flattering copy.
Section 3 is a drop-in replacement for it.

---

## 1. The voice in one paragraph

Plain, direct, first person, a little conversational. Sounds like a capable new grad talking to a
person rather than pitching to a committee. Claims are honest and sized correctly ("~2 years
professionally, 4-5 overall"), gaps are admitted with a short note on how they'd be closed, and the
reader is addressed directly ("below you can see what I bring to the table"). Confidence comes from
specifics and plain statements, not from adjectives or numbers.

---

## 2. Rules

### 2.1 Openers

- Start with the plain fact or a candid reaction to the posting. Not a thesis statement about the
  company.
  - OK: "I am applying to the Software Developer Intern role."
  - OK: "I would like to join your Card Pre-Swipe Experience team. I was not aware there was a full
    team for this, but after reading the description I could see myself working on it."
  - OK: "From what I understand, the role is about making X simpler and safer. This is right up my
    alley."
  - Cut: "Affirm's Card Pre-Swipe work sits exactly where I do my best work..."
  - Cut: "Citco's Reporting IT team builds the software that keeps clients connected... and that is
    the work I want to do."
  - Cut: "...is exactly the kind of problem I want to spend my career on."
- Don't restate the resume in the opener. Point to it: "My main credentials are on my resume;
  other than that, here's what I bring."
- One honest framing sentence about who you are is welcome: "I am, in general, a generalist. I've
  studied hardware, AI solutions, worked in development and DevOps."

### 2.2 The requirements table

- Keep the two-column "What you require / My Relevant Skills and Experience" table. Introduce it
  out loud: "Below is what I bring to the table." (A pun on "table" is allowed once, at most.)
- Requirement cells may quote the posting verbatim in quotation marks.
- Answer cells are short, first person, and direct. One or two sentences. Fragments are fine.
  - "What I've been doing daily for 4-5 years. Professionally for ~2 years."
  - "Designed the entire CRM for an architectural firm. The backend and frontend with APIs were
    done by me. I helped the DevOps guy with deployment as well."
  - "My favourite personal project was done in Vue (Resumate, on my GitHub)."
- Prefer years-of-use and "I did this myself" over outcome metrics.
- It's fine for one row to admit a weakness (see 2.4).

### 2.3 Strip list: always remove these from drafts

These were deleted by hand repeatedly. Don't generate them.

| Pattern | Example from drafts |
|---|---|
| Dollar savings | "saving about $600 a month" |
| Headcounts / user counts | "used by 40+ staff", "for 40+ contractors" |
| Superlative awards | "highest Systems Acceptance Review score in university history (97%)", "Top 30 of 102 globally" |
| Benchmark brags | "matched top models at a fraction of the cost" |
| Company-value mirroring | "BDO's focus on genuine care and forward thinking matches how I work" |
| "Exactly" / destiny framing | "exactly the environment I want", "lines up directly with what I enjoy building" |
| Stacked tech lists in prose | "Terraform and Bicep for IaC, Azure DevOps, Azure SQL, VNets, NSGs, Private Endpoints..." |
| Requisition numbers in body text | "...Automation (Requisition 17877)." |
| Flourish closers | "...how I can help the Product Analytics squad turn product data into clear, actionable recommendations." |

Achievements can stay, just stated without the scoreboard: "built the rover's driving controls and
live dashboard" is fine; "...earning the highest score in university history" is not.

### 2.4 Honesty and gaps

- Say where you're thin and what you'd do about it, in one line:
  - "This is likely where I would want to improve most if I got the internship."
  - "I've only ever worked with Maven, not much Gradle (although I can quickly learn it if needed)."
  - "Initially only worked with SQL through ORMs, but gaining direct SQL experience through my
    recent internship."
- Certifications are framed as theory you want to apply: "I recently earned the AWS Solutions
  Architect - Associate, so I'm familiar with the theory behind most AWS services and how they
  connect. I'd love the chance to apply that practically."
- Never overclaim daily use of a tool you only touched once. "One end-to-end personal project in
  Kotlin" beats "comfortable in Kotlin".

### 2.5 AI stance (recurring theme, use when relevant)

- Learned software fundamentals before LLMs were everywhere, so can debug by hand.
- Now uses AI coding tools (Cursor, Claude Code) constantly and knows "what it can and cannot do".
- Human in the loop: AI for low-judgement, time-consuming work; a person reviews and gives context.
- Keep it to one or two sentences. Light irony ("the AI epidemic") is fine; preaching is not.

### 2.6 Closers

- Short and plain. One or two sentences.
  - "In conclusion, I would like a chance to intern on your team. I believe I'll learn a lot from
    the role but also bring a lot to the table. Thank you for your consideration."
  - "I work carefully, document what I do, and verify before I call something done. Thank you for
    your time."

### 2.7 Texture

- Contractions are normal (I'm, I've, I'd).
- Casual connectors are allowed sparingly: "Anyways,", "Other than that,", "Aside from that,",
  "For context,".
- Hyphen with spaces instead of em dashes ("I was not aware there was a full team for this - but").
- Parenthetical asides: "(pun intended)", "(although I can quickly learn it if needed)".
- Quirk budget: at most one personal or playful line per letter, and only if it's true (e.g. a
  holiday greeting on the actual day). Default is zero.
- Length: usually shorter than what Resumate drafts. Cutting a whole section is better than padding.
- Do not imitate typos. They were accidents, not voice.

---

## 3. Drop-in prompt block (replaces the `VOICE` section in `_SHARED_RULES`)

```text
    VOICE
    - Plain, direct, first person, lightly conversational. Contractions are fine. Write like a
      capable new grad talking to one person, not a pitch to a committee.
    - Open with the plain fact ("I am applying to the X role.") or a candid one-line reaction to
      the posting. Never open with a thesis about the company or "exactly where I do my best work".
    - Introduce the requirements table out loud ("Below is what I bring to the table."). Answer
      cells: one or two short first-person sentences; fragments allowed; prefer years of use and
      "I built this myself" over outcome metrics.
    - Do not write dollar savings, headcounts/user counts, award rankings or percentages,
      "matched top models at a fraction of the cost", or sentences that mirror the company's values
      back at them. State achievements without the scoreboard.
    - Be honest about size and gaps: "~2 years professionally, 4-5 overall". When the evidence for
      a requirement is thin, say so in one line and say how it would be closed. Frame certifications
      as theory the candidate wants to apply in practice.
    - When AI is relevant: fundamentals learned before LLMs; now uses AI coding tools daily with a
      human in the loop. One or two sentences, no preaching.
    - Closers: one or two plain sentences. No flourish about how the candidate will transform the
      team's mission.
    - At most one light personal or playful line per letter, only if true; default is none.
    - Shorter is better. Cut rather than pad.
```

Also worth knowing: the Vori Health letter had its whole table deleted, and that draft was
generated with `faux=true` (as was BDO's Azure-heavy draft). Several of the "inflated" lines being
cut are faux-mode inventions. But the three heaviest rewrites (Quora Full-Stack, Affirm, Citco)
were all `faux=false`, so the core issue is voice, not just truthfulness.

---

## 4. Synthesized examples

Fictional companies and postings. All facts about the candidate come from the real letters; no
new achievements were invented. The `[contact line]` stands in for the normal signature line.

### Example A: Junior Full-Stack Developer

> November 8, 2026
>
> RE: Junior Full-Stack Developer
> Harbourline Freight, Mississauga, ON
>
> Dear Harbourline Freight Hiring Team,
>
> I am applying to the Junior Full-Stack Developer role. From what I understand from the posting,
> the team is small and builds the internal tools that dispatchers and drivers use every day. That's
> the kind of work I've been doing for the last couple of years, so this is right up my alley.
>
> My main credentials are on my resume. Other than that, below is what I bring to the table:
>
> | What you require | My Relevant Skills and Experience |
> |---|---|
> | "1-2 years building web applications with JavaScript/TypeScript and a modern framework" | What I've been doing daily for 4-5 years, and professionally for ~2 years. I've used React just about everywhere; my favourite personal project (Resumate, on my GitHub) is in Vue with a Python backend. |
> | "Design and build REST APIs backed by a relational database" | Designed the entire CRM for an architectural firm. The backend, frontend and APIs were done by me on PostgreSQL, and I helped the DevOps guy with deployment as well. |
> | "Comfortable owning a feature end to end" | Always doing personal projects, and I usually finish them. Professional work, I always finish. |
> | "Experience with automated testing" | I write tests with Pytest and Jest. Honestly, this is where I'd want to improve most, and a team with real test coverage is a good place to do that. |
>
> I'm also a recent postgraduate from an AI Solutions Development program. I learned software
> fundamentals before LLMs were everywhere, so I can debug by hand when I need to, but day to day I
> use AI coding tools a lot and have a good grasp of what they can and cannot do.
>
> I believe I'll be able to learn a lot from this role but also bring a lot to the table. Thank you
> for your consideration.
>
> Sincerely,
> Safwan Hossain | [contact line]

*Sources mixed in: Affirm (CRM row, Vue row), Quora Full-Stack (years row, "usually finished
them"), 1Password ("right up my alley", "what it can and cannot do"), Citco (testing admission,
closer), Agility PR (postgrad mention), PRI ("main credentials on my resume" framing).*

### Example B: Cloud / DevOps Intern

> November 8, 2026
>
> RE: Cloud Operations Intern (Winter 2027)
> Lumen Ridge Software, Toronto, ON (Hybrid)
>
> Dear Lumen Ridge Recruiting Team,
>
> I am applying to the Cloud Operations Intern role. I am, in general, a generalist: I've studied
> hardware and AI solutions, and worked in both development and DevOps. Most recently I've been an
> A.I. Engineering Intern at a cybersecurity company, where part of my work is securing our
> pipelines.
>
> I recently earned the AWS Solutions Architect - Associate certification, so I'm familiar with
> the theory behind most AWS services and how they're all connected. I'd love the chance to apply
> that practically during the internship. Below is a table for your reference (pun intended):
>
> | What you require | My Relevant Skills and Experience |
> |---|---|
> | "Hands-on experience with AWS, Docker and Linux" | Containerized an internal web app with Docker and automated its testing and deployment. I've also deployed and troubleshot services on Linux, mostly by reading container logs until the problem shows itself. |
> | "Exposure to Infrastructure as Code and CI/CD" | Built a GitHub CI/CD pipeline for that same app. I've used Terraform in projects, but not yet at production scale; that's something I'd want to grow into here. |
> | "Scripting in Python or Bash" | Constant Python use for the last 5-6 years. Bash for the routine stuff I don't want to do twice. |
> | "Clear communication and documentation" | On the Toronto MetRobotics design team I built the rover's driving controls and live dashboard, which meant working across sub-teams constantly. Goals were communicated early so issues got caught before they spread. I also like to correctly document things and automate wherever it makes sense, including the edge cases. |
>
> One more thing: I use AI tools heavily, but as the human in the loop. They're great for the
> mundane parts; a person still needs to review the work and give good context up front.
>
> I work carefully, document what I do, and verify before I call something done. Thank you for your
> time.
>
> Sincerely,
> Safwan Hossain | [contact line]

*Sources mixed in: Revvity ("generalist", human in the loop), Compass and Citco (AWS cert as theory
to apply), SOTI ("table for your reference (pun intended)"), Vori Health and BalanX (Docker/CI/CD,
container logs, closer), Affirm (Python years), Geotab (multi-team communication row), BDO
(document things, edge cases).*
