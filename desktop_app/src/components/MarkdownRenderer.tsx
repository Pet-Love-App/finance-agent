import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

type Props = {
  content: string;
};

export function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        table(props) {
          const { children, ...rest } = props;
          return (
            <div className="markdown-table-wrap">
              <table {...rest}>{children}</table>
            </div>
          );
        },
        code(props) {
          const { children, className, ...rest } = props;
          const match = /language-(\w+)/.exec(className || "");
          const codeText = String(children ?? "").replace(/\n$/, "");

          if (match) {
            return (
              <div className="markdown-codeblock">
                <SyntaxHighlighter
                  {...rest}
                  PreTag="div"
                  language={match[1]}
                  style={vscDarkPlus}
                  customStyle={{
                    margin: 0,
                    background: "transparent",
                    padding: "14px 16px",
                    fontSize: "13px",
                    lineHeight: "1.55",
                  }}
                >
                  {codeText}
                </SyntaxHighlighter>
              </div>
            );
          }

          return (
            <code {...rest} className={className}>
              {children}
            </code>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
