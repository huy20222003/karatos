"""
Brain - Autonomous System Agent
Entry point for the agent

Usage:
    python main.py              # Run agent (auto-detects Telegram)
    python main.py --test       # Run in test mode (single cycle)
    python main.py --status     # Show agent status
"""
import sys
import asyncio
import argparse
import re
from datetime import datetime
import os
# Suppress Polars/Arrow warning
os.environ["POLARS_UNKNOWN_EXTENSION_TYPE_BEHAVIOR"] = "load_as_storage"
os.environ["PYTHONUTF8"] = "1"
from channels.telegram.connector import TelegramChannel

from pathlib import Path


# Add the agent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.agent import get_agent
from config.settings import settings
from utils.logger import get_logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text


console = Console()
logger = get_logger()


def print_banner():
    """Print the agent startup banner"""
    banner = Text()
    banner.append("\n    [ agent ]\n", style="bold cyan")
    console.print(Panel(banner, border_style="cyan", expand=False))
    console.print()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Brain - Autonomous System Agent"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run a single test cycle then exit"
    )
    
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current agent status and exit"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging"
    )
    
    parser.add_argument(
        "--cycle-once",
        action="store_true",
        help="Run exactly one observation cycle then exit"
    )
    
    return parser.parse_args()



async def run_single_cycle():
    """Run a single observation cycle for testing using the unified agent logic"""
    agent = get_agent()
    
    if not await agent.initialize():
        logger.error("Failed to initialize agent")
        return False
    
    console.print("[yellow]Running single test cycle (Patrol Mode)...[/yellow]")
    await agent.patrol()
    
    # Print status
    status = agent.get_status()
    console.print(Panel.fit(
        f"Cycle completed\n"
        f"Memory: {status['memory']}\n"
        f"Brain: {status['brain']}",
        title="Cycle Summary"
    ))
    
    return True

# ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯
# MODULAR SYSTEM ENTRY POINTS (Refactored for Professional Architecture)
# ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

def show_status():
    """Show current agent status"""
    from config.settings import settings
    
    telegram_status = "✅ Configured" if settings.telegram_bot_token else "❌ Not configured"
    
    console.print(Panel.fit(
        f"Ollama Model: {settings.ollama_model_name}\n"
        f"Scan Interval: {settings.scan_interval_minutes} minutes\n"
        f"Rolling Window: {settings.rolling_window_hours} hours\n"
        f"Max Actions/Hour: {settings.max_actions_per_hour}\n"
        f"Human Approval: {'Required' if settings.human_approval_required else 'Not Required'}\n"
        f"\n[bold]Telegram[/bold]\n"
        f"Status: {telegram_status}\n"
        f"Chat ID: {settings.telegram_chat_id or 'Not set'}",
        title="Brain Status",
        border_style="cyan"
    ))


async def run_with_telegram():
    """Run agent with Telegram integration using the new Modular Connector."""
    from core.agent import get_agent
    from channels.telegram.connector import TelegramConnector
    
    # 0. Pre-fetch Identity (Populates settings.bot_username before Agent initialization)
    temp_channel = TelegramChannel()
    if await temp_channel.connect():
        await temp_channel.disconnect()
        logger.info(f"[MAIN] Identity pre-fetched: @{settings.bot_username}")

    agent = get_agent()
    
    # Ensure agent is initialized (DatabaseReader, etc.)
    if not await agent.initialize():
        logger.error("[MAIN] Failed to initialize agent components.")
        return
        
    connector = TelegramConnector(agent)

    # Main Connector Start (Blocking)
    try:
        await connector.start()
    except Exception as e:
        logger.error(f"[MAIN] Telegram Connector failure: {e}")
    finally:
        # 1. Stop communication first
        await connector.stop()
        
        # 2. Shutdown agent components (closes sessions cleanly)
        await agent.shutdown()
        
        # 3. Cancel ANY remaining background tasks
        current_task = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current_task]
        
        if tasks:
            logger.info(f"[MAIN] Cleaning up {len(tasks)} remaining background tasks...")
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

async def run_agent():
    """Run agent in CLI-only mode (Fallback)."""
    from core.agent import get_agent
    agent = get_agent()
    
    # Ensure agent is initialized
    if not await agent.initialize():
        logger.error("[MAIN] Failed to initialize agent components.")
        return
        
    logger.info("[MAIN] Running in CLI mode. Control via terminal.")
    try:
        while True:
            try:
                # Basic heartbeat loop for CLI mode
                await agent.patrol()
                await asyncio.sleep(settings.scan_interval_minutes * 60)
            except Exception as e:
                logger.error(f"[MAIN] CLI agent loop error: {e}")
                await asyncio.sleep(60)
    finally:
        # Shutdown agent first
        await agent.shutdown()
        
        # Cancel background tasks
        current_task = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current_task]
        if tasks:
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

def main():
    """Main entry point"""
    from config.settings import settings
    
    # 0. Auto-kill older instances and acquire Single Instance Lock
    from utils.singleton import acquire_or_kill_single_instance
    lock_id = settings.telegram_bot_token or "brain_cli_mode"
    console.print("\n[cyan]Checking for existing Brain instances...[/cyan]")
    if not acquire_or_kill_single_instance(f"brain_{lock_id}"):
        console.print("[bold red]❌ STARTUP FAILED: COULD NOT ACQUIRE LOCK[/bold red]")
        console.print("[yellow]Another instance is running and couldn't be terminated. Please close it manually.[/yellow]\n")
        sys.exit(1)

    # 1. Initialize Database Connections
    try:
        from config.database import get_db_factory
        factory = get_db_factory()
        factory.get_adbc_connection()
        factory.get_sqlalchemy_engine()
        logger.info("[MAIN] Shared database connections initialized.")
    except Exception as e:
        logger.error(f"[MAIN] Database initialization warning: {e}")
        
    args = parse_args()
    print_banner()
    
    if args.status:
        show_status()
        return
    
    if args.debug:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.test or args.cycle_once:
        success = asyncio.run(run_single_cycle())
        sys.exit(0 if success else 1)
    
    # Run with or without Telegram
    if settings.telegram_bot_token and settings.telegram_chat_id:
        console.print("[green]Starting Brain with Modular Telegram Connector...[/green]")
        try:
            asyncio.run(run_with_telegram())
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutdown requested.[/yellow]")
    else:
        console.print("[yellow]Telegram not configured. Running in CLI mode.[/yellow]")
        try:
            asyncio.run(run_agent())
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutdown requested.[/yellow]")

if __name__ == "__main__":
    main()
