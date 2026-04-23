# STRATOS Chat Prompting Guide

This guide shows how to get better results from **STRATOS Chat**.

STRATOS works best when you give it the mission context it needs up front:

- where the launch is
- when the launch is
- what decision you need to make
- what hardware or constraints matter
- what kind of answer format you want back

## What STRATOS Chat Can Do Today

The current STRATOS chat backend is strongest at:

- **surface weather assessment** for launch planning
- **winds aloft analysis** for upper-level risk
- **airspace hazard checks** for launch-area awareness
- **ASTRA-based trajectory simulations** for landing prediction
- **balloon and parachute selection support**
- **pre-flight fill calculations** like nozzle lift and balloon volume

## Prompting Formula

Use this pattern when possible:

> Help me with `[decision or task]` for a launch at `[location]` on `[date/time]`.  
> Use `[weather / winds aloft / airspace / trajectory]`.  
> Mission details: `[payload, balloon, gas, ascent rate, elevation, constraints]`.  
> Return `[brief / recommendation / table / checklist / go-no-go summary]`.

## What To Include

### 1. Launch location

Be specific.

- Best: exact latitude/longitude
- Good: named place plus region
- Better if relevant: launch elevation in meters

Example:

```text
Launch site: 18.2208, -67.1402
Launch elevation: 11 m
```

### 2. Launch date and time

Use an exact time when you can.

- Include timezone if there is any chance of ambiguity
- If you are comparing options, list each candidate launch time

Example:

```text
Launch time: 2026-04-27 10:00 AST
```

### 3. Mission hardware

Trajectory and fill calculations improve a lot when you include:

- balloon model
- parachute model, if known
- gas type: `Helium` or `Hydrogen`
- payload weight in kg
- target ascent rate in m/s, if you do not know nozzle lift yet
- nozzle lift in kg, if you already have it

Example:

```text
Balloon: TA800
Parachute: SPH36
Gas: Helium
Payload weight: 0.433 kg
Target ascent rate: 5.0 m/s
```

### 4. The decision you need

Ask for a decision, not just raw data.

- “Is this launch window GO / CAUTION / NO-GO?”
- “Which of these two launch times reduces landing uncertainty?”
- “What nozzle lift should we use?”
- “Is there any airspace risk we need to manually review?”

## High-Value Prompt Patterns

### Weather assessment

Use this when you want a launch recommendation.

```text
Evaluate launch weather for 18.2208, -67.1402 on 2026-04-27 from 09:00 to 15:00 AST.
Give me a GO / CAUTION / NO-GO recommendation, the best launch window, threshold violations, and observation links.
```

### Winds aloft analysis

Use this when you care about upper-level wind risk.

```text
Check winds aloft for 18.2208, -67.1402 at 2026-04-27T14:00:00Z.
Summarize the wind profile, call out any jet-stream concern, and explain how it could affect trajectory.
```

### Airspace hazard check

Use this when you want launch-area aviation awareness.

```text
Check airspace hazards within 25 km of 18.2208, -67.1402 for a launch around 2026-04-27T14:00:00Z.
Summarize hazard status, major concerns, and what still requires manual NOTAM/TFR verification.
```

### Balloon selection

Use this when hardware is still undecided.

```text
I have a 0.433 kg payload and I’m deciding between available balloon options for a standard flight.
List suitable balloon models and explain the tradeoffs.
```

### Nozzle lift calculation

Use this when you know your ascent goal but not your fill target.

```text
For a TA800 balloon using Helium with a 0.433 kg payload, calculate the nozzle lift needed for a 5.0 m/s ascent rate.
Return the answer and explain what it means operationally.
```

### Balloon volume / fill estimate

Use this when you already know nozzle lift.

```text
For a TA800 using Helium, payload 0.433 kg, and nozzle lift 2.0 kg, calculate balloon volume, gas mass, diameter, and free lift.
```

### Trajectory simulation

Use this when you want a landing prediction.

```text
Run an ASTRA trajectory simulation for:
Launch lat/lon: 18.2208, -67.1402
Launch elevation: 11 m
Launch datetime: 2026-04-27T14:00:00Z
Balloon: TA800
Gas: Helium
Payload: 0.433 kg
Nozzle lift: 2.0 kg
Parachute: SPH36
Num runs: 5

Return the expected landing area, uncertainty, and key flight milestones.
```

## Comparison Prompts

STRATOS is especially useful when comparing options.

### Compare launch windows

```text
Compare launch conditions for 2026-04-27 at 09:00 AST, 11:00 AST, and 13:00 AST for 18.2208, -67.1402.
Tell me which window is best and why.
```

### Compare trajectory outcomes

```text
Compare two trajectory cases for the same site and hardware:
1. Launch at 2026-04-27T14:00:00Z
2. Launch at 2026-04-27T16:00:00Z

Focus on landing area, uncertainty, and operational risk.
```

## Ask For The Format You Want

You will usually get better answers if you specify the output style.

Examples:

- “Give me a short mission brief.”
- “Return a GO / CAUTION / NO-GO summary first, then the details.”
- “Use a table.”
- “Keep it concise.”
- “List assumptions separately.”
- “Explain it for a new flight team member.”

## Better Prompt Examples

### Weak

```text
Can we launch?
```

### Better

```text
Can we launch a balloon from 18.2208, -67.1402 on 2026-04-27 at 10:00 AST?
Give me a GO / CAUTION / NO-GO recommendation based on surface weather and explain the main risks.
```

### Strong

```text
We are planning a standard HAB launch from 18.2208, -67.1402 at 2026-04-27 10:00 AST.
Payload weight is 0.433 kg. Balloon is TA800. Gas is Helium.
Assess surface weather and airspace hazards.
Return:
1. Overall GO / CAUTION / NO-GO
2. Threshold violations
3. Main operational risks
4. Manual checks we still need to do
5. Observation links
```

## Good Habits

- Put the decision at the top of your prompt.
- Use exact numbers when you have them.
- Ask STRATOS to compare options instead of asking one question at a time.
- Ask it to state assumptions if you are unsure about an input.
- Ask for threshold violations explicitly when making launch decisions.
- Ask for manual follow-up items when airspace or safety matters.

## Current Limits

Keep these in mind when prompting:

- STRATOS can only use the tool groups enabled by the client or route configuration.
- Airspace responses still require **manual NOTAM/TFR verification**.
- Weather and trajectory quality depend on forecast availability and input quality.
- If you omit mission hardware, STRATOS may need to make assumptions or ask follow-up questions.
- If you ask for a launch recommendation, STRATOS should use surface weather before recommending a window.

## Recommended Starter Prompts

These are good defaults for operators:

```text
What is the best launch window tomorrow for 18.2208, -67.1402? Give me a GO / CAUTION / NO-GO recommendation and explain the risks.
```

```text
Check winds aloft and tell me whether upper-level winds are likely to push the landing far offshore.
Launch site is 18.2208, -67.1402 and launch time is 2026-04-27T14:00:00Z.
```

```text
Run a trajectory simulation for our planned launch and summarize expected burst altitude, landing area, and uncertainty.
```

```text
I only know payload mass and desired ascent rate. Help me choose a balloon and calculate the nozzle lift I should target.
```

## One-Line Cheat Sheet

For the best STRATOS chat results, include:

`where + when + what decision + mission hardware + desired output format`
