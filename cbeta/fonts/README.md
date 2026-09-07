# CBETA 補充字型（CBETA Supplement Font）

## 關於本字型

本字型為 CBETA（財團法人佛教電子佛典基金會）從公開字型中抽取之子集合字型，僅包含 CBETA 電子佛典集成中所需的缺字字元，以優化檔案大小與使用效能。

目前收錄來源字型包括：

- [全宋體 FSung](https://fgwang.blogspot.com/)


## 使用授權

本子集合字型由 CBETA 免費提供，供非營利及個人研究使用。

各來源字型之著作權歸原作者所有，若有其他用途需求，請參考各字型原始授權規定：

- 全宋體：https://fgwang.blogspot.com/


## 網路字型服務
連結：https://cbeta-org.github.io/cbeta-fonts/CBETASupplement.woff2

---

# 悉曇字型（Ranjana / Siddam，RJ 缺字用）

## 用途

`Ranjana.ttf`、`Siddam.ttf` 为悉昙体装饰中文字型：同一码位（如 歾 U+6B7E）
渲染为悉昙种子字形。本管线 RJ 缺字（`<g ref="#RJ-…">`）解析为 charDecl
`rjchar` 常规字后，按 `config output.docx.siddhamFonts`（缺省
`["Ranjana","Siddam"]`）取本机已装且覆盖该字者写入 `w:rFonts`
（官方 docx 同款 `eastAsia="Ranjana"`）。

## 安装与行为

- 把 TTF 拷入本目录或系统字体目录并右键安装（本机已装即用，无需配置）。
- 未装：主题字体直显 rjchar（可读的常规汉字，只是非悉昙体）。
- 注意：二者**不含** CBETA 私用区（`U+10Cxx` 悉昙 PUA，如 U+10CCBA）
  与标准悉昙区（`U+11580`）字形；该区字符暂无可用字体，
  预览/Word 均为 tofu（检查窗点名），等 CBETA 出含 PUA 的悉昙字库。

---

CBETA (Comprehensive Buddhist Electronic Text Archive Foundation)  
http://www.cbeta.org
