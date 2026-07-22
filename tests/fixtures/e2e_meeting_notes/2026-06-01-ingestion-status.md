# Project Lighthouse — Ingestion Service Status
NOTE: This is an AI-generated test document, it's not real, and any resemblance to real people or places is coincidence.

**Date:** 2026-06-01
**Attendees:** Raj Patel (Lead Engineer), Marcus Webb (Backend Engineer), Sarah Chen (Product Manager)

## Agenda
- Status update on the streaming ingestion service.
- Discuss coordination with the billing team on shared Kafka cluster.

## Discussion
Marcus reported the ingestion service is deployed to staging and has been consuming real
stock-change events from the Seattle and Portland warehouses for the past three days
without dropped messages. Denver and Reno aren't live yet, so those topics are still
running against the simulator.

Raj said the billing team's on-call, a guy named Tom Alvarez, approved Project Lighthouse
as a new consumer group but asked that Lighthouse's consumer lag be monitored so it
doesn't interfere with billing's own SLAs. Marcus added a lag alert to the on-call rotation.

Sarah reminded the team the check-in with David Kim is scheduled for next week and asked
Marcus to prepare a short demo of live stock counts updating on a test dashboard.

There was a brief discussion about Priya Nair, the new Reno warehouse manager, asking
through David whether the compare view can show a delta between yesterday's and today's
stock counts. Sarah said it's a good V2 idea but out of scope for the August V1 milestone.

## Action Items
- Marcus: Prepare live demo of streaming stock counts for David's check-in.
- Raj: Keep monitoring consumer lag, report weekly to Tom Alvarez.
- Sarah: Log the day-over-day delta view as a V2 backlog item.

## Next Meeting
2026-06-08, same time.
