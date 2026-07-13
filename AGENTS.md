# my-classroom-tools — 班級工具總專案

## 開始工作前

- 進度與最近決策在 Obsidian：`my-classroom-tools/工作筆記.md`。
- 使用者說「開工」或要接續時，使用 `$classroom-startup`。
- 使用者說「收工」或要同步進度時，使用 `$classroom-shutdown`。

## 四個家

- Google Drive 工作區：`G:\我的雲端硬碟\my-classroom-tools`
- GitHub：`annyliu3264-droid/my-classroom-tools`
- Obsidian：`my-classroom-tools/工作筆記.md`
- Firebase：`my-teaching-tools-ee2b7`

## 工作方式

- 新工具放在 `tools/<tool-name>/`，資料夾使用英文小寫加連字號。
- 每個工具提供 README，說明用途、資料欄位、部署網址與安全規則。
- 修改後先驗證再 commit，commit 說明做了什麼與為什麼。
- 不自動 pull、不強制 push、不覆蓋使用者未提交變更。

## 安全規則

- 學生資料一律去識別化，不存姓名、電子信箱或可直接識別資料。
- 每個 Firestore 集合必須有最小權限 Security Rules。
- 不提交 `.env`、token、密碼、Admin SDK 憑證或服務帳戶金鑰。
- Firebase Web Config 可公開，但不得以它取代 Security Rules。

## 工具清單

- `firebase-word-cloud`：Firebase 即時課堂文字雲（已獨立部署）。
