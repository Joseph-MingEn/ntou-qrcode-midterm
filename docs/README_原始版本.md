# Python QR Code 導引與本機網站

程式以 `qrcode` / Pillow 產生 PNG，以 OpenCV 解碼；提供四級比較及簡單本機網站。僅對自己的網站或公開合法網址使用。程式執行目錄為本資料夾：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python src/qr_web.py make --url https://www.example.com/ --out images/qr_example.png --level H --label 'Example'
.venv/bin/python src/qr_web.py decode images/qr_example.png --expect https://www.example.com/
.venv/bin/python src/qr_web.py compare --url https://www.example.com/ --out-dir images/compare
.venv/bin/python src/qr_web.py serve --port 8000
```

`make` 會在圖片存檔後立即解碼並核對；解碼不到或不符時結束碼為 1。`compare` 對相同網址製作 L/M/Q/H 圖片並列出實際解碼結果，模組數不含四模組靜區。標籤放在 QR 靜區之外。圖片尺寸包括標籤；檔案大小為 PNG 壓縮後位元組，不只取決於容錯等級。OpenCV 可解碼不代表所有手機或所有條件都能掃描。

`serve` 嘗試自動選擇本機位址，顯示網址並產生 `images/qr_site.png`。手機與電腦需在可互通的同一網路；若顯示 127.0.0.1 或非手機可達位址，查詢電腦目前 Wi-Fi IPv4，指定 `--host-ip 192.168.x.x`（替換為實際值）。此設定不會更改網路或防火牆；校園網路隔離時可試手機熱點。兩台裝置各自掃描，確認網址與內容、按「點擊互動」，保留遮蔽後畫面及手機型號。測試結束按 Ctrl+C 關閉伺服器。

每次 make/decode/compare 與 serve 啟停會留下 `results/qr_模式_*.json` 和 `.md`；伺服器每個 HTTP 請求（含資源、404）另寫 `connections_*.jsonl`，包含時間、來源 IP、瀏覽器 User-Agent、路徑及狀態，未記錄 query。一次掃描可能產生多個請求，IP 也不等於裝置數。日誌含網路資料，交付前自行檢查、局部遮蔽；使用者須確保接入者知悉紀錄。伺服器無登入、加密，不供公開部署或傳送機密。

需完成的實測及證據見 `results/手動測試紀錄.md`、`report/報告.md`。測試證據與學生身分齊全後再依題目命名 ZIP；不要打包 `.venv` 或不必要個資。

## 連線紀錄後台

執行上方 `serve` 後，在**執行程式的同一台電腦**開啟 `http://127.0.0.1:8000/admin`（若改用其他埠號，網址中的埠號也要改）。後台讀取 `results/connections_*.jsonl`，顯示歷次網站請求及首頁載入的統計，並提供首頁篩選與「重新整理」按鈕；清單最多顯示最新 1,000 筆，格式有誤或無法讀取的檔案會顯示提示。請求數包括直接輸入、重整、圖示或預覽，**不等於掃描次數或裝置數**。管理後台只接受本機來源及本機 Host；同一 Wi-Fi 的手機可以開啟導引頁，但不能開啟後台或取得紀錄 API。測試完在執行程式的終端機按 Ctrl+C 關閉。

加入後台的程式版本與既有手機實測版本不同；先前手機實測不能自動證明修改後版本的跨裝置流程。原始連線紀錄及後台畫面可能含 IP、User-Agent 等資訊，對外繳交前請先檢視與遮蔽。

## 中央 Logo

```sh
# 內建中央標記，未指定等級時自動採用 H
.venv/bin/python src/qr_web.py make --url https://www.example.com/ --out images/qr_logo.png --logo --label 'Example'
# 使用自有圖檔作為中央 Logo
.venv/bin/python src/qr_web.py make --url https://www.example.com/ --out images/qr_custom.png --logo ./my_logo.png
```

`--logo` 可省略圖檔路徑而使用內建標記，也可指定自己有權使用的圖片；可與 `--label` 同用。Logo 僅支援 H 等級；明確指定其他等級會報錯。程式不覆寫原 Logo 圖片，並會對輸出的 PNG 解碼比對；若無法解碼或與網址不符，回傳非零。OpenCV 解碼成功不保證每台手機、每種顯示尺寸均能讀取，仍須手機實際掃描。圖內網址指向本機網站時，應使用目前服務啟動時顯示的網址，網路變更後重新產生。

後台「挑選時段」可分別設定開始與結束日期時間，按「套用時段」後，摘要與紀錄只計算該範圍；單側留空代表該側不限。時間依目前瀏覽器所用的電腦時區解讀，結束時間包含選定的整分鐘，例如結束 23:32 會包含至 23:32:59 的紀錄。按「重新整理」保留已套用時段，按「清除時段」回到全部時間。篩選會先查閱所有歷史紀錄，再擷取最新 1,000 筆，避免較舊時段被最新紀錄的數量上限排除。

## 設備點名

啟動服務後，訪客開啟 QR Code 導引頁，在「設備點名」輸入自訂設備型號並按「送出點名」。成功後頁面顯示該型號及伺服器看到的來源 IP；型號可修改後再次送出，每次送出都是一筆新紀錄。

在本機開啟 `http://127.0.0.1:8000/admin`，於「設備點名紀錄」查看時間、型號與 IP。既有的「挑選時段」和「重新整理」也適用於點名清單；清單最多顯示最新 1,000 筆。紀錄儲存於 `results/checkins.jsonl`，與連線日誌分開，服務重啟後保留，請在分享或繳交前檢查並移除不必要的個資。設備型號由訪客自行填寫，IP 可能因共用網路等因素重複，點名筆數不等於不同裝置數。

## 使用體驗問卷

訪客在導引頁的「使用體驗問卷」選擇滿意度，並可自行填寫最多 500 字的建議，再按「送出問卷」。在本機後台的「問卷回覆」查看送出時間、滿意度與建議；既有的挑選時段與重新整理也適用於問卷。問卷保存在 `results/surveys.jsonl`，與點名紀錄分開，重啟後保留；分享或繳交前請檢查是否包含不必要的個人資訊。問卷填答次數不代表掃描或裝置數。
