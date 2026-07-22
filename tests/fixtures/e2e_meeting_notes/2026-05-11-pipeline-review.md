# Project Lighthouse — Pipeline Design Review
NOTE: This is an AI-generated test document, it's not real, and any resembelenace to real people or places is coincidence. 

**Date:** 2026-05-11
**Attendees:** Sarah Chen (Product Manager), Raj Patel (Lead Engineer), Marcus Webb (Backend Engineer)

## Agenda
- Review Raj's technical design doc for the data pipeline rewrite.
- Review Marcus's Kafka streaming spike results.

## Discussion
Raj presented the design doc: replacing the nightly batch job with an event-driven pipeline
that consumes stock-change events directly from the warehouse POS systems. He proposed
using the existing Kafka cluster (the same one the billing team runs) with a new topic per
warehouse.

Marcus's spike confirmed this is feasible — he got a proof of concept publishing mock stock
events from a local warehouse simulator into Kafka and consuming them into a test Postgres
table with under 2 seconds of end-to-end latency.

Sarah asked about rollout risk given this touches the shared Kafka cluster. Raj suggested
coordinating with the billing team before deploying to production, since Project Lighthouse
would be a new consumer group on infrastructure they don't own.

Sarah flagged that David Kim wants a demo of the multi-warehouse view before the Denver
warehouse go-live in August, so the pipeline needs to be stable enough for daily use by
mid-July.

## Action Items
- Raj: Reach out to the billing team's on-call about sharing the Kafka cluster.
- Marcus: Build out the real ingestion service (not just the spike), target 2026-06-01.
- Sarah: Schedule a check-in with David Kim for early June to preview progress.

## Next Meeting
2026-05-18, same time.
