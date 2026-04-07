import { useEffect, useState } from "react";
import type { FilePreview, TemplatePreview } from "../types/preview";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

type Props = {
  preview: FilePreview | null;
  onExcelCellChange?: (
    sheetName: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => Promise<void> | void;
  onExcelRangeChange?: (
    sheetName: string,
    startRowIndex: number,
    startColIndex: number,
    values: string[][]
  ) => Promise<void> | void;
  onExcelAppendRows?: (sheetName: string, count: number) => Promise<void> | void;
  onExcelTrimSheet?: (
    sheetName: string,
    axis: "row" | "col",
    count: number
  ) => Promise<void> | void;
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

function renderExcel(
  preview: TemplatePreview,
  editingCell: { sheetName: string; rowIndex: number; colIndex: number; value: string } | null,
  setEditingCell: (
    value: { sheetName: string; rowIndex: number; colIndex: number; value: string } | null
  ) => void,
  commitEditingCell: () => Promise<void>,
  excelSaving: boolean,
  setExcelSaving: (value: boolean) => void,
  appendCount: number,
  setAppendCount: (value: number) => void,
  onExcelRangeChange?: (
    sheetName: string,
    startRowIndex: number,
    startColIndex: number,
    values: string[][]
  ) => Promise<void> | void,
  onExcelAppendRows?: (sheetName: string, count: number) => Promise<void> | void,
  onExcelTrimSheet?: (sheetName: string, axis: "row" | "col", count: number) => Promise<void> | void
) {
  return preview.sheets.map((sheet) => (
    <section key={sheet.name} className="sheet-card">
      <div className="sheet-toolbar">
        <h3>{sheet.name}</h3>
        <button
          type="button"
          className="excel-action-btn"
          disabled={excelSaving || !onExcelAppendRows}
          onClick={() => {
            if (!onExcelAppendRows) return;
            setExcelSaving(true);
            void Promise.resolve(onExcelAppendRows(sheet.name, appendCount)).finally(() => {
              setExcelSaving(false);
            });
          }}
        >
          追加 {appendCount} 行
        </button>
        <input
          type="number"
          min={1}
          max={200}
          className="excel-count-input"
          value={appendCount}
          onChange={(event) => setAppendCount(Math.max(1, Math.min(200, Number(event.target.value) || 1)))}
        />
        <button
          type="button"
          className="excel-action-btn"
          disabled={excelSaving || !onExcelTrimSheet}
          onClick={() => {
            if (!onExcelTrimSheet) return;
            setExcelSaving(true);
            void Promise.resolve(onExcelTrimSheet(sheet.name, "row", 1)).finally(() => {
              setExcelSaving(false);
            });
          }}
        >
          删除末行
        </button>
        <button
          type="button"
          className="excel-action-btn"
          disabled={excelSaving || !onExcelTrimSheet}
          onClick={() => {
            if (!onExcelTrimSheet) return;
            setExcelSaving(true);
            void Promise.resolve(onExcelTrimSheet(sheet.name, "col", 1)).finally(() => {
              setExcelSaving(false);
            });
          }}
        >
          删除末列
        </button>
      </div>
      <p className="placeholder">双击单元格可编辑并写回文件。</p>
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
                            onDoubleClick={() =>
                              setEditingCell({
                                sheetName: sheet.name,
                                rowIndex,
                                colIndex: cellIndex,
                                value: cell,
                              })
                            }
                          >
                            {editingCell &&
                            editingCell.sheetName === sheet.name &&
                            editingCell.rowIndex === rowIndex &&
                            editingCell.colIndex === cellIndex ? (
                              <input
                                className="excel-edit-input"
                                autoFocus
                                value={editingCell.value}
                                disabled={excelSaving}
                                onChange={(event) =>
                                  setEditingCell({
                                    ...editingCell,
                                    value: event.target.value,
                                  })
                                }
                                onBlur={() => {
                                  void commitEditingCell();
                                }}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    void commitEditingCell();
                                  }
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    setEditingCell(null);
                                  }
                                }}
                                onPaste={(event) => {
                                  const raw = event.clipboardData?.getData("text/plain") ?? "";
                                  if (!raw || (!raw.includes("\t") && !raw.includes("\n"))) {
                                    return;
                                  }
                                  event.preventDefault();
                                  const rows = raw
                                    .replace(/\r\n/g, "\n")
                                    .replace(/\r/g, "\n")
                                    .split("\n")
                                    .filter((line) => line.length > 0)
                                    .map((line) => line.split("\t"));
                                  if (!rows.length || !onExcelRangeChange) {
                                    return;
                                  }
                                  setExcelSaving(true);
                                  void Promise.resolve(
                                    onExcelRangeChange(sheet.name, rowIndex, cellIndex, rows)
                                  ).finally(() => {
                                    setExcelSaving(false);
                                    setEditingCell(null);
                                  });
                                }}
                              />
                            ) : cell ? (
                              <span className="excel-cell-text" title={cell}>
                                {cell}
                              </span>
                            ) : (
                              "∅"
                            )}
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
      {renderDocLike(preview)}
    </>
  );
}

export function PreviewPanel({
  preview,
  onExcelCellChange,
  onExcelRangeChange,
  onExcelAppendRows,
  onExcelTrimSheet,
}: Props) {
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState(100);
  const [excelSaving, setExcelSaving] = useState(false);
  const [editingCell, setEditingCell] = useState<{
    sheetName: string;
    rowIndex: number;
    colIndex: number;
    value: string;
  } | null>(null);
  const [appendCount, setAppendCount] = useState(1);

  useEffect(() => {
    setPdfPage(1);
    setPdfZoom(100);
    setEditingCell(null);
  }, [preview?.kind === "template" ? preview.data.filePath : ""]);

  const commitEditingCell = async () => {
    if (!editingCell || !onExcelCellChange) {
      setEditingCell(null);
      return;
    }
    setExcelSaving(true);
    try {
      await onExcelCellChange(
        editingCell.sheetName,
        editingCell.rowIndex,
        editingCell.colIndex,
        editingCell.value
      );
    } finally {
      setExcelSaving(false);
      setEditingCell(null);
    }
  };

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
    return (
      <div className="preview-panel">
        {data.fileType === "xlsx" || data.fileType === "xls"
          ? renderExcel(
              data,
              editingCell,
              setEditingCell,
              commitEditingCell,
              excelSaving,
              setExcelSaving,
              appendCount,
              setAppendCount,
              onExcelRangeChange,
              onExcelAppendRows,
              onExcelTrimSheet
            )
          : renderTemplate(data)}
      </div>
    );
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
              showLineNumbers
              wrapLongLines
              customStyle={{
                margin: 0,
                background: "transparent",
                padding: "16px",
                color: "#e5e7eb",
                fontSize: "12px",
                lineHeight: "1.7",
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
