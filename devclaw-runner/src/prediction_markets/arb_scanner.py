#!/usr/bin/env python3
"""
Prediction Market Arbitrage Scanner
Scans Polymarket (Gamma), Kalshi (REST), PredictIt for arb opportunities
Safe: alerts only, no auto-trading
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import httpx
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

@dataclass
class Market:
    platform: str
    id: str
    title: str
    description: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    resolution_date: str
    url: str
    fees: float  # total taker fees %

@dataclass
class ArbOpportunity:
    event_name: str
    market_a: Market
    market_b: Market
    spread_pct: float
    net_ev_pct: float
    profit_1k: float
    confidence: str
    idempotency_key: str
    correlation_id: str

class PredictionMarketArbScanner:
    MIN_LIQUIDITY = 10000  # $10k
    MIN_EV_PCT = 2.0       # +2%
    POLY_FEE = 0.0075      # 0.75% taker
    KALSHI_FEE = 0.05      # ~5% earnings fee estimate
    PREDICTIT_FEE = 0.10   # 10% on profits
    
    def __init__(self):
        self.telegram_bot_token = None
        self.telegram_chat_id = None
        self.correlation_id = f"arb-scan-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        
    async def fetch_polymarket(self) -> List[Market]:
        """Fetch from Gamma API (gamma-api.polymarket.com)"""
        markets = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Updated Gamma API endpoint (no auth required for read-only)
                resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"active": "true", "closed": "false", "limit": 100}
                )
                resp.raise_for_status()
                data = resp.json()
                
                # Gamma API returns a list directly
                markets_list = data if isinstance(data, list) else data.get("markets", [])
                
                for m in markets_list:
                    volume = float(m.get("volume", 0) or 0)
                    if volume < self.MIN_LIQUIDITY:
                        continue
                    
                    # Parse outcome prices from JSON string if needed
                    outcome_prices = m.get("outcomePrices")
                    if isinstance(outcome_prices, str):
                        try:
                            outcome_prices = json.loads(outcome_prices)
                        except:
                            outcome_prices = [0.5, 0.5]
                    
                    if not outcome_prices or not isinstance(outcome_prices, list):
                        outcome_prices = [0.5, 0.5]
                    
                    yes_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
                    no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else (1 - yes_price)
                    
                    markets.append(Market(
                        platform="Polymarket",
                        id=m.get("slug", m.get("id", "")),
                        title=m.get("question", ""),
                        description=m.get("description", ""),
                        yes_price=yes_price,
                        no_price=no_price,
                        volume=volume,
                        liquidity=float(m.get("liquidity", 0) or 0),
                        resolution_date=m.get("resolutionDate", m.get("endDate", "")),
                        url=f"https://polymarket.com/market/{m.get('slug', m.get('id', ''))}",
                        fees=self.POLY_FEE
                    ))
        except Exception as e:
            logger.error(f"Polymarket API failed: {e}")
            await self._log_audit("api_failure", "Polymarket", str(e))
        return markets
    
    async def fetch_kalshi(self) -> List[Market]:
        """Fetch from Kalshi REST API (api.elections.kalshi.com)"""
        markets = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Kalshi Elections API (no auth required for read-only market data)
                resp = await client.get(
                    "https://api.elections.kalshi.com/trade-api/v2/markets",
                    params={"status": "open", "limit": 100},
                    headers={"Accept": "application/json"}
                )
                resp.raise_for_status()
                data = resp.json()
                
                # Kalshi returns markets in 'markets' key
                markets_list = data.get("markets", [])
                
                for m in markets_list:
                    volume = float(m.get("volume", 0) or 0)
                    if volume < self.MIN_LIQUIDITY:
                        continue
                    
                    # Kalshi prices are in cents (0-100), convert to 0-1
                    yes_price = float(m.get("yes_ask", 0) or 0) / 100
                    no_price = float(m.get("no_ask", 0) or 0) / 100
                    
                    # Fallback to last price if ask not available
                    if yes_price == 0 and no_price == 0:
                        yes_price = float(m.get("yes_price", 0) or 0) / 100
                        no_price = float(m.get("no_price", 0) or 0) / 100
                    
                    # Derive NO price if not available directly
                    if no_price == 0 and yes_price > 0:
                        no_price = 1 - yes_price
                    if yes_price == 0 and no_price > 0:
                        yes_price = 1 - no_price
                    
                    markets.append(Market(
                        platform="Kalshi",
                        id=m.get("ticker", ""),
                        title=m.get("title", ""),
                        description=m.get("description", ""),
                        yes_price=yes_price,
                        no_price=no_price,
                        volume=volume,
                        liquidity=float(m.get("open_interest", 0) or 0),
                        resolution_date=m.get("expiration_date", m.get("settlement_date", "")),
                        url=f"https://kalshi.com/markets/{m.get('ticker', '')}",
                        fees=self.KALSHI_FEE
                    ))
        except Exception as e:
            logger.error(f"Kalshi API failed: {e}")
            await self._log_audit("api_failure", "Kalshi", str(e))
        return markets
    
    async def fetch_predictit(self) -> List[Market]:
        """Fetch from PredictIt (public data scraping)"""
        markets = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get("https://www.predictit.org/api/marketdata/all/")
                resp.raise_for_status()
                data = resp.json()
                
                for m in data.get("markets", []):
                    if m.get("volume", 0) < self.MIN_LIQUIDITY:
                        continue
                    contracts = m.get("contracts", [{}])[0]
                    markets.append(Market(
                        platform="PredictIt",
                        id=str(m.get("id", "")),
                        title=m.get("name", ""),
                        description=contracts.get("name", ""),
                        yes_price=contracts.get("bestBuyYesCost", 0),
                        no_price=contracts.get("bestBuyNoCost", 0),
                        volume=m.get("volume", 0),
                        liquidity=m.get("volume", 0) * 0.5,  # Estimate
                        resolution_date=m.get("dateEnd", ""),
                        url=f"https://www.predictit.org/markets/detail/{m.get('id', '')}",
                        fees=self.PREDICTIT_FEE
                    ))
        except Exception as e:
            logger.error(f"PredictIt API failed: {e}")
            await self._log_audit("api_failure", "PredictIt", str(e))
        return markets
    
    def similarity(self, a: str, b: str) -> float:
        """Fuzzy match two titles"""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    def calculate_arb(self, m1: Market, m2: Market) -> Optional[ArbOpportunity]:
        """Calculate if YES/NO arb exists"""
        # Check for YES/NO inversion opportunity
        # Buy YES on one, NO on other
        cost_yes = m1.yes_price * (1 + m1.fees)
        cost_no = m2.no_price * (1 + m2.fees)
        total_cost = cost_yes + cost_no
        
        if total_cost >= 1.0:
            # Try reverse
            cost_yes = m2.yes_price * (1 + m2.fees)
            cost_no = m1.no_price * (1 + m1.fees)
            total_cost = cost_yes + cost_no
            
            if total_cost >= 1.0:
                return None
            
            # Arb found (reversed)
            yes_market, no_market = m2, m1
        else:
            # Arb found
            yes_market, no_market = m1, m2
        
        profit = 1.0 - total_cost
        ev_pct = profit * 100
        
        if ev_pct < self.MIN_EV_PCT:
            return None
        
        # Check liquidity
        if yes_market.liquidity < self.MIN_LIQUIDITY or no_market.liquidity < self.MIN_LIQUIDITY:
            return None
        
        # Generate keys
        key_string = f"{yes_market.id}-{no_market.id}-{datetime.now().strftime('%Y%m%d')}"
        idempotency_key = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        
        return ArbOpportunity(
            event_name=yes_market.title[:100],
            market_a=yes_market,
            market_b=no_market,
            spread_pct=abs(yes_market.yes_price - no_market.yes_price) * 100,
            net_ev_pct=ev_pct,
            profit_1k=profit * 1000,
            confidence="high" if self.similarity(yes_market.title, no_market.title) > 0.8 else "medium",
            idempotency_key=idempotency_key,
            correlation_id=self.correlation_id
        )
    
    async def scan(self) -> List[ArbOpportunity]:
        """Main scan loop"""
        await self._log_audit("scan_start", "all", "Starting daily arb scan")
        
        # Fetch all markets
        poly = await self.fetch_polymarket()
        kalshi = await self.fetch_kalshi()
        predictit = await self.fetch_predictit()
        
        all_markets = poly + kalshi + predictit
        opportunities = []
        
        # Cross-platform matching
        for i, m1 in enumerate(all_markets):
            for m2 in all_markets[i+1:]:
                # Skip same platform
                if m1.platform == m2.platform:
                    continue
                
                # Fuzzy match titles
                if self.similarity(m1.title, m2.title) < 0.6:
                    continue
                
                # Check for arb
                arb = self.calculate_arb(m1, m2)
                if arb:
                    opportunities.append(arb)
        
        # Sort by EV
        opportunities.sort(key=lambda x: x.net_ev_pct, reverse=True)
        
        await self._log_audit("scan_complete", "all", f"Found {len(opportunities)} opportunities")
        return opportunities
    
    async def send_alerts(self, opportunities: List[ArbOpportunity]):
        """Send Telegram alerts"""
        if not opportunities:
            await self._log_audit("alert", "telegram", "No opportunities to alert")
            return
        
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.warning("Telegram credentials not set")
            return
        
        message = "🎯 *Prediction Market Arbitrage Opportunities*\n\n"
        
        for opp in opportunities[:5]:  # Top 5
            message += (
                f"*{opp.event_name[:60]}...*\n"
                f"📊 {opp.market_a.platform} YES @ {opp.market_a.yes_price:.2f} | "
                f"{opp.market_b.platform} NO @ {opp.market_b.no_price:.2f}\n"
                f"💰 EV: +{opp.net_ev_pct:.1f}% | Profit on $1k: ${opp.profit_1k:.0f}\n"
                f"🔗 [Polymarket]({opp.market_a.url if opp.market_a.platform == 'Polymarket' else opp.market_b.url}) | "
                f"[Kalshi]({opp.market_a.url if opp.market_a.platform == 'Kalshi' else opp.market_b.url})\n"
                f"💧 Liquidity: ${opp.market_a.liquidity/1000:.0f}k / ${opp.market_b.liquidity/1000:.0f}k\n\n"
            )
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                    json={
                        "chat_id": self.telegram_chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True
                    }
                )
            await self._log_audit("alert", "telegram", f"Sent {len(opportunities)} opportunities")
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")
            await self._log_audit("alert_failure", "telegram", str(e))
    
    async def _log_audit(self, event_type: str, component: str, message: str):
        """Log to audit trail"""
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": self.correlation_id,
            "idempotency_key": hashlib.sha256(f"{event_type}-{component}-{message}".encode()).hexdigest()[:16],
            "event_type": event_type,
            "component": component,
            "message": message
        }
        logger.info(f"AUDIT: {json.dumps(audit_entry)}")

async def main():
    scanner = PredictionMarketArbScanner()
    opportunities = await scanner.scan()
    await scanner.send_alerts(opportunities)
    return len(opportunities)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(main())
    print(f"Found {result} arbitrage opportunities")
