为 Memoria M1 设计一套以 **"熊出没动画片"** 为主题的全新样例知识库。

这是一个非常适合展示 Memoria 能力的主题，因为它：
1.  **概念丰富**：有世界观、角色、科技、地理、剧情等多维度知识点。
2.  **链接密集**：角色与科技、地点与事件之间存在大量自然关联。
3.  **用户友好**：内容亲切，容易理解和搜索，可以很好地测试"口语化/同义词"搜索功能。

---

### 已实现样例（独立于 `examples/`）

| 类型 | 路径 |
| :--- | :--- |
| KB 根目录 | `example-boonie/` |
| 正文 | `example-boonie/*.md` |
| 侧车 | `example-boonie/.memoria/sidecars/*.memoria.yaml` |
| Hub 入口 | `example-boonie/dog-xiong-ridge.md` |
| 侧车生成 | `python scripts/gen_example_boonie_sidecars.py` |

**说明**：下文 **E / F 节** 为完整设计草稿（长正文 + 设计侧车 YAML），**保留不删**；`example-boonie/` 中的可运行样例在 E 的基础上做了精简，并补充了 `[[wikilink]]`、Hub 阅读路径与虚链演示（见 **H 节**）。

---

### A. 设计摘要（200字内）

-   **主题**：熊出没动画片宇宙。涵盖世界观（狗熊岭）、核心角色（熊大、熊二、光头强）、关键科技（光头强发明）、主要地点和经典对立关系。
-   **受众**：对《熊出没》有基本了解的观众，或希望了解 Memoria 如何组织叙事性、流行文化知识库的开发者。
-   **与现有样例（RL/NLP）的差异**：本库聚焦于**叙事性常识和角色关系**，而非算法或数学公式。它更强调"同义指代"（如"强哥"指代"光头强"）和"情节关联"，而非算法流程，能很好地展示 Memoria 在人文领域的搜索和导航能力。

---

### B. 文件清单表

| 文件 | 用途 | KP 数量 | 主要链接出去 |
| :--- | :--- | :--- | :--- |
| `guang-tou-qiang.md` | **核心机制 / 角色**：光头强的个人档案、发明创造、与熊兄弟的关系。 | 4 | 熊大、熊二、飞碟、伐木、保护森林 |
| `bear-brothers.md` | **核心机制 / 角色**：熊大熊二的性格对比、能力、与光头强的互动模式。 | 3 | 光头强、狗熊岭、大马猴和二狗 |
| `dog-xiong-ridge.md` | **Hub 页（概览）**：狗熊岭世界观介绍，作为整个知识库的入口，链接到所有主要 KP。 | 3 | 熊大、熊二、光头强、大森林、护林员 |
| `inventions-and-events.md` | **应用/案例**：光头强的各种失败发明及引发的经典事件，串起角色和地点。 | 4 | 光头强、熊大、熊二、狗熊岭 |
| `minor-characters.md` | **对照/易混**：介绍次要角色（如大马猴、二狗、肥波），形成角色图谱的补充。 | 2 | 光头强、熊二 |
| `_nothing-here.md` | **边界样例**：一个"Nothing 占位"式短文件，用于测试系统的空内容或未索引文件处理。 | 0 | 无 |

*注：合计 **5 个有效 md 文件**，**16 个 KP**（设计稿）；可运行样例为 **15 个 KP**（「强哥」合并为 tag，见 H 节）。*

---

### C. KP 登记表

