#!/usr/bin/env python3
"""
Systemd Timer Generator for Prediction Market Arbitrage Scanner

Generates pred-market-arb.timer file for scheduled daily execution at 3:30 AM.
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional


SYSTEMD_TIMER_TEMPLATE = """[Unit]
Description=Prediction Market Arbitrage Scanner Timer
Requires=pred-market-arb.service

[Timer]
OnCalendar={schedule}
Persistent=true
AccuracySec=1h
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
"""

# Alternative schedules for different use cases
SCHEDULE_PRESETS = {
    "daily-3am": "*-*-* 03:00:00",
    "daily-330am": "*-*-* 03:30:00",  # Default
    "daily-4am": "*-*-* 04:00:00",
    "hourly": "hourly",
    "every-6-hours": "0/6:00:00",
    "weekdays-9am": "Mon..Fri *-*-* 09:00:00",
}


def generate_timer_file(
    schedule: str = "*-*-* 03:30:00",
    output_path: Optional[str] = None,
    accuracy_sec: str = "1h",
    randomized_delay: str = "10m",
) -> str:
    """
    Generate the systemd timer file content.
    
    Args:
        schedule: OnCalendar schedule expression
        output_path: Where to write the timer file
        accuracy_sec: AccuracySec value (default: 1h)
        randomized_delay: RandomizedDelaySec value (default: 10m)
        
    Returns:
        Generated timer file content
    """
    content = SYSTEMD_TIMER_TEMPLATE.format(
        schedule=schedule,
    )
    
    # Add optional settings if non-default
    if accuracy_sec != "1h" or randomized_delay != "10m":
        lines = content.split("\n")
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if line.startswith("Persistent="):
                if accuracy_sec != "1h":
                    new_lines.append(f"AccuracySec={accuracy_sec}")
                if randomized_delay != "10m":
                    new_lines.append(f"RandomizedDelaySec={randomized_delay}")
        content = "\n".join(new_lines)
    
    if output_path:
        output = Path(output_path)
        output.write_text(content)
        print(f"Timer file written to: {output}")
        
        # Set permissions
        os.chmod(output, 0o644)
        print(f"Permissions set to 644")
    
    return content


def validate_timer_file(timer_path: str) -> bool:
    """Validate the generated timer file using systemd-analyze."""
    import subprocess
    
    try:
        result = subprocess.run(
            ["systemd-analyze", "verify", timer_path],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            print("✓ Timer file validation passed")
            return True
        else:
            print(f"✗ Validation errors:\n{result.stderr}")
            return False
    except FileNotFoundError:
        print("⚠ systemd-analyze not found, skipping validation")
        return True


def explain_schedule(schedule: str) -> str:
    """Provide human-readable explanation of the schedule."""
    explanations = {
        "*-*-* 03:30:00": "Daily at 3:30 AM",
        "*-*-* 03:00:00": "Daily at 3:00 AM",
        "*-*-* 04:00:00": "Daily at 4:00 AM",
        "hourly": "Every hour",
        "0/6:00:00": "Every 6 hours (00:00, 06:00, 12:00, 18:00)",
        "Mon..Fri *-*-* 09:00:00": "Weekdays at 9:00 AM",
    }
    return explanations.get(schedule, f"Custom schedule: {schedule}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate systemd timer file for Prediction Market Arbitrage Scanner"
    )
    parser.add_argument(
        "--schedule",
        default="daily-330am",
        help="Schedule preset or custom OnCalendar expression (default: daily-330am)",
    )
    parser.add_argument(
        "--preset",
        choices=list(SCHEDULE_PRESETS.keys()),
        help="Use a predefined schedule preset",
    )
    parser.add_argument(
        "--accuracy",
        default="1h",
        help="AccuracySec value (default: 1h)",
    )
    parser.add_argument(
        "--randomized-delay",
        default="10m",
        help="RandomizedDelaySec value (default: 10m)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output path (default: stdout)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate generated file with systemd-analyze",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install to /etc/systemd/system/ (requires sudo)",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available schedule presets",
    )
    
    args = parser.parse_args()
    
    # List presets if requested
    if args.list_presets:
        print("Available schedule presets:")
        for preset, schedule in SCHEDULE_PRESETS.items():
            print(f"  {preset:20} -> {schedule:30} ({explain_schedule(schedule)})")
        return
    
    # Determine schedule
    if args.preset:
        schedule = SCHEDULE_PRESETS[args.preset]
    elif args.schedule in SCHEDULE_PRESETS:
        schedule = SCHEDULE_PRESETS[args.schedule]
    else:
        schedule = args.schedule
    
    # Generate output path if installing
    output = args.output
    if args.install and not output:
        output = "/etc/systemd/system/pred-market-arb.timer"
    
    content = generate_timer_file(
        schedule=schedule,
        output_path=output,
        accuracy_sec=args.accuracy,
        randomized_delay=args.randomized_delay,
    )
    
    if not output:
        print(content)
        print(f"\n# Schedule explanation: {explain_schedule(schedule)}")
    else:
        print(f"\nSchedule: {explain_schedule(schedule)}")
    
    # Validate if requested
    if args.validate and output:
        validate_timer_file(output)
    
    # Reload systemd and enable timer if installing
    if args.install:
        import subprocess
        try:
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            print("✓ Systemd daemon reloaded")
            
            subprocess.run(
                ["systemctl", "enable", "pred-market-arb.timer"],
                check=True
            )
            print("✓ Timer enabled")
            
            subprocess.run(
                ["systemctl", "start", "pred-market-arb.timer"],
                check=True
            )
            print("✓ Timer started")
            
            print("\nTo check timer status:")
            print("  systemctl list-timers pred-market-arb.timer")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed: {e}")
            sys.exit(1)
        except FileNotFoundError:
            print("⚠ systemctl not found, skipping activation")


if __name__ == "__main__":
    main()
