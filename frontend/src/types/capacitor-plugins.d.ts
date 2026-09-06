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

  export const Filesystem: {
    writeFile: (options: WriteFileOptions) => Promise<WriteFileResult>;
    appendFile: (options: AppendFileOptions) => Promise<void>;
  };
}
