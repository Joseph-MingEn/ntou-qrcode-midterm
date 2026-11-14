"""重現報告中的過大 Logo 實驗；會覆寫指定的實驗圖片。"""
from pathlib import Path
from PIL import Image, ImageDraw
import cv2

root = Path(__file__).resolve().parents[1]
image = Image.open(root / 'images/compare/qr_H.png').convert('RGB')
side = round(image.width * .70)
start = (image.width-side)//2
draw = ImageDraw.Draw(image)
draw.rectangle((start, start, start+side, start+side), fill='white')
draw.text((start+10, start+10), 'LOGO', fill='black')
out = root / 'images/qr_logo_too_large.png'
image.save(out)
value, points, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(out)))
print(f'圖片={image.width}x{image.height}, 遮蓋={side}x{side}, 解碼={value!r}, 找到定位={points is not None}')
