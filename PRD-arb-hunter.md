# PRD: OpenClaw – Sportsbook + Prediction Market Arbitrage Hunter

**Version:** 1.1
**Status:** READY-TO-BUILD
**Owner:** You
**Scope:** Scheduled scanner that compares Polymarket and traditional sportsbook prices for equivalent events, detects true post-fee arbitrage opportunities, and sends Telegram alerts with clean sizing and profit calculations.
**Primary Mode:** Alerting only. No auto-betting or account automation.

---

## 1) Executive Summary

This feature turns your existing OpenClaw cron infrastructure into a **cross-venue arbitrage scanner** for:

* **Prediction markets** (Polymarket first; Kalshi optional later)
* **Traditional sportsbooks** (via The Odds API or equivalent aggregated odds source)

The system identifies overlapping events, normalizes their outcomes, applies fees/slippage/liquidity filters, and alerts only on **true actionable arbitrage**.

The scanner must be conservative. False positives are worse than missed edges. A valid alert should mean:

* same underlying event
* same resolution semantics
* enough liquidity to execute
* net edge still positive after fees/slippage
* execution window not obviously stale

---

## 2) Problem Statement

Prediction markets and sportsbooks often price similar outcomes differently, but turning that into a real arbitrage workflow is hard because:

* event names differ across platforms
* outcome semantics may not match exactly
* prices may be stale or thin
* fees, vig, and slippage can erase apparent edge
* some "arbs" are fake because market resolution rules are different

Manual scanning is too slow, and raw price scraping without normalization creates junk alerts.

---

## 3) Product Goals

### Primary Goals

1. Scan overlapping events on a schedule.
2. Match equivalent events with high confidence.
3. Normalize outcomes into comparable YES/NO or side/opposite-side structures.
4. Calculate post-fee, post-slippage arbitrage correctly.
5. Send Telegram alerts only for high-confidence, actionable opportunities.
6. Log all scans, matches, rejects, and alerts for audit and later tuning.

### Non-Goals

* Auto-betting
* Browser automation
* In-play/live arbitrage in v1
* Multi-leg hedge construction across more than two venues
* Full portfolio optimization in v1

---

## 4) Product Principles

* **Conservative by default**: better to miss an arb than alert on a fake one
* **Explain every alert**: include why it matched and why it passed filters
* **Post-cost only**: no alert unless profitable after all modeled friction
* **Execution-aware**: stale or low-liquidity opportunities must be suppressed
* **Auditable**: every scan result should be reproducible from stored snapshots

---

## 5) Supported Sources (MVP)

### Prediction Markets

* Polymarket (primary)
* Kalshi (optional phase 2)

### Sportsbooks

* Aggregated sportsbook feed via The Odds API or equivalent source
* Initial supported books:
  * DraftKings
  * FanDuel
  * Bet365
  * other supported books only if normalized properly

### Assumption

This PRD assumes the relevant APIs are available and allowed for your use case. API pricing, terms, and limits should be validated during implementation.

---

## 6) Core Functional Requirements

### 6.1 Scheduled Scanning

Default scheduled run:
* daily at **3:30 a.m.**

Recommended addition:
* support **manual trigger**
* support **configurable higher-frequency mode** later, because daily scans will miss many short-lived edges

#### MVP Requirement

* cron-driven daily run
* manual run command for testing
* env flag to enable/disable scanner

---

### 6.2 Event Ingestion and Normalization

The system must ingest raw events from each source and normalize them into a common internal format.

Each normalized event must include:
* source
* source event ID
* title
* category/sport/market type
* start/resolution timestamp
* outcome labels
* odds/prices
* liquidity or market depth if available
* URL/deep link
* last updated timestamp

---

### 6.3 Event Matching

The system must perform **high-confidence event matching** before doing any arb math.

Matching must consider:
* title similarity
* category/market type
* event date/time proximity
* team/candidate/entity names
* resolution semantics
* market direction consistency

#### Examples

Good match:
* "Will Trump win 2028?" vs "Trump to win 2028 election"

Bad match:
* "Trump wins GOP nomination" vs "Trump wins general election"

#### Matching Output

Each matched pair must include:
* match score
* matched entities
* resolution confidence
* rejection reason if not accepted

