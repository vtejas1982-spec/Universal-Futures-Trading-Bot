# How to Create the Grok Stock Market Intelligence Team

## Purpose

This guide explains how to build a structured stock-market research organization inside Grok Bot. The finished system behaves like a research desk:

- Specialist Bots collect and analyse information.
- Team Leads review specialist work and remove duplication.
- A Chief Market Intelligence Officer combines the Lead reports for the user.
- Scheduled routines perform recurring checks.
- Department groups provide controlled communication paths.

The system is for research and decision support. It should not place trades, promise returns, invent missing data, or present an unsupported opinion as a fact.

## 1. Understand the building blocks

Before creating anything, separate the five objects used in Grok Bot:

| Object | Purpose |
|---|---|
| Bot | A persistent AI role with its own name, profile and conversation history. |
| Profile description | The Bot's permanent identity, responsibilities and boundaries. |
| Skill | A reusable research procedure the Bot follows for a particular type of task. |
| Group | A shared room containing a Lead and its authorised specialists. |
| Routine | A scheduled wake-up that tells one Bot to run a saved Skill at a particular time. |

A Bot is the worker, its profile is the job description, a Skill is the operating procedure, a Group is the department room, and a Routine is the schedule.

## 2. Design the organization before creating Bots

Create a written roster first. Every specialist must have exactly one normal reporting Lead, and every Lead must report to the Chief.

### Chief

- Chief Market Intelligence Officer

### Market News Research team

- Market News Research Lead
- Research Analyst
- Sentiment Analyst
- Stock Movement Analyst
- News Credibility Analyst
- Market Impact Analyst

### Equity Research team

- Equity Research Lead
- Fundamental Research Analyst
- Financial Forensics Analyst
- Pre-Earnings Intelligence Analyst

### Industry and Geopolitical Research team

- Head of Industry & Geopolitical Research
- Industry Research Analyst
- Geopolitical Risk Analyst

### Market Activity and Ownership team

- Head of Market Activity & Ownership Research
- Market Volume Intelligence Analyst
- Insider Activity Analyst
- Fund Holdings Research Analyst
- Short-Seller Research Analyst

### Independent Research Review team

- Independent Research Review Lead
- Bull Case Analyst
- Bear Case Analyst
- Research Validation Analyst

This produces 23 Bots: one Chief, five Leads and seventeen specialists.

## 3. Build in the correct order

Do not create all Bots and activate all routines at once. Use this order:

1. Create the Chief.
2. Create the five Leads.
3. Complete one department at a time.
4. For each department, create and verify every specialist.
5. Create the department Group.
6. Test specialist-to-Lead handoffs.
7. Create the Lead's synthesis Skill.
8. Test Lead-to-Chief delivery.
9. Add routines in a paused state.
10. Activate only the routines that pass acceptance testing.

The Market News Research team is a good first department because it tests discovery, verification, event impact and escalation.

## 4. Create a Bot in Grok Bot

Repeat the following procedure for each role.

### Step 1: Start a new Bot

In Grok Bot, choose the option to create a new Bot. Create it manually rather than asking another Bot to create the entire organization.

### Step 2: Assign the exact role name

Use the roster name exactly. Avoid vague names such as “Finance Bot” or “Research Helper.” Exact naming makes routing and later auditing much easier.

### Step 3: Choose a visual identity

Assign an icon and colour that identify the department. A useful convention is:

- Chief: white or neutral
- Market News: red
- Equity Research: blue
- Industry and Geopolitical: orange
- Market Activity and Ownership: green
- Independent Review: grey

### Step 4: Write the permanent profile description

Put the Bot's durable identity in its profile settings, not only in an ordinary chat message. The description should contain:

- Exact role name
- Market scope, such as NSE and BSE listed Indian equities
- Direct reporting Lead or, for a Lead, the Chief
- Tasks the Bot owns
- Tasks the Bot must not perform
- Preferred source types
- Required timestamps and evidence fields
- Handoff destination and format
- Rules for unknown, incomplete and disputed information
- Explicit instruction not to create Bots, Skills, Routines, integrations or workflows unless the owner asks
- Explicit instruction not to place trades or provide guaranteed outcomes

Keep the profile focused on identity and boundaries. Detailed task steps belong in Skills.

### Step 5: Save and reopen the Bot

After saving, reopen Bot settings and confirm that the name, description and icon are present. Do not treat a chat acknowledgement as proof that the profile was saved.

### Step 6: Record the Bot identity

Maintain a roster outside the conversation containing:

- Display name
- Grok Bot identifier
- Department
- Reporting Lead
- Group membership
- Skills owned
- Routines owned
- Current verification state

Use the Bot's own identifier when defining sensitive routing. Display names can be renamed or duplicated; identifiers provide stronger identity control.

## 5. Use a standard profile structure

