# Dev annotation board

å¼€å‘æ€ä¸“ç”¨ï¼šç»™ Memoria é¡µé¢æ³¨å…¥ä¸€ä¸ªã€Œç‚¹é€‰å…ƒç´  â†’ ç¼–è¾‘æ–‡å­—/æ‰¹æ³¨ â†’ å¯¼å‡º JSONLã€çš„æ‰¹æ³¨æ¿ã€‚**ä¸å±žäºŽäº§å“æž„å»º**ï¼Œä¸æ”¹ `src/**`ã€‚

## å¯åŠ¨ï¼ˆWindows / å½“å‰ demoï¼‰

```powershell
cd D:\AAA_Jupyter\Memoria
$env:MEMORIA_MODE='dev'
$env:MEMORIA_KB='D:\AAA_Jupyter\Memoria\artifacts\demo-kb\corpus-pilot'
python tools\dev-annotator\run_with_remote_debug.py
```

å¦å¼€ä¸€ä¸ªç»ˆç«¯æ³¨å…¥ï¼š

```powershell
python tools\dev-annotator\inject_via_cdp.py 9222
```

- æ‰¹æ³¨æ¿åœ¨å³ä¸‹è§’ï¼›æŒ‰ **Alt+Shift+A** å¼€å…³ç‚¹é€‰æ¨¡å¼ï¼›
- ç‚¹é€‰ä»»æ„å…ƒç´  â†’ è‡ªåŠ¨å¡« CSS selector / åŽŸæ–‡ï¼Œå¯ç¼–è¾‘æ‰¹æ³¨ä¸ŽåŽŸæ–‡ï¼›
- **å¯¼å‡º JSONL** ä¼šä¸‹è½½ `memoria-annotations.jsonl`ï¼ˆå¯ç›´æŽ¥å‘å›žï¼‰ï¼›
- æ•°æ®åŒæ—¶ä¿å­˜åœ¨ localStorage `memoria.dev.annotations.v1`ï¼›
- è¿™æ˜¯ dev-only æ³¨å…¥ï¼šWebView2 è¿œç¨‹è°ƒè¯•ç«¯å£ + CDPï¼Œä¸å†™äº§å“ä»£ç ã€ä¸å†™ç”¨æˆ·åº“ã€‚

## ç¤ºä¾‹åº“

`scripts/corpus/build_demo_kb.py` ä¼šä»Ž pilot çš„ Tier-A ç« èŠ‚ + 50 KP/30 è¾¹å€™é€‰ç”Ÿæˆï¼š

```
artifacts/demo-kb/corpus-pilot/
  chapter1.md
  .memoria/sidecars/chapter1.memoria.yaml
  .memoria/manifest.yaml
```

åªç”¨äºŽçœ‹æ•ˆæžœï¼Œä¸æ˜¯ goldï¼Œä¹Ÿä¸è¿›å‘å¸ƒåŒ…ã€‚