---

### 6.4 Outcome Mapping

The system must normalize outcomes into opposite-side pairs.

Examples:
* Polymarket YES vs sportsbook NO-equivalent
* market YES vs book implied NOT-YES
* over/under mappings where semantics are exact
* moneyline side vs opposite outcome only if rules truly align

If outcome mapping is ambiguous, suppress the arb.

---

### 6.5 Arbitrage Calculation

For each matched and mapped pair, calculate whether buying one side on one venue and the opposite side on another venue yields guaranteed positive return after modeled friction.

#### Costs to include

* market fees
* sportsbook vig impact
* execution slippage
* spread/price movement buffer
* optional withdrawal/settlement friction if you want conservative modeling

#### Alert threshold

Only alert if:
* net edge > **2.0%** after costs
* total usable liquidity > configurable minimum
* match confidence exceeds threshold
* freshness window is valid

---

## 7) Data Contracts

### 7.1 NormalizedMarket

Fields:
* source: string (e.g., "polymarket")
* source_event_id: string
* title: string
* market_type: string (e.g., "binary")
* category: string (e.g., "politics")
* start_or_resolution_time: ISO timestamp
* outcomes: array of {label, price, liquidity}
* url: string
* last_updated_at: ISO timestamp

### 7.2 MatchedOpportunity

Fields:
* match_id: uuid
* left_source: string
* right_source: string
* left_event_id: string
* right_event_id: string
* match_score: float (0-1)
* resolution_confidence: float (0-1)
* mapping_type: string (e.g., "yes_vs_no")
* status: string (e.g., "matched")

### 7.3 ArbOpportunity

Fields:
* arb_id: uuid
* event_title: string
* left_leg: {source, side, price, liquidity, url}
* right_leg: {source, side, price, liquidity, url}
* gross_edge_pct: float
* fees_pct: float
* slippage_pct: float
* net_edge_pct: float
* max_size: number
* expected_profit: number
* match_score: float
* resolution_confidence: float
* freshness_seconds: number
* alertable: boolean

---

## 8) Arbitrage Math Requirements

### 8.1 Internal Rule

An opportunity is only a true arb if the fully-loaded cost of covering all mutually exclusive outcomes is less than the guaranteed payout.

### 8.2 Conservative Modeling

For MVP, include:
* source price
* estimated execution slippage
* fee model per venue
* liquidity cap
* stale price penalty if last update exceeds threshold

### 8.3 Sizing

Alert should include:
* profit on $1k
* profit on $10k
* max size based on minimum usable liquidity
* note if one leg is depth-constrained

---

## 9) Filtering Rules

Suppress opportunities if any of the following are true:
* net edge <= 2.0%
* liquidity below threshold
* match confidence below threshold
* resolution semantics uncertain
* timestamps too stale
* source data incomplete
* one side appears suspended / untradable
* event start/resolution already too close or already passed
* market rules differ in a way that breaks hedge symmetry

---

## 10) Telegram Alert Format

Message structure:
```
🚨 ARB ALERT

Event: {event_title}
Match Confidence: {match_score}%
Resolution Confidence: {resolution_confidence}%

Leg 1: {source} {side} @ {price}
Leg 2: {source} {side} @ {price}

Gross Edge: +{gross_edge_pct}%
Estimated Fees/Slippage: -{fees_pct}%
Net Edge: +{net_edge_pct}%

Estimated Profit:
- $1,000 size → ${profit_1k}
- $10,000 size → ${profit_10k}

Usable Liquidity:
- {source}: ${liquidity}
- {source}: ${liquidity}

Links:
[{source}] [{source}]

Timestamp: {timestamp}
```

### Alert Rules

* one alert per unique arb per run
* dedupe repeat alerts unless edge changes materially
* optional "resolved / gone stale" follow-up alert later

---

## 11) Files to Create / Modify

### New Files

1. arb_hunter.py
2. market_normalizer.py
3. event_matcher.py
4. arb_math.py
5. telegram_formatter.py

### Modified Files

1. n8n workflow definitions
2. .env.example
3. .openclaw/review.yaml
4. README.md

---

## 12) Proposed Module Responsibilities

### arb_hunter.py