Each specialist profile should answer the following questions.

### Identity

- Who is this Bot?
- Which specific Bot identity should it use?
- Which department owns it?

### Scope

- Which market and companies can it cover?
- Is it scheduled, event-driven or both?
- What type of research does it own?

### Sources

- Which primary sources should it prefer?
- When may it use secondary sources?
- What should it do when a source is unavailable?

### Evidence rules

- Which facts and timestamps must be preserved?
- How must facts, interpretations and hypotheses be separated?
- Which claims require independent verification?

### Routing

- Which Lead receives the handoff?
- Is direct contact with the Chief prohibited?
- When should the Lead escalate the work?

### Safety boundaries

- No fabricated figures or company identities
- No autonomous trades
- No unsupported allegations
- No expansion of the company universe from model memory
- No silent replacement of missing data
- No creation of new system objects without owner approval

## 6. Configure the Chief and Leads differently

The Chief and Leads are coordinators, not larger versions of specialist Bots.

### Chief profile

The Chief should:

- Receive consolidated reports only from the five Leads.
- Decide which department should investigate a user request.
- Combine findings without hiding disagreements.
- Preserve source dates, data dates and coverage gaps.
- Escalate disputed investment conclusions to Independent Research Review.
- Avoid performing every raw search itself.
- Avoid contacting all specialists for every question.

### Lead profile

Each Lead should:

- Know its authorised specialist roster.
- Assign narrowly scoped tasks.
- Review specialist handoffs for completeness.
- Deduplicate repeated events.
- Reconcile conflicting conclusions.
- Request correction from the originating specialist when evidence is missing.
- Send only a consolidated report to the Chief.
- Avoid redoing the specialist's full analysis.

## 7. Create one Skill per repeatable research method

Create a Skill only after the Bot's role and boundaries have passed basic tests.

A production Skill should define:

1. When the Skill should be used
2. Required inputs
3. Approved company universe
4. Source priority
5. Time-window rules
6. Retrieval and retry limits
7. Evidence thresholds
8. Required calculations and validation rules
9. Status labels
10. Handoff format
11. Delivery destination
12. Duplicate-prevention behaviour
13. Completion and failure conditions
14. Explicit non-goals

### Source priority

Use a primary-source-first order:

1. Company identity registry
2. NSE and BSE filings and market publications
3. Company investor-relations pages
4. SEBI and other relevant regulators
5. Government of India and official ministry publications
6. AMFI and fund-house disclosures where ownership research is required
7. Secondary reporting only when clearly labelled and needed for context

Search-result snippets should be treated as discovery leads, not final evidence. Open and read the underlying document whenever possible.

### Time handling

Every Skill should distinguish:

- Event time: when the underlying event happened
- Publication time: when the source released it
- Retrieval time: when the Bot accessed it
- Data-as-of time: the period represented by the data

This prevents an old filing retrieved today from being described as a new event.

### Coverage states

Use clear states instead of forcing a conclusion:

- Completed with material findings
- Completed with no material findings
- Incomplete coverage
- Not classified
- Failed but retryable
- Not due
- Event-driven and not triggered

“No information found” must not automatically become “nothing happened.”

## 8. Create department Groups

Create one Grok Bot Group for each department and one Group for the Chief and Leads.

### Recommended Groups

| Group | Members |
|---|---|
| Chief Intelligence Group | Chief and five Leads |
| Market News Research Desk | Market News Lead and five specialists |
| Equity Research Desk | Equity Research Lead and three specialists |
| Industry & Geopolitical Desk | Department Lead and two specialists |
| Market Activity & Ownership Desk | Department Lead and four specialists |
| Independent Research Review Desk | Review Lead and three specialists |

### Group rules

- Add only the authorised Bots for that department.
- The Lead coordinates the room.
- Specialists address their Lead, not the Chief.
- The Chief communicates with Leads in the Chief Intelligence Group.
- Do not use a Group as a substitute for a structured handoff.
- Keep one clear owner for every request.
- Avoid acknowledgement loops between Bots.

If Grok limits the number of Bots in a Group, design the hierarchy around that limit rather than placing the whole organization in one room.

## 9. Define structured handoffs

A handoff is the contract between a specialist and its Lead. Standardise it before automation.

Every handoff should include:

- Request or event identifier
- Bot identity
- Company name and symbol
- Scope and time window
- Source links
- Publication, retrieval and data-as-of timestamps
- Verified facts
- Interpretation
- Contradictions
- Unknown or missing information
- Coverage status
- Confidence based on evidence
- Recommended Lead action

The receiving Lead should explicitly accept, reject, request correction or mark the work incomplete. Message delivery by itself is not research acceptance.

## 10. Add duplicate and delivery controls

Scheduled systems can wake twice, retry after an interruption or lose track of a delivery. Define the following controls conceptually for every recurring workflow:

- A stable event identity
- A reporting-period identity
- A unique run identity
- A delivery receipt identity
- A status showing whether work is open, pending delivery, delivered, partial or failed
- A rule preventing an old run from changing a newer run
- A rule that resends only the exact pending report
- A rule that waits when recipient status is unknown
- A rule that suppresses an already delivered duplicate
- A rule that advances the research window only after successful coverage and Lead acceptance

Keep acceptance tests separate from production records. Testing a workflow should not consume a scheduled production slot or move a production cursor.

## 11. Create routines only after manual tests pass

Open the completed Bot and add a routine from its routine or scheduling area.

For each routine:

1. Give it a precise, unique name.
2. Select the intended timezone, normally Asia/Kolkata.
3. Set the weekday or weekly cadence.
4. Instruct it to run one named Skill.
5. State the approved universe.
6. State the destination Lead.
7. State what to do when coverage is incomplete.
8. Set source and retry limits.
9. Prohibit creation of new system objects during a run.
10. Save it initially as paused.
11. Reopen the routine and verify its displayed schedule and instruction.

Do not create two active routines with the same purpose and time. Rename or retire older copies and verify that they remain paused.

## 12. Recommended production schedule

The reference organization uses the following Asia/Kolkata schedule:

| Time | Routine | Owner |
|---|---|---|
| Weekdays 08:00 | Pre-Earnings defence calendar | Pre-Earnings Intelligence Analyst |
| Weekdays 08:15 | Industry structure morning | Industry Research Analyst |
| Weekdays 08:30 | Geopolitical transmission morning | Geopolitical Risk Analyst |
| Weekdays 09:00 | Pre-market Lead synthesis | Chief |
| Weekdays 12:00 | Primary-source news | Research Analyst |
| Weekdays 12:30 | Midday published-narrative check | Sentiment Analyst |
| Weekdays 15:35 | Closing published-narrative check | Sentiment Analyst |
| Weekdays 18:00 | End-of-day volume triage | Market Volume Intelligence Analyst |
| Weekdays 18:10 | Insider-disclosure review | Insider Activity Analyst |
| Fridays 18:30 | Fundamental pair review | Fundamental Research Analyst |
| First Monday 18:30 | Fund-holdings review | Fund Holdings Research Analyst |
| Fridays 18:50 | Financial-forensics pair review | Financial Forensics Analyst |
| Weekdays 19:15 | Evening Lead synthesis | Chief |

The Fund Holdings routine should check whether the date is within the first seven days of the month. If it is not the first Monday, it should exit without research.

Event-driven specialists such as News Credibility, Market Impact, Stock Movement and the Independent Review workers do not necessarily need permanent daily routines. Their Leads should invoke them when a qualifying event exists.

## 13. Test every Bot in stages

Use the same acceptance sequence for every specialist.

### Stage A: Identity test

Ask the Bot to state:

- Its role
- Its Lead
- Its permitted sources
- Its prohibited actions
- Its expected handoff destination

Fail the test if it claims another Bot's identity or reports to the wrong recipient.

### Stage B: Boundary test

Give it a request outside its role. It should refuse the unsupported portion and route the issue appropriately.

Examples:

- Sentiment Analyst should not claim price causation.
- Volume Analyst should not call unusual activity manipulation.
- Financial Forensics should not label an anomaly fraud.
- Impact Analyst should not turn a project milestone into a new order without evidence.
- Lead should not bypass its specialists and perform every raw task.

### Stage C: Controlled real-source test

Use a small, real and bounded company set. Confirm that the Bot:

- Opens original sources
- Preserves timestamps
- Reports source failures
- Does not invent missing values
- Sends the result only to its Lead

### Stage D: Generalisation test

Test a different company or event. This confirms the Bot learned a reusable method rather than memorising one example.

### Stage E: Handoff test

Verify the complete specialist-to-Lead exchange. The Lead should review the evidence rather than merely acknowledge receipt.

### Stage F: Routine test

Run the routine once while it is still paused from automatic scheduling, if Grok provides a manual test option. Verify:

- Correct Bot executed
- Correct Skill ran
- Correct schedule and timezone are displayed
- Correct Lead received the handoff
- Duplicate work was not generated
- Incomplete coverage remained incomplete

### Stage G: Department test

Run one scenario through all relevant specialists, the Lead and the Chief. Use real data for production acceptance. Clearly label any separate training scenario as non-live and prevent it from entering production reports.

## 14. Activate production safely

Use this activation order:

1. Confirm Bot profiles and Group membership.
2. Confirm Skills are saved under the correct Bots.
3. Confirm all routines are paused.
4. Run manual acceptance tests.
5. Resolve routing and evidence failures.
6. Activate worker routines first.
7. Activate Chief synthesis routines after worker delivery times.
8. Reopen every routine and confirm that the control now shows active.
9. Maintain a final list of active and intentionally paused routines.
10. Observe the first scheduled production cycle.

