/**
 * Type declarations for Capacitor plugins used at runtime on mobile devices.
 * These are dynamically imported and will not be available in the web/dev bundle.
 */

declare module "@capacitor/filesystem" {
  export enum Directory {
    Cache = "CACHE",
    Data = "DATA",
    Documents = "DOCUMENTS",
    External = "EXTERNAL",
    ExternalStorage = "EXTERNAL_STORAGE",
    Library = "LIBRARY",
  }

  export interface WriteFileOptions {
    path: string;
    data: string;
    directory?: Directory;
    recursive?: boolean;
  }

  export interface WriteFileResult {
    uri: string;
  }

  export interface AppendFileOptions {
    path: string;
    data: string;
    directory?: Directory;
    recursive?: boolean;
  }

  export interface StatOptions {
    path: string;
    directory?: Directory;
  }

  /** 与 @capacitor/filesystem v7 的 StatResult 对齐（缓存判定只用 size） */
  export interface StatResult {
    type: string;
    size: number;
    mtime: number;
    uri: string;
  }

  export interface GetUriResult {
    uri: string;
  }

  export const Filesystem: {
    writeFile: (options: WriteFileOptions) => Promise<WriteFileResult>;
    appendFile: (options: AppendFileOptions) => Promise<void>;
    stat: (options: StatOptions) => Promise<StatResult>;
    getUri: (options: StatOptions) => Promise<GetUriResult>;
  };
}