Top-level job runner:
* fetch data
* normalize
* match
* compute arb
* filter
* alert
* log

### market_normalizer.py

* transforms raw API responses into canonical format

### event_matcher.py

* fuzzy title matching
* entity extraction
* resolution/date consistency checks

### arb_math.py

* computes gross and net arb edge
* applies fee/slippage/liquidity constraints
* computes recommended sizing and profit estimates

### telegram_formatter.py

* generates readable alert payloads
* handles dedupe formatting

---

## 13) Environment and Config

### Required Environment Variables

* ARB_HUNTER_ENABLED=true|false
* POLYMARKET_API_BASE=...
* ODDS_API_KEY=...
* KALSHI_API_KEY=... (optional)
* TELEGRAM_BOT_TOKEN=...
* TELEGRAM_CHAT_ID=...

### Configurable Thresholds

* ARB_MIN_NET_EDGE_PCT=2.0
* ARB_MIN_TOTAL_LIQUIDITY=10000
* ARB_MAX_STALENESS_SECONDS=120
* ARB_MATCH_CONFIDENCE_MIN=0.85
* ARB_RESOLUTION_CONFIDENCE_MIN=0.90

---

## 14) Failure Modes and Degradation

| Scenario | Expected Behavior |
|----------|-------------------|
| one API fails | continue with partial scan, log degraded run |
| no matches found | log success with zero opportunities |
| ambiguous match | suppress and log reject reason |
| stale price data | suppress opportunity |
| Telegram failure | persist alert payload and log delivery failure |
| duplicate opportunity | dedupe within configurable window |
| liquidity missing | downgrade confidence or suppress |

---

## 15) Logging and Auditability

Every run must log:
* run ID
* start/end timestamps
* sources queried
* number of markets fetched
* number of matches found
* number of opportunities rejected
* rejection reasons
* alerts sent
* API failures
* correlation ID / idempotency key for each alert

Recommended artifact storage:
* raw source snapshot for each run
* matched pair records
* final arb candidates
* sent alerts

This will let you tune thresholds later.

---

## 16) Acceptance Criteria

- [ ] Job runs on schedule without crashing
- [ ] Manual run works
- [ ] Events are normalized into a common format
- [ ] Matching logic correctly links at least 3 known overlapping markets in test data
- [ ] Arb math includes fees, slippage, and liquidity
- [ ] Only net-positive >2% opportunities alert
- [ ] Telegram alert format is readable and actionable
- [ ] Every run writes an audit trail
- [ ] Scanner can be enabled/disabled via env var
- [ ] False-positive suppression works for mismatched resolution rules

---

## 17) Test Plan

### Unit Tests

* normalize Polymarket market
* normalize sportsbook event
* fuzzy match positive case
* fuzzy match rejection case
* yes/no mapping
* fee-adjusted arb calculation
* stale-price suppression
* liquidity suppression
* alert dedupe

### Integration Tests

* Polymarket + sportsbook fetch pipeline
* end-to-end matched event generation
* Telegram message formatting
* degraded-mode run when one API fails

### End-to-End Tests

* run against 3 known overlapping markets
* verify one true arb alerts
* verify one false arb is rejected due to resolution mismatch
* verify logs and output artifacts written

---

## 18) Implementation Checklist

- [ ] Create arb_hunter.py
- [ ] Create market_normalizer.py
- [ ] Create event_matcher.py
- [ ] Create arb_math.py
- [ ] Create telegram_formatter.py
- [ ] Add scheduled cron in n8n
- [ ] Add manual trigger path
- [ ] Add environment variables to .env.example
- [ ] Add API permissions note to .openclaw/review.yaml
- [ ] Write tests for normalization, matching, math, and alerts
- [ ] Test with 3 real overlapping markets
- [ ] Update README

---

## 19) Future Enhancements

* higher-frequency scans
* Kalshi integration
* richer liquidity/depth modeling
* venue-specific fee models
* opportunity ranking
* optional dashboard view
* historical "missed opportunity" analysis
* alert cooldown tuning

---

## 20) Recommended Build Order

1. normalization layer
2. matching layer
3. arb math
4. alert formatting
5. job runner
6. cron integration
7. logging/audit
8. tests
9. README
