import { useEffect, useState } from "react";
import type { FilePreview, TemplatePreview } from "../types/preview";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

type Props = {
  preview: FilePreview | null;
};

function buildColumnWidths(rows: string[][]): number[] {
  if (rows.length === 0) return [];
  const columnCount = rows.reduce((max, row) => Math.max(max, row.length), 0);
  const widths = Array.from({ length: columnCount }, () => 120);

  for (let col = 0; col < columnCount; col += 1) {
    let maxLen = 4;
    for (let row = 0; row < rows.length; row += 1) {
      const value = (rows[row]?.[col] || "").trim();
      if (!value) continue;
      maxLen = Math.max(maxLen, Math.min(36, value.length));
    }
    widths[col] = Math.max(92, Math.min(360, maxLen * 9 + 24));
  }
  return widths;
}

function toExcelColumnLabel(index: number): string {
  let current = index + 1;
  let label = "";
  while (current > 0) {
    const remainder = (current - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    current = Math.floor((current - 1) / 26);
  }
  return label;
}

function isLikelyNumericCell(value: string): boolean {
  const text = value.trim();
  if (!text) return false;
  return /^[-+]?((\d+(\.\d+)?)|(\.\d+))%?$/.test(text.replace(/,/g, ""));
}

function renderExcel(preview: TemplatePreview) {
  return preview.sheets.map((sheet) => (
    <section key={sheet.name} className="sheet-card">
      <h3>{sheet.name}</h3>
      <div className="table-wrap template-html-block">
        {sheet.rows.length === 0 ? (
          <table className="excel-preview-table">
            <tbody>
              <tr>
                <td>空工作表</td>
              </tr>
            </tbody>
          </table>
        ) : (
          (() => {
            const widths = buildColumnWidths(sheet.rows);
            return (
              <table className="excel-preview-table">
                <colgroup>
                  <col style={{ width: "60px" }} />
                  {widths.map((width, colIndex) => (
                    <col key={`${sheet.name}-col-${colIndex}`} style={{ width: `${width}px` }} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    <th className="excel-index-cell">#</th>
                    {Array.from({ length: widths.length }, (_, cellIndex) => (
                      <th key={`${sheet.name}-col-header-${cellIndex}`}>{toExcelColumnLabel(cellIndex)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sheet.rows.map((row, rowIndex) => (
                    <tr key={`${sheet.name}-${rowIndex}`}>
                      <th className="excel-row-index">{rowIndex + 1}</th>
                      {Array.from({ length: widths.length }, (_, cellIndex) => {
                        const cell = row[cellIndex] ?? "";
                        const isEmpty = !String(cell).trim();
                        const isNumeric = isLikelyNumericCell(cell);
                        return (
                          <td
                            key={`${sheet.name}-${rowIndex}-${cellIndex}`}
                            className={
                              isEmpty ? "excel-cell-empty" : isNumeric ? "excel-cell-number" : undefined
                            }
                          >
                            {cell ? <span className="excel-cell-text" title={cell}>{cell}</span> : "∅"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            );
          })()
        )}
      </div>
    </section>
  ));
}

function renderDocLike(preview: TemplatePreview) {
  return (
    <section className="docx-card">
      <h3>文档内容</h3>
      {preview.htmlContent ? (
        <div className="template-html-block" dangerouslySetInnerHTML={{ __html: preview.htmlContent }} />
      ) : preview.textSections.length === 0 ? (
        <p className="placeholder">未解析出正文内容，建议转为 docx 后重试。</p>
      ) : (
        preview.textSections.map((block, index) => <p key={index}>{block}</p>)
      )}
    </section>
  );
}

function renderTemplate(preview: TemplatePreview) {
  return (
    <>
      {preview.warnings.length > 0 && (
        <div className="warning-box">
          {preview.warnings.map((warning, index) => (
            <p key={index}>{warning}</p>
          ))}
        </div>
      )}

      {preview.fileType === "xlsx" || preview.fileType === "xls" ? renderExcel(preview) : renderDocLike(preview)}
    </>
  );
}

export function PreviewPanel({ preview }: Props) {
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState(100);

  useEffect(() => {
    setPdfPage(1);
    setPdfZoom(100);
  }, [preview?.kind === "template" ? preview.data.filePath : ""]);

  if (!preview) {
    return <div className="empty-state">请选择文件开始预览</div>;
  }

  if (preview.kind === "template") {
    const data = preview.data;
    if (data.fileType === "pdf") {
      const safePage = Math.max(1, Math.floor(pdfPage || 1));
      const safeZoom = Math.max(50, Math.min(300, Math.floor(pdfZoom || 100)));
      const src = data.fileUrl ? `${data.fileUrl}#page=${safePage}&zoom=${safeZoom}` : "";

      return (
        <div className="preview-panel">
          {data.warnings.length > 0 && (
            <div className="warning-box">
              {data.warnings.map((warning, index) => (
                <p key={index}>{warning}</p>
              ))}
            </div>
          )}
          <section className="docx-card">
            <div className="pdf-toolbar">
              <h3>PDF 预览</h3>
              <div className="pdf-controls">
                <label>
                  页码
                  <input
                    type="number"
                    min={1}
                    value={safePage}
                    onChange={(event) => setPdfPage(Math.max(1, Number(event.target.value) || 1))}
                  />
                </label>
                <label>
                  缩放
                  <input
                    type="range"
                    min={50}
                    max={300}
                    step={10}
                    value={safeZoom}
                    onChange={(event) => setPdfZoom(Number(event.target.value))}
                  />
                </label>
                <span>{safeZoom}%</span>
              </div>
            </div>
            {data.fileUrl ? (
              <iframe className="pdf-preview-frame" src={src} title={data.filePath} />
            ) : (
              <p className="placeholder">当前 PDF 无法内嵌显示，请使用系统应用打开。</p>
            )}
          </section>
        </div>
      );
    }
    return <div className="preview-panel">{renderTemplate(data)}</div>;
  }

  const lowerType = preview.fileType.toLowerCase();
  const showMarkdown = preview.kind === "text" && lowerType === "md";
  const languageMap: Record<string, string> = {
    ts: "typescript",
    tsx: "tsx",
    js: "javascript",
    jsx: "jsx",
    json: "json",
    py: "python",
    java: "java",
    cs: "csharp",
    cpp: "cpp",
    c: "c",
    go: "go",
    rs: "rust",
    php: "php",
    rb: "ruby",
    kt: "kotlin",
    swift: "swift",
    css: "css",
    scss: "scss",
    html: "html",
    xml: "xml",
    yaml: "yaml",
    yml: "yaml",
    sh: "bash",
    bash: "bash",
    ps1: "powershell",
    sql: "sql",
  };
  const codeLanguage = preview.kind === "text" ? languageMap[lowerType] : undefined;

  return (
    <div className="preview-panel">
      {preview.truncated && (
        <div className="warning-box">
          <p>文件过大，仅展示部分内容。</p>
        </div>
      )}

      {preview.kind === "image" ? (
        <div className="image-preview">
          <img src={preview.dataUrl} alt={preview.filePath} />
        </div>
      ) : preview.kind === "text" ? (
        showMarkdown ? (
          <div className="markdown-content">
            <MarkdownRenderer content={preview.content} />
          </div>
        ) : codeLanguage ? (
          <div className="code-preview">
            <SyntaxHighlighter
              language={codeLanguage}
              style={vscDarkPlus}
              customStyle={{
                margin: 0,
                background: "transparent",
                padding: "16px",
                fontSize: "12px",
                lineHeight: "1.6",
              }}
            >
              {preview.content}
            </SyntaxHighlighter>
          </div>
        ) : (
          <pre className="text-preview">{preview.content}</pre>
        )
      ) : (
        <div className="binary-preview">
          <div className="binary-meta">大小: {preview.size} 字节</div>
          <pre className="text-preview">{preview.hex}</pre>
        </div>
      )}
    </div>
  );
}
