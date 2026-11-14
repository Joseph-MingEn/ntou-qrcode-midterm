from pathlib import Path
from PIL import Image, ImageDraw
import cv2

folder = Path("results/本次實測_20261113_0033")
source = folder / "levels/qr_H.png"
target = folder / "qr_過大遮擋.png"
with Image.open(source) as original:
    image = original.convert("RGB")
side = round(image.width * 0.70)
start = (image.width - side) // 2
draw = ImageDraw.Draw(image)
draw.rectangle((start, start, start + side - 1, start + side - 1), fill="white")
draw.text((start + 10, start + 10), "LOGO", fill="black")
image.save(target)
decoded, points, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(target)))
print(f"來源：{source}")
print(f"圖片：{image.width}×{image.height} 像素；白色遮擋：{side}×{side} 像素")
print(f"找到定位點：{points is not None}；解碼內容：{decoded!r}")
print(f"結果：{target}")
