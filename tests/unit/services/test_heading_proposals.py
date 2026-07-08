"""标题提议：##–######。"""

from memoria.services.heading_proposals import propose_ranges_from_headings


def test_proposes_h4_headings():
    body = """# Root

## Section

### Sub

#### 知识点1-1

line a

#### 知识点1-2

line b
"""
    props = propose_ranges_from_headings(body)
    names = [p["name"] for p in props]
    assert "知识点1-1" in names
    assert "知识点1-2" in names
    kp1 = next(p for p in props if p["name"] == "知识点1-1")
    assert kp1["range"]["start"]["line_hint"] == 7
    assert kp1["range"]["end"]["line_hint"] == 9


def test_proposes_h2_through_h6():
    body = """## Two

a

### Three

b

#### Four

c

##### Five

d

###### Six

e
"""
    props = propose_ranges_from_headings(body)
    names = [p["name"] for p in props]
    assert names == ["Two", "Three", "Four", "Five", "Six"]
    four = next(p for p in props if p["name"] == "Four")
    assert four["range"]["end"]["line_hint"] == 19
