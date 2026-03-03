"""Timeline builder agent -- assembles chronological timeline from person data."""

from __future__ import annotations

import logging
from datetime import date

from src.agents.base import BaseAgent
from src.agents.registry import register_agent
from src.models import Person, SourceType, TimelineEvent

logger = logging.getLogger(__name__)


@register_agent("timeline_builder")
class TimelineBuilderAgent(BaseAgent):
    """Assembles a chronological timeline from all person data and stores as facts."""

    name = "timeline_builder"
    source_type = SourceType.WEB_SEARCH  # meta agent
    description = "Chronological timeline construction"

    async def run(self, person: Person) -> Person:
        await self._report_progress("running", f"Building timeline for {person.namn}")

        events: list[TimelineEvent] = []

        # Birth
        if person.fodelsedatum:
            events.append(TimelineEvent(
                datum=person.fodelsedatum,
                titel=f"{person.namn} född",
                source=SourceType.RATSIT,
                category="identity",
            ))

        # Income history
        for inc in person.inkomst:
            events.append(TimelineEvent(
                datum=date(inc.ar, 12, 31),
                titel=f"Inkomst {inc.ar}: {inc.belopp:,} kr",
                beskrivning=f"Taxerad inkomst i {inc.kommun}" if inc.kommun else "",
                source=SourceType.RATSIT,
                category="financial",
            ))

        # Tax history
        for tax in person.skatt:
            events.append(TimelineEvent(
                datum=date(tax.ar, 12, 31),
                titel=f"Skatt {tax.ar}: {tax.belopp:,} kr",
                source=SourceType.RATSIT,
                category="financial",
            ))

        # Payment remarks
        for remark in person.betalningsanmarkningar:
            if remark.datum:
                events.append(TimelineEvent(
                    datum=remark.datum,
                    titel=f"Betalningsanmärkning: {remark.typ}",
                    beskrivning=f"Belopp: {remark.belopp} kr" if remark.belopp else "",
                    source=SourceType.RATSIT,
                    category="financial",
                ))

        # Company roles
        for role in person.foretag:
            if role.fran:
                events.append(TimelineEvent(
                    datum=role.fran,
                    titel=f"{role.roll.value} i {role.foretag_namn}",
                    beskrivning=f"Org.nr: {role.org_nummer}" if role.org_nummer else "",
                    source=SourceType.ALLABOLAG,
                    category="professional",
                ))
            if role.till:
                events.append(TimelineEvent(
                    datum=role.till,
                    titel=f"Avgick som {role.roll.value} i {role.foretag_namn}",
                    source=SourceType.ALLABOLAG,
                    category="professional",
                ))

        # News mentions
        for news in person.news_mentions:
            if news.datum:
                events.append(TimelineEvent(
                    datum=news.datum,
                    titel=news.title,
                    beskrivning=f"{news.publication}: {news.snippet[:200]}",
                    source=SourceType.NEWS,
                    category="social",
                    url=news.url,
                ))

        # Breach records
        for breach in person.breaches:
            if breach.breach_date:
                events.append(TimelineEvent(
                    datum=breach.breach_date,
                    titel=f"Dataläcka: {breach.breach_name}",
                    beskrivning=f"Exponerad data: {', '.join(breach.exposed_data)}",
                    source=SourceType.HIBP,
                    category="digital",
                ))

        # Sort chronologically
        events.sort(key=lambda e: e.datum)

        # Store each event as a fact in HiveMindDB
        for event in events:
            await self.store_person_fact(
                person,
                f"[{event.datum}] [{event.category}] {event.titel}"
                + (f" — {event.beskrivning}" if event.beskrivning else ""),
                tags=["timeline", event.category, person.namn],
            )

        person.sources.append(self.make_source_ref("analysis:timeline"))
        logger.info(
            "TimelineBuilder: Created %d timeline events for %s",
            len(events), person.namn,
        )
        return person