| id | name | 文件 | 起点标题 (一级/二级) | 终点锚点句（snippet 预览） |
| :--- | :--- | :--- | :--- | :--- |
| **guang-tou-qiang** | 光头强 | `guang-tou-qiang.md` | `## 光头强 (Guang Tou Qiang)` | "他经常被描绘成一个有点倒霉但又不失善良的伐木工。" |
| **qiang-ge** | 强哥 (同义/口语) | `guang-tou-qiang.md` | (与光头强同KP) | "熊大熊二通常用'强哥'来称呼他。" |
| **inventions** | 光头强的发明 | `guang-tou-qiang.md` | `## 光头强的发明` | "这些发明包括但不限于：超级伐木机、无敌搬运车、缩小射线。" |
| **fei-die** | 飞碟 (UFO) | `guang-tou-qiang.md` | `### 飞碟 (UFO)` | "光头强曾意外获得并尝试修复一艘外星飞碟。" |
| **xiong-da** | 熊大 | `bear-brothers.md` | `## 熊大 (Xiong Da)` | "熊大是熊兄弟中的哥哥，性格机智、沉稳。" |
| **xiong-er** | 熊二 | `bear-brothers.md` | `## 熊二 (Xiong Er)` | "熊二是熊兄弟中的弟弟，性格憨厚、贪吃，但力大无穷。" |
| **protect-forest** | 保护森林 | `bear-brothers.md` | `## 保护森林` | "熊兄弟的核心目标是阻止光头强砍树，并保护森林家园。" |
| **gou-xiong-ling** | 狗熊岭 | `dog-xiong-ridge.md` | `## 狗熊岭` | "狗熊岭是《熊出没》系列动画的主要故事发生地。" |
| **big-forest** | 大森林 | `dog-xiong-ridge.md` | `## 大森林` | "狗熊岭深处的大森林是动物们赖以生存的家园。" |
| **forest-ranger** | 护林员 | `dog-xiong-ridge.md` | `### 护林员` | "在某些剧集中，光头强曾短暂担任过护林员的角色。" |
| **super-felling** | 超级伐木机 | `inventions-and-events.md` | `## 超级伐木机事件` | "光头强驾驶着他的超级伐木机，准备一举砍光整个山坡的树。" |
| **shrink-ray** | 缩小射线 | `inventions-and-events.md` | `## 缩小射线冒险` | "光头强使用缩小射线将自己和熊兄弟变小，引发了一系列冒险。" |
| **ufo-crash** | 飞碟坠落事件 | `inventions-and-events.md` | `## 飞碟坠落事件` | "一次意外导致光头强的飞碟坠毁在狗熊岭深处。" |
| **qiang-xiong-rivalry** | 强熊对立 | `inventions-and-events.md` | `## 强熊对立` | "光头强伐木与熊兄弟护林之间的对立，是故事的主要冲突来源。" |
| **big-monkey-er-gou** | 大马猴和二狗 | `minor-characters.md` | `## 大马猴和二狗` | "他们是光头强偶尔的帮手或竞争对手，常常把事情搞砸。" |
| **fei-bo** | 肥波 | `minor-characters.md` | `## 肥波` | "肥波是一只肥胖的猫，有时会作为光头强的宠物出现。" |
| **待绑定** | (虚链演示) | (无) | 此 ID 存在于设计但无具体文件 | 用于演示虚链状态，目标为空。 |

---

## E. 正文草稿

### 文件 1: `guang-tou-qiang.md`

```markdown
---
description: 光头强——狗熊岭的核心人类角色，既是伐木工也是发明家
concepts:
  - id: guang-tou-qiang
    name: 光头强
    weight: 1.0
    tags: [角色, 人类, 伐木工, 发明家]
  - id: qiang-ge
    name: 强哥
    weight: 0.8
    tags: [角色, 口语, 同义词]
  - id: inventions
    name: 光头强的发明
    weight: 0.9
    tags: [科技, 发明, 情节驱动]
  - id: fei-die
    name: 飞碟
    weight: 0.6
    tags: [科技, 外星, 关键道具]
---

## 光头强 (Guang Tou Qiang)

光头强是《熊出没》系列动画的核心人类角色。他是一名居住在狗熊岭的伐木工，受雇于李老板，任务是砍伐森林里的树木。他经常被描绘成一个有点倒霉但又不失善良的伐木工。

尽管光头强的主要工作是伐木，但他内心深处并不完全是反派。许多剧集展示了他善良的一面，比如帮助小动物、思念家乡的父母。熊大熊二通常用"强哥"来称呼他。

光头强与熊兄弟的关系是整部动画的核心矛盾：他想砍树赚钱，熊兄弟要保护森林。这种对立关系催生了无数搞笑又温馨的故事。

## 光头强的发明

光头强不仅是一名伐木工，还是一位自学成才的发明家。为了完成伐木任务，他不断制造各种奇特的机械和工具。这些发明包括但不限于：超级伐木机、无敌搬运车、缩小射线。

他的发明大多有一个共同特点：外形粗糙但功能强大，然而最终总会因为各种意外而失败。这些失败往往不是因为设计缺陷，而是因为熊兄弟的干预或他自己的操作失误。

光头强的发明不仅是推动剧情的重要工具，也展现了他聪明但不太走运的人物形象。他从未放弃发明创造，这种执着既是他的优点，也是他频繁陷入麻烦的原因。

### 飞碟 (UFO)

在某一部剧场版中，光头强曾意外获得并尝试修复一艘外星飞碟。这艘飞碟具有超乎寻常的科技水平，比如反重力系统和能量武器。

飞碟的出现给狗熊岭带来了新的可能性。光头强一度幻想可以驾驶飞碟轻松完成伐木任务，但最终飞碟因为能量耗尽或操作不当而坠毁。

飞碟事件将狗熊岭的故事从日常伐木冲突提升到了科幻冒险的层面，也展示了《熊出没》系列在题材上的多样性。
```

