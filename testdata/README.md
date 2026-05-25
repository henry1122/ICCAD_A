# 測資說明

## 檔案結構

```
testdata/
├── design/          # 閘級 Verilog 網表
│   ├── top.v        # 較完整測資：含 path 與 _gc__ buffer
│   └── simple.v     # 最簡測資：兩層邏輯
├── test_input.txt   # 完整流程測試（貼到 stdin 或重導向）
├── test_simple.txt  # 簡短流程測試
└── README.md        # 本說明
```

## 測資內容

### top.v
- **輸入**: in0, in1, clk, rst_n  
- **輸出**: out0, out1  
- **邏輯**: in0 → NOT → n1 → AND(in1) → n2 → BUF → out0；in0 → U_gc__buf0 → out1  
- **用途**: 測 max depth（in0 到 out0 深度 3）、list_gates（buf + _gc__）、replace_buffers_with_and、write

### simple.v
- **輸入**: in0, in1, in2  
- **輸出**: out0  
- **邏輯**: (in0 & in1) | in2 → out0（兩層）  
- **用途**: 快速測 read / max_depth / write

## 如何跑測試

### 方法一：PowerShell 用管線（推薦）

PowerShell **不支援** `<` 重導向，請用 **管線** 把檔案內容傳給程式：

```powershell
cd C:\Users\User\Desktop\ICCAD_A
Get-Content testdata\test_input.txt | python main.py -config config.yaml
```

或簡單版：

```powershell
Get-Content testdata\test_simple.txt | python main.py -config config.yaml
```

### 方法一 B：用 CMD 重導向

若用「命令提示字元」(cmd)，可以用 `<`：

```cmd
cd C:\Users\User\Desktop\ICCAD_A
python main.py -config config.yaml < testdata\test_input.txt
```

程式會依序處理每一行請求，stdout 會出現 `#RESPONSE` / `#END`，並會產生：
- `case1.log` 或 `simple.log`（在當前目錄）
- `testdata/case1_out.v` 或 `testdata/simple_out.v`（若請求中有寫出網表）

### 方法二：手動貼一行一行

1. 執行：`python main.py -config config.yaml`
2. 貼上第一行（開始 testcase）後按 Enter
3. 看到 `#END 1` 後，貼上下一行（例如 Load design...）
4. 重複直到最後一行
5. 結束：Ctrl+Z（Windows）或 Ctrl+D（Linux）或關閉終端

### 方法三：從 design 子目錄讀檔

若希望「從當前目錄」讀 design，可先把 `top.v` 複製到專案根目錄，或把請求改成：

```
Read in design from top.v
```
（不加 directory，則會從執行時的當前目錄找 `top.v`。執行時請在 `ICCAD_A` 下，且先把 `testdata/design/top.v` 複製到 `ICCAD_A/top.v`，或改用 `testdata/design/top.v` 當路徑。）

使用 `test_input.txt` 時，已指定 `directory testdata/design/`，所以會讀 `testdata/design/top.v`，無需複製。

### 離線測試（不需 API key）

規則式解析器會先處理常見指令，可用下列指令驗證（不呼叫 LLM）：

```powershell
python testdata/test_rules_offline.py test_input
python testdata/test_rules_offline.py test_weird
```

`test_weird.txt` 含多餘空白、引號、口語化用詞等邊界測試。

### 進階測試（Section 4.3 變換）

```powershell
python testdata/test_rules_offline.py test_advanced
Get-Content testdata\test_advanced.txt | python main.py -config config.yaml
```

涵蓋：fanout 查詢/限制、移除 dangling、INV+BUF 合併、cone 深度優化等。
