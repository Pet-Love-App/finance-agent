import type { FilePreview, TemplatePreview } from "../types/preview";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

type Props = {
  preview: FilePreview | null;
};

function renderExcel(preview: TemplatePreview) {
  return preview.sheets.map((sheet) => (
    <section key={sheet.name} className="sheet-card">
      <h3>{sheet.name}</h3>
      <div className="table-wrap">
        <table>
          <tbody>
            {sheet.rows.length === 0 ? (
              <tr>
                <td>空工作表</td>
              </tr>
            ) : (
              sheet.rows.map((row, rowIndex) => (
                <tr key={`${sheet.name}-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`${sheet.name}-${rowIndex}-${cellIndex}`}>{cell}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  ));
}

function renderDocx(preview: TemplatePreview) {
  return (
    <section className="docx-card">
      <h3>文档段落</h3>
      {preview.textSections.length === 0 ? (
        <p className="placeholder">未解析出正文内容</p>
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

      {preview.fileType === "docx" ? renderDocx(preview) : renderExcel(preview)}
    </>
  );
}

export function PreviewPanel({ preview }: Props) {
  if (!preview) {
    return <div className="empty-state">请选择文件开始预览</div>;
  }

  if (preview.kind === "template") {
    const data = preview.data;
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
