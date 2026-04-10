"""Isolated subprocess bridge for HAB_Predictor tool execution."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from vendor import hab_predictor  # noqa: F401
from vendor.hab_predictor import app as hab_app


def _configure_runtime() -> None:
    cache_dir = os.environ.get("ASTRA_GFS_CACHE_DIR")
    if cache_dir:
        hab_app.GFS_CACHE_ROOT = Path(cache_dir).expanduser().resolve()


def _balloon_catalog_by_name() -> dict[str, dict[str, Any]]:
    return {
        item["name"]: {
            "family": item["family"],
            "mass_kg": item["mass_kg"],
            "burst_diameter_m": item["burst_diameter_m"],
            "weibull_lambda": item["weibull_lambda"],
            "weibull_k": item["weibull_k"],
        }
        for item in hab_app.get_balloon_catalog()
    }


def _parachute_catalog_by_name() -> dict[str, dict[str, Any]]:
    return {
        item["name"]: {
            "reference_area_m2": item["reference_area_m2"],
            "approx_diameter_m": item["approx_diameter_m"],
        }
        for item in hab_app.get_parachute_catalog()
        if item["name"]
    }


def _balloon_catalog_markdown() -> str:
    lines = [
        "# Available Balloon Models",
        "",
        "| Model | Family | Mass (kg) | Burst Diameter (m) |",
        "|-------|--------|----------:|-------------------:|",
    ]
    for name, spec in _balloon_catalog_by_name().items():
        lines.append(
            f"| {name} | {spec['family']} | {spec['mass_kg']:.4f} | {spec['burst_diameter_m']:.3f} |"
        )
    return "\n".join(lines)


def _parachute_catalog_markdown() -> str:
    lines = [
        "# Available Parachute Models",
        "",
        "| Model | Reference Area (m^2) | Approx. Diameter (m) |",
        "|-------|----------------------:|---------------------:|",
    ]
    for name, spec in _parachute_catalog_by_name().items():
        lines.append(
            f"| {name} | {spec['reference_area_m2']:.4f} | {spec['approx_diameter_m']:.2f} |"
        )
    return "\n".join(lines)


def _calculate_nozzle_lift(payload: dict[str, Any]) -> dict[str, Any]:
    result = hab_app.calculate_nozzle_lift(payload)
    result["note"] = (
        "Calculated at standard sea-level conditions (15C, 1013.25 mbar). "
        "Actual values will differ with launch site conditions."
    )
    return result


def _calculate_balloon_volume(payload: dict[str, Any]) -> dict[str, Any]:
    result = hab_app.calculate_balloon_volume(payload)
    payload_weight_kg = result.get("payload_weight_kg") or 0.0
    free_lift_kg = result.get("free_lift_kg") or 0.0
    result["free_lift_fraction"] = (
        round(float(free_lift_kg) / float(payload_weight_kg), 4)
        if payload_weight_kg
        else 0.0
    )
    result["note"] = (
        "Calculated at standard sea-level conditions (15C, 1013.25 mbar). "
        "Actual values will differ with launch site conditions."
    )
    return result


def _dispatch(tool_name: str, payload: dict[str, Any]) -> str:
    if tool_name == "astra_list_balloons":
        if payload.get("response_format", "json") == "markdown":
            return _balloon_catalog_markdown()
        return json.dumps(_balloon_catalog_by_name(), indent=2)

    if tool_name == "astra_list_parachutes":
        if payload.get("response_format", "json") == "markdown":
            return _parachute_catalog_markdown()
        return json.dumps(_parachute_catalog_by_name(), indent=2)

    if tool_name == "astra_calculate_nozzle_lift":
        return json.dumps(_calculate_nozzle_lift(payload), indent=2)

    if tool_name == "astra_calculate_balloon_volume":
        return json.dumps(_calculate_balloon_volume(payload), indent=2)

    if tool_name == "astra_run_simulation":
        return json.dumps(hab_app.run_simulation(payload), indent=2, default=str)

    raise ValueError(f"Unknown tool: {tool_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()

    _configure_runtime()
    try:
        payload = json.loads(args.payload)
        stdout_buffer = io.StringIO()
        with contextlib.redirect_stdout(stdout_buffer):
            result = _dispatch(args.tool, payload)
        progress_output = stdout_buffer.getvalue().strip()
        if progress_output:
            print(progress_output, file=sys.stderr)
        sys.stdout.write(result)
        sys.stdout.write("\n")
    except Exception as exc:
        sys.stdout.write(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
