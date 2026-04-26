# STRATOS Chat Prompting Guide

This guide shows how to get better results from **STRATOS Chat**.

STRATOS works best when you give it the mission context it needs up front:

- where the launch is
- when the launch is
- what decision you need to make
- the SondeHub flight profile values
- what kind of answer format you want back

## What STRATOS Chat Can Do Today

The current STRATOS chat backend is strongest at:

- **surface weather assessment** for launch planning
- **winds aloft analysis** for upper-level risk
- **balloon no-flight-zone checks** for trajectory-based airspace awareness
- **SondeHub Tawhiri trajectory simulations** for landing prediction
- **Monte Carlo landing uncertainty** from flight-profile and launch-time spread

## Prompting Formula

Use this pattern when possible:

> Help me with `[decision or task]` for a launch at `[location]` on `[date/time]`.  
> Use `[weather / winds aloft / no-flight-zone / trajectory]`.  
> Mission details: `[launch elevation, ascent rate, burst altitude, descent rate, number of runs]`.  
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

### 3. Flight profile

SondeHub trajectory predictions require profile values, not balloon hardware:

- ascent rate in m/s
- burst altitude in meters
- descent rate in m/s
- number of Monte Carlo runs

STRATOS does not infer these from balloon model, payload mass, gas type, nozzle lift, or parachute model.

Example:

```text
Ascent rate: 5.0 m/s
Burst altitude: 30000 m
Descent rate: 6.0 m/s
Num runs: 10
```

Optional Monte Carlo controls:

- seed, if you need repeatable results
- ascent-rate spread as a percent
- burst-altitude spread in meters
- descent-rate spread as a percent
- launch-time spread in minutes

### 4. The decision you need

Ask for a decision, not just raw data.

- “Is this launch window GO / CAUTION / NO-GO?”
- “Which of these two launch times reduces landing uncertainty?”
- “What is the expected landing area?”
- “Does the predicted balloon corridor cross any restriction we need to manually review?”

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
Summarize the wind profile and call out any jet-stream concern.
```

### Balloon no-flight-zone check

Use this when you want trajectory-based airspace awareness for the full balloon route.

```text
Compute the balloon no-flight zone for this launch:
Launch lat/lon: 18.2208, -67.1402
Launch elevation: 11 m
Launch datetime: 2026-04-27T14:00:00Z
Ascent rate: 5.0 m/s
Burst altitude: 30000 m
Descent rate: 6.0 m/s
Num runs: 10

Return status, intersecting restrictions, map-ready corridor context, and any manual review items.
```

### Trajectory simulation

Use this when you want a landing prediction.

```text
Run a SondeHub trajectory simulation for:
Launch lat/lon: 18.2208, -67.1402
Launch elevation: 11 m
Launch datetime: 2026-04-27T14:00:00Z
Ascent rate: 5.0 m/s
Burst altitude: 30000 m
Descent rate: 6.0 m/s
Num runs: 5

Return the expected landing area, uncertainty, and key flight milestones.
```

### Repeatable Monte Carlo run

Use this when you want to reproduce the same sampled SondeHub ensemble later.

```text
Run a SondeHub trajectory simulation for:
Launch lat/lon: 18.2208, -67.1402
Launch elevation: 11 m
Launch datetime: 2026-04-27T14:00:00Z
Ascent rate: 5.0 m/s
Burst altitude: 30000 m
Descent rate: 6.0 m/s
Num runs: 10
Seed: 1234
Ascent spread: 5%
Burst altitude spread: 1000 m
Descent spread: 10%
Launch time spread: 10 minutes

Return the mean landing point, one-sigma uncertainty, and per-run landing points.
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
Compare two trajectory cases for the same site and flight profile:
1. Launch at 2026-04-27T14:00:00Z
2. Launch at 2026-04-27T16:00:00Z
Ascent rate 5.0 m/s, burst altitude 30000 m, descent rate 6.0 m/s, 10 runs.

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
We are planning a standard HAB launch from 18.2208, -67.1402 at 2026-04-27T14:00:00Z.
Launch elevation is 11 m. Ascent rate is 5.0 m/s, burst altitude is 30000 m, descent rate is 6.0 m/s, and we want 10 SondeHub runs.
Assess surface weather, balloon no-flight-zone risk, and trajectory.
Return:
1. Overall GO / CAUTION / NO-GO
2. Threshold violations
3. Main operational risks
4. Manual checks we still need to do
5. Expected landing area and uncertainty
```

## Good Habits

- Put the decision at the top of your prompt.
- Use exact numbers when you have them.
- Ask STRATOS to compare options instead of asking one question at a time.
- Ask it to state assumptions if you are unsure about an input.
- Provide SondeHub profile rates directly for trajectory requests.
- Ask for threshold violations explicitly when making launch decisions.
- Ask for manual follow-up items when no-flight-zone or safety matters.

## Current Limits

Keep these in mind when prompting:

- No-flight-zone responses still require **official manual restriction / NOTAM / TFR review** before launch.
- If a no-flight-zone result is `UNVERIFIED`, treat it as incomplete coverage, not as clear airspace.
- Weather and trajectory quality depend on forecast availability and input quality.
- If you omit ascent rate, burst altitude, or descent rate, STRATOS will ask for those values before running trajectory prediction.
- Balloon, payload, gas, nozzle lift, and parachute details do not replace SondeHub profile values.
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
Run a SondeHub trajectory simulation for our planned launch. Launch site is 18.2208, -67.1402, elevation 11 m, launch time 2026-04-27T14:00:00Z, ascent rate 5.0 m/s, burst altitude 30000 m, descent rate 6.0 m/s, and 10 runs. Summarize landing area and uncertainty.
```

```text
Compute the balloon no-flight zone for our planned launch. Launch site is 18.2208, -67.1402, elevation 11 m, launch time 2026-04-27T14:00:00Z, ascent rate 5.0 m/s, burst altitude 30000 m, descent rate 6.0 m/s, and 10 runs. Return status, intersecting restrictions, and manual review items.
```

```text
I only know payload mass and desired ascent rate. What SondeHub profile values are still missing before STRATOS can run a trajectory?
```

## One-Line Cheat Sheet

For the best STRATOS chat results, include:

`where + when + launch elevation + ascent rate + burst altitude + descent rate + runs + desired output`
