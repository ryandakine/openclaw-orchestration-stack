#!/usr/bin/env python3
"""
Main entry point for the Sportsbook/Arbitrage Hunter.

Usage:
    python main.py                    # Run continuously on schedule
    python main.py --dry-run          # Run once, print results, don't send alerts
    python main.py --config path.yml  # Use custom config file
    python main.py --once             # Run single scan and exit

Pipeline:
    [Scheduled Trigger] → [Fetch Sportsbook Data] → [Fetch Prediction Market Data]
    → [Normalize Data] → [Save to DB] → [Run Arbitrage Detection] → [Send Telegram Alerts]
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from src.utils.config import Config, ConfigLoader
from src.utils.logger import setup_logging, get_logger
from src.runner import (
    ArbitrageRunner,
    create_runner,
    EXIT_SUCCESS,
    EXIT_ERROR,
    EXIT_SHUTDOWN,
)


# ASCII art banner
BANNER = r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ███████╗██████╗  ██████╗ ██████╗ ████████╗███████╗██████╗  ██████╗  ██████╗ ║
║   ██╔════╝██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝██╔══██╗██╔════╝ ██╔═══██╗║
║   ███████╗██████╔╝██║   ██║██████╔╝   ██║   █████╗  ██████╔╝██║  ███╗██║   ██║║
║   ╚════██║██╔═══╝ ██║   ██║██╔══██╗   ██║   ██╔══╝  ██╔══██╗██║   ██║██║   ██║║
║   ███████║██║     ╚██████╔╝██║  ██║   ██║   ███████╗██║  ██║╚██████╔╝╚██████╔╝║
║   ╚══════╝╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ║
║                                                                              ║
║                    █████╗ ██████╗  ██████╗██╗  ██╗██╗  ██╗██╗   ██╗███╗   ██╗████████╗███████╗██████╗   ║
║                   ██╔══██╗██╔══██╗██╔════╝██║  ██║██║  ██║██║   ██║████╗  ██║╚══██╔══╝██╔════╝██╔══██╗  ║
║                   ███████║██████╔╝██║     ███████║███████║██║   ██║██╔██╗ ██║   ██║   █████╗  ██████╔╝  ║
║                   ██╔══██║██╔══██╗██║     ██╔══██║██╔══██║██║   ██║██║╚██╗██║   ██║   ██╔══╝  ██╔══██╗  ║
║                   ██║  ██║██║  ██║╚██████╗██║  ██║██║  ██║╚██████╔╝██║ ╚████║   ██║   ███████╗██║  ██║  ║
║                   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


def print_banner() -> None:
    """Print the application banner."""
    print(BANNER)


def print_config_summary(config: Config) -> None:
    """Print a summary of the loaded configuration."""
    print("\n" + "=" * 80)
    print("  CONFIGURATION SUMMARY")
    print("=" * 80)
    
    print(f"\n  📅 Scheduling:")
    print(f"     • Scan interval: {config.scan_interval_minutes} minutes")
    print(f"     • Enabled: {config.enabled}")
    print(f"     • Dry run: {config.dry_run}")
    
    print(f"\n  🏆 Sports to scan ({len(config.sports_to_scan)}):")
    sports_str = ", ".join(config.sports_to_scan[:6])
    if len(config.sports_to_scan) > 6:
        sports_str += f" and {len(config.sports_to_scan) - 6} more"
    print(f"     • {sports_str}")
    
    print(f"\n  💰 Profit Thresholds:")
    print(f"     • Minimum profit: {config.min_profit_threshold * 100:.1f}%")
    print(f"     • Min edge: {config.min_edge_percent:.1f}%")
    print(f"     • Min profit/unit: ${config.min_profit_per_unit:.2f}")
    
    enabled_sources = config.get_enabled_sources()
    print(f"\n  📡 Data Sources ({len(enabled_sources)} enabled):")
    for name, source_config in enabled_sources.items():
        configured = "✅" if config.is_source_configured(name) else "⚠️"
        print(f"     • {configured} {name.title()}")
    
    print(f"\n  🔔 Alerts:")
    print(f"     • Telegram enabled: {config.telegram_enabled}")
    print(f"     • Top N alerts: {config.top_n_alerts}")
    
    print(f"\n  💾 Database:")
    print(f"     • Enabled: {config.database.enabled}")
    print(f"     • Host: {config.database.host}")
    
    print(f"\n  📝 Logging:")
    print(f"     • Level: {config.logging.level}")
    print(f"     • Format: {config.logging.format}")
    print(f"     • Console: {config.logging.console_output}")
    
    print("\n" + "=" * 80 + "\n")


def setup_signal_handlers(runner: ArbitrageRunner) -> None:
    """Set up signal handlers for graceful shutdown."""
    
    def signal_handler(sig: int, frame) -> None:
        """Handle shutdown signals."""
        logger = get_logger(__name__)
        sig_name = signal.Signals(sig).name
        logger.info(f"received_signal", signal=sig_name, signal_number=sig)
        print(f"\n\n⚠️  Received {sig_name}. Shutting down gracefully...")
        runner.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill command
    
    # Ignore SIGPIPE (broken pipe - happens when output is piped and closed)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)


async def run_dry_mode(runner: ArbitrageRunner) -> int:
    """
    Run in dry-run mode (once, print results, don't send alerts).
    
    Returns:
        Exit code
    """
    logger = get_logger(__name__)
    logger.info("dry_run_starting")
    
    print("\n" + "=" * 80)
    print("  DRY RUN MODE - Results will be printed but no alerts sent")
    print("=" * 80 + "\n")
    
    try:
        result = await runner.run_once(dry_run=True)
        
        print("\n" + "-" * 80)
        print("  DRY RUN RESULTS")
        print("-" * 80)
        print(f"\n  Run ID: {result.run_id}")
        print(f"  Duration: {result.duration_seconds:.2f} seconds")
        print(f"  Success: {result.success}")
        
        print(f"\n  Stage Results:")
        for stage, stage_result in result.stage_results.items():
            print(f"    • {stage}: {stage_result}")
        
        print(f"\n  Arbitrages Found: {result.arbitrages_found}")
        print(f"  Alerts Would Send: {result.alerts_sent}")
        
        if result.errors:
            print(f"\n  Errors ({len(result.errors)}):")
            for error in result.errors:
                print(f"    • Stage '{error['stage']}': {error['error']}")
        
        print("\n" + "-" * 80 + "\n")
        
        logger.info("dry_run_complete", success=result.success)
        return EXIT_SUCCESS
        
    except Exception as e:
        logger.error("dry_run_failed", error=str(e))
        print(f"\n❌ Dry run failed: {e}\n")
        return EXIT_ERROR


async def run_once_mode(runner: ArbitrageRunner) -> int:
    """
    Run a single scan and exit.
    
    Returns:
        Exit code
    """
    logger = get_logger(__name__)
    logger.info("once_mode_starting")
    
    print("\n" + "=" * 80)
    print("  SINGLE SCAN MODE")
    print("=" * 80 + "\n")
    
    try:
        result = await runner.run_once()
        
        print("\n" + "-" * 80)
        print("  SCAN COMPLETE")
        print("-" * 80)
        print(f"\n  ✅ Found {result.arbitrages_found} arbitrage opportunities")
        print(f"  📤 Sent {result.alerts_sent} alerts")
        print(f"  ⏱️  Duration: {result.duration_seconds:.2f} seconds")
        print("\n" + "-" * 80 + "\n")
        
        logger.info("once_mode_complete", arbitrages=result.arbitrages_found)
        return EXIT_SUCCESS
        
    except Exception as e:
        logger.error("once_mode_failed", error=str(e))
        print(f"\n❌ Scan failed: {e}\n")
        return EXIT_ERROR


async def run_continuous_mode(runner: ArbitrageRunner) -> int:
    """
    Run continuously on a schedule until interrupted.
    
    Returns:
        Exit code
    """
    logger = get_logger(__name__)
    logger.info("continuous_mode_starting")
    
    print("\n" + "=" * 80)
    print("  CONTINUOUS MODE - Press Ctrl+C to stop")
    print("=" * 80 + "\n")
    
    setup_signal_handlers(runner)
    
    try:
        await runner.run_scheduled()
        
        print("\n✅ Runner stopped gracefully")
        logger.info("continuous_mode_stopped_gracefully")
        return EXIT_SUCCESS
        
    except Exception as e:
        logger.error("continuous_mode_failed", error=str(e))
        print(f"\n❌ Runner failed: {e}\n")
        return EXIT_ERROR


async def main_async() -> int:
    """
    Main async entry point.
    
    Returns:
        Exit code
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Sportsbook/Arbitrage Hunter - Find arbitrage opportunities across sportsbooks and prediction markets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                    # Run continuously on schedule
    python main.py --dry-run          # Run once in dry-run mode
    python main.py --once             # Run single scan and exit
    python main.py --config dev.yml   # Use custom config file
        """,
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration file (default: searches ./config.yaml, ./config.yml)",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Run once, print results, don't send alerts",
    )
    parser.add_argument(
        "--once", "-o",
        action="store_true",
        help="Run a single scan and exit",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Skip printing the startup banner",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 1.0.0",
    )
    
    args = parser.parse_args()
    
    # Load configuration first to get logging settings
    try:
        config = ConfigLoader.load(args.config)
    except FileNotFoundError as e:
        print(f"\n❌ Configuration error: {e}\n")
        print("Please create a config.yaml file or specify one with --config\n")
        return EXIT_ERROR
    except Exception as e:
        print(f"\n❌ Failed to load configuration: {e}\n")
        return EXIT_ERROR
    
    # Setup logging
    setup_logging(
        level=config.logging.level,
        log_file=config.logging.log_file,
        format_type=config.logging.format,
        max_file_size_mb=config.logging.max_file_size_mb,
        backup_count=config.logging.backup_count,
        console_output=config.logging.console_output,
    )
    
    logger = get_logger(__name__)
    logger.info("application_starting", version="1.0.0")
    
    # Print banner
    if not args.no_banner:
        print_banner()
    
    # Validate configuration
    is_valid, errors = ConfigLoader.validate(config)
    if not is_valid:
        print(f"\n❌ Configuration validation failed:")
        for error in errors:
            print(f"   • {error}")
        print()
        logger.error("config_validation_failed", errors=errors)
        return EXIT_ERROR
    
    # Print configuration summary
    print_config_summary(config)
    
    # Create runner
    try:
        runner = await create_runner(args.config)
    except Exception as e:
        logger.error("runner_creation_failed", error=str(e))
        print(f"\n❌ Failed to create runner: {e}\n")
        return EXIT_ERROR
    
    # Run in appropriate mode
    if args.dry_run:
        return await run_dry_mode(runner)
    elif args.once:
        return await run_once_mode(runner)
    else:
        return await run_continuous_mode(runner)


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code
    """
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user\n")
        return EXIT_SHUTDOWN
    except Exception as e:
        print(f"\n❌ Fatal error: {e}\n")
        import traceback
        traceback.print_exc()
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