The Grok scheduling interface is the authority for active or paused state. A saved copy, chat statement or exported snapshot may lag the actual scheduler.

## 15. Source and research controls

### Company identity

Maintain an approved company universe. Resolve the canonical name, exchange symbol and aliases before research. If the identity service is unavailable, use only an explicitly approved fallback universe and report the outage.

### Primary-source preference

Prefer exchange filings, company investor-relations documents, regulator publications and official government releases. Do not treat a social post or search snippet as proof.

### Numerical work

Use validated calculations for prices, returns, volume comparisons, ownership changes and financial ratios. The Bot should not perform approximate arithmetic from prose when a verified figure is required.

### Market-data freshness

Label information as live, delayed, end-of-day, historical or latest available. Retrieving a historical record today does not make it current.

### Incomplete evidence

Incomplete research must remain visible. Do not translate missing documents into neutral sentiment, no news, no risk or no material event.

### Cost control

Define source limits and daily budgets before activation. In the current free-source design, paid X access is disabled and the published-narrative Bot does not represent social-media sentiment.

## 16. Operating the completed system

The user should normally communicate with the Chief.

A good request to the Chief specifies:

- Companies or approved universe
- Question to investigate
- Required time period
- Whether current, delayed or last-session data is acceptable
- Need for primary sources
- Desired level of review
- Whether Independent Review is required

The Chief should use existing, current handoffs before starting duplicate work. It should involve only the departments needed for the question.

## 17. Common mistakes to avoid

### Broad creation instructions in ordinary chat

A long organization-building instruction can cause Grok to create extra objects. Use Bot settings for permanent identity and create system components deliberately.

### Identity stored only in conversation

Conversation context is not a substitute for a saved profile. Store durable role boundaries in Bot settings.

### Duplicate Bots or routines

Always search the existing Bot and routine lists before creating a new object.

### Specialist bypasses the Lead

Workers should send normal handoffs to their Lead. Leads consolidate for the Chief.

### Lead duplicates specialist work

The Lead should review, reconcile and prioritise. It should not repeat every source search.

### Chief becomes a raw scanner

The Chief should coordinate and synthesise, not replace the organization.

### Activation accepted without readback

After every edit, reopen the actual Bot, Skill or routine and confirm the saved state.

### Delivery confused with research success

A delivered message can still contain incomplete research. Track coverage and delivery separately.

### Old data presented as current

Always show source publication time, data-as-of time and retrieval time.

### Group agreement treated as independent proof

Multiple Bots can share the same source or reasoning error. Independent Review must inspect evidence, not count votes.

## 18. Final acceptance checklist

### Organization

- [ ] One Chief exists
- [ ] Five Leads exist
- [ ] Seventeen specialists exist
- [ ] Every specialist has exactly one normal Lead
- [ ] Every Bot has a unique recorded identity

### Profiles

- [ ] Role and market scope are saved
- [ ] Sources and boundaries are saved
- [ ] Reporting destination is explicit
- [ ] Autonomous object creation is prohibited
- [ ] Trading and unsupported conclusions are prohibited

### Skills

- [ ] Each recurring method has one saved Skill
- [ ] Source order and time rules are explicit
- [ ] Coverage states are explicit
- [ ] Retrieval limits are explicit
- [ ] Handoff format is explicit
- [ ] Duplicate and delivery behaviour is explicit

### Groups and routing

- [ ] Six department/coordination Groups are created
- [ ] Group membership matches the roster
- [ ] Specialist-to-Lead handoffs pass
- [ ] Lead-to-Chief delivery passes
- [ ] Direct worker-to-Chief routing is blocked for normal work

### Routines

- [ ] Schedule and timezone are correct
- [ ] Every routine has a unique purpose
- [ ] Initial state was paused
- [ ] Manual routine test passed
- [ ] Intended routines are active in the Grok interface
- [ ] Obsolete routines remain paused

### Research quality

- [ ] Real sources are used for production acceptance
- [ ] Facts and interpretation are separated
- [ ] Missing evidence remains visible
- [ ] Old and current data are distinguished
- [ ] Disputed claims are escalated
- [ ] No trade execution is enabled

## 19. Definition of complete

The system is complete only when:

- Every Bot has a saved and verified identity.
- Each specialist performs only its assigned role.
- Every repeatable workflow has a tested Skill.
- Department routing works from specialist to Lead.
- Lead synthesis reaches the Chief without duplicate research.
- Scheduled routines display the correct active state in Grok Bot.
- Incomplete evidence fails safely.
- The first production cycle is observed and reviewed.
- The final roster, schedules and known limitations are documented.

Completion means the research organization operates predictably. It does not mean every data source is always available, every market event is captured, or the system can guarantee successful investments.