# agent 会话栏宽度探针（0.4.7 任务 3）

- 开始：2026-10-23T05:19:08.111079+00:00
- 用时：32.3s
- 结论：✅ PASS

| 检查 | 结果 | 详情 |
|---|---|---|
| G0-dock-present | ✅ | `{"rem": 16, "dock": 352, "dockInline": "22rem", "dockCollapsed": false, "dockAutoHidden": false, "dockMaxWidth": "100%", "dockMinWidth": "256px", "sidebar": 280, "content": 624, "main": 1256, "win": {"w": 1256, "h": 774}}` |
| A1-wide-exceeds-34rem | ✅ | `{"gotPx": 800, "gotRem": 50, "oldCapPx": 544, "mode": "testHook", "maxWidth": "100%", "win": {"w": 1920, "h": 1080}}` |
| A2-content-kept-360 | ✅ | `{"content": 840, "main": 1920, "sidebar": 280}` |
| A3-narrow-capped-by-available | ✅ | `{"dock": 640, "content": 360, "main": 1280, "win": {"w": 1280, "h": 800}}` |
| A4-very-narrow-safe | ✅ | `{"dock": 260, "collapsed": false, "autoHidden": false, "content": 360, "main": 900, "win": {"w": 900, "h": 700}}` |
| A5-restored-after-resize | ✅ | `{"dock": 960, "gotRem": 60, "content": 680, "autoHidden": false}` |