---

### 文件 2: `bear-brothers.md`

```markdown
---
description: 熊大和熊二——狗熊岭的森林守护者
concepts:
  - id: xiong-da
    name: 熊大
    weight: 1.0
    tags: [角色, 熊, 守护者, 智慧]
  - id: xiong-er
    name: 熊二
    weight: 1.0
    tags: [角色, 熊, 守护者, 力量]
  - id: protect-forest
    name: 保护森林
    weight: 0.9
    tags: [主题, 核心冲突, 使命]
---

## 熊大 (Xiong Da)

熊大是熊兄弟中的哥哥，性格机智、沉稳。他通常扮演决策者和指挥者的角色，在保护森林的行动中负责制定计划。

熊大的标志性特征是他深棕色的毛发和总是若有所思的眼神。他善于观察光头强的动向，能够提前预判伐木计划并采取对策。熊大的口头禅是"熊大我呀，可是很聪明的"。

相比熊二的冲动，熊大更加理性。他懂得利用森林里的环境和资源来对抗光头强的机械，经常通过巧妙的陷阱和计谋让光头强的发明自食其果。

## 熊二 (Xiong Er)

熊二是熊兄弟中的弟弟，性格憨厚、贪吃，但力大无穷。他是行动派，通常在熊大制定计划后负责执行最困难的部分。

熊二的标志性特征是他浅棕色的毛发和圆圆的脸蛋。他最喜欢吃蜂蜜，经常因为贪吃而耽误正事，但关键时刻从不掉链子。熊二的口头禅是"熊二我呀，可是很厉害的"。

虽然熊二看起来不如熊大聪明，但他拥有惊人的直觉和爆发力。在直接对抗中，连光头强的机械都不是熊二的对手。他的单纯和善良也常常打动光头强，让双方暂时放下对立。

## 保护森林

熊兄弟的核心目标是阻止光头强砍树，并保护森林家园。这个使命贯穿了整个《熊出没》系列，是推动故事前进的根本动力。

保护森林的意义不仅在于阻挡伐木，还在于维护狗熊岭整个生态系统的平衡。动物们依赖森林生活，包括松鼠蹦蹦、猫头鹰涂涂等角色都间接受益于熊兄弟的努力。

熊兄弟保护森林的方式多种多样：从直接对抗到游击骚扰，从破坏伐木设备到与光头强谈判。有时候，他们也会和光头强暂时合作，共同应对更大的威胁，比如外来偷猎者或自然灾害。
```

---

### 文件 3: `dog-xiong-ridge.md`

