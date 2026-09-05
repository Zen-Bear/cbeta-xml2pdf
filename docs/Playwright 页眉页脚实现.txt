可以。**Playwright 完全可以实现 PDF 的页眉/页脚**，而且是 Chromium 原生的 PDF header/footer 机制。

例如：

```python
page.pdf(
    path="output.pdf",
    format="A4",
    display_header_footer=True,
    header_template="""
        <div style="font-size:9px; width:100%; text-align:center;">
            《佛教电子书》
        </div>
    """,
    footer_template="""
        <div style="font-size:9px; width:100%; text-align:center;">
            第 <span class="pageNumber"></span> 页 /
            共 <span class="totalPages"></span> 页
        </div>
    """
)
```

其中 Chromium 提供几个特殊变量：

* `<span class="pageNumber"></span>` → 当前页码
* `<span class="totalPages"></span>` → 总页数
* `<span class="date"></span>` → 日期
* `<span class="title"></span>` → 页面标题
* `<span class="url"></span>` → URL

### 但是有一个重要限制

Playwright 的 `header_template` / `footer_template` **不是普通网页区域**，它属于 Chromium 的 PDF 打印页眉页脚模板。

因此不能完全按照普通 HTML 页面那样操作，例如：

```html
<header>
    很复杂的网页布局
</header>
```

然后期待它自动出现在每页。

通常需要：

```text
display_header_footer=True
        ↓
header_template
footer_template
        ↓
Chromium PDF
```

并且还要给页眉页脚**预留空间**，例如：

```python
page.pdf(
    path="book.pdf",
    format="A4",
    display_header_footer=True,
    margin={
        "top": "20mm",
        "bottom": "20mm",
        "left": "15mm",
        "right": "15mm",
    },
    header_template="...",
    footer_template="..."
)
```

### 如果你做电子书，我更推荐这样

```text
HTML 正文
   │
   ├── CSS 控制正文
   │
   └── Playwright
          │
          ├── header_template
          ├── footer_template
          ├── pageNumber
          └── totalPages
                 ↓
               PDF
                 ↓
             PyMuPDF
          （必要时后处理）
```

所以，**“Playwright 没有页眉页脚”这个说法是不对的**。它不仅可以做，而且**页码/总页数这种动态页脚非常方便**。

如果你需要的是你之前那种**书籍排版的页眉：左页显示书名、右页显示章节名，中间/外侧页码，并且奇偶页不同**，那就要另外讨论了——这种情况下 **Playwright 原生 header/footer 有一定限制，CSS Paged Media + 后处理会更灵活**。
