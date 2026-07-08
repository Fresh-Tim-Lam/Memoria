"""合并 S1 标题 + S2 mention + S5 定义句提议，去重。"""



from __future__ import annotations



import re



from memoria.services.definition_proposals import propose_ranges_from_definitions

from memoria.services.heading_proposals import propose_ranges_from_headings

from memoria.services.mention_proposals import propose_ranges_from_mentions





def _normalize_name(s: str) -> str:

    return re.sub(r"\s+", "", (s or "").lower())





def _ranges_overlap(a: dict, b: dict) -> bool:

    ar = a.get("range") or {}

    br = b.get("range") or {}

    a0 = ar.get("start", {}).get("line_hint") or 0

    a1 = ar.get("end", {}).get("line_hint") or 0

    b0 = br.get("start", {}).get("line_hint") or 0

    b1 = br.get("end", {}).get("line_hint") or 0

    if not a0 or not a1 or not b0 or not b1:

        return False

    return not (a1 < b0 or b1 < a0)





def merge_range_proposals(

    heading: list[dict],

    mention: list[dict],

    definition: list[dict] | None = None,

) -> list[dict]:

    """标题优先；mention / definition 与同名或重叠 range 的跳过。"""

    out: list[dict] = []

    heading_names = {_normalize_name(p.get("name", "")) for p in heading}

    taken: list[dict] = list(heading)



    for p in heading:

        item = dict(p)

        item.setdefault("strategy", "heading")

        out.append(item)



    for p in mention:

        name = _normalize_name(p.get("name", ""))

        if name in heading_names:

            continue

        if any(_ranges_overlap(p, h) for h in taken):

            continue

        item = dict(p)

        item.setdefault("strategy", "mention")

        out.append(item)

        taken.append(item)



    for p in definition or []:

        name = _normalize_name(p.get("name", ""))

        if name in heading_names:

            continue

        if any(_normalize_name(x.get("name", "")) == name for x in mention):

            continue

        if any(_ranges_overlap(p, h) for h in taken):

            continue

        item = dict(p)

        item.setdefault("strategy", "definition")

        out.append(item)

        taken.append(item)



    return out





def propose_all_ranges(

    body: str,

    frontmatter: dict | None,

) -> tuple[list[dict], list[dict], list[dict], list[dict]]:

    """返回 (heading, mention, definition, merged)。"""

    heading = propose_ranges_from_headings(body)

    mention = propose_ranges_from_mentions(body, frontmatter)

    definition = propose_ranges_from_definitions(body)

    merged = merge_range_proposals(heading, mention, definition)

    return heading, mention, definition, merged

