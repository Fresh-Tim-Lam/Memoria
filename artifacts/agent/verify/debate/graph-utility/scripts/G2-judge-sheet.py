# -*- coding: utf-8 -*-
"""G2 人判判据表生成（24 条分层抽样；只读 frozen 快照）。

读取 G2-sampling.json，给每条抽样边补上：
  · source/target 的 KP 名、文件、原区间起止行、start snippet（判据者不用翻原文）
输出 `G2-judgment-sheet.md`（判据表模板；每位判据者独立填写）。

Run:  python scripts/G2-judge-sheet.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)
ROUND2 = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'kg-retrieval', 'round2')
FROZEN = os.path.join(ROUND2, 'frozen', '数字通信原理')
SAMPLING = os.path.join(OUT_DIR, 'G2-sampling.json')
OUT = os.path.join(OUT_DIR, 'G2-judgment-sheet.md')

sys.path.insert(0, os.path.join(ROUND2, 'scripts'))
import q1_research_probe as q1  # noqa: E402


def main():
    sampling = json.load(open(SAMPLING, encoding='utf-8'))
    sidecars = os.path.join(FROZEN, '.memoria', 'sidecars')
    kp_meta = {}
    for root, _, files in os.walk(sidecars):
        for fn in files:
            if not fn.endswith('.memoria.yaml'):
                continue
            sc = q1.parse_sidecar(os.path.join(root, fn))
            for kp in sc['kps']:
                kp_meta[kp['id']] = {
                    'file': sc['file'],
                    'name': kp.get('name') or kp['id'],
                    'start_snippet': (kp.get('start') or {}).get('snippet') or '',
                    'start_line': (kp.get('start') or {}).get('line_hint'),
                    'end_line': (kp.get('end') or {}).get('line_hint'),
                }

    lines = []
    lines.append('# G2 · L2 边语义人判表（24 条分层抽样）\n')
    lines.append('> 给判据者：**独立填写，不要互相讨论**。每条约 1 分钟，24 条约 25 分钟（+10 分钟培训）。')
    lines.append('> 你**看不到边的原类型/来源**（盲化）；只凭两端的名称、原文起句与所在章节判断。')
    lines.append('> 谓词定义见 `G2-L2-protocol.md` §1；若拿不准，选「不确定」，不要猜。\n')
    lines.append('## 填写说明\n')
    lines.append('- **Q1 可表述性**：能否用一句有意义的陈述表达这两个知识点之间的关系？（能/不能/不确定）')
    lines.append('- **Q2 谓词**：该关系属于哪个谓词？（组成 / 前置 / 例证 / 对比 / 引用(无断言) / 仅顺序 / 无关系 / 不确定）')
    lines.append('- **Q3 真值**：这句话在给定原文/上下文下是否为真？（真/假/无支撑）')
    lines.append('- **Q4 方向**：若关系成立，箭头方向对吗？（对/反了/不适用）')
    lines.append('- **Q5 去留**：这条边应保留还是删除？（保留/删除/不确定）')
    lines.append('- **Q6 置信度**：你对以上判断的整体把握（1=很低 … 5=很高）')
    lines.append('- 备选理由：一句话写你为什么这么判（可空）\n')
    lines.append('## 判据表（24 条）\n')
    lines.append('| # | 文件 | 起点知识点（原文首句） | 终点知识点（原文首句） | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | 理由 |')
    lines.append('|---|---|---|---|---|---|---|---|---|---|---|')
    for e in sampling['selected']:
        s = kp_meta.get(e['src'], {})
        t = kp_meta.get(e['tgt'], {})
        f = e['file'].split('/')[-1]
        ss = (s.get('start_snippet') or '').replace('\n', ' ')[:80]
        ts = (t.get('start_snippet') or '').replace('\n', ' ')[:80]
        fname = f"`{f}` (L{s.get('start_line')}-{s.get('end_line')})"
        lines.append(f"| **{e['sample_id']}** | {fname} | **{e['src_name']}**<br>{ss} | **{e['tgt_name']}**<br>{ts} |  |  |  |  |  |  |  |")
    lines.append('\n## 判定者信息（每人填自己的）\n')
    lines.append('| 判定者 | 姓名/代号 | 类型（真人/agent 代理） | 日期 | 用时 |')
    lines.append('|---|---|---|---|---|')
    lines.append('| J1 |  |  |  |  |')
    lines.append('| J2 |  |  |  |  |')
    lines.append('| J3（可选） |  |  |  |  |')
    lines.append('\n> agent 代判必须显式标「agent 代理」；一致性系数只作内部参考，不可等同于人判（见 protocol §2.4）。')
    open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('wrote', OUT, 'rows', len(sampling['selected']))


if __name__ == '__main__':
    main()