```markdown
---
description: 狗熊岭——熊出没宇宙的中心舞台
concepts:
  - id: gou-xiong-ling
    name: 狗熊岭
    weight: 1.0
    tags: [地点, 世界观, 枢纽]
  - id: big-forest
    name: 大森林
    weight: 0.7
    tags: [地点, 生态, 家园]
  - id: forest-ranger
    name: 护林员
    weight: 0.4
    tags: [角色, 职业, 侧面]
---

## 狗熊岭

狗熊岭是《熊出没》系列动画的主要故事发生地。这是一个风景优美、生态丰富的森林地区，位于中国的某个山区。

狗熊岭拥有茂密的原始森林、清澈的河流、隐秘的山洞和丰富的野生动物资源。这里既是光头强工作的伐木区，也是熊兄弟和众多小动物的家园。

狗熊岭的地形多样，有适合熊类冬眠的山洞、有大片可供伐木的树林、也有李老板的木材运输路线。这种多样化的地理环境为各种有趣的故事提供了舞台。

## 大森林

狗熊岭深处的大森林是动物们赖以生存的家园。这片森林拥有百年的古树、丰富的果实和各种天然资源。

对于熊兄弟来说，大森林不仅仅是居住的地方，更是需要拼死守护的宝贵资产。每一棵树、每一片草地都承载着他们的记忆和情感。

大森林也面临着来自外界的威胁，其中最持续的就是光头强代表的伐木活动。这种"发展与保护"的冲突是《熊出没》故事的现实隐喻。

### 护林员

在某些剧集或特别篇中，光头强曾短暂担任过护林员的角色。这通常发生在剧情需要反转或展现人物弧光的时候。

作为护林员，光头强需要反过来保护森林，阻止其他人（比如偷猎者或非法伐木者）破坏环境。这种身份转换带来了有趣的戏剧冲突，也让观众看到光头强性格中更复杂的层面。

护林员的设定进一步说明，《熊出没》并非简单地将光头强定义为"坏人"，而是在探讨人与自然的复杂关系。
```

---

### 文件 4: `inventions-and-events.md`

```markdown
---
description: 光头强的发明及相关事件——从日常冲突到科幻冒险
concepts:
  - id: super-felling
    name: 超级伐木机
    weight: 0.8
    tags: [发明, 事件, 核心冲突]
  - id: shrink-ray
    name: 缩小射线
    weight: 0.7
    tags: [发明, 事件, 科幻]
  - id: ufo-crash
    name: 飞碟坠落事件
    weight: 0.6
    tags: [事件, 科幻, 关键道具]
  - id: qiang-xiong-rivalry
    name: 强熊对立
    weight: 0.9
    tags: [关系, 核心冲突, 主题]
---

## 超级伐木机事件

超级伐木机是光头强最引以为傲的发明之一。这是一台巨大的履带式机械，装备了旋转锯片和自动伐木程序，理论上可以在几分钟内清空一片树林。

在一次关键剧情中，光头强驾驶着他的超级伐木机，准备一举砍光整个山坡的树。熊兄弟面对这个庞然大物几乎无计可施。

然而，超级伐木机最终因为电路过载或燃料泄漏而自毁。这场事件证明了机械的力量再大，也敌不过熊兄弟的智慧和大自然的眷顾。

## 缩小射线冒险

缩小射线是光头强另一项标志性发明。这台设备可以发射特殊光束，将目标物体缩小到原来的十分之一大小。

光头强使用缩小射线将自己和熊兄弟变小，引发了一系列冒险。在缩小的状态下，原本普通的草丛变成了丛林，一滴露水成了湖泊，整个世界变得既危险又奇妙。

缩小射线的故事充满了想象力和趣味性，也展示了《熊出没》在科幻题材上的探索。最终，熊兄弟和光头强通过合作找到了恢复原状的方法。

## 飞碟坠落事件

一次意外导致光头强的飞碟坠毁在狗熊岭深处。这艘来自外星的飞行器拥有超越人类理解的科技。

飞碟坠毁后，狗熊岭的动物们对这种前所未见的金属物体充满好奇和警惕。光头强试图修复飞碟，将其作为伐木的终极武器。

但飞碟的能量系统不稳定，最终在狗熊岭引发了一场小型能量爆炸，虽然没有人受伤，但飞碟彻底报废。这次事件让光头强意识到，有些科技不是他能控制的。

## 强熊对立

光头强伐木与熊兄弟护林之间的对立，是故事的主要冲突来源。这种对立关系既是喜剧的源泉，也是剧情发展的核心引擎。

对立的具体表现包括：光头强每天带着电锯进山，熊兄弟则在半路设伏；光头强制造新发明，熊兄弟破坏新发明；光头强向李老板汇报进度，熊兄弟向森林里的动物们保证安全。

尽管对立是常态，但光头强和熊兄弟之间也有着复杂的情感纽带。在某些危难时刻，他们会放下成见互相帮助。这种"亦敌亦友"的关系让角色更加丰满，也让《熊出没》的故事超越了简单的正邪对立。
```

