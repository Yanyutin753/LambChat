declare module "react-file-icon" {
  import { FC } from "react";

  export interface FileIconProps {
    extension?: string;
    size?: number;
    color?: string;
    type?: Type;
    labelColor?: string;
    radius?: number;
    fold?: boolean;
    gradient?: boolean;
    kes?: number;
    className?: string;
  }

  export interface TypeStyle {
    color?: string;
    labelColor?: string;
    gradient?: {
      direction: number;
      colors: string[];
    };
  }

  export const defaultStyles: Record<string, TypeStyle>;
  export const FileIcon: FC<FileIconProps>;
  export type { Type } from "file-extensions";

  export default FileIcon;
}
