export type SheetPreview = {
  name: string;
  rows: string[][];
};

export type TemplatePreview = {
  filePath: string;
  fileType: "xlsx" | "xls" | "docx" | "unknown";
  updatedAt: string;
  textSections: string[];
  sheets: SheetPreview[];
  warnings: string[];
};

export type FilePreview =
  | { kind: "template"; data: TemplatePreview }
  | {
      kind: "text";
      filePath: string;
      fileType: string;
      updatedAt: string;
      content: string;
      truncated?: boolean;
    }
  | {
      kind: "image";
      filePath: string;
      fileType: string;
      updatedAt: string;
      dataUrl: string;
      truncated?: boolean;
    }
  | {
      kind: "binary";
      filePath: string;
      fileType: string;
      updatedAt: string;
      size: number;
      hex: string;
      truncated?: boolean;
    };
