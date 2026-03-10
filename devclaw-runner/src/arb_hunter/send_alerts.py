"""
Send alerts module.

Formats and sends Telegram alerts via telegram_formatter.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp
import structlog

from .config_loader import Config
from .job_context import JobContext
from .filter_and_rank import ArbAlert

logger = structlog.get_logger(__name__)


@dataclass
class AlertResult:
    """Result of sending alerts."""
    
    total_attempted: int = 0
    sent_count: int = 0
    failed_count: int = 0
    errors: list[dict[str, Any]] = None  # type: ignore
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def add_success(self) -> None:
        self.sent_count += 1
        self.total_attempted += 1
    
    def add_failure(self, alert_id: str, error: str) -> None:
        self.failed_count += 1
        self.total_attempted += 1
        self.errors.append({
            "alert_id": alert_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        })


def format_arb_alert(alert: ArbAlert) -> str:
    """
    Format a single arbitrage alert as a Telegram message.
    
    Uses telegram_formatter style formatting.
    """
    arb = alert.arb
    
    # Determine emoji based on priority
    priority_emoji = {
        "high": "🚨",
        "medium": "⚡",
        "low": "📊",
    }.get(alert.alert_priority, "📊")
    
    # Format the message
    lines = [
        f"{priority_emoji} *ARBITRAGE OPPORTUNITY #{alert.rank}*",
        "",
        f"📌 *Event:* {arb.event_title}",
        f"🎯 *Outcome:* {arb.outcome_name}",
        f"🏢 *Sportsbook:* {arb.sportsbook.title()}",
        "",
        "📊 *Odds Comparison:*",
        f"  • Polymarket: `{arb.polymarket_decimal_odds:.3f}` ({arb.polymarket_probability*100:.1f}%)",
        f"  • {arb.sportsbook.title()}: `{arb.sportsbook_decimal_odds:.3f}` ({arb.sportsbook_probability*100:.1f}%)",
        "",
        "💰 *Profit Analysis:*",
        f"  • Net Edge: `{arb.edge_percent:.2f}%`",
        f"  • Guaranteed Profit: `${arb.guaranteed_profit:.2f}`",
        f"  • ROI: `{arb.return_on_investment:.2f}%`",
        "",
        "💵 *Recommended Stakes:*",
        f"  • Polymarket: `${arb.recommended_pm_stake:.2f}`",
        f"  • {arb.sportsbook.title()}: `${arb.recommended_sb_stake:.2f}`",
        f"  • Total Exposure: `${arb.total_exposure:.2f}`",
        "",
        f"📝 *Reason:* {alert.alert_reason}",
        f"🎯 *Match Confidence:* {arb.match_score*100:.0f}%",
        "",
        f"⏰ *Detected:* {arb.calculated_at.strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    
    return "\n".join(lines)


def format_summary_alert(alerts: list[ArbAlert], ctx: JobContext) -> str:
    """Format a summary message with all alerts."""
    lines = [
        f"🔍 *ARBITRAGE SCAN COMPLETE* — Run `{ctx.run_id}`",
        "",
        f"Found *{len(alerts)}* arbitrage opportunities",
        "",
        "📈 *Top Opportunities:*",
    ]
    
    for alert in alerts[:5]:  # Top 5 in summary
        arb = alert.arb
        emoji = {"high": "🚨", "medium": "⚡", "low": "📊"}.get(alert.alert_priority, "📊")
        lines.append(
            f"{emoji} #{alert.rank} {arb.event_title[:40]}... "
            f"Edge: `{arb.edge_percent:.1f}%` Profit: `${arb.guaranteed_profit:.0f}`"
        )
    
    if len(alerts) > 5:
        lines.append(f"\n... and {len(alerts) - 5} more opportunities")
    
    lines.extend([
        "",
        f"⏱️ Scan duration: {ctx.duration_seconds:.1f}s",
        f"📊 Markets analyzed: {ctx.markets_fetched}",
        f"🔗 Matches found: {ctx.matches_found}",
    ])
    
    return "\n".join(lines)


def format_no_arbs_message(ctx: JobContext) -> str:
    """Format a message when no arbitrages are found."""
    return "\n".join([
        f"📊 *ARBITRAGE SCAN COMPLETE* — Run `{ctx.run_id}`",
        "",
        "No arbitrage opportunities found meeting current thresholds.",
        "",
        f"📈 *Scan Statistics:*",
        f"  • Markets analyzed: {ctx.markets_fetched}",
        f"  • Normalized markets: {ctx.markets_normalized}",
        f"  • Matches found: {ctx.matches_found}",
        f"  • Arbs calculated: {ctx.arbs_calculated}",
        "",
        f"⏱️ Duration: {ctx.duration_seconds:.1f}s",
    ])


async def send_telegram_message(
    bot_token: str,
    chat_id: str,
    message: str,
    session: aiohttp.ClientSession,
    parse_mode: str = "Markdown",
) -> bool:
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    
    try:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                return True
            else:
                error_text = await resp.text()
                logger.error("telegram_send_failed", status=resp.status, error=error_text)
                return False
    except Exception as e:
        logger.error("telegram_send_exception", error=str(e))
        return False


async def send_alerts(
    alerts: list[ArbAlert],
    config: Config,
    ctx: JobContext,
) -> tuple[AlertResult, JobContext]:
    """
    Format and send Telegram alerts.
    
    Returns:
        Tuple of (alert_result, updated_context)
    """
    log = logger.bind(run_id=ctx.run_id)
    log.info("starting_alert_send", alert_count=len(alerts))
    
    result = AlertResult()
    
    # Check if alerting is configured
    if not config.telegram_bot_token or not config.telegram_chat_id:
        log.warning("telegram_not_configured", has_token=bool(config.telegram_bot_token), has_chat_id=bool(config.telegram_chat_id))
        return result, ctx
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if not alerts:
            # Send "no arbs" message
            message = format_no_arbs_message(ctx)
            success = await send_telegram_message(
                config.telegram_bot_token,
                config.telegram_chat_id,
                message,
                session,
            )
            if success:
                result.add_success()
                log.info("no_arbs_message_sent")
            else:
                result.add_failure("summary", "failed_to_send_no_arbs_message")
                log.error("no_arbs_message_failed")
            
            updated_ctx = ctx.with_alerts_sent(result.sent_count)
            return result, updated_ctx
        
        # Send summary first
        summary_message = format_summary_alert(alerts, ctx)
        summary_success = await send_telegram_message(
            config.telegram_bot_token,
            config.telegram_chat_id,
            summary_message,
            session,
        )
        
        if summary_success:
            result.add_success()
            log.info("summary_alert_sent")
        else:
            result.add_failure("summary", "failed_to_send_summary")
            log.error("summary_alert_failed")
        
        # Send individual alerts for high/medium priority
        for alert in alerts:
            if alert.alert_priority in ("high", "medium"):
                message = format_arb_alert(alert)
                success = await send_telegram_message(
                    config.telegram_bot_token,
                    config.telegram_chat_id,
                    message,
                    session,
                )
                
                if success:
                    result.add_success()
                    log.info("individual_alert_sent", rank=alert.rank, priority=alert.alert_priority)
                else:
                    result.add_failure(alert.arb.arb_id, "failed_to_send")
                    log.error("individual_alert_failed", rank=alert.rank)
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
    
    updated_ctx = ctx.with_alerts_sent(result.sent_count)
    
    log.info(
        "alert_send_complete",
        sent=result.sent_count,
        failed=result.failed_count,
    )
    
    return result, updated_ctx
