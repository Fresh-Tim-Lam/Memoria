"""裁剪图片（bundled Pillow）；用法：python crop.py <src> <dst> x y w h"""

import sys

from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
x, y, w, h = (int(v) for v in sys.argv[3:7])
img = Image.open(src)
x = max(0, x)
y = max(0, y)
img.crop((x, y, x + w, y + h)).save(dst)
print(f"ok {dst}")
