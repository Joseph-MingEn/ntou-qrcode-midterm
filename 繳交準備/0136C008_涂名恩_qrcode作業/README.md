# QR Code 網址與本機互動網頁

學號：0136C008　姓名：涂名恩

## 檔案說明

- `src/qr_web.py`：產生與解碼 QR Code、比較容錯等級，以及啟動本機網站。
- `site/index.html`：手機導引頁，包含互動按鈕、設備點名及問卷。
- `src/admin.html`：本機管理後台，查詢連線、點名與問卷紀錄。
- `images/`：本次實測的中央 Logo、本機網站及 L／M／Q／H 等級 QR Code。
- `report/`：Word 實作報告。
- `results/`：報告提及的本次圖片、執行結果，以及所述時段的連線、點名與問卷紀錄。紀錄按時段篩選，保留所選原始資料列；後台統計以此資料夾所收錄的紀錄為準。
- `tests/`：自動測試程式。

## 安裝與使用

請在本資料夾執行以下指令（macOS／Linux）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/qr_web.py --help
.venv/bin/python src/qr_web.py serve --port 8000
```

啟動後，終端機會顯示網站網址及 QR Code 路徑；手機須和電腦連上可互通的網路。若自動選出的位址不是手機可使用的位址，請加上 `--host-ip 電腦的區域網路IP`。本機後台為 http://127.0.0.1:8000/admin，結束服務請按 Ctrl+C。

產生與解碼圖片（將網址換成要測試的 HTTP 或 HTTPS 網址）：

```sh
.venv/bin/python src/qr_web.py make --url 'http://127.0.0.1:8000/' --out images/qr_new.png --level H --logo --label 'Local website'
.venv/bin/python src/qr_web.py decode images/qr_new.png --expect 'http://127.0.0.1:8000/'
.venv/bin/python src/qr_web.py compare --url 'http://127.0.0.1:8000/' --out-dir images/compare
.venv/bin/python -m unittest discover -s tests -v
```

範例中的 `127.0.0.1` 僅供電腦本機測試；若要讓手機掃描，請使用服務啟動時顯示的可連線 IP。既有圖片記錄當時的 `192.168.0.240:8000`；網路位址變更時，需重新產生供目前網路使用的 QR Code。執行程式會新增結果至 `results/`。