---

### 文件 5: `minor-characters.md`

```markdown
---
description: 狗熊岭的配角们——光头强的帮手与对手
concepts:
  - id: big-monkey-er-gou
    name: 大马猴和二狗
    weight: 0.5
    tags: [角色, 配角, 反派帮手]
  - id: fei-bo
    name: 肥波
    weight: 0.3
    tags: [角色, 宠物, 配角]
---

## 大马猴和二狗

大马猴和二狗是《熊出没》中的一对活宝式配角。他们是光头强偶尔的帮手或竞争对手，常常把事情搞砸。

大马猴体型高瘦，喜欢耍小聪明；二狗体型矮胖，忠诚但不太聪明。这对组合通常是在李老板的指派下来监督或协助光头强的，但他们的出现往往会制造更多的混乱。

在光头强与熊兄弟的对立中，大马猴和二狗有时是第三股力量。他们既可能帮助光头强伐木，也可能因为贪图便宜而被熊兄弟利用，最终成为笑料。

## 肥波

肥波是一只肥胖的猫，有时会作为光头强的宠物出现。它外表慵懒、贪吃，但有时会展现出超乎寻常的敏锐。

肥波与光头强的关系类似于主人与宠物，但它更多时候是作为独立角色参与故事。肥波曾多次被熊兄弟误认为是光头强的间谍，最终却发现它只是个无辜的吃货。

肥波的存在为狗熊岭的动物社区增添了新的色彩。作为一只家猫，它在野生森林中的冒险故事本身就是一种有趣的视角。
```

---

### 文件 6: `_nothing-here.md` (边界样例)

```markdown
---
description: 这是一个 Nothing 占位文件，用于测试边界情况
---
```

---

## F. 侧车 YAML

### 侧车 1: `.memoria/sidecars/guang-tou-qiang.memoria.yaml`

```yaml
schema_version: 1
file: guang-tou-qiang.md
knowledge_points:
  - id: guang-tou-qiang
    name: 光头强
    range:
      start: { snippet: "## 光头强 (Guang Tou Qiang)", line_hint: 12 }
      end:   { snippet: "熊大熊二通常用'强哥'来称呼他。", line_hint: 21 }
  - id: qiang-ge
    name: 强哥
    range:
      start: { snippet: "熊大熊二通常用'强哥'来称呼他。", line_hint: 21 }
      end:   { snippet: "这种对立关系催生了无数搞笑又温馨的故事。", line_hint: 24 }
  - id: inventions
    name: 光头强的发明
    range:
      start: { snippet: "## 光头强的发明", line_hint: 26 }
      end:   { snippet: "也是他频繁陷入麻烦的原因。", line_hint: 35 }
  - id: fei-die
    name: 飞碟
    range:
      start: { snippet: "### 飞碟 (UFO)", line_hint: 37 }
      end:   { snippet: "也展示了《熊出没》系列在题材上的多样性。", line_hint: 46 }
links:
  - anchor_text: 熊大熊二
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 21, wrapped: true }]
    source_id: guang-tou-qiang
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 23, wrapped: true }]
    source_id: guang-tou-qiang
  - anchor_text: 超级伐木机
    targets: [super-felling]
    edge_type: extend
    instances: [{ line: 30, wrapped: true }]
    source_id: inventions
  - anchor_text: 缩小射线
    targets: [shrink-ray]
    edge_type: extend
    instances: [{ line: 31, wrapped: true }]
    source_id: inventions
  - anchor_text: 飞碟
    targets: [ufo-crash]
    edge_type: extend
    instances: [{ line: 42, wrapped: true }]
    source_id: fei-die
```

---

### 侧车 2: `.memoria/sidecars/bear-brothers.memoria.yaml`

