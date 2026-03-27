# STRATOS

**STRATOS** stands for **System for Trajectory, Analysis & Telemetry Operations in the Stratosphere**.

STRATOS is a unified platform for **high-altitude balloon mission planning, AI-assisted operations, live mission control, and postflight data analysis**.

It is designed to replace fragmented HAB workflows with one integrated system that helps teams plan missions, monitor flights, and learn from the data after recovery.

---

## Table of Contents

1. [Mission Intelligence for High-Altitude Balloon Operations](#mission-intelligence-for-high-altitude-balloon-operations)
2. [Core Modules](#core-modules)
   - [Chat](#chat)
   - [Pre-Flight](#pre-flight)
   - [Mission Control](#mission-control)
   - [Post-Flight](#post-flight)
3. [Why STRATOS](#why-stratos)
4. [Who It’s For](#who-its-for)
5. [Vision](#vision)
6. [MCP Tooling Reference](#mcp-tooling-reference)
7. [Status](#status)
8. [Credits](#credits)

---

## Mission Intelligence for High-Altitude Balloon Operations

High-altitude balloon missions are often managed through disconnected tools and manual workflows:

- weather and trajectory tools  
- separate telemetry dashboards  
- scattered planning notes and checklists  
- postflight scripts and spreadsheet cleanup  
- external documentation stored across different systems  

STRATOS brings these functions together into a single mission platform.

---

## Core Modules

### Chat

The **Chat** module is the intelligence layer of STRATOS.

It allows users to interact with mission tools and documents through natural language. The assistant can talk to external tools such as trajectory services like **Tawhiri**, access mission-related documents and files such as **SharePoint content and locations**, and help users reason through mission planning decisions.

The Chat module is intended to act as a mission copilot, not just a chatbot. It helps users retrieve information, run planning-related actions, and understand mission context across all stages of the workflow.

**Examples of what Chat can do:**

- query trajectory and weather tools  
- access and summarize mission documentation  
- answer questions about procedures and prior flights  
- support planning decisions before launch  
- provide contextual assistance during and after the mission  

---

### Pre-Flight

The **Pre-Flight** module helps teams prepare for launch with a structured, AI-assisted workflow.

It is centered around a smart mission checklist that supports operational readiness and launch decision-making. This includes **AI-powered to-do lists**, prelaunch validation, and **GO / NO-GO** evaluation support.

The goal is to reduce missed steps, improve consistency, and make launch readiness easier to assess.

**Pre-Flight capabilities include:**

- mission setup and configuration  
- launch preparation checklist  
- AI-assisted readiness review  
- GO / NO-GO support  
- planning guidance before launch  

---

### Mission Control

The **Mission Control** module provides the live operational view during flight.

It combines a real-time map interface with telemetry monitoring and trajectory awareness. Users can view the balloon's current position, compare the **planned trajectory** against the **real flight path**, and monitor **landing predictions during flight** as telemetry updates come in.

This module is designed for active flight operations and recovery coordination.

**Mission Control capabilities include:**

- live telemetry map view  
- real-time position and altitude tracking  
- updated landing prediction during flight  
- comparison between predicted path and actual path  
- live operational awareness for controllers and recovery teams  

---

### Post-Flight

The **Post-Flight** module begins after payload recovery.

STRATOS can connect to onboard hardware such as a **Raspberry Pi**, ingest collected data, clean and organize the dataset, and generate useful analysis from the mission results.

This creates a consistent postflight workflow so teams can move from raw recovered files to structured insights faster.

**Post-Flight capabilities include:**

- connect recovered onboard systems such as Raspberry Pi  
- ingest mission data and logs  
- clean and normalize raw datasets  
- analyze flight performance  
- support learning and iteration for future missions  

---

## Why STRATOS

STRATOS is built to serve as a **mission operating system** for HAB teams.

Instead of switching between separate software, documents, dashboards, and scripts, teams can work inside one environment that supports the full mission lifecycle:

- **Plan** the mission  
- **Prepare** for launch  
- **Control** the flight  
- **Analyze** the results  

---

## Who It’s For

STRATOS is designed for:

- student engineering teams  
- university research groups  
- high-altitude balloon programs  
- near-space experimentation projects  
- teams that need a more organized and intelligent flight workflow  

---

## Vision

STRATOS aims to make high-altitude balloon operations more structured, data-driven, and reliable.

The long-term goal is to provide a system where mission knowledge, live telemetry, planning tools, and postflight analysis all work together in one place.

---

## MCP Tooling Reference

STRATOS currently exposes mission operations through FastMCP servers located in `backend/mcp_servers/`.

### Available MCP Servers and Tools

#### 1) NOTAM Server (`liftoff-notam`)

File: `backend/mcp_servers/notam_server.py`

Tool:

- `check_notam_airspace(latitude, longitude, radius_km=25.0, launch_datetime="", faa_client_id="", faa_client_secret="")`

What it does:

- queries NOTAM sources (FAA when credentials are provided, plus AviationWeather)
- filters and scores balloon-relevant advisories
- returns a launch-airspace clearance recommendation

Key outputs:

- `total_notams`
- `relevant_notams` (with `keywords_matched`)
- `clearance_status` (`NO_CRITICAL_ALERTS`, `REVIEW_REQUIRED`, `MANUAL_CHECK_REQUIRED`)
- `sources_queried`
- `observation_links`

#### 2) Weather Server (`liftoff-weather`)

File: `backend/mcp_servers/weather_server.py`

Tools:

- `get_surface_weather(latitude, longitude, forecast_hours=24)`
- `get_winds_aloft(latitude, longitude, forecast_datetime)`

What they do:

- `get_surface_weather`: fetches hourly surface forecast data and computes GO/CAUTION/NO-GO windows
- `get_winds_aloft`: fetches vertical wind profile at standard pressure levels and flags jet-stream risk

Key outputs:

- surface weather: `overall_assessment`, `go_windows`, `caution_windows`, `no_go_windows`, `hourly_conditions`
- winds aloft: `wind_profile`, `jet_stream_alert`, `jet_stream_message`, `forecast_time`
- both include `observation_links`

#### 3) Trajectory Server (`trajectory`)

File: `backend/mcp_servers/trajectory/server.py`

Tools:

- `predict_standard(launch_latitude, launch_longitude, launch_datetime, ascent_rate, burst_altitude, descent_rate, launch_altitude=0.0)`
- `health_check()`
- `get_supported_profiles()`

What they do:

- `predict_standard`: runs a standard ascent-burst-descent prediction through the Tawhiri wrapper
- `health_check`: confirms trajectory service configuration state
- `get_supported_profiles`: lists available trajectory profiles and required fields

Key outputs:

- prediction response includes `ok`, `profile`, `request`, `summary`, `path`, `raw`
- `summary` includes burst/landing points and `water_landing`

### Running MCP Servers Locally

From the `backend/` directory:

```bash
python -m mcp_servers.notam_server
python -m mcp_servers.weather_server
python -m mcp_servers.trajectory.server
```

### README Template for New MCP Tools

When adding a new MCP tool, document it with this structure:

```markdown
## Tool: <tool_name>

- Server name: <fastmcp_server_name>
- File: <path/to/server.py>
- Purpose: <what mission problem this solves>

### Inputs
- <param_name> (<type>, default: <value>): <description>

### Output
- <field_name>: <description>

### Error behavior
- <validation/network/upstream behavior>

### Example
- Request: <example args>
- Response: <example JSON snippet>
```

Recommended minimum documentation per tool:

- parameter list (types, defaults, limits)
- output schema and status fields
- external dependencies (APIs, environment variables)
- operational interpretation (how to use result in GO/NO-GO decisions)
- one realistic example call and response

---

## Status

Concept in development.

---

## Credits

This project builds upon and is inspired by existing work in the high-altitude balloon and telemetry ecosystem.

- Mission Support Telemetry  

  <https://github.com/INSOJO/mission-support-telemetry>  

Additional credits and acknowledgments will be added as STRATOS evolves.
