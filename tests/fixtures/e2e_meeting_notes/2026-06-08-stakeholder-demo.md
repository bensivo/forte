# Project Lighthouse — Stakeholder Demo
NOTE: This is an AI-generated test document, it's not real, and any resemblance to real people or places is coincidence.

**Date:** 2026-06-08
**Attendees:** Sarah Chen (Product Manager), Raj Patel (Lead Engineer), Elena Torres (Design Lead),
Marcus Webb (Backend Engineer), David Kim (Stakeholder, VP of Operations)

## Agenda
- Demo the multi-warehouse compare view to David Kim.
- Confirm timeline for August V1 launch.

## Discussion
Marcus demoed the live dashboard showing stock counts updating in near-real-time for
Seattle and Portland, with Denver and Reno shown against simulated data since those
warehouses aren't open yet. David was impressed with the latency and said it was already
better than what the operations team currently gets from the legacy dashboard.

Elena walked through the finished compare-all-warehouses landing page. David approved the
layout with one small request: surface the warehouse manager's name (e.g., Priya Nair for
Reno) in the header of each warehouse's column so his team knows who to contact about
discrepancies.

Raj confirmed the Kafka consumer lag has stayed well within the threshold Tom Alvarez's
team set, and billing has had no complaints in the week since going live in staging.

Sarah confirmed the plan to go to production ahead of the Denver warehouse opening in
August, with a freeze on new scope after this meeting so the team can focus on hardening
and the production Kafka cutover with the billing team.

## Action Items
- Elena: Add warehouse manager name to each column header.
- Raj: Coordinate production Kafka cutover date with Tom Alvarez.
- Sarah: Communicate scope freeze to the wider Nimbus Analytics stakeholder list.
- Marcus: Begin load testing ahead of the Denver/Reno go-live.

## Next Meeting
2026-06-22 (biweekly cadence starting now).
