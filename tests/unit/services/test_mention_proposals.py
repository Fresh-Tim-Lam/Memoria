"""S2 mention 提议测试。"""

from memoria.services.mention_proposals import propose_ranges_from_mentions
from memoria.services.range_proposals import merge_range_proposals, propose_all_ranges
from memoria.storage.markdown import strip_frontmatter


SAMPLE = """---
concepts:
  - id: foo
    name: Foo Term
---

# Title

Intro without the term.

Some paragraph mentioning Foo Term here.
Second line of paragraph.

## Section

More text.
"""


def test_mention_proposal_finds_paragraph():
    body, fm = strip_frontmatter(SAMPLE)
    props = propose_ranges_from_mentions(body, fm)
    assert len(props) == 1
    assert props[0]["strategy"] == "mention"
    assert props[0]["range"]["start"]["line_hint"] == 5
    assert props[0]["range"]["end"]["line_hint"] == 6


def test_merge_dedupes_heading_and_mention():
    body, fm = strip_frontmatter(SAMPLE)
    heading, mention, merged = propose_all_ranges(body, fm)
    assert len(heading) == 1
    assert heading[0]["name"] == "Section"
    assert len(mention) == 1
