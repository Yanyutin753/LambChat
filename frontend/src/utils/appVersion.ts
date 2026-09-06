import { version } from "../../package.json";

/**
 * 打包进 bundle 的客户端版本。与 Android versionName / tauri.conf.json 同源，
 * 发版时三者同步递增（CI 构建保证嵌入 App 的 bundle 与原生版本一致）。
 * 移动端自检更新时上报给后端做 has_update 比较。
 */
export const APP_VERSION: string = version;