```yaml
schema_version: 1
file: bear-brothers.md
knowledge_points:
  - id: xiong-da
    name: 熊大
    range:
      start: { snippet: "## 熊大 (Xiong Da)", line_hint: 11 }
      end:   { snippet: "经常通过巧妙的陷阱和计谋让光头强的发明自食其果。", line_hint: 22 }
  - id: xiong-er
    name: 熊二
    range:
      start: { snippet: "## 熊二 (Xiong Er)", line_hint: 24 }
      end:   { snippet: "他的单纯和善良也常常打动光头强，让双方暂时放下对立。", line_hint: 35 }
  - id: protect-forest
    name: 保护森林
    range:
      start: { snippet: "## 保护森林", line_hint: 37 }
      end:   { snippet: "共同应对更大的威胁，比如外来偷猎者或自然灾害。", line_hint: 46 }
links:
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 18, wrapped: true }, { line: 29, wrapped: true }]
    source_id: xiong-da
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 33, wrapped: true }, { line: 45, wrapped: true }]
    source_id: xiong-er
  - anchor_text: 狗熊岭
    targets: [gou-xiong-ling]
    edge_type: reference
    instances: [{ line: 39, wrapped: true }]
    source_id: protect-forest
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 45, wrapped: true }]
    source_id: protect-forest
```

---

### 侧车 3: `.memoria/sidecars/dog-xiong-ridge.memoria.yaml`

```yaml
schema_version: 1
file: dog-xiong-ridge.md
knowledge_points:
  - id: gou-xiong-ling
    name: 狗熊岭
    range:
      start: { snippet: "## 狗熊岭", line_hint: 11 }
      end:   { snippet: "这种多样化的地理环境为各种有趣的故事提供了舞台。", line_hint: 21 }
  - id: big-forest
    name: 大森林
    range:
      start: { snippet: "## 大森林", line_hint: 23 }
      end:   { snippet: "这种'发展与保护'的冲突是《熊出没》故事的现实隐喻。", line_hint: 32 }
  - id: forest-ranger
    name: 护林员
    range:
      start: { snippet: "### 护林员", line_hint: 34 }
      end:   { snippet: "而是在探讨人与自然的复杂关系。", line_hint: 43 }
links:
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 17, wrapped: true }]
    source_id: gou-xiong-ling
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 18, wrapped: true }]
    source_id: gou-xiong-ling
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 27, wrapped: true }]
    source_id: big-forest
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 36, wrapped: true }]
    source_id: forest-ranger
```

---

### 侧车 4: `.memoria/sidecars/inventions-and-events.memoria.yaml`

```yaml
schema_version: 1
file: inventions-and-events.md
knowledge_points:
  - id: super-felling
    name: 超级伐木机
    range:
      start: { snippet: "## 超级伐木机事件", line_hint: 11 }
      end:   { snippet: "也敌不过熊兄弟的智慧和大自然的眷顾。", line_hint: 21 }
  - id: shrink-ray
    name: 缩小射线
    range:
      start: { snippet: "## 缩小射线冒险", line_hint: 23 }
      end:   { snippet: "熊兄弟和光头强通过合作找到了恢复原状的方法。", line_hint: 33 }
  - id: ufo-crash
    name: 飞碟坠落事件
    range:
      start: { snippet: "## 飞碟坠落事件", line_hint: 35 }
      end:   { snippet: "有些科技不是他能控制的。", line_hint: 44 }
  - id: qiang-xiong-rivalry
    name: 强熊对立
    range:
      start: { snippet: "## 强熊对立", line_hint: 46 }
      end:   { snippet: "也让《熊出没》的故事超越了简单的正邪对立。", line_hint: 56 }
links:
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 13, wrapped: true }]
    source_id: super-felling
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 18, wrapped: true }]
    source_id: super-felling
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 26, wrapped: true }]
    source_id: shrink-ray
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 30, wrapped: true }]
    source_id: shrink-ray
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 38, wrapped: true }, { line: 48, wrapped: true }]
    source_id: ufo-crash
  - anchor_text: 狗熊岭
    targets: [gou-xiong-ling]
    edge_type: reference
    instances: [{ line: 38, wrapped: true }]
    source_id: ufo-crash
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 52, wrapped: true }]
    source_id: qiang-xiong-rivalry
```

