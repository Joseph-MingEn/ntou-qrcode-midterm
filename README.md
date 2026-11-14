# QR Code 網址產生與本機互動網頁

資料結構期中作業，學號 0136C008，涂名恩。程式可產生 QR Code、使用 OpenCV 解碼驗證、比較 L／M／Q／H 容錯等級，並架設可記錄連線的互動網頁及本機管理後台。

## 專案內容

- `src/qr_web.py`：產生、解碼、比較 QR Code 與啟動伺服器。
- `site/index.html`：設備點名、問卷與互動頁面。
- `src/admin.html`：查詢連線、點名與問卷，可依時段篩選。
- `images/`、`results/`：專案圖片、執行紀錄與實測資料。
- `report/`、`docs/`：歷版報告與設計文件。
- `tests/`：自動測試。
- `繳交準備/`：先前準備的不同繳交版本。
- `繳交檔案/0136C008_涂名恩_qrcode作業/`：最新整理過的繳交資料夾，包含 Word 和 PDF 報告。
- `歷史版本/格式整理前/`：主要程式整理排版前的原始檔。

## 執行方式（macOS／Linux）

在專案目錄執行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/qr_web.py --help
.venv/bin/python src/qr_web.py serve --port 8000
```

啟動後請依終端機顯示的區域網路網址與 QR Code 連線，管理後台位於 `http://127.0.0.1:8000/admin`；按 Ctrl+C 結束。執行期間會在 `results/` 新增紀錄。若偵測到的位址無法供手機使用，可指定 `--host-ip` 為電腦目前的區域網路 IP。

執行自動測試：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

更多產生、解碼及比較指令，請參考 [原始說明](docs/README_原始版本.md) 和 [最新繳交說明](繳交檔案/0136C008_涂名恩_qrcode作業/README.md)。舊圖片記錄當時使用的網址；網路改變後，應重新產生 QR Code。