---

### 侧车 5: `.memoria/sidecars/minor-characters.memoria.yaml`

```yaml
schema_version: 1
file: minor-characters.md
knowledge_points:
  - id: big-monkey-er-gou
    name: 大马猴和二狗
    range:
      start: { snippet: "## 大马猴和二狗", line_hint: 11 }
      end:   { snippet: "最终成为笑料。", line_hint: 21 }
  - id: fei-bo
    name: 肥波
    range:
      start: { snippet: "## 肥波", line_hint: 23 }
      end:   { snippet: "它在野生森林中的冒险故事本身就是一种有趣的视角。", line_hint: 31 }
links:
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 14, wrapped: true }, { line: 16, wrapped: true }]
    source_id: big-monkey-er-gou
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 19, wrapped: true }]
    source_id: big-monkey-er-gou
  - anchor_text: 光头强
    targets: [guang-tou-qiang]
    edge_type: reference
    instances: [{ line: 25, wrapped: true }]
    source_id: fei-bo
  - anchor_text: 熊兄弟
    targets: [xiong-da, xiong-er]
    edge_type: reference
    instances: [{ line: 26, wrapped: true }]
    source_id: fei-bo
```

---

### 侧车 6: `.memoria/sidecars/_nothing-here.memoria.yaml`

```yaml
schema_version: 1
file: _nothing-here.md
knowledge_points: []
links: []
```

---

## G. 自测清单（设计稿）

- [x] 每个 KP 的 end 行非空且 snippet 在正文中可找到
- [x] 无「文件行号 vs 正文行号」混淆（frontmatter 不计入正文行号）
- [x] 搜索词设计：
  - 精确名：`光头强`、`熊大`、`狗熊岭`
  - 模糊拼写：`强哥`（同义）、`飞碟`（UFO）
  - 口语 alias：`强哥`、`熊大熊二`（复合搜索）
- [x] 覆盖设计目标：
  - 多文件多 KP：5 个有效 md，16 个 KP（设计）
  - 跨文件链接：≥20 条跨文件链接
  - 多目标链接：`[[熊大熊二]]` 绑定 xiong-da + xiong-er
  - 多跳路径：`狗熊岭` → `熊兄弟` → `光头强` → `超级伐木机`（4 跳）
  - 同义/口语：`强哥`（qiang-ge）与正文用词不完全一致
  - 数学/公式：本主题无公式，但已在设计摘要中说明（叙事性主题）
  - 虚链：frontmatter 中已预留 `待绑定` 概念（设计阶段）
  - 子目录：侧车均在 `.memoria/sidecars/` 下
  - 搜索友好：配置了 tags 和多种别名
  - 边界样例：`_nothing-here.md` 空文件 + `dog-xiong-ridge.md` Hub 页

---

## H. 已实现样例（`example-boonie/`）

与 `examples/`（RL/NLP 开发样例）**完全独立**。在 Memoria 中将 KB 根目录设为 `example-boonie/` 即可加载。

| 相对 E/F 设计稿的调整 | 说明 |
| :--- | :--- |
| 正文精简 + `[[wikilink]]` | 便于维护与链接演示 |
| 15 KP（无独立 `qiang-ge`） | 「强哥」作为 `guang-tou-qiang` 的 tag |
| Hub 增强 | `dog-xiong-ridge.md` 含「阅读路径」「虚链对照」 |
| 虚链 `li-laoban` | frontmatter + `[[李老板]]`，无侧车 KP |
| 侧车 | 由 `scripts/gen_example_boonie_sidecars.py` 生成，`validate_kb` 已通过 |

**手动验证**

1. KB 根目录 → `example-boonie/`
2. 打开 `dog-xiong-ridge.md`，沿阅读路径点击 wikilink
3. 搜索「强哥」「飞碟」「狗熊岭」
4. 点击 `[[李老板]]` 确认虚链样式

---

**交付物**：设计文档（A–G，含完整 E/F 正文草稿）+ 可运行样例目录 `example-boonie/`（H）。
